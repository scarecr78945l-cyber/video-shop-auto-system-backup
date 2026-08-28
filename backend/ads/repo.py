"""M5 自动小店投放（商品托管）模块数据访问层（函数式 CRUD，Session 参数）。

对齐 sourcing/repo.py 风格：全部函数式、无类封装、Session 传入。
app_config 为 M0 基座共享表，本模块只读（read_app_config，禁止 INSERT/UPDATE）。
snapshot/material 的 upsert 均幂等（按业务唯一键存在则更新）。
金额一律「分」（int）；时间 UTC 带时区。
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import func, select, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from . import tables as T
from .models import utcnow


# ---------------------------------------------------------------- 配置（app_config 只读）
def read_app_config(session: Session, key: str, default: Any = None) -> Any:
    """只读 M0 基座共享表 app_config（本模块无写权限，禁止 INSERT/UPDATE）。

    app_config 表定义在 M0/sourcing（跨模块表结构不 import，用原生 SQL 只读）；
    本模块库中该表不存在时（正常情况）返回 default，不抛错。
    """
    try:
        row = session.execute(
            text("SELECT value FROM app_config WHERE key = :key"), {"key": key}
        ).scalar_one_or_none()
    except OperationalError:
        return default  # 本模块库无 app_config 表（M0 基座表在 m1-sourcing.db）
    if row is None:
        return default
    if isinstance(row, str):
        try:
            return json.loads(row)
        except (TypeError, ValueError):
            return row
    return row


# ---------------------------------------------------------------- campaign
def create_campaign(
    session: Session,
    product_id: int,
    ad_mode: str = "goods_trust",
    target_type: str = "roi",
    target_roi: float = 2.00,
    material_ids: Optional[list] = None,
    status: str = "pending",
    diagnosis: Optional[str] = None,
    batch_id: Optional[int] = None,
) -> int:
    """新建托管投放计划（1 商品 + 1 组投放设置），返回 campaign id。"""
    row = T.AdCampaign(
        product_id=product_id,
        ad_mode=ad_mode,
        target_type=target_type,
        target_roi=target_roi,
        material_ids_json=material_ids if material_ids is not None else [],
        status=status,
        diagnosis=diagnosis,
        batch_id=batch_id,
    )
    session.add(row)
    session.flush()
    return row.id


def get_campaign(session: Session, campaign_id: int) -> Optional[T.AdCampaign]:
    return session.get(T.AdCampaign, campaign_id)


def list_campaigns(
    session: Session, status: Optional[str] = None
) -> list[T.AdCampaign]:
    stmt = select(T.AdCampaign)
    if status is not None:
        stmt = stmt.where(T.AdCampaign.status == status)
    return list(session.execute(stmt.order_by(T.AdCampaign.id)).scalars())


def update_campaign_status(session: Session, campaign_id: int, status: str) -> bool:
    row = session.get(T.AdCampaign, campaign_id)
    if row is None:
        return False
    row.status = status
    return True


def update_campaign_diagnosis(
    session: Session, campaign_id: int, diagnosis: Optional[str]
) -> bool:
    row = session.get(T.AdCampaign, campaign_id)
    if row is None:
        return False
    row.diagnosis = diagnosis
    return True


def list_active_campaigns(session: Session) -> list[T.AdCampaign]:
    """投放中（status=active）托管计划列表（S6 上限约束的清单侧）。"""
    return list(
        session.execute(
            select(T.AdCampaign)
            .where(T.AdCampaign.status == "active")
            .order_by(T.AdCampaign.id)
        ).scalars()
    )


# ---------------------------------------------------------------- run
def create_run(
    session: Session,
    campaign_id: int,
    attempt: int = 1,
    status: str = "running",
    error_code: Optional[str] = None,
    evidence: Optional[dict] = None,
    lease_owner: Optional[str] = None,
    lease_expires_at: Optional[datetime] = None,
    batch_id: Optional[int] = None,
) -> int:
    """新建一次托管执行记录，返回 run id。"""
    row = T.AdRun(
        campaign_id=campaign_id,
        attempt=attempt,
        status=status,
        error_code=error_code,
        evidence_json=evidence if evidence is not None else {},
        lease_owner=lease_owner,
        lease_expires_at=lease_expires_at,
        batch_id=batch_id,
    )
    session.add(row)
    session.flush()
    return row.id


def update_run_result(
    session: Session,
    campaign_id: int,
    attempt: int,
    status: str,
    error_code: Optional[str] = None,
    evidence: Optional[dict] = None,
) -> bool:
    """按 (campaign_id, attempt) 回写执行结果；无对应记录返回 False。"""
    row = session.execute(
        select(T.AdRun).where(
            T.AdRun.campaign_id == campaign_id, T.AdRun.attempt == attempt
        )
    ).scalar_one_or_none()
    if row is None:
        return False
    row.status = status
    if error_code is not None:
        row.error_code = error_code
    if evidence is not None:
        row.evidence_json = evidence
    return True


def count_runs(
    session: Session,
    campaign_id: Optional[int] = None,
    status: Optional[str] = None,
) -> int:
    stmt = select(func.count(T.AdRun.id))
    if campaign_id is not None:
        stmt = stmt.where(T.AdRun.campaign_id == campaign_id)
    if status is not None:
        stmt = stmt.where(T.AdRun.status == status)
    return session.execute(stmt).scalar_one()


# ---------------------------------------------------------------- snapshot
def upsert_snapshot(
    session: Session,
    campaign_id: int,
    recorded_at: datetime,
    impressions: int = 0,
    spend: int = 0,
    gmv: int = 0,
    platform_subsidy: int = 0,
    diagnosis: Optional[str] = None,
    status: Optional[str] = None,
) -> int:
    """按 (campaign_id, recorded_at) 唯一 upsert：存在则更新，幂等（同周期仅保留最新）。"""
    row = session.execute(
        select(T.AdReportSnapshot).where(
            T.AdReportSnapshot.campaign_id == campaign_id,
            T.AdReportSnapshot.recorded_at == recorded_at,
        )
    ).scalar_one_or_none()
    if row is None:
        row = T.AdReportSnapshot(
            campaign_id=campaign_id,
            recorded_at=recorded_at,
            impressions=impressions,
            spend=spend,
            gmv=gmv,
            platform_subsidy=platform_subsidy,
            diagnosis=diagnosis,
            status=status,
        )
        session.add(row)
        session.flush()
        return row.id
    row.impressions = impressions
    row.spend = spend
    row.gmv = gmv
    row.platform_subsidy = platform_subsidy
    row.diagnosis = diagnosis
    row.status = status
    return row.id


def list_snapshots(
    session: Session,
    campaign_id: Optional[int] = None,
    since: Optional[datetime] = None,
) -> list[T.AdReportSnapshot]:
    stmt = select(T.AdReportSnapshot)
    if campaign_id is not None:
        stmt = stmt.where(T.AdReportSnapshot.campaign_id == campaign_id)
    if since is not None:
        stmt = stmt.where(T.AdReportSnapshot.recorded_at >= since)
    return list(session.execute(stmt.order_by(T.AdReportSnapshot.recorded_at)).scalars())


# ---------------------------------------------------------------- account
def get_account_state(session: Session) -> Optional[T.AdAccountState]:
    """读取投放账户状态（单例语义：id 最小一行），无记录返回 None。"""
    return session.execute(
        select(T.AdAccountState).order_by(T.AdAccountState.id).limit(1)
    ).scalar_one_or_none()


def upsert_account_state(
    session: Session,
    balance: Optional[int] = None,
    status: Optional[str] = None,
    throttle_level: Optional[int] = None,
    paused_until: Optional[datetime] = None,
    pause_reason: Optional[str] = None,
) -> T.AdAccountState:
    """单例 upsert：无记录则创建，有则更新给定字段（None 字段保持不变）。"""
    row = get_account_state(session)
    if row is None:
        row = T.AdAccountState()
        session.add(row)
        session.flush()
    if balance is not None:
        row.balance = balance
    if status is not None:
        row.status = status
    if throttle_level is not None:
        row.throttle_level = throttle_level
    if paused_until is not None:
        row.paused_until = paused_until
    if pause_reason is not None:
        row.pause_reason = pause_reason
    row.updated_at = utcnow()
    return row


def bump_throttle(session: Session) -> int:
    """节流级 +1（上限 4，间隔 ×1/2/4/8/16），返回新级别。"""
    row = upsert_account_state(session)
    row.throttle_level = min(row.throttle_level + 1, 4)
    row.updated_at = utcnow()
    return row.throttle_level


def reset_throttle(session: Session) -> int:
    """节流级归零（成功探针后），返回 0。"""
    row = upsert_account_state(session)
    row.throttle_level = 0
    row.updated_at = utcnow()
    return row.throttle_level


# ---------------------------------------------------------------- material
def upsert_material(
    session: Session,
    material_id: str,
    asset_id: Optional[int] = None,
    file_path: Optional[str] = None,
    duration: Optional[float] = None,
    resolution: Optional[str] = None,
    evaluation: str = "exploring",
    upload_status: str = "reviewing",
    platform_material_id: Optional[str] = None,
) -> T.AdMaterial:
    """按 material_id 唯一 upsert：存在则更新（None 字段保持不变），幂等。"""
    row = session.execute(
        select(T.AdMaterial).where(T.AdMaterial.material_id == material_id)
    ).scalar_one_or_none()
    if row is None:
        row = T.AdMaterial(
            material_id=material_id,
            asset_id=asset_id,
            file_path=file_path,
            duration=duration,
            resolution=resolution,
            evaluation=evaluation,
            upload_status=upload_status,
            platform_material_id=platform_material_id,
        )
        session.add(row)
        session.flush()
        return row
    if asset_id is not None:
        row.asset_id = asset_id
    if file_path is not None:
        row.file_path = file_path
    if duration is not None:
        row.duration = duration
    if resolution is not None:
        row.resolution = resolution
    row.evaluation = evaluation
    row.upload_status = upload_status
    if platform_material_id is not None:
        row.platform_material_id = platform_material_id
    row.updated_at = utcnow()
    return row


def list_materials(
    session: Session, evaluation: Optional[str] = None
) -> list[T.AdMaterial]:
    stmt = select(T.AdMaterial)
    if evaluation is not None:
        stmt = stmt.where(T.AdMaterial.evaluation == evaluation)
    return list(session.execute(stmt.order_by(T.AdMaterial.id)).scalars())


# ---------------------------------------------------------------- 预算/止损辅助
def sum_spend_since(session: Session, since: datetime) -> int:
    """日总花费（分）：ad_report_snapshots.spend 按 recorded_at >= since 汇总（S7 预算硬约束）。"""
    total = session.execute(
        select(func.coalesce(func.sum(T.AdReportSnapshot.spend), 0)).where(
            T.AdReportSnapshot.recorded_at >= since
        )
    ).scalar_one()
    return int(total)


def count_active_campaigns(session: Session) -> int:
    """投放中（active）托管计划数（S6 上限约束用）。"""
    return session.execute(
        select(func.count(T.AdCampaign.id)).where(T.AdCampaign.status == "active")
    ).scalar_one()
