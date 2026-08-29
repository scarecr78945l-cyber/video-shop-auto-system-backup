"""M2 素材库基座 · repo 层测试：入库认领/查询/评估回流/上传/下载租约/源账本/合规。"""

from datetime import timedelta

import pytest
from sqlalchemy import select

from materials import tables as T
from materials.models import iso_now, utcnow
from materials.repo import (
    AssetNotFoundError,
    AssetRepo,
    DuplicateAssetError,
    DuplicateUploadError,
)


def base_video(**over):
    data = dict(
        asset_type="video",
        source_platform="视频号",
        source_url="https://example.com/v.mp4",
        source_author="达人A",
        md5="a1b2c3d4e5f60718293a4b5c6d7e8f90",
        phash="0f0f0f0f0f0f0f00",
        file_path="videos/2025/v1.mp4",
        duration=15,
        resolution="720x1280",
        size=204800,
        compliance_status="passed",
    )
    data.update(over)
    return data


def base_image(**over):
    data = dict(
        asset_type="image",
        source_platform="抖音",
        source_url="https://example.com/i.jpg",
        source_author="达人B",
        md5="feedfacecafebeef0000000000000001",
        phash="1010101010101010",
        file_path="images/2025/i1.jpg",
        size=51200,
        compliance_status="pending",
    )
    data.update(over)
    return data


def make_repo(db_materials) -> AssetRepo:
    return AssetRepo(db_materials)


# ---------------------------------------------------------------- 入库与查询
def test_create_asset_video_and_image(db_materials):
    repo = make_repo(db_materials)
    vid = repo.create_asset(**base_video())
    img = repo.create_asset(**base_image())
    v = repo.get_asset(vid)
    assert v["asset_type"] == "video"
    assert v["source_platform"] == "视频号"
    assert v["duration"] == 15
    assert v["resolution"] == "720x1280"
    assert v["evaluation"] is None          # M2 入库时 evaluation 为空
    assert v["upload_status"] == "local"
    i = repo.get_asset(img)
    assert i["asset_type"] == "image"
    assert len(repo.list_assets()) == 2


def test_get_asset_missing_returns_none(db_materials):
    repo = make_repo(db_materials)
    assert repo.get_asset(12345) is None


def test_list_assets_filters(db_materials):
    repo = make_repo(db_materials)
    v1 = repo.create_asset(**base_video())
    i1 = repo.create_asset(**base_image())
    assert len(repo.list_assets(asset_type="video")) == 1
    assert len(repo.list_assets(source_platform="抖音")) == 1
    assert len(repo.list_assets(compliance_status="passed")) == 1
    repo.update_evaluation(v1, "efficient", None, "M5")
    assert len(repo.list_assets(evaluation="efficient")) == 1
    repo.mark_uploaded(v1, "mat-9")
    assert len(repo.list_assets(upload_status="uploaded")) == 1
    # limit/offset（id 倒序：i1=2, v1=1）
    assert [a["id"] for a in repo.list_assets(limit=1)] == [i1]
    assert [a["id"] for a in repo.list_assets(limit=1, offset=1)] == [v1]


# ---------------------------------------------------------------- 指纹认领
def test_duplicate_md5_raises_and_bumps_hits(db_materials):
    repo = make_repo(db_materials)
    a1 = repo.create_asset(**base_video())
    with pytest.raises(DuplicateAssetError) as ei:
        repo.create_asset(**base_video(md5="a1b2c3d4e5f60718293a4b5c6d7e8f90", phash="2020202020202020"))
    assert ei.value.fingerprint_type == "md5"
    with db_materials.session() as s:
        fp = s.execute(
            select(T.AssetDedupFingerprint).where(
                T.AssetDedupFingerprint.fingerprint_type == "md5",
                T.AssetDedupFingerprint.fingerprint_value == "a1b2c3d4e5f60718293a4b5c6d7e8f90",
            )
        ).scalar_one()
        assert fp.asset_id == a1
        assert fp.hits == 2            # 重复命中留证据
    assert len(repo.list_assets()) == 1  # 重复不入库


def test_duplicate_phash_raises(db_materials):
    repo = make_repo(db_materials)
    repo.create_asset(**base_image())
    with pytest.raises(DuplicateAssetError):
        repo.create_asset(**base_image(md5="c" * 32, file_path="images/2025/i2.jpg"))
    with db_materials.session() as s:
        fp = s.execute(
            select(T.AssetDedupFingerprint).where(
                T.AssetDedupFingerprint.fingerprint_type == "image_phash",
                T.AssetDedupFingerprint.fingerprint_value == "1010101010101010",
            )
        ).scalar_one()
        assert fp.hits == 2


def test_claim_fingerprint_primitive(db_materials):
    """公开认领原语：首次 True，重复 False（幂等）。"""
    repo = make_repo(db_materials)
    aid = repo.create_asset(**base_image())
    with db_materials.session() as s:
        assert AssetRepo.claim_fingerprint(s, "md5", "deadbeef" * 4, aid) is True
        assert AssetRepo.claim_fingerprint(s, "md5", "deadbeef" * 4, aid) is False


