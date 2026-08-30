"""S5 人工闸门按达标自动放松测试（gate_relax，v1.1+）。

覆盖（验收标准）：
- 未启用不放松（默认 enabled=false 行为零变化）；
- 样本不足不放松；
- 通过率不足不放松；
- 达标自动放行（should_relax_category=True + relax_manual_review 实际写库放行）；
- dry-run 只报告不放行；
- 类目过滤（gate.relax.categories 子集 + relax_manual_review categories 覆盖）；
- app_config 注入（临时库 get_config_value 读取）与类型非法回落默认；
- 统计窗口过滤（窗口外不计入样本）；
- pipeline 接线：默认零变化 / 启用达标后 manual_review 候选自动放行入池；
- CLI gate-relax --dry-run / --apply。
"""

import uuid
from datetime import timedelta

import pytest
from click.testing import CliRunner

from sourcing import repo
from sourcing.cli import cli
from sourcing.gate import (
    GateRelaxConfig,
    compute_category_stats,
    load_gate_relax_config,
    relax_manual_review,
    should_relax_category,
)
from sourcing.models import ComplianceState, SourceItem, utcnow
from sourcing.pipeline import SourcingPipeline
from sourcing.tables import Product

# 达标组合：48 通过 + 2 拒绝 = 50 样本，通过率 0.96 ≥ 0.95
_PASSED = 48
_REJECTED = 2


# ---------------------------------------------------------------- 造数工具
def _add_product(db, category, state, days_ago=1, title="S5 测试商品"):
    with db.session() as session:
        row = Product(
            fingerprint=f"s5-{uuid.uuid4().hex[:12]}",
            title=title,
            sanitized_title=title,
            category=category,
            state=state,
            created_at=utcnow() - timedelta(days=days_ago),
        )
        session.add(row)
        session.flush()
        return row.id


def _seed_stats(db, category, passed, rejected, days_ago=1):
    """造窗口内该类目复核统计：passed 条 pool + rejected 条 rejected。"""
    for _ in range(passed):
        _add_product(db, category, "pool", days_ago=days_ago)
    for _ in range(rejected):
        _add_product(db, category, "rejected", days_ago=days_ago)


def _set_relax_config(db, **overrides):
    """写 app_config gate.relax.* 键（测试注入；生产由总控协调写，本模块只读）。"""
    values = {
        "enabled": True,
        "min_samples": 50,
        "pass_rate": 0.95,
        "window_days": 30,
    }
    values.update(overrides)
    with db.session() as session:
        for key, value in values.items():
            repo.set_config_value(session, f"gate.relax.{key}", value)


def _qualified_config(**overrides) -> GateRelaxConfig:
    base = dict(enabled=True, min_samples=50, pass_rate=0.95, window_days=30)
    base.update(overrides)
    return GateRelaxConfig(**base)


# ---------------------------------------------------------------- 未启用 / 默认零变化
def test_disabled_no_relax_default_config(cfg, db):
    """未启用（默认 GateRelaxConfig）→ 不放松，即使统计达标。"""
    _seed_stats(db, "家居日用", passed=_PASSED, rejected=_REJECTED)
    ok, reasons = should_relax_category(db, "家居日用", GateRelaxConfig())
    assert ok is False
    assert any("未启用" in r for r in reasons)
    # app_config 无键 → load 回落默认 disabled
    with db.session() as session:
        loaded = load_gate_relax_config(session)
    assert loaded == GateRelaxConfig()


def test_appconfig_no_keys_means_disabled(cfg, db):
    """app_config 完全没有 gate.relax.* 键 → 回落默认（不放松，零变化）。"""
    _seed_stats(db, "家居日用", passed=_PASSED, rejected=_REJECTED)
    with db.session() as session:
        loaded = load_gate_relax_config(session)
    assert loaded.enabled is False
    assert should_relax_category(db, "家居日用", loaded)[0] is False


# ---------------------------------------------------------------- 样本不足 / 通过率不足
def test_insufficient_samples_no_relax(cfg, db):
    """样本不足（30 < 50）→ 不放松。"""
    _seed_stats(db, "家居日用", passed=20, rejected=10)
    ok, reasons = should_relax_category(db, "家居日用", _qualified_config())
    assert ok is False
    assert any("样本不足" in r for r in reasons)
    assert any("30 品" in r and "min_samples 50" in r for r in reasons)


def test_low_pass_rate_no_relax(cfg, db):
    """样本够但通过率不足（0.8 < 0.95）→ 不放松。"""
    _seed_stats(db, "家居日用", passed=40, rejected=10)
    ok, reasons = should_relax_category(db, "家居日用", _qualified_config())
    assert ok is False
    assert any("通过率不足" in r for r in reasons)
    assert any("0.8000" in r and "0.95" in r for r in reasons)


