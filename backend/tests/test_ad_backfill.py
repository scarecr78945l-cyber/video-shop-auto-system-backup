"""ad_backfill 回写接入器测试（S2，M1）。

覆盖（任务书验收标准）：
- 幂等：同交换文件两次 apply_exchange → cache 行不重复（唯一键生效）、ingests 行不重复且 rows_loaded 更新；
- 覆盖：同 (category, period) 新 roi 覆盖旧值；
- 脏数据：roi≤0 / sales_amount 非 int / 条目非对象 → 该条拒绝计入 skipped（审计 partial + message）；
  schema_version≠1 / period 非法 → load_exchange 抛 AdBackfillError；
- 无文件降级：load_exchange(不存在) 返回 None，backfill 不抛异常（含未配置 ad_exchange_file）；
- 弱样本导入：sample_count=3 仍写入 cache（数据留痕，消费端过滤属 S1b 已测范围）；
- generated_at ISO 含 Z 解析为 aware datetime；
- CLI 冒烟：ad-sync --file 输出统计；缺文件/文件不可用 exit 1。
"""

import json
from datetime import datetime
from pathlib import Path

import pytest
from click.testing import CliRunner
from sqlalchemy import select

from sourcing.ad_backfill import (
    AdBackfillError,
    apply_exchange,
    backfill,
    load_exchange,
)
from sourcing.cli import cli
from sourcing.config import SourcingConfig
from sourcing.db import Database
from sourcing.models import ensure_aware
from sourcing.tables import M1AdConversionCache, M1AdConversionIngest

EMPTY_STATS = {"categories": 0, "upserted": 0, "inserted": 0, "skipped": 0, "rows_loaded": 0}


def _exchange(**overrides):
    base = {
        "schema_version": 1,
        "period": {"start": "2026-08-01", "end": "2026-08-31"},
        "generated_at": "2026-08-28T00:00:00+08:00",
        "data": {
            "收纳整理": {"roi": 3.2, "sales_amount": 12800000, "sample_count": 34},
            "宠物用品": {"roi": 2.4, "sales_amount": 8600000, "sample_count": 3},
        },
    }
    base.update(overrides)
    return base


def _write_exchange(tmp_path, data) -> Path:
    p = tmp_path / "m5-ad-conversion.json"
    p.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return p


def _cache_rows(db):
    with db.session() as session:
        return list(session.execute(select(M1AdConversionCache)).scalars())


def _ingest_rows(db):
    with db.session() as session:
        return list(session.execute(select(M1AdConversionIngest)).scalars())


# ---------------------------------------------------------------- 幂等与覆盖
def test_apply_twice_idempotent(cfg, db, tmp_path):
    """同交换文件两次导入：cache/ingests 行不重复，ingests rows_loaded 更新。"""
    path = _write_exchange(tmp_path, _exchange())
    ex = load_exchange(path)
    assert ex is not None
    s1 = apply_exchange(db, ex, str(path))
    s2 = apply_exchange(db, ex, str(path))
    assert s1 == {"categories": 2, "upserted": 0, "inserted": 2, "skipped": 0, "rows_loaded": 2}
    assert s2 == {"categories": 2, "upserted": 2, "inserted": 0, "skipped": 0, "rows_loaded": 2}
    assert len(_cache_rows(db)) == 2  # 唯一键 (category, period_start, period_end) 生效
    ingests = _ingest_rows(db)
    assert len(ingests) == 1  # 审计行不重复
    assert ingests[0].rows_loaded == 2  # rows_loaded 已更新
    assert ingests[0].status == "ok"


def test_apply_overrides_previous_roi(cfg, db, tmp_path):
    """同 (category, period) 新交换文件覆盖旧 roi/sales_amount/sample_count。"""
    path = _write_exchange(tmp_path, _exchange())
    ex = load_exchange(path)
    apply_exchange(db, ex, str(path))
    ex2 = load_exchange(
        _write_exchange(
            tmp_path,
            _exchange(data={"收纳整理": {"roi": 5.0, "sales_amount": 9990000, "sample_count": 40}}),
        )
    )
    stats = apply_exchange(db, ex2, str(path))
    assert stats["upserted"] == 1
    assert stats["inserted"] == 0
    with db.session() as session:
        row = session.execute(
            select(M1AdConversionCache).where(M1AdConversionCache.category == "收纳整理")
        ).scalar_one()
    assert row.roi == 5.0
    assert row.sales_amount == 9990000
    assert row.sample_count == 40