# ---------------------------------------------------------------- 评估回流
def test_update_evaluation_writes_audit_and_current(db_materials):
    repo = make_repo(db_materials)
    aid = repo.create_asset(**base_video())
    repo.update_evaluation(aid, "efficient", {"batch": "2025-01-01"}, "M5")
    repo.update_evaluation(aid, "potential", {"batch": "2025-01-02"}, "M5")  # 幂等不报错
    assert repo.get_asset(aid)["evaluation"] == "potential"  # 只存当前值
    with db_materials.session() as s:
        audits = s.execute(
            select(T.AssetEvaluation).where(T.AssetEvaluation.asset_id == aid)
        ).scalars().all()
        assert len(audits) == 2       # 每次回写留痕
        assert audits[0].evaluation == "efficient"
        assert audits[0].source_agent == "M5"
        assert audits[1].evaluation == "potential"
    with pytest.raises(AssetNotFoundError):
        repo.update_evaluation(99999, "efficient", None, "M5")


# ---------------------------------------------------------------- 上传标记
def test_mark_uploaded_idempotent_and_conflict(db_materials):
    repo = make_repo(db_materials)
    a1 = repo.create_asset(**base_video())
    a2 = repo.create_asset(**base_image())
    repo.mark_uploaded(a1, "mat-001")
    repo.mark_uploaded(a1, "mat-001")  # 幂等
    asset = repo.get_asset(a1)
    assert asset["upload_status"] == "uploaded"
    assert asset["platform_material_id"] == "mat-001"
    with db_materials.session() as s:
        ups = s.execute(
            select(T.AssetUpload).where(T.AssetUpload.platform_material_id == "mat-001")
        ).scalars().all()
        assert len(ups) == 1          # 幂等：不重复插入上传记录
        assert ups[0].status == "success"
        assert ups[0].asset_id == a1
    with pytest.raises(DuplicateUploadError):
        repo.mark_uploaded(a2, "mat-001")   # 该 ID 已被 a1 占用
    with pytest.raises(AssetNotFoundError):
        repo.mark_uploaded(99999, "mat-x")


# ---------------------------------------------------------------- 下载任务
def test_download_job_claim_and_lease(db_materials):
    repo = make_repo(db_materials)
    j1 = repo.record_download_job(
        source_platform="抖音", source_url="https://example.com/a.mp4", job_type="video"
    )
    j2 = repo.record_download_job(
        source_platform="快手", source_url="https://example.com/b.mp4", job_type="video"
    )
    got1 = repo.claim_next_download_job("worker-1", 45)
    assert got1["id"] == j1
    assert got1["status"] == "running"
    assert got1["lease_owner"] == "worker-1"
    assert got1["lease_expires_at"] > got1["updated_at"]   # 租约在将来
    got2 = repo.claim_next_download_job("worker-2", 45)    # 第二个任务
    assert got2["id"] == j2
    assert got2["lease_owner"] == "worker-2"
    assert repo.claim_next_download_job("worker-3", 45) is None  # 无可用任务


def test_download_job_expired_lease_recovered(db_materials):
    repo = make_repo(db_materials)
    j1 = repo.record_download_job(
        source_platform="抖音", source_url="https://example.com/a.mp4", job_type="video"
    )
    repo.claim_next_download_job("worker-1", 45)
    # 模拟实例掉线：租约已过期
    with db_materials.session() as s:
        job = s.get(T.AssetDownloadJob, j1)
        job.lease_expires_at = (utcnow() - timedelta(minutes=1)).isoformat(timespec="microseconds")
    got = repo.claim_next_download_job("worker-2", 45)
    assert got is not None
    assert got["id"] == j1
    assert got["lease_owner"] == "worker-2"   # 过期租约回收后重新领取
    assert got["status"] == "running"


def test_download_job_finish_success_backfills_asset(db_materials):
    repo = make_repo(db_materials)
    aid = repo.create_asset(**base_video())
    j1 = repo.record_download_job(
        source_platform="视频号", source_url="https://example.com/v.mp4", job_type="video"
    )
    repo.claim_next_download_job("worker-1", 45)
    out = repo.finish_download_job(j1, success=True, asset_id=aid, evidence_json={"ok": True})
    assert out["status"] == "success"
    assert out["asset_id"] == aid
    assert out["lease_owner"] is None
    assert out["error_code"] is None


def test_download_job_retry_until_max(db_materials):
    repo = make_repo(db_materials)
    j1 = repo.record_download_job(
        source_platform="抖音", source_url="https://example.com/a.mp4",
        job_type="video", max_retries=2,
    )
    past = (utcnow() - timedelta(minutes=1)).isoformat(timespec="microseconds")
    for i in range(1, 3):
        assert repo.claim_next_download_job("w", 45) is not None
        out = repo.finish_download_job(
            j1, success=False, error_code="TIMEOUT", next_run_at=past, throttle_level=i
        )
        assert out["status"] == "failed"
        assert out["retry_count"] == i
        assert out["next_run_at"] <= past
    # 已达重试上限：不再领取
    assert repo.claim_next_download_job("w", 45) is None


