"""合规三态 + 标题清洗测试。"""

import pytest

from sourcing.compliance import ComplianceEngine, sanitize_title
from sourcing.config import SourcingConfig
from sourcing.models import ComplianceState, SourceItem


def item(title: str, category: str = "家居日用") -> SourceItem:
    return SourceItem(
        source="opportunities", board="机会品", platform_item_id="t1",
        title=title, category=category,
    )


def engine(**overrides) -> ComplianceEngine:
    cfg = SourcingConfig(**overrides)
    return ComplianceEngine(cfg)


def test_clean_title_candidate():
    r = engine().evaluate(item("免打孔卫生间置物架 浴室收纳架"))
    assert r.state == ComplianceState.CANDIDATE
    assert "免打孔卫生间置物架 浴室收纳架" in r.sanitized_title


def test_prohibited_word_hard_reject():
    # 「水果口味」命中 permanent 食品词（P-031），电子烟命中禁售词——均须 hard_reject
    r = engine().evaluate(item("一次性电子烟 原味"))
    assert r.state == ComplianceState.HARD_REJECT
    assert any("禁售词" in x for x in r.reasons)


def test_brand_word_hard_reject():
    r = engine().evaluate(item("耐克官方旗舰店运动水杯"))
    assert r.state == ComplianceState.HARD_REJECT
    assert any("品牌侵权" in x for x in r.reasons)


def test_efficacy_word_manual_review():
    # 防脱发功效词（类目在白名单内）→ manual_review（缺资质）；不含 permanent 词
    r = engine().evaluate(item("防脱发洗发水 温和配方"))
    assert r.state == ComplianceState.MANUAL_REVIEW
    assert any("功效" in x for x in r.reasons)


def test_category_outside_whitelist_hard_reject():
    """P-031：类目不在白名单 → hard_reject（用户裁定「只找白名单里的品，其他的不要找」）。"""
    r = engine().evaluate(item("美妆蛋收纳盒", category="美妆"))
    assert r.state == ComplianceState.HARD_REJECT
    assert any("白名单" in x for x in r.reasons)


def test_whitelist_disabled_passes():
    r = engine(category_whitelist_enabled=False).evaluate(item("美妆蛋收纳盒", category="美妆"))
    assert r.state == ComplianceState.CANDIDATE


def test_whitelist_custom_via_engine():
    r = ComplianceEngine(SourcingConfig(), category_whitelist=["美妆"]).evaluate(
        item("美妆蛋收纳盒", category="美妆")
    )
    assert r.state == ComplianceState.CANDIDATE


def test_category_inferred_when_missing():
    """P-031：采集源未带类目时按标题推断白名单类目（锅刷→厨房用品）。"""
    r = engine().evaluate(item("不锈钢锅刷不伤锅具去污 长柄厨房清洁刷", category=""))
    assert r.state == ComplianceState.CANDIDATE
    assert r.category == "厨房用品"


def test_category_unmappable_hard_reject():
    """P-031：标题无法映射到白名单类目（且无永久排除词）→ hard_reject（用户裁定）。"""
    r = engine().evaluate(item("汽车雨刮器 通用款", category=""))
    assert r.state == ComplianceState.HARD_REJECT
    assert any("白名单" in x for x in r.reasons)


def test_permanent_exclusion_hard_reject():
    """P-031：永久排除词（食品/饮品等）命中 → hard_reject（用户裁定不做）。"""
    r = engine().evaluate(item("新疆纯驼乳粉320g*2罐", category=""))
    assert r.state == ComplianceState.HARD_REJECT
    assert any("永久排除" in x for x in r.reasons)
    # 补全词生效：酸奶（此前被「健身」映射到户外运动漏网）
    r2 = engine().evaluate(item("0蔗糖低温酸奶无蔗糖健身轻食代餐", category=""))
    assert r2.state == ComplianceState.HARD_REJECT
    # 误伤修复：「原始黄金」品牌名不再被「黄金」贵金属词误拦，但驼奶粉本身被「驼乳」拦
    r3 = engine().evaluate(item("原始黄金驼奶粉330g 特级产区", category=""))
    assert r3.state == ComplianceState.HARD_REJECT
    assert not any("黄金" in x for x in r3.reasons)


def test_sanitize_removes_marketing_and_brand():
    t = sanitize_title("【包邮】耐克同款官方旗舰店运动水壶 2025新款 爆款特价")
    assert "包邮" not in t
    assert "同款" not in t
    assert "旗舰" not in t
    assert "爆款" not in t
    assert "运动水壶" in t


def test_sanitize_empty_after_cleaning_rejects():
    r = engine().evaluate(item("官方旗舰店"))
    assert r.state == ComplianceState.HARD_REJECT
