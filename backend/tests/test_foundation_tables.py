"""M0 基座共享表测试：五表可建 / 列对齐最终 DDL（v0.2）/ 唯一约束 / 错误码种子。

对齐 `_management/modules/m0-foundation/database/README.md` 五表 DDL。
运行：python -m pytest tests -q --basetemp=".pytest-tmp"（P-001）
"""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import inspect

from foundation.config import FoundationConfig
from foundation.db import Database
from foundation.tables import ERROR_CODE_SEEDS, Base


@pytest.fixture()
def fdb() -> Database:
    """SQLite 内存库（StaticPool 单连接，跨 session 可见）。"""
    cfg = FoundationConfig(db_url="sqlite:///:memory:", lease_minutes=45, data_dir=Path("."))
    database = Database(cfg)
    database.create_all()
    database.seed()
    return database


EXPECTED_TABLES = {"workflow_jobs", "tasks", "logs", "app_config", "error_codes"}

# 五表时间戳字段全部 _at 后缀（REC-005）
REC005_TIMESTAMP_COLUMNS = {
    "workflow_jobs": {"retry_after", "lease_expires_at", "created_at", "updated_at"},
    "tasks": {"retry_after", "lease_expires_at", "created_at", "updated_at"},
    "logs": {"created_at"},
    "app_config": {"updated_at"},
    "error_codes": set(),
}


def test_five_tables_created(fdb: Database) -> None:
    """五表全部可建（workflow_jobs/tasks/logs/app_config/error_codes）。"""
    inspector = inspect(fdb.engine)
    actual = set(inspector.get_table_names())
    assert EXPECTED_TABLES.issubset(actual), f"缺失表: {EXPECTED_TABLES - actual}"


def test_workflow_jobs_columns_align_ddl(fdb: Database) -> None:
    """workflow_jobs 列与最终 DDL 一致：含 retry_after/evidence_json，无旧命名。"""
    inspector = inspect(fdb.engine)
    cols = {c["name"] for c in inspector.get_columns("workflow_jobs")}
    assert {"id", "product_id", "stage", "status", "error_code", "error_message",
            "retry_count", "retry_after", "lease_owner", "lease_expires_at",
            "generation_version", "payload", "evidence_json", "created_at", "updated_at"} <= cols
    assert "next_retry_at" not in cols  # 旧命名已废弃
    assert "result" not in cols  # 旧命名已废弃


def test_tasks_columns_align_ddl(fdb: Database) -> None:
    """tasks 列与最终 DDL 一致：job_id/stage/task_type/retry_after/evidence_json 等。"""
    inspector = inspect(fdb.engine)
    cols = {c["name"] for c in inspector.get_columns("tasks")}
    assert {"id", "job_id", "stage", "task_type", "status", "error_code", "error_message",
            "retry_count", "retry_after", "lease_owner", "lease_expires_at",
            "payload", "evidence_json", "created_at", "updated_at"} <= cols
    assert "result" not in cols


def test_timestamp_columns_at_suffix(fdb: Database) -> None:
    """REC-005：五表时间戳字段全部 _at 后缀（且仅这些时间列）。"""
    inspector = inspect(fdb.engine)
    for table, expected_ts in REC005_TIMESTAMP_COLUMNS.items():
        cols = {c["name"] for c in inspector.get_columns(table)}
        ts_cols = {c for c in cols if c.endswith("_at")}
        assert ts_cols == expected_ts, f"{table} 时间戳列 {ts_cols} != {expected_ts}"


def test_unique_constraints_present(fdb: Database) -> None:
    """幂等唯一约束：workflow_jobs (product_id, stage, generation_version)、tasks (job_id, task_type)。"""
    inspector = inspect(fdb.engine)
    wj_uniques = {frozenset(u["column_names"]) for u in inspector.get_unique_constraints("workflow_jobs")}
    assert frozenset({"product_id", "stage", "generation_version"}) in wj_uniques
    tk_uniques = {frozenset(u["column_names"]) for u in inspector.get_unique_constraints("tasks")}
    assert frozenset({"job_id", "task_type"}) in tk_uniques


def test_seed_error_codes_idempotent(fdb: Database) -> None:
    """错误码种子幂等：seed 两次不重复新增，条数与种子表一致。"""
    from foundation.tables import ErrorCode

    with fdb.session() as session:
        first = session.query(ErrorCode).count()
    assert first == len(ERROR_CODE_SEEDS) == 9
    added = fdb.seed()  # 二次 seed
    assert added == 0
    with fdb.session() as session:
        second = session.query(ErrorCode).count()
    assert second == first


def test_error_code_seed_values(fdb: Database) -> None:
    """关键错误码种子值：RATE_LIMIT 180s 重试、VERIFICATION_REQUIRED 人工接管、PLATFORM_REJECT 永久阻塞。"""
    from foundation.tables import ErrorCode

    with fdb.session() as session:
        rate_limit = session.get(ErrorCode, "RATE_LIMIT")
        verification = session.get(ErrorCode, "VERIFICATION_REQUIRED")
        reject = session.get(ErrorCode, "PLATFORM_REJECT")
        unexpected = session.get(ErrorCode, "UNEXPECTED")
    assert rate_limit is not None and rate_limit.retryable and rate_limit.backoff_seconds == 180
    assert verification is not None and not verification.retryable and verification.action == "manual_takeover"
    assert reject is not None and reject.action == "block_forever"
    assert unexpected is not None and unexpected.retryable and unexpected.backoff_seconds == 60


def test_create_all_idempotent(fdb: Database) -> None:
    """create_all 幂等：重复执行不报错。"""
    fdb.create_all()
    fdb.create_all()


def test_orm_metadata_has_all_tables() -> None:
    """ORM 元数据注册五表（无拼写偏差）。"""
    names = set(Base.metadata.tables.keys())
    assert EXPECTED_TABLES.issubset(names)