def test_different_period_coexists(cfg, db, tmp_path):
    """不同 period 的同类目数据可共存（唯一键按 (category, period) 而非类目）。"""
    path = _write_exchange(tmp_path, _exchange())
    ex = load_exchange(path)
    apply_exchange(db, ex, str(path))
    ex2 = load_exchange(
        _write_exchange(
            tmp_path,
            _exchange(
                period={"start": "2026-09-01", "end": "2026-09-30"},
                data={"收纳整理": {"roi": 4.0, "sales_amount": 20000000, "sample_count": 50}},
            ),
        )
    )
    stats = apply_exchange(db, ex2, str(path))
    assert stats["inserted"] == 1
    assert len(_cache_rows(db)) == 3


# ---------------------------------------------------------------- 脏数据
def test_reject_roi_non_positive_skipped(cfg, db, tmp_path):
    """roi≤0 的类目拒绝该条计入 skipped，不整体拒绝。"""
    path = _write_exchange(
        tmp_path,
        _exchange(
            data={
                "收纳整理": {"roi": 0.0, "sales_amount": 12800000, "sample_count": 34},
                "宠物用品": {"roi": -1.0, "sales_amount": 8600000, "sample_count": 21},
                "厨房用品": {"roi": 2.1, "sales_amount": 5400000, "sample_count": 12},
            }
        ),
    )
    ex = load_exchange(path)
    stats = apply_exchange(db, ex, str(path))
    assert stats["skipped"] == 2
    assert stats["rows_loaded"] == 1
    assert [r.category for r in _cache_rows(db)] == ["厨房用品"]
    ingest = _ingest_rows(db)[0]
    assert ingest.skipped == 2
    assert ingest.status == "partial"
    assert "收纳整理" in ingest.message and "宠物用品" in ingest.message


def test_reject_sales_amount_non_int_skipped(cfg, db, tmp_path):
    """sales_amount 非 int（浮点/字符串）拒绝该条计入 skipped。"""
    path = _write_exchange(
        tmp_path,
        _exchange(
            data={
                "收纳整理": {"roi": 3.2, "sales_amount": 12.5, "sample_count": 10},
                "宠物用品": {"roi": 2.4, "sales_amount": "八百万", "sample_count": 21},
                "厨房用品": {"roi": 2.1, "sales_amount": 5400000, "sample_count": 12},
            }
        ),
    )
    ex = load_exchange(path)
    stats = apply_exchange(db, ex, str(path))
    assert stats["skipped"] == 2
    assert [r.category for r in _cache_rows(db)] == ["厨房用品"]


def test_reject_non_dict_entry_skipped(cfg, db, tmp_path):
    """条目非对象（如字符串）拒绝该条计入 skipped。"""
    path = _write_exchange(
        tmp_path,
        _exchange(data={"收纳整理": "not-an-object", "宠物用品": {"roi": 2.4, "sales_amount": 8600000, "sample_count": 21}}),
    )
    ex = load_exchange(path)
    stats = apply_exchange(db, ex, str(path))
    assert stats["skipped"] == 1
    assert stats["rows_loaded"] == 1
    assert [r.category for r in _cache_rows(db)] == ["宠物用品"]


def test_reject_schema_version_raises(tmp_path):
    """schema_version≠1 → 整体拒绝（AdBackfillError）。"""
    path = _write_exchange(tmp_path, _exchange(schema_version=2))
    with pytest.raises(AdBackfillError, match="schema_version"):
        load_exchange(path)


def test_reject_missing_schema_version_raises(tmp_path):
    """缺 schema_version → AdBackfillError。"""
    data = _exchange()
    del data["schema_version"]
    path = _write_exchange(tmp_path, data)
    with pytest.raises(AdBackfillError):
        load_exchange(path)


def test_reject_bad_period_raises(tmp_path):
    """period 非 YYYY-MM-DD → AdBackfillError。"""
    path = _write_exchange(tmp_path, _exchange(period={"start": "2026/08/01", "end": "2026-08-31"}))
    with pytest.raises(AdBackfillError):
        load_exchange(path)


def test_reject_bad_generated_at_raises(tmp_path):
    """generated_at 非 ISO8601 → AdBackfillError。"""
    path = _write_exchange(tmp_path, _exchange(generated_at="上个星期"))
    with pytest.raises(AdBackfillError):
        load_exchange(path)


# ---------------------------------------------------------------- 无文件降级
def test_load_exchange_missing_file_returns_none(tmp_path):
    assert load_exchange(tmp_path / "nope.json") is None


def test_load_exchange_corrupt_json_returns_none(tmp_path):
    p = tmp_path / "bad.json"
    p.write_text("{not json", encoding="utf-8")
    assert load_exchange(p) is None


def test_backfill_missing_file_no_raise(cfg, db, tmp_path):
    stats = backfill(db, path=str(tmp_path / "nope.json"))
    assert stats == EMPTY_STATS


def test_backfill_invalid_file_no_raise(cfg, db, tmp_path):
    """校验失败的文件 → backfill 返回空统计不抛异常（优雅降级）。"""
    path = _write_exchange(tmp_path, _exchange(schema_version=9))
    assert backfill(db, path=str(path)) == EMPTY_STATS


