"""M2 自动收集素材模块 · 数据访问层（AssetRepo）。

提供：素材入库（指纹认领防并发重复）、查询、评估回流审计、上传标记、
下载任务账本（租约领取/过期回收/完成回写）、采集源账本、合规预审记录。
所有写入幂等、失败可重试（宪法第 8 节）；错误码复用全局码表
（VERIFICATION_REQUIRED / AUTH_REQUIRED / RATE_LIMIT / TIMEOUT /
NO_MATCH / PLATFORM_REJECT / UNEXPECTED）。
"""

from __future__ import annotations

import json
from datetime import timedelta
from typing import Any, Optional

from sqlalchemy import and_, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from . import tables as T
from .db import Database
from .models import add_minutes_iso, iso_now, utcnow

# 人工接管类错误：不自动重试（P-002），任务转 blocked
MANUAL_ERROR_CODES = ("AUTH_REQUIRED", "VERIFICATION_REQUIRED")


class MaterialsRepoError(Exception):
    """素材库基座错误基类。"""


class DuplicateAssetError(MaterialsRepoError):
    """指纹认领冲突：素材已存在（重复），不入库（不静默吞）。"""

    def __init__(
        self,
        fingerprint_type: str,
        fingerprint_value: str,
        existing_asset_id: Optional[int] = None,
    ):
        self.fingerprint_type = fingerprint_type
        self.fingerprint_value = fingerprint_value
        self.existing_asset_id = existing_asset_id
        super().__init__(
            f"duplicate asset: {fingerprint_type}={fingerprint_value}"
            + (f" (existing asset_id={existing_asset_id})" if existing_asset_id else "")
        )


class AssetNotFoundError(MaterialsRepoError):
    def __init__(self, asset_id: int):
        self.asset_id = asset_id
        super().__init__(f"asset {asset_id} not found")


class DuplicateUploadError(MaterialsRepoError):
    """platform_material_id 已被其他素材占用（防重复上传回填）。"""

    def __init__(self, platform_material_id: str, owner_asset_id: int):
        self.platform_material_id = platform_material_id
        self.owner_asset_id = owner_asset_id
        super().__init__(
            f"platform_material_id {platform_material_id} already owned by asset {owner_asset_id}"
        )


class JobNotFoundError(MaterialsRepoError):
    def __init__(self, job_id: int):
        self.job_id = job_id
        super().__init__(f"download job {job_id} not found")


def _as_json(value: Any) -> str:
    """dict/list → JSON 字符串；已是字符串则原样返回（证据字段落 TEXT）。"""
    if isinstance(value, str):
        return value
    return json.dumps(value or {}, ensure_ascii=False)


