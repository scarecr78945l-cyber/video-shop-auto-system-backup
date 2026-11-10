# -*- coding: utf-8 -*-
"""P0-2 批次 1（B1）：report version/evidence/observation 纯函数与类型（round-133）。

依据 round-132-cdx（F132-1~F132-5）+ idempotency.md §二.8 + t3_expected.py：

- report_version_key 格式（§3.2）：
    priority: platform_version_id > platform_updated_at > raw_evidence_hash
    id key:   id:<NFC(trimmed opaque id)>
    ts key:   ts:YYYY-MM-DDTHH:MM:SS.ffffffZ
    hash key: hash:<64 lowercase hex>
  - aware datetime 先转 UTC；时间键固定 6 位微秒 + Z；相同时刻跨时区生成同一键
  - platform_updated_at 为空时进入 hash fallback；captured_at 没有任何入键路径（F132-2）
  - 最终 UTF-8 字节长度与字符长度都满足 varchar(128) 边界；超限整条拒绝，禁止截断
- 平台版本 ID = case-sensitive opaque token（F132-3）：先 Unicode NFC，再去除首尾空白，
  内部字符与大小写原样保留；空字符串视为来源缺失，转下一优先级
- hash_raw_evidence(raw: bytes) -> lower_hex_sha256（F132-4）：raw 必须非空 bytes，
  现场计算 64 位小写 SHA-256；领域层只校验 64 位小写 hex，不从已解析 row 猜回 raw
- ReportObservation：批次 1 保存平台观测值（不在本层计算 observed ROI），
  全维度仍由应用校验 + 组合 FK + trg_snapshots_dimension_consistency 共同闭合
"""
from __future__ import annotations

import hashlib
import re
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Optional

# ---------------------------------------------------------------- 冻结枚举 exact-set
# 60enum000000（round-49/51 冻结）——批次 1 只接受冻结枚举 exact-set
ENUM_SNAPSHOT_GRANULARITY = {"campaign", "shop_listing", "shop_listing_sku", "campaign_asset"}
ENUM_SNAPSHOT_DIAG = {"excellent", "good", "optimize_1", "optimize_n", "unknown"}
ENUM_SNAPSHOT_STATUS = {"active", "paused", "not_eligible", "pending", "ended", "unknown"}

_HASH_RE = re.compile(r"^[0-9a-f]{64}$")

# varchar(128) 边界（round-132 §3.2：UTF-8 字节与字符长度都 ≤ 128）
_VERSION_KEY_MAX_BYTES = 128
_VERSION_KEY_MAX_CHARS = 128


class ObservationValidationError(ValueError):
    """观测行校验失败（批次 1 本地校验异常，非冻结错误码）。"""


# ---------------------------------------------------------------- 纯函数
def _is_aware(dt: datetime) -> bool:
    """完整 aware 判定（R134-2）：tzinfo 非空且 utcoffset() 非空。

    自定义 tzinfo 若返回空 offset，astimezone 会按宿主本地时区解释——必须拒绝，
    否则同一输入在不同宿主时区生成不同版本键，破坏确定性。"""
    return isinstance(dt, datetime) and dt.tzinfo is not None and dt.utcoffset() is not None


def normalize_version_id(raw: Optional[str]) -> Optional[str]:
    """平台版本 ID 归一（F132-3 + R134-2）：None -> None；**只接受真实 str**，
    其余类型（int/bool/bytes/object）抛 ObservationValidationError——运行时不再静默 str()。
    str -> NFC + strip；空 -> None（来源缺失）。"""
    if raw is None:
        return None
    if not isinstance(raw, str):
        raise ObservationValidationError(
            f"platform_version_id 必须为 str 或 None，got {type(raw).__name__}")
    s = unicodedata.normalize("NFC", raw).strip()
    return s or None


def canonical_ts(dt: datetime) -> str:
    """aware datetime -> UTC -> 'YYYY-MM-DDTHH:MM:SS.ffffffZ'（固定 6 位微秒 + Z，F132 §3.2）。

    拒绝条件（R134-2）：naive（tzinfo is None）或 tzinfo 存在但 utcoffset() is None——
    两者都按宿主本地时区解释，破坏跨宿主确定性。"""
    if not _is_aware(dt):
        raise ObservationValidationError(
            "canonical_ts: 必须 timezone-aware（tzinfo 非空且 utcoffset() 非空）")
    u = dt.astimezone(timezone.utc)
    return u.strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def hash_raw_evidence(raw: bytes) -> str:
    """原始证据 bytes -> 64 位小写 SHA-256（F132-4）。raw 必须非空 bytes。"""
    if not isinstance(raw, bytes) or not raw:
        raise ObservationValidationError("hash_raw_evidence: raw 必须非空 bytes")
    return hashlib.sha256(raw).hexdigest()