def test_backfill_no_config_no_raise(cfg, db):
    """未配置 ad_exchange_file（默认 ""）→ 优雅跳过，不抛异常。"""
    assert backfill(db) == EMPTY_STATS


def test_backfill_uses_config_path(tmp_path):
    """backfill 缺省 path 读 config.ad_exchange_file。"""
    path = _write_exchange(tmp_path, _exchange())
    cfg = SourcingConfig(
        db_url=f"sqlite:///{tmp_path / 'cfg.db'}",
        fixtures_dir=tmp_path,
        data_dir=tmp_path / "data",
        ad_exchange_file=str(path),
    )
    database = Database(cfg)
    database.create_all()
    stats = backfill(database)
    assert stats == {"categories": 2, "upserted": 0, "inserted": 2, "skipped": 0, "rows_loaded": 2}


def test_backfill_valid_path_writes_rows(cfg, db, tmp_path):
    path = _write_exchange(tmp_path, _exchange())
    stats = backfill(db, path=str(path))
    assert stats["inserted"] == 2
    assert len(_cache_rows(db)) == 2


# ---------------------------------------------------------------- 弱样本与时间
def test_weak_sample_still_imported(cfg, db, tmp_path):
    """sample_count=3 弱样本仍写入 cache（数据留痕，消费端过滤属 S1b 范围）。"""
    path = _write_exchange(
        tmp_path,
        _exchange(data={"厨房用品": {"roi": 2.1, "sales_amount": 5400000, "sample_count": 3}}),
    )
    ex = load_exchange(path)
    stats = apply_exchange(db, ex, str(path))
    assert stats["inserted"] == 1
    assert stats["skipped"] == 0
    with db.session() as session:
        row = session.execute(
            select(M1AdConversionCache).where(M1AdConversionCache.category == "厨房用品")
        ).scalar_one()
    assert row.sample_count == 3
    assert row.roi == 2.1


def test_generated_at_z_parsed_aware_utc(cfg, db, tmp_path):
    """generated_at ISO 含 Z（UTC）解析为 aware datetime 并入库。"""
    path = _write_exchange(tmp_path, _exchange(generated_at="2026-08-28T00:00:00Z"))
    ex = load_exchange(path)
    assert isinstance(ex.generated_at, datetime)
    assert ex.generated_at.tzinfo is not None  # Z → +00:00 → aware
    assert ex.generated_at.utcoffset().total_seconds() == 0
    apply_exchange(db, ex, str(path))
    with db.session() as session:
        row = session.execute(select(M1AdConversionCache)).scalars().first()
    stored = ensure_aware(row.generated_at)  # SQLite 丢 tzinfo，读取补 UTC
    assert stored.hour == 0  # Z = UTC 0 点


def test_generated_at_plus0800_normalized_utc(cfg, db, tmp_path):
    """+08:00 时间戳归一化为 UTC（08-28 00:00+08:00 → 08-27 16:00 UTC）。"""
    path = _write_exchange(tmp_path, _exchange(generated_at="2026-08-28T00:00:00+08:00"))
    ex = load_exchange(path)
    assert ex.generated_at.utcoffset().total_seconds() == 8 * 3600
    apply_exchange(db, ex, str(path))
    with db.session() as session:
        row = session.execute(select(M1AdConversionCache)).scalars().first()
    stored = ensure_aware(row.generated_at)
    assert stored.hour == 16


# ---------------------------------------------------------------- CLI
def test_cli_ad_sync_smoke(tmp_path):
    """ad-sync --file 输出统计（类目/新增/更新/跳过）。"""
    path = _write_exchange(tmp_path, _exchange())
    runner = CliRunner()
    result = runner.invoke(
        cli,
        ["--db-url", f"sqlite:///{tmp_path / 'cli.db'}", "ad-sync", "--file", str(path)],
    )
    assert result.exit_code == 0, result.output
    assert "ad-sync 完成" in result.output
    assert "类目 2 个" in result.output
    assert "新增 2" in result.output
    assert "跳过 0" in result.output


def test_cli_ad_sync_no_file_exits_1(tmp_path):
    """无 --file 且未配置 ad_exchange_file → 清晰错误 exit 1。"""
    runner = CliRunner()
    result = runner.invoke(cli, ["--db-url", f"sqlite:///{tmp_path / 'cli.db'}", "ad-sync"])
    assert result.exit_code == 1
    assert "未指定交换文件" in result.output


def test_cli_ad_sync_missing_file_exits_1(tmp_path):
    """--file 指向不存在的文件 → 清晰错误 exit 1。"""
    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "--db-url",
            f"sqlite:///{tmp_path / 'cli.db'}",
            "ad-sync",
            "--file",
            str(tmp_path / "nope.json"),
        ],
    )
    assert result.exit_code == 1
    assert "不可用" in result.output
