"""M4 自动上架：listing_* 7 表 DDL 落地单测（对齐 database/README.md DDL v0）。

纪律：本模块独立 basetemp `--basetemp=".pytest-tmp-m4"`（P-001/P-011）；
全部用例用 tmp_path 临时 SQLite（fixture 注入 db_url），零网络零真实平台，
不触碰真实 m4-listing.db。
"""

import pytest
import sqlalchemy as sa

from listing.models import ListingTask
from listing.repo import DuplicateTaskError, ListingRepo

EXPECTED_TABLES = {
    "listing_tasks",
    "listing_spus",
    "listing_skus",
    "listing_upload_assets",
    "listing_op_logs",
    "listing_audit_records",
    "listing_quota_states",
}


def _inspector(db_listing) -> sa.Inspector:
    return sa.inspect(db_listing.engine)


def _column_names(inspector: sa.Inspector, table: str) -> set[str]:
    return {c["name"] for c in inspector.get_columns(table)}


def _unique_column_sets(inspector: sa.Inspector, table: str) -> set[frozenset[str]]:
    """唯一约束列集合（列顺序可能不同，一律 set 比较）。"""
    return {
        frozenset(uc["column_names"])
        for uc in inspector.get_unique_constraints(table)
    }


def _index_names(inspector: sa.Inspector, table: str) -> set[str]:
    return {ix["name"] for ix in inspector.get_indexes(table)}


# ---------------------------------------------------------------- 表存在性


def test_init_db_creates_seven_listing_tables(db_listing):
    """init-db 后 7 张 listing_* 表全部存在。"""
    tables = set(_inspector(db_listing).get_table_names())
    assert EXPECTED_TABLES <= tables, f"缺失表: {EXPECTED_TABLES - tables}"


def test_create_all_idempotent(db_listing):
    """create_all 幂等：重复执行不报错且表集合不变。"""
    before = set(_inspector(db_listing).get_table_names())
    db_listing.create_all()
    after = set(_inspector(db_listing).get_table_names())
    assert before == after


# ---------------------------------------------------------------- 唯一约束


def test_listing_tasks_unique_identity_constraint(db_listing):
    """(product_id, stage, generation_version) 唯一约束存在（set 比较，忽略列顺序）。"""
    unique_sets = _unique_column_sets(_inspector(db_listing), "listing_tasks")
    assert frozenset({"product_id", "stage", "generation_version"}) in unique_sets


def test_listing_skus_unique_constraint(db_listing):
    """(spu_id, product_sku_code) 唯一约束存在。"""
    unique_sets = _unique_column_sets(_inspector(db_listing), "listing_skus")
    assert frozenset({"spu_id", "product_sku_code"}) in unique_sets


def test_listing_upload_assets_unique_constraint(db_listing):
    """(task_id, file_sha256) 唯一约束存在（上传幂等去重键）。"""
    unique_sets = _unique_column_sets(_inspector(db_listing), "listing_upload_assets")
    assert frozenset({"task_id", "file_sha256"}) in unique_sets


def test_listing_audit_records_unique_constraint(db_listing):
    """(task_id, audit_id) 唯一约束存在。"""
    unique_sets = _unique_column_sets(_inspector(db_listing), "listing_audit_records")
    assert frozenset({"task_id", "audit_id"}) in unique_sets


# ---------------------------------------------------------------- 关键列


def test_listing_tasks_columns_present(db_listing):
    """listing_tasks 关键列齐全（含 `_at` 时间戳列）。"""
    cols = _column_names(_inspector(db_listing), "listing_tasks")
    assert {
        "task_id",
        "product_id",
        "generation_version",
        "stage",
        "status",
        "gate_result",
        "platform_spu_id",
        "product_link",
        "link_verified_at",
        "reject_reason_code",
        "attempts",
        "lease_owner",
        "lease_expires_at",
        "created_at",
        "updated_at",
    } <= cols


def test_op_logs_columns_present(db_listing):
    """listing_op_logs 关键列齐全（证据留痕字段）。"""
    cols = _column_names(_inspector(db_listing), "listing_op_logs")
    assert {
        "log_id",
        "task_id",
        "request_id",
        "api",
        "direction",
        "payload_digest",
        "status_code",
        "error_code",
        "platform_code",
        "evidence_json",
        "created_at",
    } <= cols


def test_listing_quota_states_primary_key_api(db_listing):
    """listing_quota_states 主键为 api。"""
    pk = set(
        _inspector(db_listing).get_pk_constraint("listing_quota_states")[
            "constrained_columns"
        ]
    )
    assert pk == {"api"}


# ---------------------------------------------------------------- 索引


def test_listing_tasks_indexes(db_listing):
    """listing_tasks 的 status / product 索引存在。"""
    indexes = _index_names(_inspector(db_listing), "listing_tasks")
    assert "idx_listing_tasks_status" in indexes
    assert "idx_listing_tasks_product" in indexes


def test_op_logs_index(db_listing):
    """listing_op_logs 的 (task_id, created_at) 索引存在。"""
    indexes = _index_names(_inspector(db_listing), "listing_op_logs")
    assert "idx_listing_oplogs_task" in indexes


# ---------------------------------------------------------------- 幂等防重复入队


def test_duplicate_create_task_raises(db_listing):
    """重复 (product_id, stage, generation_version) 入队抛 DuplicateTaskError。"""
    repo = ListingRepo(db_listing)
    repo.create_task(
        ListingTask(task_id="T-1", product_id=42, generation_version="g1")
    )
    dup = ListingTask(task_id="T-2", product_id=42, generation_version="g1")
    with pytest.raises(DuplicateTaskError):
        repo.create_task(dup)
    # 原任务仍可读（幂等防重复入队生效，不覆盖）
    assert repo.get_task("T-1") is not None
    assert repo.get_task("T-2") is None
