"""选品流水线：采集 → 去重 → 合规三态 → 数据补全 → 打分 → TopN 入池。

对应方案文档 04 第二节流水线：
  采集（账本游标/节流/熔断）→ 去重 → 合规三态 → 数据补全（1688 询价+淘宝素材）
  → 打分（五维）→ 排序取 Top N → 商品池 →（可选人工复核闸门）
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Iterable, Optional

from .collectors import make_collector, resolve_mode
from .collectors.fixtures import load_ad_snapshots
from .compliance import ComplianceEngine
from .config import SourcingConfig
from .db import Database
from .dedup import DedupEngine
from .models import (
    ComplianceState,
    PipelineResult,
    ProductCandidate,
    Quote,
    SourceItem,
)
from .pricing import suggested_price
from .scoring import ScoreInput, Scorer

log = logging.getLogger("sourcing.pipeline")


class SourcingPipeline:
    def __init__(self, config: SourcingConfig, db: Optional[Database] = None):
        self.config = config
        self.db = db or Database(config)
        self.scorer = Scorer(config.scoring)
        # 类目白名单优先级：app_config 运行时配置 > config 默认（读不到/异常回落默认，不抛异常）
        self.compliance = ComplianceEngine(
            config, category_whitelist=self._load_category_whitelist()
        )
        # S5 闸门放松配置（gate.relax.*，app_config 只读；默认 enabled=false 零变化）
        self.gate_relax = self._load_gate_relax_config()

    # ------------------------------------------------------------ 运行时配置
    def _load_category_whitelist(self) -> Optional[list[str]]:
        """从 app_config 读取类目白名单（运行时优先级高于 config 默认）。

        - self.db 可用且 app_config.category.whitelist 为 list[str] → 使用之；
        - 键不存在/类型非法/任何异常 → 返回 None（ComplianceEngine 回落 config.category_whitelist）；
        - 绝不抛异常打断流水线；persist=False 时同样兼容（只读查询）。
        """
        if self.db is None:
            return None
        try:
            from . import repo

            with self.db.session() as session:
                value = repo.get_config_value(session, "category.whitelist", None)
            if isinstance(value, list) and all(isinstance(v, str) for v in value):
                log.info("app_config.category.whitelist 生效：%d 个类目", len(value))
                return value
            if value is not None:
                log.warning(
                    "app_config.category.whitelist 类型非法（%s），回落 config 默认",
                    type(value).__name__,
                )
        except Exception:
            log.warning("读取 app_config.category.whitelist 失败，回落 config 默认", exc_info=True)
        return None

    def _load_gate_relax_config(self):
        """从 app_config 读取闸门放松配置（gate.relax.*，S5）；失败/未配置回落默认（不放松）。"""
        from .gate import DEFAULT_GATE_RELAX, load_gate_relax_config

        if self.db is None:
            return DEFAULT_GATE_RELAX
        try:
            with self.db.session() as session:
                cfg = load_gate_relax_config(session)
            if cfg.enabled:
                log.info("app_config gate.relax.* 生效：%s", cfg.describe())
            return cfg
        except Exception:
            log.warning("读取 app_config gate.relax.* 失败，回落默认（不放松）", exc_info=True)
            return DEFAULT_GATE_RELAX

    def _relax_manual_review(self, candidates) -> int:
        """S5：人工闸门按达标自动放松（人工复核前生效点，默认 enabled=false 零变化）。

        对 `state='manual_review'` 的候选，按窗口内该类目复核统计（通过率≥阈值 且
        样本≥min_samples，gate.relax.* 配置）自动放行 pool；放行理由追加到
        compliance.reasons（可解释纪律，随 compliance_reasons 落库审计）。
        返回放行数。
        """
        if not self.gate_relax.enabled:
            return 0
        from .gate import should_relax_category

        released = 0
        for cand in candidates:
            if cand.state != "manual_review":
                continue
            ok, reasons = should_relax_category(self.db, cand.category, self.gate_relax)
            if ok:
                cand.state = "pool"
                cand.compliance.reasons.append(
                    "gate.relax 自动放行：" + (reasons[0] if reasons else "达标")
                )
                released += 1
        return released

    @staticmethod
    def _ad_data_usable(ad: dict, max_age_days: float) -> bool:
        """单类目投放转化数据是否可用（新鲜度 + 弱样本过滤，C-2 / R-14）。

        - generated_at 存在且超过 max_age_days 天 → 不可用（过期）；
        - sample_count 存在且 < 5 → 不可用（弱样本）；
        - 两者都缺（fixtures 旧格式仅 {roi, sales}）→ 可用（兼容既有 39 测试行为）；
        - 元数据解析失败保守按「不可用」处理（宁缺勿错，不污染打分）。
        generated_at 兼容 ISO 字符串（含尾部 Z）与 datetime，naive 按 UTC 处理。
        """
        generated_at = ad.get("generated_at")
        if generated_at is not None:
            try:
                if isinstance(generated_at, str):
                    generated_at = generated_at.replace("Z", "+00:00")
                    generated_at = datetime.fromisoformat(generated_at)
                if generated_at.tzinfo is None:
                    generated_at = generated_at.replace(tzinfo=timezone.utc)
                age = datetime.now(timezone.utc) - generated_at
                if age.total_seconds() > max_age_days * 86400:
                    log.info("类目投放转化数据过期（generated_at=%s，>%s 天），视为无数据", generated_at, max_age_days)
                    return False
            except (TypeError, ValueError):
                log.warning("generated_at=%r 解析失败，按无数据处理", ad.get("generated_at"))
                return False
        sample_count = ad.get("sample_count")
        if sample_count is not None:
            try:
                if int(sample_count) < 5:
                    log.info("类目投放转化弱样本（sample_count=%s<5），视为无数据", sample_count)
                    return False
            except (TypeError, ValueError):
                log.warning("sample_count=%r 非法，按无数据处理", sample_count)
                return False
        return True

    def _fresh_ad_by_category(self, ad_by_cat: dict) -> dict:
        """按新鲜度/弱样本过滤类目级投放转化数据（两处 ad_by_cat 组装统一入口）。

        不可用类目置空 dict（打分时不传 ad_roi/ad_sales，维度自动不生效），
        可用类目原样保留（含 roi/sales/sales_amount/sample_count/generated_at 元数据）。
        """
        if not ad_by_cat:
            return {}
        max_age = float(self.config.scoring.ad_data_max_age_days)
        fresh: dict = {}
        for category, ad in ad_by_cat.items():
            if not isinstance(ad, dict):
                continue
            fresh[category] = ad if self._ad_data_usable(ad, max_age) else {}
        return fresh

    # ------------------------------------------------------------ 采集
    def collect(self, sources: Iterable[str], mode: str = "fixtures") -> dict[str, list[SourceItem]]:
        collected: dict[str, list[SourceItem]] = {}
        created: list = []
        for source in sources:
            try:
                use_mode = resolve_mode(source, self.config, mode)
                collector = make_collector(source, self.config, use_mode)
                created.append(collector)
                if not collector.enabled:
                    continue
                board_items: dict[str, list[SourceItem]] = {}
                for board in collector.boards:
                    try:
                        items = collector.collect_board(board, limit=200)
                        board_items[board] = items
                        log.info("采集 %s/%s: %d 条", source, board, len(items))
                    except Exception as e:
                        log.warning("采集 %s/%s 失败: %s", source, board, e)
                collected[source] = [it for lst in board_items.values() for it in lst]
            except Exception as e:
                log.error("来源 %s 整体失败: %s", source, e)
        # 断开所有浏览器 CDP 连接（不影响真实浏览器与登录态）。
        # 必须断开：playwright connect_over_cdp 不支持对同一浏览器重复连接，
        # 连接未断时后续源重复 connect 会报「Connection closed while reading from the driver」
        # （P-028 实测 2026-08-31；collect 内逐源连接/断开循环是安全的）。
        for c in created:
            browser = getattr(c, "browser", None)
            if browser is not None:
                try:
                    browser.close()
                except Exception:
                    pass
        return collected

    # ------------------------------------------------------------ 补全
    def complete(
        self,
        candidates: list[ProductCandidate],
        mode: str = "fixtures",
        quote_limit: int = 10,
        max_items: int | None = 10,
    ) -> None:
        """1688 逐 SKU 询价 + 淘宝参考素材；取最低有效总成本。

        对候选的全部来源条目逐个询价（同款多榜出现时，任一榜单条目都可能命中报价），
        按 (供应商, SKU, 单价) 去重后取最低有效成本。

        max_items：本轮询价的 pool 候选商品数上限（默认 10）。
        真实询价每个商品 40~70s（air 直链 + detail 读价），大榜采集（如抖店 100+ 条）
        全量询价会跑 1~2 小时——按商品数截断，保证单轮流水线分钟级完成；
        剩余候选保留 quotes 为空，后续轮次/按需补询（真实运行验证 2026-08-31 定）。
        """
        quote_col = make_collector("alibaba", self.config, mode)
        quoted_count = 0
        for cand in candidates:
            if cand.state != "pool":  # 数据补全只对入池候选执行（S5 放松后 manual_review→pool 同样补全）
                continue
            if max_items is not None and quoted_count >= max_items:
                break
            quoted_count += 1
            quotes: list[Quote] = []
            seen_quote: set[tuple] = set()
            for src_item in cand.source_items:
                try:
                    for q in quote_col.quote(src_item)[:quote_limit]:
                        if not isinstance(q, Quote):
                            continue
                        key = (q.supplier_name, q.sku_name, q.unit_cost)
                        if key in seen_quote:
                            continue
                        seen_quote.add(key)
                        quotes.append(q)
                except Exception as e:
                    log.warning("询价失败 %s: %s", src_item.core_key[:24], e)
            cand.quotes = quotes
            if quotes:
                valid = [q for q in quotes if q.raw_url and q.effective_cost > 0]
                if valid:
                    cheapest = min(valid, key=lambda q: q.effective_cost)
                    cand.real_cost = cheapest.effective_cost
                    cand.supplier_count = len({q.supplier_name for q in valid})
            if cand.real_cost is not None:
                cand.suggested_price = suggested_price(cand.real_cost, self.config.pricing)
                cand.profit_margin = (
                    (cand.suggested_price - cand.real_cost) / cand.suggested_price
                    if cand.suggested_price else None
                )

    # ------------------------------------------------------------ 主体
    def run(
        self,
        sources: Optional[list[str]] = None,
        mode: str = "fixtures",
        top_n: Optional[int] = None,
        do_quotes: bool = True,
        persist: bool = True,
    ) -> PipelineResult:
        result = PipelineResult()
        sources = sources or ["opportunities", "youmi", "doudian"]
        top_n = top_n or self.config.scoring.top_n

        # 1) 采集
        collected = self.collect(sources, mode)
        result.collected = sum(len(v) for v in collected.values())
        all_items = [it for lst in collected.values() for it in lst]

        # 2) 去重（属性指纹 + phash + 多源合并）
        dedup = DedupEngine(
            self.config,
            library_has=(lambda fp, ph: self._library_has(fp, ph))
            if persist
            else (lambda fp, ph: False),
        )
        merged = dedup.process(all_items)
        new_items = [m for m in merged if not m.is_duplicate]
        result.after_dedup = len(new_items)

        # 3) 合规三态 + 组装候选
        candidates: list[ProductCandidate] = []
        for m in new_items:
            best = m.merged[0]
            comp = self.compliance.evaluate(best)
            cand = ProductCandidate(
                fingerprint=m.fingerprint,
                image_phash=m.image_phash,
                title=best.title,
                sanitized_title=comp.sanitized_title,
                category=comp.category or best.category,
                platform_price=best.price,
                sales=sum(i.sales for i in m.merged),
                rank_best=min((i.rank or 9999) for i in m.merged),
                board_count=len(m.merged),
                source_items=m.merged,
                compliance=comp,
                state="pool" if comp.state == ComplianceState.CANDIDATE else comp.state.value,
            )
            if comp.state == ComplianceState.HARD_REJECT:
                result.hard_rejected += 1
            elif comp.state == ComplianceState.MANUAL_REVIEW:
                result.manual_review += 1
            candidates.append(cand)
        result.candidates = sum(1 for c in candidates if c.is_candidate)
        # 3.5) S5 人工闸门按达标自动放松（默认 enabled=false 零变化；放行理由落 compliance.reasons）
        result.gate_relaxed = self._relax_manual_review(candidates)

        # 4) 数据补全（询价/素材）——只对 candidate 执行；max_items 限制单轮询价商品数
        #    （真实询价 40~70s/商品，大榜全量询价会跑 1~2 小时；fixtures 模式不受限——引号走内存）
        if do_quotes:
            self.complete(
                candidates,
                mode,
                max_items=None if mode == "fixtures" else self.config.quoting_max_items,
            )
            result.quoted = sum(1 for c in candidates if c.quotes)

        # 5) 打分（五维，投放转化按类目回流）
        ad_by_cat = load_ad_snapshots(self.config) if mode == "fixtures" else self.config.ad_conversion_by_category
        ad_by_cat = self._fresh_ad_by_category(ad_by_cat)
        for cand in candidates:
            ad = ad_by_cat.get(cand.category, {})
            data = ScoreInput(
                rank=cand.rank_best,
                sales=cand.sales,
                board_count=cand.board_count,
                platform_price=cand.platform_price,
                real_cost=cand.real_cost,
                suggested_price=cand.suggested_price,
                return_rate=cand.return_rate,
                supplier_count=cand.supplier_count,
                ad_roi=ad.get("roi") if ad else None,
                ad_sales=ad.get("sales_amount", ad.get("sales")),
            )
            cand.score = self.scorer.score(data)
            cand.ad_conversion = ad

        # 6) 排序取 TopN → 入池（人工闸门项不自动入池；S5 达标放松项 state=pool 参与）
        pool_candidates = [c for c in candidates if c.state == "pool"]
        pool_candidates.sort(key=lambda c: c.score.total, reverse=True)
        entered = pool_candidates[:top_n]
        result.pool_entered = len(entered)
        result.pool = entered

        # 7) 持久化
        if persist:
            self._persist(candidates, entered, collected)
        result.finished_at = datetime.now(timezone.utc)
        log.info(
            "流水线完成：采集 %d → 去重后 %d → 候选 %d → 人工复核 %d(闸门放松 %d) → 入池 %d（%.1fs）",
            result.collected, result.after_dedup, result.candidates,
            result.manual_review, result.gate_relaxed,
            result.pool_entered, result.elapsed_seconds(),
        )
        return result

    def run_from_items(
        self,
        items: list[SourceItem],
        mode: str = "fixtures",
        top_n: Optional[int] = None,
        do_quotes: bool = True,
        persist: bool = True,
    ) -> PipelineResult:
        """由调度器驱动的入口：给定已采集条目，执行去重→合规→补全→打分→入池。"""
        result = PipelineResult()
        result.collected = len(items)
        top_n = top_n or self.config.scoring.top_n

        dedup = DedupEngine(
            self.config,
            library_has=(lambda fp, ph: self._library_has(fp, ph))
            if persist
            else (lambda fp, ph: False),
        )
        merged = dedup.process(items)
        new_items = [m for m in merged if not m.is_duplicate]
        result.after_dedup = len(new_items)

        candidates: list[ProductCandidate] = []
        for m in new_items:
            best = m.merged[0]
            comp = self.compliance.evaluate(best)
            cand = ProductCandidate(
                fingerprint=m.fingerprint,
                image_phash=m.image_phash,
                title=best.title,
                sanitized_title=comp.sanitized_title,
                category=comp.category or best.category,
                platform_price=best.price,
                sales=sum(i.sales for i in m.merged),
                rank_best=min((i.rank or 9999) for i in m.merged),
                board_count=len(m.merged),
                source_items=m.merged,
                compliance=comp,
                state="pool" if comp.state == ComplianceState.CANDIDATE else comp.state.value,
            )
            if comp.state == ComplianceState.HARD_REJECT:
                result.hard_rejected += 1
            elif comp.state == ComplianceState.MANUAL_REVIEW:
                result.manual_review += 1
            candidates.append(cand)
        result.candidates = sum(1 for c in candidates if c.is_candidate)
        # 3.5) S5 人工闸门按达标自动放松（默认 enabled=false 零变化；放行理由落 compliance.reasons）
        result.gate_relaxed = self._relax_manual_review(candidates)

        if do_quotes:
            self.complete(
                candidates,
                mode,
                max_items=None if mode == "fixtures" else self.config.quoting_max_items,
            )
            result.quoted = sum(1 for c in candidates if c.quotes)

        ad_by_cat = load_ad_snapshots(self.config) if mode == "fixtures" else self.config.ad_conversion_by_category
        ad_by_cat = self._fresh_ad_by_category(ad_by_cat)
        for cand in candidates:
            ad = ad_by_cat.get(cand.category, {})
            data = ScoreInput(
                rank=cand.rank_best,
                sales=cand.sales,
                board_count=cand.board_count,
                platform_price=cand.platform_price,
                real_cost=cand.real_cost,
                suggested_price=cand.suggested_price,
                return_rate=cand.return_rate,
                supplier_count=cand.supplier_count,
                ad_roi=ad.get("roi") if ad else None,
                ad_sales=ad.get("sales_amount", ad.get("sales")),
            )
            cand.score = self.scorer.score(data)
            cand.ad_conversion = ad

        pool_candidates = [c for c in candidates if c.state == "pool"]  # S5 放松项 state=pool 参与 TopN
        pool_candidates.sort(key=lambda c: c.score.total, reverse=True)
        entered = pool_candidates[:top_n]
        result.pool_entered = len(entered)
        result.pool = entered

        if persist:
            self._persist(candidates, entered, {"scheduler": items})
        result.finished_at = datetime.now(timezone.utc)
        return result

    # ------------------------------------------------------------ 持久化
    def _library_has(self, fingerprint: str, image_phash: str) -> bool:
        from . import repo

        with self.db.session() as session:
            return repo.library_lookup(session, fingerprint, image_phash) is not None

    def _persist(
        self,
        candidates: list[ProductCandidate],
        entered: list[ProductCandidate],
        collected: dict[str, list[SourceItem]],
    ) -> None:
        from . import repo

        with self.db.session() as session:
            for source, items in collected.items():
                run_id = repo.record_run(session, source, "pipeline", len(items), True)
                repo.record_events(session, run_id, items)
            for cand in candidates:
                if not repo.claim_fingerprint(session, cand.fingerprint, "pipeline"):
                    continue
                row = repo.upsert_product(session, cand)
                repo.save_evidence(session, row.id, cand.source_items)
                repo.save_quotes(session, row.id, cand.quotes)
                repo.upsert_library(session, cand)
