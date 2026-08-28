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
        self.compliance = ComplianceEngine(config)

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
        # 断开所有浏览器 CDP 连接（不影响真实浏览器与登录态）
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
    ) -> None:
        """1688 逐 SKU 询价 + 淘宝参考素材；取最低有效总成本。

        对候选的全部来源条目逐个询价（同款多榜出现时，任一榜单条目都可能命中报价），
        按 (供应商, SKU, 单价) 去重后取最低有效成本。
        """
        quote_col = make_collector("alibaba", self.config, mode)
        for cand in candidates:
            if not cand.is_candidate:
                continue
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

        # 4) 数据补全（询价/素材）——只对 candidate 执行
        if do_quotes:
            self.complete(candidates, mode)
            result.quoted = sum(1 for c in candidates if c.quotes)

        # 5) 打分（五维，投放转化按类目回流）
        ad_by_cat = load_ad_snapshots(self.config) if mode == "fixtures" else self.config.ad_conversion_by_category
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
                ad_sales=ad.get("sales"),
            )
            cand.score = self.scorer.score(data)
            cand.ad_conversion = ad

        # 6) 排序取 TopN → 入池（人工闸门项不自动入池）
        pool_candidates = [c for c in candidates if c.is_candidate]
        pool_candidates.sort(key=lambda c: c.score.total, reverse=True)
        entered = pool_candidates[:top_n]
        result.pool_entered = len(entered)
        result.pool = entered

        # 7) 持久化
        if persist:
            self._persist(candidates, entered, collected)
        result.finished_at = datetime.now(timezone.utc)
        log.info(
            "流水线完成：采集 %d → 去重后 %d → 候选 %d → 入池 %d（%.1fs）",
            result.collected, result.after_dedup, result.candidates,
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

        if do_quotes:
            self.complete(candidates, mode)
            result.quoted = sum(1 for c in candidates if c.quotes)

        ad_by_cat = load_ad_snapshots(self.config) if mode == "fixtures" else self.config.ad_conversion_by_category
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
                ad_sales=ad.get("sales"),
            )
            cand.score = self.scorer.score(data)
            cand.ad_conversion = ad

        pool_candidates = [c for c in candidates if c.is_candidate]
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
