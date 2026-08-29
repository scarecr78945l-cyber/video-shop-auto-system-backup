"""REC-迁移-01（C1）：鞋服/包类硬拦词表 fixtures 测试。

旧系统 SOURCING_HARD_BLOCK_POLICY 语义迁移验证：
① 命中鞋服词（无安全上下文）→ hard_reject
② 安全上下文豁免（衣架/洗衣机/收纳/客服）→ 放行（不因鞋服词拒绝）
③ 命中包词（无安全上下文）→ hard_reject
④ 安全上下文豁免（垃圾袋/收纳袋/保鲜袋）→ 放行
"""

from sourcing.compliance import ComplianceEngine, HardBlockPolicy
from sourcing.config import SourcingConfig
from sourcing.models import ComplianceState, SourceItem


def _engine() -> ComplianceEngine:
    cfg = SourcingConfig(_env_file=None)
    return ComplianceEngine(cfg)


def _item(title: str) -> SourceItem:
    return SourceItem(
        source="fixtures", board="board", platform_item_id="id-1",
        title=title, category="家居日用",
    )


def test_apparel_word_hard_reject() -> None:
    """① 命中鞋服词（无安全上下文）→ hard_reject。"""
    r = _engine().evaluate(_item("夏季新款棉质连衣裙 女装"))
    assert r.state == ComplianceState.HARD_REJECT
    assert any("鞋服/包类" in x for x in r.reasons)


def test_apparel_safe_context_allowed() -> None:
    """② 安全上下文豁免：衣架/洗衣机/收纳 → 不因鞋服词拒绝。"""
    for title in ("不锈钢晾衣架 落地式", "迷你洗衣机 宿舍专用", "衣柜收纳盒 分隔板"):
        r = _engine().evaluate(_item(title))
        assert r.state != ComplianceState.HARD_REJECT, f"{title} 不应被硬拦"


def test_bag_word_hard_reject() -> None:
    """③ 命中包词（无安全上下文）→ hard_reject。"""
    r = _engine().evaluate(_item("头层牛皮双肩包 商务"))
    assert r.state == ComplianceState.HARD_REJECT
    assert any("鞋服/包类" in x for x in r.reasons)


def test_bag_safe_context_allowed() -> None:
    """④ 安全上下文豁免：垃圾袋/收纳袋/保鲜袋 → 放行。"""
    for title in ("加厚垃圾袋 45x50cm 100只", "真空收纳袋 压缩袋 家用", "食品保鲜袋 加厚抽取式"):
        r = _engine().evaluate(_item(title))
        assert r.state != ComplianceState.HARD_REJECT, f"{title} 不应被硬拦"


def test_policy_loaded_from_json() -> None:
    """词表从 JSON 配置加载（REC-迁移-01：不硬编码）。"""
    policy = HardBlockPolicy()
    assert len(policy.apparel_terms) >= 200, f"apparel_terms 应 ≥200，实际 {len(policy.apparel_terms)}"
    assert len(policy.bag_terms) >= 50, f"bag_terms 应 ≥50，实际 {len(policy.bag_terms)}"
    assert "服装" in policy.apparel_terms
    assert "衣架" in policy.safe_apparel_terms
    assert "垃圾袋" in policy.safe_bag_terms


def test_disabled_policy_allows_apparel() -> None:
    """总开关关闭时鞋服词不硬拦（可配置化放松）。"""
    cfg = SourcingConfig(_env_file=None)
    cfg.hard_block_policy_enabled = False
    engine = ComplianceEngine(cfg)
    r = engine.evaluate(_item("夏季新款棉质连衣裙 女装"))
    assert r.state != ComplianceState.HARD_REJECT
