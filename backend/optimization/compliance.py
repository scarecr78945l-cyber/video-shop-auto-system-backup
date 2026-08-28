"""M3 自动素材优化模块 · 合规封装（复用 sourcing.compliance 词库并扩展）。

供应链词/品牌词/功效词/禁售词复用 M1 已验证的合规引擎；本模块按 06/10 文档
扩展素材专用规则（字幕/角标/主图提示词场景）。任何优化素材（视频字幕/角标、
主图、文案）产出前后都必须过本模块预审。
"""

from __future__ import annotations

from sourcing.compliance import (  # noqa: F401  复用（backend 根运行时可导入）
    BRAND_WORDS,
    EFFICACY_WORDS,
    PROHIBITED_WORDS,
    SUPPLY_CHAIN_WORDS,
    ComplianceEngine,
    ComplianceState,
    sanitize_title,
)

# 素材专用扩展：06/10 文档要求 1688/工厂/源头/厂家/一件代发/批发 不出现在
# 标题、主图、素材；广告物料额外禁「同款」「官方旗舰」等引流侵权表述。
SUPPLY_CHAIN_WORDS_EXTRA = ["1688", "工厂", "源头", "厂家", "批发", "一件代发", "代发"]
AD_BADGE_FORBIDDEN = [
    "同款", "官方旗舰", "官方", "旗舰店", "代言", "联名", "正品", "保真",
]

_MERGE_SUPPLY = sorted(set(SUPPLY_CHAIN_WORDS) | set(SUPPLY_CHAIN_WORDS_EXTRA))
AD_BADGE_FORBIDDEN_LOWER = [w.lower() for w in AD_BADGE_FORBIDDEN]


def check_supply_chain(text: str) -> list[str]:
    """命中供应链词列表（字幕/角标/主图/标题用）。"""
    t = (text or "").lower()
    return [w for w in _MERGE_SUPPLY if w.lower() in t]


def check_brand_ad(text: str) -> list[str]:
    """命中广告物料禁用词列表（品牌词/「同款」/「官方旗舰」等）。"""
    t = (text or "").lower()
    return [w for w in AD_BADGE_FORBIDDEN_LOWER if w in t]


def check_text(text: str) -> list[str]:
    """完整规则预审：供应链词 + 广告禁用词 + 品牌词 + 功效词 + 禁售词。"""
    hits: list[str] = []
    t = (text or "").lower()
    for w in _MERGE_SUPPLY:
        if w.lower() in t:
            hits.append(f"供应链词:{w}")
    for w in AD_BADGE_FORBIDDEN_LOWER:
        if w in t:
            hits.append(f"广告禁用词:{w}")
    for w in BRAND_WORDS:
        if w.lower() in t:
            hits.append(f"品牌词:{w}")
    for w in EFFICACY_WORDS:
        if w in t:
            hits.append(f"功效词:{w}")
    for w in PROHIBITED_WORDS:
        if w in t:
            hits.append(f"禁售词:{w}")
    return hits
