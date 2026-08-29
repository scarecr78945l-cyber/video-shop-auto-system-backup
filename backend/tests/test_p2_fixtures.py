"""P2-1 实战数据 fixtures 回归样本测试（旧系统 app.db 脱敏提取）。

验证：fixtures 文件可读、计数正确、字段完整、脱敏合规（无图片外链/聊天内容）。
用途：选品/上架/素材模块的实战数据回归样本（与 fixtures 离线模式同语义）。
"""

import json
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent.parent / "_management" / "data-exchange" / "old-system-assets" / "fixtures"


def _load(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


@pytest.mark.parametrize(
    "file,expected_count",
    [
        ("p2-products.json", 17),
        ("p2-category-memory.json", 4),
        ("p2-rule-drafts.json", 46),
        ("p2-events-sample.json", 50),
    ],
)
def test_fixtures_present_and_counted(file, expected_count):
    """① 文件存在且计数正确。"""
    data = _load(file)
    assert data["count"] == expected_count
    assert len(data["items"]) == expected_count


def test_products_field_completeness():
    """② 商品样本字段完整（定价/盈亏/淘汰决策字段在位）。"""
    items = _load("p2-products.json")["items"]
    first = items[0]
    for field in ("name", "opportunity_category", "sales_rank", "match_score",
                  "supplier_name", "purchase_price", "suggested_price", "status"):
        assert field in first, f"缺字段 {field}"
    # 至少包含 已淘汰/已入库 等状态样本（覆盖决策路径）
    statuses = {i.get("status") for i in items}
    assert len(statuses) >= 2


def test_fixtures_redaction():
    """③ 脱敏合规：不含图片外链/聊天/密钥特征。"""
    for name in ("p2-products.json", "p2-events-sample.json"):
        text = (FIXTURES / name).read_text(encoding="utf-8")
        assert "snscosdownload" not in text  # 微信 CDN 图片外链已剔除
        assert "wxapp.tc.qq.com" not in text
        assert "password" not in text.lower()
        assert "secret" not in text.lower()


def test_rule_drafts_statuses():
    """④ 规则草稿含 draft/active 状态样本（P0-2 消费端可用）。"""
    items = _load("p2-rule-drafts.json")["items"]
    statuses = {i.get("status") for i in items}
    assert statuses & {"draft", "active"}  # 至少一种生产状态