def test_download_job_backoff_default_computed(db_materials):
    repo = make_repo(db_materials)
    j1 = repo.record_download_job(
        source_platform="抖音", source_url="https://example.com/a.mp4", job_type="video"
    )
    repo.claim_next_download_job("w", 45)
    out = repo.finish_download_job(j1, success=False, error_code="RATE_LIMIT", throttle_level=1)
    assert out["status"] == "failed"
    assert out["next_run_at"] is not None
    assert out["next_run_at"] > iso_now()   # 30 * 2^1 = 60s 退避


def test_download_job_auth_required_blocks(db_materials):
    repo = make_repo(db_materials)
    j1 = repo.record_download_job(
        source_platform="视频号", source_url="https://example.com/v.mp4", job_type="video"
    )
    repo.claim_next_download_job("w", 45)
    out = repo.finish_download_job(j1, success=False, error_code="AUTH_REQUIRED")
    assert out["status"] == "blocked"      # 人工接管，不自动重试（P-002）
    assert out["retry_count"] == 0
    assert repo.claim_next_download_job("w", 45) is None


# ---------------------------------------------------------------- 采集源账本
def test_source_ledger_get_or_create_and_update(db_materials):
    repo = make_repo(db_materials)
    src = repo.get_or_create_source("视频号", "author-1", source_name="达人一")
    src2 = repo.get_or_create_source("视频号", "author-1")
    assert src["id"] == src2["id"]         # 幂等：同 (platform, key) 复用
    updated = repo.update_source_ledger(
        "视频号",
        "author-1",
        cursor_value="page-2",
        throttle_level=2,
        consecutive_failures=1,
        risk_control=1,
        idle_runs=3,
        completed_for_date="2025-01-01",
    )
    assert updated["cursor_value"] == "page-2"
    assert updated["throttle_level"] == 2
    assert updated["consecutive_failures"] == 1
    assert updated["risk_control"] == 1
    assert updated["idle_runs"] == 3
    assert updated["source_name"] == "达人一"    # 未给的字段不变
    again = repo.get_or_create_source("视频号", "author-1")
    assert again["cursor_value"] == "page-2"    # 账本已持久化


# ---------------------------------------------------------------- 合规预审
def test_compliance_check_syncs_status(db_materials):
    repo = make_repo(db_materials)
    aid = repo.create_asset(**base_video(compliance_status="pending"))
    repo.record_compliance_check(aid, "supply_chain_word", "pass", ["例词"], "无命中")
    assert repo.get_asset(aid)["compliance_status"] == "passed"
    repo.record_compliance_check(aid, "brand_word", "reject", ["某品牌"], "命中品牌词")
    assert repo.get_asset(aid)["compliance_status"] == "rejected"
    with db_materials.session() as s:
        checks = s.execute(
            select(T.AssetComplianceCheck).where(T.AssetComplianceCheck.asset_id == aid)
        ).scalars().all()
        assert len(checks) == 2
        assert checks[0].check_type == "supply_chain_word"
        assert checks[0].result == "pass"
        assert checks[1].result == "reject"
    with pytest.raises(AssetNotFoundError):
        repo.record_compliance_check(99999, "brand_word", "reject")


# ---------------------------------------------------------------- 相关性门（REC-迁移-03 C3）
def test_create_asset_relevance_status_default_and_custom(db_materials):
    """入库默认 relevance_status=pending；可显式传入（如断点续跑重放 M3 结果）。"""
    repo = make_repo(db_materials)
    a1 = repo.create_asset(**base_video())
    assert repo.get_asset(a1)["relevance_status"] == "pending"
    a2 = repo.create_asset(**base_image(relevance_status="passed"))
    assert repo.get_asset(a2)["relevance_status"] == "passed"


def test_update_relevance_status_idempotent_and_readable(db_materials):
    """M3 判定结果回写幂等；failed 状态可查询（不进入询价/上架链的凭据）。"""
    repo = make_repo(db_materials)
    aid = repo.create_asset(**base_video())
    repo.update_relevance_status(aid, "passed")
    assert repo.get_asset(aid)["relevance_status"] == "passed"
    repo.update_relevance_status(aid, "passed")      # 幂等：同值重复回写不报错
    repo.update_relevance_status(aid, "failed")      # M3 重新判定 → 状态更新
    assert repo.get_asset(aid)["relevance_status"] == "failed"
    assert [a["id"] for a in repo.list_assets(relevance_status="failed")] == [aid]
    assert repo.list_assets(relevance_status="passed") == []
    with pytest.raises(AssetNotFoundError):
        repo.update_relevance_status(99999, "failed")