class AssetRepo:
    """M2 素材库统一数据访问（供下载中台/双去重/采集器/M3/M5 复用）。"""

    def __init__(self, db: Database):
        self.db = db

    # ---------------------------------------------------------- 指纹认领
    @staticmethod
    def claim_fingerprint(
        session: Session, fingerprint_type: str, fingerprint_value: str, asset_id: int
    ) -> bool:
        """幂等认领指纹：同 (type, value) 已存在 → False（重复）并累加 hits；否则插入返回 True。

        唯一约束 (fingerprint_type, fingerprint_value) 是并发兜底：极端并发下
        INSERT 冲突抛 IntegrityError，调用方按「重复」处理（不静默吞）。
        """
        row = session.execute(
            select(T.AssetDedupFingerprint).where(
                T.AssetDedupFingerprint.fingerprint_type == fingerprint_type,
                T.AssetDedupFingerprint.fingerprint_value == fingerprint_value,
            )
        ).scalar_one_or_none()
        if row is not None:
            row.hits += 1
            return False
        session.add(
            T.AssetDedupFingerprint(
                fingerprint_type=fingerprint_type,
                fingerprint_value=fingerprint_value,
                asset_id=asset_id,
                hits=1,
                claimed_at=iso_now(),
            )
        )
        session.flush()
        return True

    def _bump_hits(self, fingerprints: list[tuple[str, str]]) -> None:
        """对已存在的指纹累加命中次数（重复留证据；只加已存在行）。"""
        with self.db.session() as s:
            for ftype, fval in fingerprints:
                row = s.execute(
                    select(T.AssetDedupFingerprint).where(
                        T.AssetDedupFingerprint.fingerprint_type == ftype,
                        T.AssetDedupFingerprint.fingerprint_value == fval,
                    )
                ).scalar_one_or_none()
                if row is not None:
                    row.hits += 1

    # ---------------------------------------------------------- 素材入库
    def create_asset(
        self,
        *,
        asset_type: str,
        source_platform: str,
        source_url: str,
        md5: str,
        phash: str,
        file_path: str,
        size: int,
        source_author: Optional[str] = None,
        duration: Optional[int] = None,
        resolution: Optional[str] = None,
        tags_json: Optional[str] = None,
        heat_score: Optional[float] = None,
        compliance_status: str = "pending",
        derivation_note: Optional[str] = None,
    ) -> int:
        """素材入库（先认领后入库）。

        认领 md5 + {asset_type}_phash 两组指纹；任一冲突 → DuplicateAssetError
        （事务整体回滚，asset 与已认领指纹不残留），冲突指纹 hits+1 留证据。
        """
        fingerprints: list[tuple[str, str]] = [
            ("md5", md5),
            (f"{asset_type}_phash", phash),
        ]
        try:
            with self.db.session() as s:
                row = T.AssetItem(
                    asset_type=asset_type,
                    source_platform=source_platform,
                    source_url=source_url,
                    source_author=source_author,
                    md5=md5,
                    phash=phash,
                    file_path=file_path,
                    duration=duration,
                    resolution=resolution,
                    size=size,
                    tags_json=tags_json,
                    heat_score=heat_score,
                    compliance_status=compliance_status,
                    derivation_note=derivation_note,
                )
                s.add(row)
                s.flush()  # 先落 asset 取 id（同一事务，失败整体回滚）
                for ftype, fval in fingerprints:
                    if not self.claim_fingerprint(s, ftype, fval, row.id):
                        existing = s.execute(
                            select(T.AssetDedupFingerprint).where(
                                T.AssetDedupFingerprint.fingerprint_type == ftype,
                                T.AssetDedupFingerprint.fingerprint_value == fval,
                            )
                        ).scalar_one_or_none()
                        raise DuplicateAssetError(
                            ftype,
                            fval,
                            existing_asset_id=existing.asset_id if existing else None,
                        )
                return row.id
        except DuplicateAssetError:
            # 事务已回滚（asset + 新指纹不残留）；补记命中次数留证据
            self._bump_hits(fingerprints)
            raise
        except IntegrityError:
            # 并发兜底：唯一约束冲突即重复（SQLite 下通常为 md5 首个冲突）
            self._bump_hits(fingerprints)
            raise DuplicateAssetError(fingerprints[0][0], fingerprints[0][1]) from None

    # ---------------------------------------------------------- 查询
    @staticmethod
    def _asset_to_dict(row: T.AssetItem) -> dict[str, Any]:
        return {c.name: getattr(row, c.name) for c in T.AssetItem.__table__.columns}

    def get_asset(self, asset_id: int) -> Optional[dict[str, Any]]:
        with self.db.session() as s:
            row = s.get(T.AssetItem, asset_id)
            if row is None:
                return None
            return self._asset_to_dict(row)

    def list_assets(
        self,
        *,
        asset_type: Optional[str] = None,
        source_platform: Optional[str] = None,
        upload_status: Optional[str] = None,
        evaluation: Optional[str] = None,
        compliance_status: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        with self.db.session() as s:
            stmt = select(T.AssetItem)
            if asset_type is not None:
                stmt = stmt.where(T.AssetItem.asset_type == asset_type)
            if source_platform is not None:
                stmt = stmt.where(T.AssetItem.source_platform == source_platform)
            if upload_status is not None:
                stmt = stmt.where(T.AssetItem.upload_status == upload_status)
            if evaluation is not None:
                stmt = stmt.where(T.AssetItem.evaluation == evaluation)
            if compliance_status is not None:
                stmt = stmt.where(T.AssetItem.compliance_status == compliance_status)
            stmt = stmt.order_by(T.AssetItem.id.desc()).limit(limit).offset(offset)
            rows = s.execute(stmt).scalars().all()
            return [self._asset_to_dict(r) for r in rows]

    # ---------------------------------------------------------- 评估回流审计
    def update_evaluation(
        self,
        asset_id: int,
        evaluation: str,
        evidence_json: Any = None,
        source_agent: str = "",
    ) -> None:
        """M5 评估标签回写：写 asset_evaluations 审计 + 更新 asset_items.evaluation。

        幂等：重复调用收敛到同一当前值，不报错；审计表为台账（每次回写留痕）。
        """
        with self.db.session() as s:
            asset = s.get(T.AssetItem, asset_id)
            if asset is None:
                raise AssetNotFoundError(asset_id)
            s.add(
                T.AssetEvaluation(
                    asset_id=asset_id,
                    evaluation=evaluation,
                    evidence_json=_as_json(evidence_json),
                    source_agent=source_agent,
                    created_at=iso_now(),
                )
            )
            asset.evaluation = evaluation

    # ---------------------------------------------------------- 上传标记
    def mark_uploaded(self, asset_id: int, platform_material_id: str) -> None:
        """M3 上传成功回填：幂等；platform_material_id 被其他素材占用 → DuplicateUploadError。"""
        with self.db.session() as s:
            asset = s.get(T.AssetItem, asset_id)
            if asset is None:
                raise AssetNotFoundError(asset_id)
            if (
                asset.platform_material_id == platform_material_id
                and asset.upload_status == "uploaded"
            ):
                return  # 幂等：同素材同 ID 重复调用直接返回
            owner = s.execute(
                select(T.AssetItem).where(
                    T.AssetItem.platform_material_id == platform_material_id
                )
            ).scalar_one_or_none()
            if owner is not None and owner.id != asset_id:
                raise DuplicateUploadError(platform_material_id, owner.id)
            asset.upload_status = "uploaded"
            asset.platform_material_id = platform_material_id
            up = s.execute(
                select(T.AssetUpload).where(
                    T.AssetUpload.platform_material_id == platform_material_id
                )
            ).scalar_one_or_none()
            if up is None:
                s.add(
                    T.AssetUpload(
                        asset_id=asset_id,
                        attempt=1,
                        status="success",
                        platform_material_id=platform_material_id,
                    )
                )
            else:
                up.status = "success"
                up.attempt += 1

    # ---------------------------------------------------------- 下载任务账本
    def record_download_job(
        self,
        *,
        source_platform: str,
        source_url: str,
        job_type: str,
        max_retries: int = 3,
        asset_id: Optional[int] = None,
    ) -> int:
        """登记下载任务（queued）。返回 job id。"""
        with self.db.session() as s:
            job = T.AssetDownloadJob(
                asset_id=asset_id,
                source_platform=source_platform,
                source_url=source_url,
                job_type=job_type,
                status="queued",
                max_retries=max_retries,
            )
            s.add(job)
            s.flush()
            return job.id

    @staticmethod
    def _job_to_dict(row: T.AssetDownloadJob) -> dict[str, Any]:
        return {c.name: getattr(row, c.name) for c in T.AssetDownloadJob.__table__.columns}

    def claim_next_download_job(
        self, worker_id: str, lease_minutes: int
    ) -> Optional[dict[str, Any]]:
        """租约领取：先回收过期租约（running 且 lease_expires_at < now → queued），
        再领取下一个可执行任务（queued，或 failed 且未超重试上限且已到 next_run_at）。

        返回任务 dict；无可用任务返回 None。SQLite 开发环境无行锁，生产切
        PostgreSQL 后可将领取改为 FOR UPDATE SKIP LOCKED（迁移脚本见 database/）。
        """
        now = iso_now()
        with self.db.session() as s:
            # 1) 回收过期租约（进程崩溃/实例掉线自愈，断点续跑）
            expired = s.execute(
                select(T.AssetDownloadJob).where(
                    T.AssetDownloadJob.status == "running",
                    T.AssetDownloadJob.lease_expires_at < now,
                )
            ).scalars().all()
            for job in expired:
                job.status = "queued"
                job.lease_owner = None
                job.lease_expires_at = None
                job.updated_at = now
            # 2) 领取下一个任务
            stmt = (
                select(T.AssetDownloadJob)
                .where(
                    or_(
                        T.AssetDownloadJob.status == "queued",
                        and_(
                            T.AssetDownloadJob.status == "failed",
                            T.AssetDownloadJob.retry_count < T.AssetDownloadJob.max_retries,
                            or_(
                                T.AssetDownloadJob.next_run_at.is_(None),
                                T.AssetDownloadJob.next_run_at <= now,
                            ),
                        ),
                    )
                )
                .order_by(T.AssetDownloadJob.id.asc())
                .limit(1)
            )
            job = s.execute(stmt).scalar_one_or_none()
            if job is None:
                return None
            job.status = "running"
            job.lease_owner = worker_id
            job.lease_expires_at = add_minutes_iso(lease_minutes)
            job.updated_at = now
            return self._job_to_dict(job)

    def _backoff_iso(self, throttle_level: int) -> str:
        base = self.db.config.download.backoff_base_seconds
        seconds = base * (2**throttle_level)
        return (utcnow() + timedelta(seconds=seconds)).isoformat(timespec="microseconds")

    def finish_download_job(
        self,
        job_id: int,
        *,
        success: bool,
        error_code: Optional[str] = None,
        error_message: Optional[str] = None,
        next_run_at: Optional[str] = None,
        throttle_level: Optional[int] = None,
        evidence_json: Any = None,
        asset_id: Optional[int] = None,
    ) -> dict[str, Any]:
        """完成回写（幂等可重试）。

        - success=True → status=success，清租约/错误，可回填 asset_id；
        - success=False → AUTH_REQUIRED/VERIFICATION_REQUIRED 转 blocked（人工接管，
          不自动重试）；其余转 failed + retry_count+1；next_run_at 未给时按
          throttle_level 退避（间隔 ×2^level）。
        """
        with self.db.session() as s:
            job = s.get(T.AssetDownloadJob, job_id)
            if job is None:
                raise JobNotFoundError(job_id)
            job.updated_at = iso_now()
            job.lease_owner = None
            job.lease_expires_at = None
            if evidence_json is not None:
                job.evidence_json = _as_json(evidence_json)
            if throttle_level is not None:
                job.throttle_level = throttle_level
            if success:
                job.status = "success"
                job.error_code = None
                job.error_message = None
                if asset_id is not None:
                    job.asset_id = asset_id
            else:
                job.error_code = error_code
                job.error_message = error_message
                if error_code in MANUAL_ERROR_CODES:
                    job.status = "blocked"  # 人工接管，不自动重试（P-002）
                else:
                    job.status = "failed"
                    job.retry_count += 1
                job.next_run_at = next_run_at or self._backoff_iso(job.throttle_level)
            return self._job_to_dict(job)

    # ---------------------------------------------------------- 采集源账本
    @staticmethod
    def _source_to_dict(row: T.AssetSource) -> dict[str, Any]:
        return {c.name: getattr(row, c.name) for c in T.AssetSource.__table__.columns}

    def get_or_create_source(
        self,
        source_platform: str,
        source_key: str,
        source_name: Optional[str] = None,
    ) -> dict[str, Any]:
        """取或建采集源（(source_platform, source_key) 唯一，幂等）。"""
        with self.db.session() as s:
            row = s.execute(
                select(T.AssetSource).where(
                    T.AssetSource.source_platform == source_platform,
                    T.AssetSource.source_key == source_key,
                )
            ).scalar_one_or_none()
            if row is None:
                row = T.AssetSource(
                    source_platform=source_platform,
                    source_key=source_key,
                    source_name=source_name,
                )
                s.add(row)
                s.flush()
            return self._source_to_dict(row)

    def update_source_ledger(
        self,
        source_platform: str,
        source_key: str,
        *,
        source_name: Optional[str] = None,
        cursor_value: Optional[str] = None,
        next_run_at: Optional[str] = None,
        completed_for_date: Optional[str] = None,
        throttle_level: Optional[int] = None,
        consecutive_failures: Optional[int] = None,
        risk_control: Optional[int] = None,
        idle_runs: Optional[int] = None,
        config_json: Any = None,
    ) -> dict[str, Any]:
        """更新源账本（游标/节流/熔断/空转；不存在则创建；只更新给定字段）。"""
        with self.db.session() as s:
            row = s.execute(
                select(T.AssetSource).where(
                    T.AssetSource.source_platform == source_platform,
                    T.AssetSource.source_key == source_key,
                )
            ).scalar_one_or_none()
            if row is None:
                row = T.AssetSource(source_platform=source_platform, source_key=source_key)
                s.add(row)
            if source_name is not None:
                row.source_name = source_name
            if cursor_value is not None:
                row.cursor_value = cursor_value
            if next_run_at is not None:
                row.next_run_at = next_run_at
            if completed_for_date is not None:
                row.completed_for_date = completed_for_date
            if throttle_level is not None:
                row.throttle_level = throttle_level
            if consecutive_failures is not None:
                row.consecutive_failures = consecutive_failures
            if risk_control is not None:
                row.risk_control = risk_control
            if idle_runs is not None:
                row.idle_runs = idle_runs
            if config_json is not None:
                row.config_json = _as_json(config_json)
            row.updated_at = iso_now()
            return self._source_to_dict(row)

    # ---------------------------------------------------------- 合规预审
    def record_compliance_check(
        self,
        asset_id: int,
        check_type: str,
        result: str,
        hit_words_json: Any = None,
        note: Optional[str] = None,
    ) -> None:
        """内容预审记录；同时同步 asset_items.compliance_status
        （result=pass → passed；result=reject → rejected；review 不动）。"""
        with self.db.session() as s:
            asset = s.get(T.AssetItem, asset_id)
            if asset is None:
                raise AssetNotFoundError(asset_id)
            s.add(
                T.AssetComplianceCheck(
                    asset_id=asset_id,
                    check_type=check_type,
                    result=result,
                    hit_words_json=_as_json(hit_words_json),
                    note=note,
                    created_at=iso_now(),
                )
            )
            if result == "pass":
                asset.compliance_status = "passed"
            elif result == "reject":
                asset.compliance_status = "rejected"

    # ---------------------------------------------------------- 拒审下架（R-M2-20）
    def mark_disabled(self, asset_id: int, reason: str) -> None:
        """平台拒审/源文件损坏 → upload_status=disabled（幂等，R-M2-20）。

        对齐 05 设计：平台判「审核不通过或源文件损坏」的素材自动下架标记，避免继续投放；
        每次标记在 asset_uploads 留一条 status=disabled 台账（evidence_json 记拒审原因，
        证据留痕）。幂等：已 disabled 的素材重复调用直接返回，不重复记台账。
        资产不存在 → AssetNotFoundError。
        """
        with self.db.session() as s:
            asset = s.get(T.AssetItem, asset_id)
            if asset is None:
                raise AssetNotFoundError(asset_id)
            if asset.upload_status == "disabled":
                return  # 幂等：已下架不再重复记台账
            asset.upload_status = "disabled"
            s.add(
                T.AssetUpload(
                    asset_id=asset_id,
                    attempt=1,
                    status="disabled",
                    evidence_json=_as_json({"reason": reason, "action": "platform_reject"}),
                )
            )
