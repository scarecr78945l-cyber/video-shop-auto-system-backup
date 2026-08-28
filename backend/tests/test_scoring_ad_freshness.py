"""投放转化数据新鲜度/弱样本过滤测试（S1b）。

覆盖四类场景（C-2 / R-14）：
① 新鲜数据（generated_at=now, sample_count=10）→ 投放转化维度 active，总分含该维（基础四维折算，和=100）；
② 过期数据（generated_at 超过 ad_data_max_age_days）→ 维度不生效，总分=基础四维和；
③ 弱样本（sample_count<5）→ 维度不生效；
④ 无元数据（fixtures 旧格式仅 {roi, sales}）→ 维度生效（兼容既有 39 测试行为）。

构造配置一律走构造函数（SourcingConfig(scoring=ScoringConfig(ad_data_max_age_days=...))）；
pydantic v2 禁止对未声明字段 setattr。
"""

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from sourcing.config import ScoringConfig, SourcingConfig
from sourcing.db import Database
from sourcing.pipeline import SourcingPipeline
from sourcing.scoring import ScoreInput, Scorer

NOW = datetime.now(timezone.utc)
STALE = NOW - timedelta(days=10)  # > 默认 7 天阈值


@pytest.fixture()
def ad_cfg(tmp_path):
    return SourcingConfig(
        db_url=f"sqlite:///{tmp_path / 'ad-fresh.db'}",
        fixtures_dir=Path(__file__).resolve().parent.parent / "fixtures",
        data_dir=tmp_path / "data",
        scoring=ScoringConfig(ad_data_max_age_days=7.0),
    )


@pytest.fixture()
def ad_db(ad_cfg):
    database = Database(ad_cfg)
    database.create_all()
    return database


@pytest.fixture()
def pipe(ad_cfg, ad_db):
    return SourcingPipeline(ad_cfg, ad_db)


def _score(pipe: SourcingPipeline, ad_roi, ad_sales):
    """与 pipeline 打分路径一致的满分基础四维输入（趋势35/利润30/售后20/供给15）。"""
    return Scorer(pipe.config.scoring).score(
        ScoreInput(
            rank=1, sales=10000, board_count=2,
            real_cost=5.0, suggested_price=29.9,
            return_rate=0.02, supplier_count=10,
            ad_roi=ad_roi, ad_sales=ad_sales,
        )
    )


def test_config_default_max_age_is_7_days():
    assert ScoringConfig().ad_data_max_age_days == 7.0


def test_fresh_data_ad_dimension_active(pipe):
    """① 新鲜数据：维度 active，基础四维按 (100-10)/100 折算，和=100。"""
    ad = {"roi": 3.2, "sales_amount": 1280000, "sample_count": 10, "generated_at": NOW.isoformat()}
    filtered = pipe._fresh_ad_by_category({"收纳整理": ad})
    assert filtered["收纳整理"] == ad  # 保留元数据

    s = _score(pipe, ad["roi"], ad["sales_amount"])
    assert s.dimensions["ad_conversion"].active
    assert s.dimensions["ad_conversion"].raw == 10.0
    assert s.dimensions["ad_conversion"].weighted == 10.0
    assert abs(s.total - 100.0) < 1e-6
    assert abs(s.dimensions["trend"].weighted - 31.5) < 1e-6  # 35 × 0.9


def test_stale_data_dimension_inactive(pipe):
    """② 过期数据：过滤置空，维度不生效，总分=基础四维和（满分 100 未折算）。"""
    ad = {
        "roi": 3.2, "sales_amount": 1280000, "sample_count": 10,
        "generated_at": STALE.isoformat(),
    }
    filtered = pipe._fresh_ad_by_category({"收纳整理": ad})
    assert filtered["收纳整理"] == {}

    s = _score(pipe, None, None)  # 视为无数据 → 不传 ad_roi/ad_sales
    assert not s.dimensions["ad_conversion"].active
    assert s.dimensions["ad_conversion"].weight == 0
    assert s.total == 100.0
    assert s.dimensions["trend"].weighted == 35.0  # 基础四维未折算


def test_weak_sample_dimension_inactive(pipe):
    """③ 弱样本（sample_count=3 < 5）：过滤置空，维度不生效。"""
    ad = {"roi": 3.2, "sales_amount": 1280000, "sample_count": 3, "generated_at": NOW.isoformat()}
    filtered = pipe._fresh_ad_by_category({"收纳整理": ad})
    assert filtered["收纳整理"] == {}

    s = _score(pipe, None, None)
    assert not s.dimensions["ad_conversion"].active
    assert s.total == 100.0


def test_no_metadata_legacy_fixture_active(pipe):
    """④ 无元数据（fixtures 旧格式 {roi, sales}）：视为可用，维度生效（兼容既有行为）。"""
    ad = {"roi": 3.2, "sales": 128000}
    filtered = pipe._fresh_ad_by_category({"收纳整理": ad})
    assert filtered["收纳整理"] == ad

    s = _score(pipe, ad["roi"], ad["sales"])
    assert s.dimensions["ad_conversion"].active
    assert s.dimensions["ad_conversion"].weighted == 10.0
    assert abs(s.total - 100.0) < 1e-6


def test_generated_at_iso_z_suffix_fresh(pipe):
    """ISO 字符串带 Z 后缀（UTC 表示）解析为新鲜数据。"""
    ad = {
        "roi": 2.4, "sales_amount": 860000, "sample_count": 21,
        "generated_at": NOW.isoformat().replace("+00:00", "Z"),
    }
    filtered = pipe._fresh_ad_by_category({"宠物用品": ad})
    assert filtered["宠物用品"] == ad


def test_naive_generated_at_assumed_utc(pipe):
    """naive datetime（无 tzinfo，如 SQLite 读取）按 UTC 补时区，不误判过期。"""
    ad = {
        "roi": 2.0, "sales": 100, "sample_count": 8,
        "generated_at": datetime.now().replace(tzinfo=None),
    }
    filtered = pipe._fresh_ad_by_category({"数码配件": ad})
    assert filtered["数码配件"] == ad


def test_sales_amount_preferred_over_legacy_sales(pipe):
    """同时含 sales_amount 与 sales 时优先用 sales_amount（C-2 新口径）。"""
    ad = {"roi": 1.8, "sales_amount": 430000, "sales": 999, "sample_count": 12}
    filtered = pipe._fresh_ad_by_category({"家居日用": ad})
    assert filtered["家居日用"] == ad
    s = _score(pipe, ad["roi"], ad["sales_amount"])
    assert s.dimensions["ad_conversion"].active