# ---------------------------------------------------------------- 达标放行 / dry-run
def test_qualified_auto_release(cfg, db):
    """达标（通过率 0.96 ≥ 0.95 且样本 50 ≥ 50）→ 放行；relax_manual_review 实际写库。"""
    _seed_stats(db, "家居日用", passed=_PASSED, rejected=_REJECTED)
    cfg_obj = _qualified_config()
    ok, reasons = should_relax_category(db, "家居日用", cfg_obj)
    assert ok is True
    assert any("达标放行" in r for r in reasons)

    pid = _add_product(db, "家居日用", "manual_review")
    report = relax_manual_review(db, config=cfg_obj, dry_run=False)
    assert report.dry_run is False
    assert report.relaxed_count == 1
    assert report.kept_count == 0
    assert len(report.actions) == 1 and report.actions[0].relaxed is True
    with db.session() as session:
        assert session.get(Product, pid).state == "pool"


def test_dry_run_reports_only(cfg, db):
    """dry-run：报告可放行但不改库（state 保持 manual_review）。"""
    _seed_stats(db, "家居日用", passed=_PASSED, rejected=_REJECTED)
    cfg_obj = _qualified_config()
    pid = _add_product(db, "家居日用", "manual_review")
    report = relax_manual_review(db, config=cfg_obj, dry_run=True)
    assert report.dry_run is True
    assert report.relaxed_count == 1  # 可放行（只报告）
    assert len(report.actions) == 1 and report.actions[0].relaxed is True
    with db.session() as session:
        assert session.get(Product, pid).state == "manual_review"  # 未放行


# ---------------------------------------------------------------- 类目过滤
def test_category_subset_filter(cfg, db):
    """gate.relax.categories 子集：命中类目放行、子集外不放松。"""
    _seed_stats(db, "家居日用", passed=_PASSED, rejected=_REJECTED)
    _seed_stats(db, "宠物用品", passed=_PASSED, rejected=_REJECTED)
    cfg_obj = _qualified_config(categories=("家居日用",))

    ok, _ = should_relax_category(db, "家居日用", cfg_obj)
    assert ok is True
    ok, reasons = should_relax_category(db, "宠物用品", cfg_obj)
    assert ok is False
    assert any("子集" in r for r in reasons)


def test_relax_categories_override(cfg, db):
    """relax_manual_review(categories=...) 覆盖 config.categories：只放行覆盖子集内。"""
    _seed_stats(db, "家居日用", passed=_PASSED, rejected=_REJECTED)
    _seed_stats(db, "宠物用品", passed=_PASSED, rejected=_REJECTED)
    cfg_obj = _qualified_config(categories=("家居日用",))
    p_keep = _add_product(db, "家居日用", "manual_review")
    p_relax = _add_product(db, "宠物用品", "manual_review")

    report = relax_manual_review(db, config=cfg_obj, dry_run=False, categories=["宠物用品"])
    assert report.relaxed_count == 1
    with db.session() as session:
        assert session.get(Product, p_relax).state == "pool"
        assert session.get(Product, p_keep).state == "manual_review"


# ---------------------------------------------------------------- app_config 注入 / 类型回落 / 窗口
def test_appconfig_injection(cfg, db):
    """app_config 注入（临时库 get_config_value）→ load 生效并驱动判定。"""
    _seed_stats(db, "家居日用", passed=_PASSED, rejected=_REJECTED)
    _set_relax_config(db)  # enabled=True min=50 rate=0.95 window=30 categories=全部
    with db.session() as session:
        loaded = load_gate_relax_config(session)
    assert loaded.enabled is True
    assert loaded.min_samples == 50
    assert loaded.pass_rate == 0.95
    assert loaded.window_days == 30
    assert loaded.categories == ()
    assert should_relax_category(db, "家居日用", loaded)[0] is True


def test_invalid_types_fall_back_to_default(cfg, db):
    """类型非法/越界 → 逐键回落默认（整体 disabled 零变化，不抛异常）。"""
    with db.session() as session:
        repo.set_config_value(session, "gate.relax.enabled", "yes")      # 非 bool
        repo.set_config_value(session, "gate.relax.min_samples", "很多")  # 非法 int
        repo.set_config_value(session, "gate.relax.pass_rate", 2.5)       # 越界 >1
        repo.set_config_value(session, "gate.relax.window_days", 0)       # <1
        repo.set_config_value(session, "gate.relax.categories", "家居日用")  # 非 list
    with db.session() as session:
        loaded = load_gate_relax_config(session)
    assert loaded == GateRelaxConfig()