def _check_key_length(key: str) -> None:
    """varchar(128) 边界：UTF-8 字节长度与字符长度都 ≤ 128；超限整条拒绝（禁止截断）。"""
    if len(key.encode("utf-8")) > _VERSION_KEY_MAX_BYTES or len(key) > _VERSION_KEY_MAX_CHARS:
        raise ObservationValidationError(
            f"report_version_key 超长: bytes={len(key.encode('utf-8'))} chars={len(key)}")


def build_report_version_key(
    platform_version_id: Optional[str],
    platform_updated_at: Optional[datetime],
    raw_evidence_hash: Optional[str],
) -> str:
    """report_version_key 三源生成（F132 §3.2）。

    优先级：platform_version_id > platform_updated_at > raw_evidence_hash。
    - platform_version_id：NFC + trim；空视为缺失转下一优先级（F132-3）；
    - platform_updated_at：aware -> UTC -> 6 位微秒 Z；可空（F132-1）；空转下一优先级；
    - raw_evidence_hash：必须 64 位小写 hex；空转下一优先级；
    - captured_at 没有任何入键路径（F132-2）。
    三源全缺 -> ValueError。最终键超 varchar(128) -> ValueError（整条拒绝）。
    """
    vid = normalize_version_id(platform_version_id)
    if vid is not None:
        key = "id:" + vid
        _check_key_length(key)
        return key

    if platform_updated_at is not None:
        if not isinstance(platform_updated_at, datetime):
            raise ObservationValidationError(
                f"platform_updated_at 必须为 datetime 或 None，got {type(platform_updated_at).__name__}")
        key = "ts:" + canonical_ts(platform_updated_at)
        _check_key_length(key)
        return key

    if raw_evidence_hash is not None:
        if not isinstance(raw_evidence_hash, str) or not _HASH_RE.match(raw_evidence_hash):
            raise ObservationValidationError(
                "raw_evidence_hash 必须为 64 位小写 hex")
        key = "hash:" + raw_evidence_hash
        _check_key_length(key)
        return key

    raise ObservationValidationError(
        "report_version_key 三源全缺（platform_version_id/platform_updated_at/raw_evidence_hash）")


# ---------------------------------------------------------------- ReportObservation
@dataclass(frozen=True)
class ReportObservation:
    """批次 1 观测行（平台观测值原样保存，不在本层计算 observed ROI）。

    字段与 ad_report_snapshots 可持久化事实字段对应（F132 §3.1）；raw_evidence 为原始证据 bytes
    （hash 在 Collector 写 PG 前现场计算，F132-4）。"""
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
    platform_version_id: Optional[str]
    platform_updated_at: Optional[datetime]
    captured_at: datetime
    spend: int = 0
    gmv: int = 0
    roi: Optional[Decimal] = None
    impressions: int = 0
    clicks: int = 0
    orders: int = 0
    diagnosis: str = "unknown"
    status: str = "unknown"
    raw_evidence: bytes = b""


def _check_positive_id(name: str, value: Any) -> int:
    """`type(value) is int` 且 > 0；bool 拒绝（F132 §3.1）。"""
    if type(value) is not int or value <= 0:
        raise ObservationValidationError(f"{name} 必须为正 int（bool 拒绝）")
    return value


def _check_optional_id(name: str, value: Any) -> Optional[int]:
    if value is None:
        return None
    return _check_positive_id(name, value)


def _check_nonneg_int(name: str, value: Any) -> int:
    if type(value) is not int or value < 0:
        raise ObservationValidationError(f"{name} 必须为非负 int（bool 拒绝）")
    return value


