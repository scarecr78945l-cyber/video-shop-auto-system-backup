"""M3 文案管线 · 投放文案 / 角标候选生成（ad / badge）。

- 每类候选 ≥ config.copywriting.ad_variants_min / badge_variants_min（默认各 2）；
- 候选间**真实差异**：卖点侧重不同（材质/规格 vs 颜色/包装/数量 vs 综合）与句式不同；
- 合规预审必过：生成后逐条 ``check_text``（含 AD_BADGE_FORBIDDEN 广告禁用词），
  命中即剔除；LLM 候选不足或全命中 → 规则模板补齐，保证至少 min 套且全部通过；
- LLM 优先（DeepSeek 结构化 JSON），无 Key / 失败降级规则（source="rule_fallback"）。

返回 ``list[CopywriteDraft]``（variant_no 从 1 起连续编号）。
"""

from __future__ import annotations

import json
from typing import Any, Optional

from ..compliance import check_text
from ..config import M3Config, load_config
from ..models import CopywriteDraft
from .llm import DeepSeekClient
from .script import _spec_facts

AD_BADGE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "ads": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"content": {"type": "string", "minLength": 4}},
                "required": ["content"],
            },
        },
        "badges": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"content": {"type": "string", "minLength": 1}},
                "required": ["content"],
            },
        },
    },
    "required": ["ads", "badges"],
}

SYSTEM_PROMPT = (
    "你是视频号小店投放文案/角标撰写助手。"
    "只能基于用户提供的 SKU 真实规格与类目编写，严禁编造赠品/数量/效果/"
    "品牌授权等来源未证实信息；禁用词包括：同款、官方、旗舰店、代言、联名、"
    "正品、保真、批发、一件代发、厂家、源头、工厂、1688 等。"
    "投放文案（ads）每条约 10~25 字、卖点侧重互不相同；角标（badges）每条 ≤ 8 字。"
)

# 通用安全兜底候选（规则不足时补齐，全部过合规预审）
_GENERIC_ADS = ["品质好物，日常之选。", "用心选品，安心选购。"]
_GENERIC_BADGES = ["精选好物", "品质之选", "上新推荐"]


