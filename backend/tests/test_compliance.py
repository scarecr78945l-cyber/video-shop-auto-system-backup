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
    r = engine().evaluate(item("一次性电子烟 水果口味"))
    assert r.state == ComplianceState.HARD_REJECT
    assert any("禁售词" in x for x in r.reasons)


def test_brand_word_hard_reject():
    r = engine().evaluate(item("耐克官方旗舰店运动水杯"))
    assert r.state == ComplianceState.HARD_REJECT
    assert any("品牌侵权" in x for x in r.reasons)


def test_efficacy_word_manual_review():
    r = engine().evaluate(item("生姜防脱发洗发水"))
    assert r.state == ComplianceState.MANUAL_REVIEW
    assert any("功效" in x for x in r.reasons)


def test_category_outside_whitelist_manual_review():
    r = engine().evaluate(item("美妆蛋收纳盒", category="美妆"))
    assert r.state == ComplianceState.MANUAL_REVIEW
    assert any("白名单" in x for x in r.reasons)


def test_whitelist_disabled_passes():
    r = engine(category_whitelist_enabled=False).evaluate(item("美妆蛋收纳盒", category="美妆"))
    assert r.state == ComplianceState.CANDIDATE


def test_whitelist_custom_via_engine():
    r = ComplianceEngine(SourcingConfig(), category_whitelist=["美妆"]).evaluate(
        item("美妆蛋收纳盒", category="美妆")
    )
    assert r.state == ComplianceState.CANDIDATE


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