def validate_observation(obs: ReportObservation) -> ReportObservation:
    """观测行校验（F132 §3.1）：返回规范化后的不可变观测（时间统一 UTC）。

    校验点：
    - 时间：window_start/window_end/captured_at 必须 aware；platform_updated_at 可空；
      非空时间统一转 UTC；window_start < window_end；
    - ID：tenant/account/shop/shop_listing/product/campaign 必须正 int（bool 拒绝）；
      SKU/asset 可空，非空同规则；
    - 金额/计数：spend/gmv/impressions/clicks/orders 严格非负 int（bool 拒绝）；
    - roi：可空；非空必须 finite Decimal（NaN/Inf 拒绝）；
    - 枚举：granularity/diagnosis/status 只接受冻结枚举 exact-set；
    - attribution_mode 非空且长度 ≤ 64；
    - raw_evidence 非空 bytes（hash 由 Collector 现场计算）。
    """
    tenant_id = _check_positive_id("tenant_id", obs.tenant_id)
    account_id = _check_positive_id("account_id", obs.account_id)
    shop_id = _check_positive_id("shop_id", obs.shop_id)
    shop_listing_id = _check_positive_id("shop_listing_id", obs.shop_listing_id)
    shop_listing_sku_id = _check_optional_id("shop_listing_sku_id", obs.shop_listing_sku_id)
    product_id = _check_positive_id("product_id", obs.product_id)
    campaign_id = _check_positive_id("campaign_id", obs.campaign_id)
    asset_binding_id = _check_optional_id("asset_binding_id", obs.asset_binding_id)

    if obs.granularity not in ENUM_SNAPSHOT_GRANULARITY:
        raise ObservationValidationError(f"granularity 非法: {obs.granularity!r}")
    if obs.diagnosis not in ENUM_SNAPSHOT_DIAG:
        raise ObservationValidationError(f"diagnosis 非法: {obs.diagnosis!r}")
    if obs.status not in ENUM_SNAPSHOT_STATUS:
        raise ObservationValidationError(f"status 非法: {obs.status!r}")
    if not isinstance(obs.attribution_mode, str) or not obs.attribution_mode.strip() \
            or len(obs.attribution_mode) > 64:
        raise ObservationValidationError("attribution_mode 必须非空且 ≤ 64")

    for name, dt in (("window_start", obs.window_start), ("window_end", obs.window_end),
                     ("captured_at", obs.captured_at)):
        if not _is_aware(dt):
            raise ObservationValidationError(
                f"{name} 必须为 timezone-aware datetime（tzinfo 非空且 utcoffset() 非空）")
    if obs.platform_updated_at is not None and not _is_aware(obs.platform_updated_at):
        raise ObservationValidationError(
            "platform_updated_at 非空时必须 timezone-aware（tzinfo 非空且 utcoffset() 非空）")

    ws = obs.window_start.astimezone(timezone.utc)
    we = obs.window_end.astimezone(timezone.utc)
    if not (ws < we):
        raise ObservationValidationError("window_start 必须 < window_end（零/反向窗口拒绝）")
    cap = obs.captured_at.astimezone(timezone.utc)
    pua = obs.platform_updated_at.astimezone(timezone.utc) if obs.platform_updated_at is not None else None

    spend = _check_nonneg_int("spend", obs.spend)
    gmv = _check_nonneg_int("gmv", obs.gmv)
    impressions = _check_nonneg_int("impressions", obs.impressions)
    clicks = _check_nonneg_int("clicks", obs.clicks)
    orders = _check_nonneg_int("orders", obs.orders)

    roi = obs.roi
    if roi is not None:
        if not isinstance(roi, Decimal) or not roi.is_finite():
            raise ObservationValidationError("roi 非空必须为 finite Decimal")

    if not isinstance(obs.raw_evidence, bytes) or not obs.raw_evidence:
        raise ObservationValidationError("raw_evidence 必须非空 bytes")

    return ReportObservation(
        tenant_id=tenant_id, account_id=account_id, shop_id=shop_id,
        shop_listing_id=shop_listing_id, shop_listing_sku_id=shop_listing_sku_id,
        product_id=product_id, campaign_id=campaign_id, asset_binding_id=asset_binding_id,
        granularity=obs.granularity, window_start=ws, window_end=we,
        attribution_mode=obs.attribution_mode.strip(),
        platform_version_id=normalize_version_id(obs.platform_version_id),
        platform_updated_at=pua, captured_at=cap,
        spend=spend, gmv=gmv, roi=roi, impressions=impressions, clicks=clicks, orders=orders,
        diagnosis=obs.diagnosis, status=obs.status, raw_evidence=obs.raw_evidence,
    )
