"""M2 素材库基座 · 表结构测试：7 表可建、CHECK 枚举生效、唯一约束生效。"""

import pytest
from sqlalchemy import inspect
from sqlalchemy.exc import IntegrityError

from materials import tables as T
from materials.models import iso_now

EXPECTED_TABLES = {
    "asset_items",
    "asset_download_jobs",
    "asset_sources",
    "asset_dedup_fingerprints",
    "asset_evaluations",
    "asset_compliance_checks",
    "asset_uploads",
}


def _unique_column_sets(engine, table: str) -> list[set[str]]:
    insp = inspect(engine)
    return [set(u["column_names"]) for u in insp.get_unique_constraints(table)]


# ---------------------------------------------------------------- 建表
def test_seven_tables_created(db_materials):
    insp = inspect(db_materials.engine)
    names = set(insp.get_table_names())
    assert EXPECTED_TABLES <= names


def test_asset_items_columns_and_indexes(db_materials):
    insp = inspect(db_materials.engine)
    cols = {c["name"] for c in insp.get_columns("asset_items")}
    for name in (
        "asset_type", "source_platform", "source_url", "source_author", "md5",
        "phash", "file_path", "duration", "resolution", "size", "tags_json",
        "heat_score", "evaluation", "upload_status", "platform_material_id",
        "compliance_status", "derivation_note", "created_at", "updated_at",
    ):
        assert name in cols, f"asset_items 缺列 {name}"
    idx = {i["name"] for i in insp.get_indexes("asset_items")}
    assert {
        "idx_asset_items_platform",
        "idx_asset_items_type_status",
        "idx_asset_items_evaluation",
        "idx_asset_items_compliance",
        "idx_asset_items_md5",
    } <= idx
    assert {"platform_material_id"} in _unique_column_sets(db_materials.engine, "asset_items")


def test_key_unique_constraints_exist(db_materials):
    """关键唯一约束：指纹 (type,value) 与采集源 (platform,key) 防并发重复。"""
    assert {"fingerprint_type", "fingerprint_value"} in _unique_column_sets(
        db_materials.engine, "asset_dedup_fingerprints"
    )
    assert {"source_platform", "source_key"} in _unique_column_sets(
        db_materials.engine, "asset_sources"
    )
    assert {"platform_material_id"} in _unique_column_sets(
        db_materials.engine, "asset_uploads"
    )


# ---------------------------------------------------------------- 枚举 CHECK
def _base_asset(**over):
    data = dict(
        asset_type="video",
        source_platform="视频号",
        source_url="https://example.com/v.mp4",
        source_author="达人A",
        md5="a" * 32,
        phash="0f0f0f0f0f0f0f00",
        file_path="videos/2025/v1.mp4",
        duration=15,
        resolution="720x1280",
        size=102400,
        compliance_status="passed",
    )
    data.update(over)
    return data


def test_invalid_asset_type_rejected(db_materials):
    with pytest.raises(IntegrityError):
        with db_materials.session() as s:
            s.add(T.AssetItem(**_base_asset(asset_type="audio")))


def test_invalid_upload_status_rejected(db_materials):
    with pytest.raises(IntegrityError):
        with db_materials.session() as s:
            s.add(T.AssetItem(**_base_asset(upload_status="flying")))


def test_invalid_compliance_status_rejected(db_materials):
    with pytest.raises(IntegrityError):
        with db_materials.session() as s:
            s.add(T.AssetItem(**_base_asset(compliance_status="maybe")))


def test_invalid_evaluation_rejected(db_materials):
    with pytest.raises(IntegrityError):
        with db_materials.session() as s:
            s.add(T.AssetItem(**_base_asset(evaluation="great")))


def test_evaluation_null_allowed(db_materials):
    """M2 入库时 evaluation 为 NULL（M5 回写前），CHECK 允许 NULL。"""
    with db_materials.session() as s:
        row = T.AssetItem(**_base_asset(evaluation=None))
        s.add(row)
        s.flush()
        assert row.evaluation is None


def test_invalid_download_job_status_rejected(db_materials):
    with pytest.raises(IntegrityError):
        with db_materials.session() as s:
            s.add(
                T.AssetDownloadJob(
                    source_platform="抖音",
                    source_url="https://example.com/x.mp4",
                    job_type="video",
                    status="zombie",
                )
            )


def test_invalid_upload_record_status_rejected(db_materials):
    with pytest.raises(IntegrityError):
        with db_materials.session() as s:
            s.add(T.AssetUpload(asset_id=1, status="nope"))


def test_invalid_evaluation_audit_rejected(db_materials):
    with pytest.raises(IntegrityError):
        with db_materials.session() as s:
            s.add(T.AssetEvaluation(asset_id=1, evaluation="great"))


# ---------------------------------------------------------------- 唯一约束
def _create_asset(db_materials, **over):
    with db_materials.session() as s:
        row = T.AssetItem(**_base_asset(**over))
        s.add(row)
        s.flush()
        return row.id


def test_platform_material_id_unique(db_materials):
    _create_asset(db_materials, platform_material_id="mat-1")
    with pytest.raises(IntegrityError):
        _create_asset(
            db_materials,
            md5="b" * 32,
            phash="1010101010101010",
            platform_material_id="mat-1",
        )


def test_dedup_fingerprint_unique(db_materials):
    a1 = _create_asset(db_materials)
    with db_materials.session() as s:
        s.add(
            T.AssetDedupFingerprint(
                fingerprint_type="md5",
                fingerprint_value="a" * 32,
                asset_id=a1,
            )
        )
    with pytest.raises(IntegrityError):
        with db_materials.session() as s:
            s.add(
                T.AssetDedupFingerprint(
                    fingerprint_type="md5",
                    fingerprint_value="a" * 32,
                    asset_id=a1,
                )
            )


def test_source_unique(db_materials):
    with db_materials.session() as s:
        s.add(T.AssetSource(source_platform="视频号", source_key="author-1"))
    with pytest.raises(IntegrityError):
        with db_materials.session() as s:
            s.add(T.AssetSource(source_platform="视频号", source_key="author-1"))