def test_window_excludes_old_products(cfg, db):
    """统计窗口：窗口外（>30 天）商品不计入样本。"""
    _seed_stats(db, "家居日用", passed=_PASSED, rejected=_REJECTED, days_ago=1)
    _add_product(db, "家居日用", "pool", days_ago=40)     # 窗口外通过 → 不计
    _add_product(db, "家居日用", "rejected", days_ago=31)  # 窗口外拒绝 → 不计
    cfg_obj = _qualified_config()
    stats = compute_category_stats(db, "家居日用", cfg_obj)
    assert stats.sample_size == 50
    assert stats.passed == _PASSED and stats.rejected == _REJECTED
    assert stats.pass_rate == pytest.approx(0.96)
    assert should_relax_category(db, "家居日用", cfg_obj)[0] is True


def test_empty_category_conservative(cfg, db):
    """空类目保守不放松（无法按类目统计，R-54 兜底）。"""
    ok, reasons = should_relax_category(db, "", _qualified_config(min_samples=1, pass_rate=0.5))
    assert ok is False
    assert any("类目为空" in r for r in reasons)


# ---------------------------------------------------------------- pipeline 接线
def test_pipeline_default_zero_change(cfg, db):
    """默认（无 app_config 键）→ manual_review 候选停在人工闸门，不入池（零变化）。"""
    pipe = SourcingPipeline(cfg, db)
    items = [
        SourceItem(
            source="youmi", board="商品榜", platform_item_id="s5-a",
            title="生姜防脱发洗发水", category="家居日用",
        )
    ]
    result = pipe.run_from_items(items, mode="fixtures", do_quotes=False, persist=False)
    assert result.gate_relaxed == 0
    assert result.manual_review == 1
    assert result.pool_entered == 0
    assert all(c.state == "pool" for c in result.pool)


def test_pipeline_relax_enabled_releases_to_pool(cfg, db):
    """启用 + 达标 → manual_review 候选人工复核前自动放行 pool 并参与 TopN。"""
    _seed_stats(db, "家居日用", passed=_PASSED, rejected=_REJECTED)
    _set_relax_config(db)
    pipe = SourcingPipeline(cfg, db)
    items = [
        SourceItem(
            source="youmi", board="商品榜", platform_item_id="s5-b",
            title="生姜防脱发洗发水", category="家居日用",
        )
    ]
    result = pipe.run_from_items(items, mode="fixtures", do_quotes=False, persist=False)
    assert result.gate_relaxed == 1
    assert result.manual_review == 1  # 仍计数为人工复核来源
    assert any(
        c.state == "pool" and c.compliance.state == ComplianceState.MANUAL_REVIEW
        for c in result.pool
    )
    # 放行理由追加到 compliance.reasons（可解释纪律）
    released = next(c for c in result.pool if c.compliance.state == ComplianceState.MANUAL_REVIEW)
    assert any("gate.relax 自动放行" in r for r in released.compliance.reasons)


def test_pipeline_relax_category_not_configured_stays(cfg, db):
    """启用但该类目不在 gate.relax.categories 子集 → 仍停人工闸门。"""
    _seed_stats(db, "家居日用", passed=_PASSED, rejected=_REJECTED)
    _set_relax_config(db, categories=["宠物用品"])
    pipe = SourcingPipeline(cfg, db)
    items = [
        SourceItem(
            source="youmi", board="商品榜", platform_item_id="s5-c",
            title="生姜防脱发洗发水", category="家居日用",
        )
    ]
    result = pipe.run_from_items(items, mode="fixtures", do_quotes=False, persist=False)
    assert result.gate_relaxed == 0
    assert result.manual_review == 1
    assert result.pool_entered == 0


# ---------------------------------------------------------------- CLI
def test_cli_gate_relax_dry_run_then_apply(cfg, db):
    """CLI：缺省 dry-run 只报告不放行；--apply 实际放行。"""
    _seed_stats(db, "家居日用", passed=_PASSED, rejected=_REJECTED)
    _set_relax_config(db)
    pid = _add_product(db, "家居日用", "manual_review")

    runner = CliRunner()
    dry = runner.invoke(cli, ["--db-url", cfg.db_url, "gate-relax"])
    assert dry.exit_code == 0, dry.output
    assert "DRY-RUN 只报告" in dry.output
    assert "达标可放行 1" in dry.output
    with db.session() as session:
        assert session.get(Product, pid).state == "manual_review"  # 未放行

    applied = runner.invoke(cli, ["--db-url", cfg.db_url, "gate-relax", "--apply"])
    assert applied.exit_code == 0, applied.output
    assert "已放行" in applied.output
    with db.session() as session:
        assert session.get(Product, pid).state == "pool"  # 已放行