class AdBadgeGenerator:
    """投放文案/角标候选生成器（LLM 优先，规则降级，合规必过）。"""

    def __init__(
        self,
        config: Optional[M3Config] = None,
        llm: Optional[DeepSeekClient] = None,
    ):
        self.config = config or load_config()
        self.llm = llm or DeepSeekClient(self.config)

    # ---------- 主流程 ----------

    def generate_ads(
        self,
        product_id: str,
        category: str = "",
        sku_spec: Optional[dict[str, Any]] = None,
    ) -> list[CopywriteDraft]:
        return self._generate_kind(
            "ad", product_id, category, sku_spec,
            self.config.copywriting.ad_variants_min,
        )

    def generate_badges(
        self,
        product_id: str,
        category: str = "",
        sku_spec: Optional[dict[str, Any]] = None,
    ) -> list[CopywriteDraft]:
        return self._generate_kind(
            "badge", product_id, category, sku_spec,
            self.config.copywriting.badge_variants_min,
        )

    # ---------- 内部实现 ----------

    def _generate_kind(
        self,
        kind: str,  # ad / badge
        product_id: str,
        category: str,
        sku_spec: Optional[dict[str, Any]],
        min_count: int,
    ) -> list[CopywriteDraft]:
        cap = min_count + 2  # 候选上限（至少 min 套，多留 2 套备选）
        candidates: list[str] = []
        source = "rule_fallback"

        if self.llm.has_key():
            out = self.llm.generate_structured(
                SYSTEM_PROMPT,
                self._user_message(category, sku_spec),
                AD_BADGE_SCHEMA,
            )
            if out:
                items = out.get("ads" if kind == "ad" else "badges", [])
                for it in items:
                    c = str(it.get("content", "")).strip()
                    if c and not check_text(c):
                        candidates.append(c)
                if candidates:
                    source = "llm"

        # 规则候选（卖点侧重/句式互不相同）
        rules = (
            self._rule_ad_variants(category, sku_spec)
            if kind == "ad"
            else self._rule_badge_variants(sku_spec)
        )
        for c in rules:
            if c not in candidates and not check_text(c):
                candidates.append(c)

        # 通用兜底（理论上规则已够，双保险）
        generic = _GENERIC_ADS if kind == "ad" else _GENERIC_BADGES
        for c in generic:
            if len(candidates) >= min_count:
                break
            if c not in candidates and not check_text(c):
                candidates.append(c)

        # 去重保序 + 合规双保险 + 上限截取
        seen: list[str] = []
        final: list[str] = []
        for c in candidates:
            if c in seen or check_text(c):
                continue
            seen.append(c)
            final.append(c)
            if len(final) >= cap:
                break

        drafts: list[CopywriteDraft] = []
        for i, c in enumerate(final, start=1):
            drafts.append(
                CopywriteDraft(
                    product_id=product_id,
                    copy_type=kind,
                    content=c,
                    variant_no=i,
                    char_len=len(c),
                    sku_basis=None,
                    compliance_hits=[],
                    passed=True,
                    source=source,
                )
            )
        return drafts

    # ---------- 规则模板 ----------

    def _user_message(self, category: str, sku_spec: Optional[dict[str, Any]]) -> str:
        return (
            f"类目：{category or '未知'}\n"
            f"SKU 真实规格（JSON）：{json.dumps(sku_spec or {}, ensure_ascii=False)}\n"
            "请输出投放文案（ads）与角标（badges）。"
        )

    def _rule_ad_variants(
        self, category: str, sku_spec: Optional[dict[str, Any]]
    ) -> list[str]:
        """规则投放文案：不同卖点侧重 + 不同句式（真实差异）。"""
        facts, used = _spec_facts(sku_spec)
        label = (category or "").strip() or "好物"
        # used[i] 与 facts[i] 一一对应（仅含 spec 中真实存在的字段）
        fact_by_key = dict(zip(used, facts))

        def first_of(keys: list[str]) -> str:
            for k in keys:
                if k in fact_by_key:
                    return fact_by_key[k]
            return ""

        variants: list[str] = []
        # v1：材质/规格侧重（句式 A）
        seg = first_of(["材质", "容量", "尺寸"])
        variants.append(
            f"精选{label}，{seg}，日常使用更安心。"
            if seg else f"精选{label}，品质在线，日常使用更安心。"
        )
        # v2：颜色/包装/数量侧重（句式 B）
        seg2 = first_of(["颜色", "包装", "数量"])
        variants.append(
            f"{seg2}，{label}好物，满足日常所需。"
            if seg2 else f"{label}好物，满足日常所需。"
        )
        # v3：综合卖点（句式 C，差异化兜底）
        segs = "，".join(facts[:2])
        variants.append(
            f"{label}优选：{segs}。" if segs else f"{label}优选，值得一试。"
        )
        return _dedupe_strs(variants)

    def _rule_badge_variants(self, sku_spec: Optional[dict[str, Any]]) -> list[str]:
        """规则角标：短词、真实规格驱动 + 通用词，互不相同。"""
        spec = sku_spec or {}
        out: list[str] = []
        if spec.get("材质"):
            out.append("甄选材质")
        if spec.get("颜色"):
            out.append("多色可选")
        if spec.get("数量"):
            n = str(spec["数量"]).strip()
            out.append("单件装" if n in ("1", "1.0") else f"{spec['数量']}件装")
        out += ["精选好物", "上新推荐", "品质之选"]
        return _dedupe_strs(out)


def _dedupe_strs(items: list[str]) -> list[str]:
    seen: list[str] = []
    for it in items:
        if it not in seen:
            seen.append(it)
    return seen


def generate_ads(
    product_id: str,
    category: str = "",
    sku_spec: Optional[dict[str, Any]] = None,
    config: Optional[M3Config] = None,
) -> list[CopywriteDraft]:
    """模块级便捷入口：投放文案候选。"""
    return AdBadgeGenerator(config).generate_ads(product_id, category, sku_spec)


def generate_badges(
    product_id: str,
    category: str = "",
    sku_spec: Optional[dict[str, Any]] = None,
    config: Optional[M3Config] = None,
) -> list[CopywriteDraft]:
    """模块级便捷入口：角标候选。"""
    return AdBadgeGenerator(config).generate_badges(product_id, category, sku_spec)
