# -*- coding: utf-8 -*-
"""P0-2 批次 1（B2）：append-only SnapshotRepository（round-133；round-135 R134-1 加固）。

依据 round-132-cdx（F132-4/5 + §3.3）+ round-134-cdx R134-1 + t3_expected.py：

- **单一 public 写入口 `write_observation(obs)`**：入口携带 ReportObservation（含 raw_evidence bytes），
  在受信边界完成 validate_observation + 现场 SHA-256 + version key 构造 + _SnapshotDraft 不变量重验，
  才落到 INSERT——调用方无法绕过校验任意 hash 文本（R134-1）。
- `_SnapshotDraft` 为模块内部传递结构（下划线私有，**不再从 package public export**）；
  即使保留内部 draft，Repository 在 INSERT 前仍验证全部持久化不变量（防御纵深）。
- ad_report_snapshots 只追加：新 (S,V) -> INSERT；完全重放 -> 原 id created=false；同 (S,V) 比较集不同 ->
  SnapshotContentConflict（旧行保持原值）；并发 23505 -> 精确查回比较，不做宽泛吞错。
- 统计身份 S = (campaign_id, granularity, shop_listing_sku_id, asset_binding_id,
  window_start, window_end, attribution_mode)（uq NULLS NOT DISTINCT）。
- 比较集 COMPARISON_FIELDS 排除 id/created_at/captured_at（F132-5）。
- SQL 路径无 UPDATE/DELETE；不复用 legacy SQLite (campaign_id, recorded_at) 语义。
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import text
from sqlalchemy.engine import Connection

from .version import (
    ENUM_SNAPSHOT_DIAG,
    ENUM_SNAPSHOT_GRANULARITY,
    ENUM_SNAPSHOT_STATUS,
    ObservationValidationError,
    ReportObservation,
    _is_aware,
    build_report_version_key,
    hash_raw_evidence,
    validate_observation,
)

# 统计身份列（uq 唯一键，NULLS NOT DISTINCT）
IDENTITY_COLUMNS = (
    "campaign_id", "granularity", "shop_listing_sku_id", "asset_binding_id",
    "window_start", "window_end", "attribution_mode",
)

# F132-5 比较集：业务身份 + 不可变事实字段；排除 id/created_at/captured_at
COMPARISON_FIELDS = (
    "tenant_id", "account_id", "shop_id", "shop_listing_id", "shop_listing_sku_id",
    "product_id", "campaign_id", "asset_binding_id", "granularity",
    "window_start", "window_end", "attribution_mode", "report_version_key",
    "platform_updated_at", "spend", "gmv", "roi", "impressions", "clicks", "orders",
    "diagnosis", "status", "raw_evidence_hash",
)

_HASH_RE = re.compile(r"^[0-9a-f]{64}$")


class SnapshotContentConflict(Exception):
    """同 (S,V) 但比较集字段不同：确定性冲突错误，旧行保持原值。"""


@dataclass(frozen=True)
class SnapshotWriteResult:
    snapshot_id: int
    created: bool


@dataclass(frozen=True)
class _SnapshotDraft:
    """内部传递结构（私有）：含 report_version_key 与 digest。构造后经 _validate_draft 重验。"""
    tenant_id: int
    account_id: int
    shop_id: int
    shop_listing_id: int
    shop_listing_sku_id: Optional[int]
    product_id: int
    campaign_id: int
    asset_binding_id: Optional[int]
    granularity: str
    window_start: datetime
    window_end: datetime
    attribution_mode: str
    report_version_key: str
    platform_version_id: Optional[str]
    platform_updated_at: Optional[datetime]
    captured_at: datetime
    spend: int
    gmv: int
    roi: Optional[Decimal]
    impressions: int
    clicks: int
    orders: int
    diagnosis: str
    status: str
    raw_evidence_hash: str


_INSERT_COLUMNS = (
    "tenant_id", "account_id", "shop_id", "shop_listing_id", "shop_listing_sku_id",
    "product_id", "campaign_id", "asset_binding_id", "granularity",
    "window_start", "window_end", "attribution_mode", "report_version_key",
    "platform_updated_at", "captured_at", "spend", "gmv", "roi", "impressions",
    "clicks", "orders", "diagnosis", "status", "raw_evidence_hash",
)


def _draft_values(draft: _SnapshotDraft) -> dict:
    return {
        "tenant_id": draft.tenant_id,
        "account_id": draft.account_id,
        "shop_id": draft.shop_id,
        "shop_listing_id": draft.shop_listing_id,
        "shop_listing_sku_id": draft.shop_listing_sku_id,
        "product_id": draft.product_id,
        "campaign_id": draft.campaign_id,
        "asset_binding_id": draft.asset_binding_id,
        "granularity": draft.granularity,
        "window_start": draft.window_start,
        "window_end": draft.window_end,
        "attribution_mode": draft.attribution_mode,
        "report_version_key": draft.report_version_key,
        "platform_updated_at": draft.platform_updated_at,
        "captured_at": draft.captured_at,
        "spend": draft.spend,
        "gmv": draft.gmv,
        "roi": draft.roi,
        "impressions": draft.impressions,
        "clicks": draft.clicks,
        "orders": draft.orders,
        "diagnosis": draft.diagnosis,
        "status": draft.status,
        "raw_evidence_hash": draft.raw_evidence_hash,
    }


class SnapshotRepository:
    """append-only 快照仓库；唯一 public 写入口 = write_observation(obs)。"""

    def __init__(self, conn: Connection):
        self._conn = conn

    # ------------------------------------------------------------ 内部 SQL
    _INSERT_SQL = (
        "INSERT INTO app.ad_report_snapshots ({cols}) VALUES ({ph}) "
        "ON CONFLICT (campaign_id, granularity, shop_listing_sku_id, asset_binding_id, "
        "window_start, window_end, attribution_mode, report_version_key) "
        "DO NOTHING RETURNING id"
    ).format(cols=", ".join(_INSERT_COLUMNS), ph=", ".join(":" + c for c in _INSERT_COLUMNS))

    _SELECT_BY_IDENTITY_SQL = (
        "SELECT {cmp} FROM app.ad_report_snapshots "
        "WHERE campaign_id = :campaign_id "
        "AND granularity = :granularity "
        "AND shop_listing_sku_id IS NOT DISTINCT FROM :shop_listing_sku_id "
        "AND asset_binding_id IS NOT DISTINCT FROM :asset_binding_id "
        "AND window_start = :window_start "
        "AND window_end = :window_end "
        "AND attribution_mode = :attribution_mode "
        "AND report_version_key = :report_version_key "
        "ORDER BY id LIMIT 1"
    ).format(cmp=", ".join(["id"] + list(COMPARISON_FIELDS)))

    # ------------------------------------------------------------ 唯一 public 写入口
    def write_observation(self, obs: ReportObservation) -> SnapshotWriteResult:
        """唯一 public 写入口：受信边界内 validate + 现场 hash + version key + draft 重验。

        R134-1：调用方只能传 ReportObservation（含 raw bytes），无法绕过校验任意 hash 文本；
        digest 由 raw_evidence 现场计算，version key 由三源构造，全部不变量在 INSERT 前重验。"""
        v = validate_observation(obs)  # 1) 观测校验（含类型/aware 判定）
        evidence_hash = hash_raw_evidence(v.raw_evidence)  # 2) 现场 SHA-256（F132-4）
        version_key = build_report_version_key(  # 3) 三源 version key
            v.platform_version_id, v.platform_updated_at, evidence_hash)
        draft = _SnapshotDraft(
            tenant_id=v.tenant_id, account_id=v.account_id, shop_id=v.shop_id,
            shop_listing_id=v.shop_listing_id, shop_listing_sku_id=v.shop_listing_sku_id,
            product_id=v.product_id, campaign_id=v.campaign_id,
            asset_binding_id=v.asset_binding_id, granularity=v.granularity,
            window_start=v.window_start, window_end=v.window_end,
            attribution_mode=v.attribution_mode, report_version_key=version_key,
            platform_version_id=v.platform_version_id,
            platform_updated_at=v.platform_updated_at, captured_at=v.captured_at,
            spend=v.spend, gmv=v.gmv, roi=v.roi, impressions=v.impressions,
            clicks=v.clicks, orders=v.orders, diagnosis=v.diagnosis, status=v.status,
            raw_evidence_hash=evidence_hash,
        )
        self._validate_draft(draft)  # 4) 受信边界重验（防御纵深，防绕过）
        return self._insert_or_select(draft)

    # ------------------------------------------------------------ 受信边界重验（R134-1）
    def _validate_draft(self, draft: _SnapshotDraft) -> None:
        """INSERT 前重验全部持久化不变量（防内部 draft 绕过/伪造 digest/错误 version key）。"""
        for name in ("tenant_id", "account_id", "shop_id", "shop_listing_id",
                     "product_id", "campaign_id"):
            if type(getattr(draft, name)) is not int or getattr(draft, name) <= 0:
                raise ObservationValidationError(f"_validate_draft: {name} 必须为正 int")
        for name in ("shop_listing_sku_id", "asset_binding_id"):
            val = getattr(draft, name)
            if val is not None and (type(val) is not int or val <= 0):
                raise ObservationValidationError(f"_validate_draft: {name} 可空且非空时正 int")
        for name in ("spend", "gmv", "impressions", "clicks", "orders"):
            if type(getattr(draft, name)) is not int or getattr(draft, name) < 0:
                raise ObservationValidationError(f"_validate_draft: {name} 必须非负 int")
        if draft.granularity not in ENUM_SNAPSHOT_GRANULARITY:
            raise ObservationValidationError(f"_validate_draft: granularity 非法 {draft.granularity!r}")
        if draft.diagnosis not in ENUM_SNAPSHOT_DIAG:
            raise ObservationValidationError(f"_validate_draft: diagnosis 非法 {draft.diagnosis!r}")
        if draft.status not in ENUM_SNAPSHOT_STATUS:
            raise ObservationValidationError(f"_validate_draft: status 非法 {draft.status!r}")
        if not isinstance(draft.attribution_mode, str) or not draft.attribution_mode.strip() \
                or len(draft.attribution_mode) > 64:
            raise ObservationValidationError("_validate_draft: attribution_mode 非空且 ≤64")
        for name in ("window_start", "window_end", "captured_at"):
            if not _is_aware(getattr(draft, name)):
                raise ObservationValidationError(f"_validate_draft: {name} 必须 aware")
        if draft.platform_updated_at is not None and not _is_aware(draft.platform_updated_at):
            raise ObservationValidationError("_validate_draft: platform_updated_at 必须 aware")
        if not (draft.window_start < draft.window_end):
            raise ObservationValidationError("_validate_draft: window_start < window_end")
        if draft.roi is not None and (not isinstance(draft.roi, Decimal) or not draft.roi.is_finite()):
            raise ObservationValidationError("_validate_draft: roi 必须 finite Decimal")
        if not isinstance(draft.raw_evidence_hash, str) or not _HASH_RE.match(draft.raw_evidence_hash):
            raise ObservationValidationError(
                f"_validate_draft: raw_evidence_hash 必须 64 位小写 hex，got {draft.raw_evidence_hash!r}")
        # version key 一致性：必须能由 draft 自身三源重算（防伪造 digest/错误 version key 绕过）
        expected_key = build_report_version_key(
            draft.platform_version_id, draft.platform_updated_at, draft.raw_evidence_hash)
        if draft.report_version_key != expected_key:
            raise ObservationValidationError(
                f"_validate_draft: report_version_key 与三源不一致 got={draft.report_version_key!r} "
                f"expected={expected_key!r}")
        if len(draft.report_version_key.encode("utf-8")) > 128 or len(draft.report_version_key) > 128:
            raise ObservationValidationError("_validate_draft: report_version_key 超长")
        # 平台版本 ID 类型（防御纵深）
        if draft.platform_version_id is not None and not isinstance(draft.platform_version_id, str):
            raise ObservationValidationError(
                f"_validate_draft: platform_version_id 必须 str 或 None")

    # ------------------------------------------------------------ insert-or-select
    def _insert_or_select(self, draft: _SnapshotDraft) -> SnapshotWriteResult:
        """insert-or-select；返回 (snapshot_id, created)。无 UPDATE/DELETE。"""
        vals = _draft_values(draft)
        row = self._conn.execute(text(self._INSERT_SQL), vals).first()
        if row is not None:
            return SnapshotWriteResult(snapshot_id=int(row[0]), created=True)

        # 冲突（含并发 23505 后查回）：精确查回并比较完整逻辑身份与内容
        existing = self._conn.execute(text(self._SELECT_BY_IDENTITY_SQL), vals).first()
        if existing is None:
            raise SnapshotContentConflict(
                "insert-or-select 查回失败：同 (S,V) 无既有行")
        snap_id = int(existing[0])
        for i, field in enumerate(COMPARISON_FIELDS):
            got = existing[i + 1]
            want = vals[field]
            # 统一类型比较（numeric<->Decimal、datetime 规范化、None 原样）
            if got is None or want is None:
                same = (got is None) and (want is None)
            elif isinstance(want, Decimal):
                if isinstance(got, str):
                    got_d = Decimal(got)
                elif isinstance(got, (int, float)):
                    got_d = Decimal(str(got))
                else:
                    got_d = got
                same = got_d == want
            else:
                same = got == want
            if not same:
                raise SnapshotContentConflict(
                    f"同 (S,V) 比较字段冲突: {field} 既有={got!r} 新={want!r}；旧行保持原值")
        return SnapshotWriteResult(snapshot_id=snap_id, created=False)
