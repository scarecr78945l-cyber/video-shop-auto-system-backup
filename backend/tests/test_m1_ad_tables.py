"""m1 投放转化两表测试：建表/唯一键/索引（对照 database/README.md v0.1 DDL 镜像）。

- 两表随 create_all 建出，且重复 create_all 幂等；
- 唯一键 (category, period_start, period_end) 与 (source_file, period_start, period_end, generated_at)
  重复插入触发 IntegrityError（幂等导入契约）；
- 索引 idx_m1_ad_cache_category / idx_m1_ad_cache_period 存在；
- sales_amount 为 INTEGER（分，与 M5 口径一致）。
"""

from datetime import datetime, timezone

import pytest
from sqlalchemy import inspect
from sqlalchemy.exc import IntegrityError

from sourcing.tables import M1AdConversionCache, M1AdConversionIngest

TS = datetime(2026, 9, 1, tzinfo=timezone.utc)


def _cache_row(**overrides):
    base = dict(
        category="收纳整理",
        roi=3.2,
        sales_amount=1280000,
        sample_count=34,
        period_start="2026-08-01",
        period_end="2026-08-31",
        generated_at=TS,
        source_file="m5-ad-conversion.json",
    )
    base.update(overrides)
    return M1AdConversionCache(**base)


def _ingest_row(**overrides):
    base = dict(
        source_file="m5-ad-conversion.json",
        schema_ver=1,
        period_start="2026-08-01",
        period_end="2026-08-31",
        generated_at=TS,
        rows_loaded=6,
        skipped=0,
        status="ok",
    )
    base.update(overrides)
    return M1AdConversionIngest(**base)


def test_tables_created(db):
    """两表随 create_all 建出。"""
    inspector = inspect(db.engine)
    tables = set(inspector.get_table_names())
    assert "m1_ad_conversion_cache" in tables
    assert "m1_ad_conversion_ingests" in tables


def test_create_all_idempotent(db):
    """重复 create_all 幂等不报错（对应 SQL 脚本 IF NOT EXISTS 语义）。"""
    db.create_all()
    db.create_all()


def test_cache_unique_key(cfg, db):
    """同 (category, period_start, period_end) 重复插入 → IntegrityError。"""
    with db.session() as session:
        session.add(_cache_row())
        session.flush()
        session.add(
            _cache_row(
                roi=2.0,
                sales_amount=100,
                generated_at=datetime(2026, 9, 2, tzinfo=timezone.utc),
            )
        )
        with pytest.raises(IntegrityError):
            session.flush()
        session.rollback()  # 清理失败事务，避免 with 出口 commit 抛 PendingRollbackError


def test_cache_unique_key_allows_different_period(db):
    """不同周期（period 不同）可共存，唯一键按周期而非类目。"""
    with db.session() as session:
        session.add(_cache_row())
        session.add(_cache_row(period_start="2026-09-01", period_end="2026-09-30"))
        session.flush()


def test_ingests_unique_key(db):
    """同 (source_file, period_start, period_end, generated_at) 重复插入 → IntegrityError。"""
    with db.session() as session:
        session.add(_ingest_row())
        session.flush()
        session.add(_ingest_row(rows_loaded=5))
        with pytest.raises(IntegrityError):
            session.flush()
        session.rollback()


def test_ingests_unique_key_allows_new_generated_at(db):
    """generated_at 不同（新批次）可共存。"""
    with db.session() as session:
        session.add(_ingest_row())
        session.add(_ingest_row(generated_at=datetime(2026, 9, 2, tzinfo=timezone.utc)))
        session.flush()


def test_cache_indexes_exist(db):
    """category / period 索引存在（对照 SQL 脚本 CREATE INDEX IF NOT EXISTS）。"""
    inspector = inspect(db.engine)
    indexes = {ix["name"] for ix in inspector.get_indexes("m1_ad_conversion_cache")}
    assert "idx_m1_ad_cache_category" in indexes
    assert "idx_m1_ad_cache_period" in indexes


def test_cache_sales_amount_column_integer(db):
    """sales_amount 列为 INTEGER（单位分，C-2 口径，禁元/分混用）。"""
    inspector = inspect(db.engine)
    cols = {c["name"]: c["type"] for c in inspector.get_columns("m1_ad_conversion_cache")}
    assert "sales_amount" in cols
    assert str(cols["sales_amount"]) == "INTEGER"
    assert "category" in cols
