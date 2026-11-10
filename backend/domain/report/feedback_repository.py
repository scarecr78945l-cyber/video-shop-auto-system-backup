# -*- coding: utf-8 -*-
"""P0-2 批次 2（C2）：FeedbackRepository——单 source 贡献 append-only 写入（round-161 实现）。

依据 round-141/142/145/147 冻结契约 + round-160 R160-1~3：

- **单快照贡献模型**：每行严格由一个 source snapshot 派生；`origin_snapshot_ids` 恰为
  `[source_snapshot_id]`，跨 source 聚合留在 C3；
- **身份**：`fb:v1:<lower_hex_sha256(canonical_join([source_snapshot_id, feedback_type,
  subject_type, subject_key, aggregation_version]))>`（内部派生，不接受调用方传入）；
- **append-only**：`INSERT ... ON CONFLICT DO NOTHING RETURNING id`；冲突后按**实际五字段自然键**
  查回 + `(tenant_id, idempotency_key)` 查回，两侧一致性 + key 现场复算 + NULL-safe 完整业务内容比较；
- **不用 NULLS NOT DISTINCT 改索引语义**（round-160 §四 勘误）：两个 UNIQUE 不含 nullable 列；
  NULL-safe 只用于完整业务内容（SKU/asset/extra_explanation）比较；
- **分层**：`FeedbackValidationError`（非法 draft，写前异常）/ `FeedbackContentConflict`（既有行内容不同）；
- **D1 选项 B**：`sku_margin` 固定关闭 gate（不接受调用方参数开启）；
- 本模块是**内部持久化层**：不写审计、不解析 actor/租户身份、不从 `report/__init__` 导出。
"""
from __future__ import annotations

import datetime
import json
import uuid
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Dict, Optional, Tuple

from sqlalchemy import text
from sqlalchemy.engine import Connection

from domain.workflow.queue import _canonical_join, _hash_key

# 五类 feedback_type；本批仅授权四类写入（D1 选项 B）
FEEDBACK_TYPES = ("product_score", "category_score", "material_score", "shop_strategy", "sku_margin")
WRITABLE_FEEDBACK_TYPES = frozenset(
    {"product_score", "category_score", "material_score", "shop_strategy"})
SKU_FEEDBACK_TYPE = "sku_margin"
SKU_GATE_MESSAGE = (
    "sku_margin 写入在当前批次固定关闭（D1 选项 B）：shop_listing_skus.public_id 稳定键迁移"
    "尚未授权，拒绝以 platform_sku_id 或数据库数字 id 替代稳定 public_id")

SUBJECT_BY_FEEDBACK = {
    "product_score": "product",
    "category_score": "category",
    "material_score": "material",
    "shop_strategy": "shop",
    "sku_margin": "sku",
}
UUID_SUBJECT_TYPES = frozenset({"product", "material", "shop", "sku"})
CATEGORY_SUBJECT_TYPE = "category"
CATEGORY_MAX_LEN = 128
UUID_SUBJECT_MAX_LEN = 36

# extra_explanation 五键 exact-set（round-160 §四）
EXTRA_EXPLANATION_KEYS = frozenset(
    {"numerator_gmv", "denominator_spend", "origin_snapshot_ids", "selector_evidence",
     "aggregation_version"})

# 自然键（与 uq1 完全一致的五字段；不含 nullable 列）
NATURAL_KEY_COLS = ("source_snapshot_id", "feedback_type", "subject_type", "subject_key",
                    "aggregation_version")

# replay 完整业务内容比较列（排除 id/created_at/idempotency_key）
REPLAY_COLS = (
    "tenant_id", "account_id", "shop_id", "shop_listing_id", "shop_listing_sku_id",
    "product_id", "campaign_id", "asset_binding_id", "source_snapshot_id",
    "window_start", "window_end", "attribution_mode", "feedback_type", "subject_type",
    "subject_key", "value", "aggregation_version", "extra_explanation",
)

_INSERT_COLS = (
    "tenant_id", "account_id", "shop_id", "shop_listing_id", "shop_listing_sku_id",
    "product_id", "campaign_id", "asset_binding_id", "source_snapshot_id",
    "window_start", "window_end", "attribution_mode", "feedback_type", "subject_type",
    "subject_key", "value", "extra_explanation", "aggregation_version", "idempotency_key",
)


class FeedbackValidationError(ValueError):
    """非法 draft / 非法请求（写前异常，零落盘）。"""


class FeedbackContentConflict(RuntimeError):
    """既有行与本次输入内容不同（本地领域冲突，旧行保持）。"""


class FeedbackInvisibleConflict(RuntimeError):
    """冲突已发生但两侧行均不可见/不可序列化——不得伪造成功，传播为可重试事务异常。"""


def _is_aware(dt) -> bool:
    return isinstance(dt, datetime.datetime) and dt.tzinfo is not None and dt.utcoffset() is not None


def _is_pos_int(v) -> bool:
    return type(v) is int and v > 0


def normalize_subject_key(feedback_type: str, raw) -> str:
    """subject_key 合法化（同一函数用于比较/落库/落键；round-160 §四）。

    - product/material/shop/sku：规范化标准 UUID 字符串（小写连字符形式）；
    - category：opaque，NFC 归一、case-sensitive、**无 trim**，受 DB 长度约束。
    """
    if feedback_type not in SUBJECT_BY_FEEDBACK:
        raise FeedbackValidationError(f"未知 feedback_type: {feedback_type!r}")
    subject_type = SUBJECT_BY_FEEDBACK[feedback_type]
    if not isinstance(raw, str) or raw == "":
        raise FeedbackValidationError(f"subject_key 必须为非空 str，got {raw!r}")
    if subject_type in UUID_SUBJECT_TYPES:
        try:
            canonical = str(uuid.UUID(raw))
        except (ValueError, AttributeError, TypeError) as exc:
            raise FeedbackValidationError(
                f"{subject_type} 的 subject_key 必须是合法 UUID，got {raw!r}") from exc
        if len(canonical) > UUID_SUBJECT_MAX_LEN:
            raise FeedbackValidationError("规范化 UUID 超长")
        return canonical
    # category：NFC、case-sensitive、不 trim
    import unicodedata

    normalized = unicodedata.normalize("NFC", raw)
    if len(normalized) > CATEGORY_MAX_LEN:
        raise FeedbackValidationError(
            f"category subject_key 超长（>{CATEGORY_MAX_LEN}）")
    return normalized


def build_feedback_idempotency_key(
    source_snapshot_id: int,
    feedback_type: str,
    subject_type: str,
    subject_key: str,
    aggregation_version: str,
) -> str:
    """`fb:v1:<hex>`（五字段固定序；复用 workflow.queue 的 canonical_join/_hash_key）。"""
    return _hash_key("fb", [source_snapshot_id, feedback_type, subject_type, subject_key,
                            aggregation_version])


def _validate_extra_explanation(extra: Any, aggregation_version: str) -> None:
    if not isinstance(extra, dict):
        raise FeedbackValidationError("extra_explanation 必须为 dict")
    if set(extra) != EXTRA_EXPLANATION_KEYS:
        raise FeedbackValidationError(
            f"extra_explanation key exact-set 不符: {sorted(extra)} != "
            f"{sorted(EXTRA_EXPLANATION_KEYS)}")
    for name in ("numerator_gmv", "denominator_spend"):
        if not _is_pos_int(extra[name]) and not (type(extra[name]) is int and extra[name] == 0):
            raise FeedbackValidationError(f"extra_explanation.{name} 必须为非负 int")
    origin = extra["origin_snapshot_ids"]
    if not isinstance(origin, list) or not origin or not all(_is_pos_int(v) for v in origin):
        raise FeedbackValidationError("extra_explanation.origin_snapshot_ids 必须为非空正 int 列表")
    if not isinstance(extra["selector_evidence"], dict):
        raise FeedbackValidationError("extra_explanation.selector_evidence 必须为 dict")
    if extra["aggregation_version"] != aggregation_version:
        raise FeedbackValidationError(
            "extra_explanation.aggregation_version 必须与 draft.aggregation_version 一致")


@dataclass(frozen=True)
class FeedbackDraft:
    """单 source 贡献 draft（字段与 `app.roi_feedback_events` 可写列一一对应）。"""
    tenant_id: int
    account_id: int
    shop_id: int
    shop_listing_id: int
    product_id: int
    campaign_id: int
    source_snapshot_id: int
    window_start: datetime.datetime
    window_end: datetime.datetime
    attribution_mode: str
    feedback_type: str
    subject_key: str
    value: Decimal
    aggregation_version: str
    extra_explanation: Dict[str, Any]
    shop_listing_sku_id: Optional[int] = None
    asset_binding_id: Optional[int] = None
    subject_type: str = field(default="")

    def __post_init__(self):
        # subject_type 由 feedback_type 派生（不接受调用方覆盖）
        object.__setattr__(self, "subject_type", SUBJECT_BY_FEEDBACK.get(self.feedback_type, ""))
        object.__setattr__(self, "subject_key",
                           normalize_subject_key(self.feedback_type, self.subject_key))
        _validate_draft(self)


def _validate_draft(d: Any) -> None:
    """draft 不变量（R160 四部门禁共用；任何字段访问前先做运行时类型检查）。"""
    if not isinstance(d, FeedbackDraft):
        raise FeedbackValidationError(f"draft 必须是 FeedbackDraft，got {type(d).__name__}")
    for name in ("tenant_id", "account_id", "shop_id", "shop_listing_id", "product_id",
                 "campaign_id", "source_snapshot_id"):
        if not _is_pos_int(getattr(d, name)):
            raise FeedbackValidationError(f"{name} 必须为正 int")
    for name in ("shop_listing_sku_id", "asset_binding_id"):
        v = getattr(d, name)
        if v is not None and not _is_pos_int(v):
            raise FeedbackValidationError(f"{name} 必须为正 int 或 None")
    if d.feedback_type not in FEEDBACK_TYPES:
        raise FeedbackValidationError(f"未知 feedback_type: {d.feedback_type!r}")
    if d.subject_type != SUBJECT_BY_FEEDBACK[d.feedback_type]:
        raise FeedbackValidationError("feedback/subject 配对非法")
    if not isinstance(d.attribution_mode, str) or not d.attribution_mode:
        raise FeedbackValidationError("attribution_mode 必须为非空 str")
    if len(d.attribution_mode) > 64:
        raise FeedbackValidationError("attribution_mode 超长（>64）")
    if not isinstance(d.aggregation_version, str) or not d.aggregation_version:
        raise FeedbackValidationError("aggregation_version 必须为非空 str")
    if not isinstance(d.value, Decimal) or not d.value.is_finite():
        raise FeedbackValidationError("value 必须为 finite Decimal")
    if d.value.as_tuple().exponent != -6:
        raise FeedbackValidationError("value 必须为 scale=6 canonical 表示")
    if not _is_aware(d.window_start) or not _is_aware(d.window_end):
        raise FeedbackValidationError("window_start/window_end 必须 timezone-aware")
    if not (d.window_start.astimezone(datetime.timezone.utc)
            < d.window_end.astimezone(datetime.timezone.utc)):
        raise FeedbackValidationError("window_start 必须 < window_end")
    _validate_extra_explanation(d.extra_explanation, d.aggregation_version)


@dataclass(frozen=True)
class FeedbackWriteResult:
    ledger_id: int
    created: bool


def _jsonb(value: Optional[dict]) -> Optional[str]:
    return None if value is None else json.dumps(value, ensure_ascii=False, sort_keys=True)


def _as_int(v) -> int:
    return int(v)


def _content_equal(draft: FeedbackDraft, row: Dict[str, Any]) -> bool:
    """NULL-safe 完整业务内容比较（round-160 §四）。"""
    for col in REPLAY_COLS:
        db_val = row.get(col)
        if col == "value":
            if db_val is None or Decimal(db_val) != draft.value:
                return False
        elif col == "extra_explanation":
            # NULL↔对象、NULL↔NULL、对象↔对象 均按 NULL-safe equality（禁止先把 NULL 补成 {}）
            if db_val is None and draft.extra_explanation is None:
                continue
            if db_val is None or draft.extra_explanation is None:
                return False
            if dict(db_val) != dict(draft.extra_explanation):
                return False
        elif col in ("feedback_type", "subject_type", "subject_key", "attribution_mode",
                     "aggregation_version"):
            if str(db_val) != str(getattr(draft, col)):
                return False
        elif col in ("window_start", "window_end"):
            if db_val != getattr(draft, col):
                return False
        else:
            if db_val != getattr(draft, col):
                return False
    return True


class FeedbackRepository:
    """内部持久化层（append-only ledger）。不作为公开业务写入口，不从 report/__init__ 导出。"""

    def __init__(self, conn: Connection):
        self._conn = conn

    def write(self, draft: FeedbackDraft) -> FeedbackWriteResult:
        _validate_draft(draft)
        if draft.feedback_type == SKU_FEEDBACK_TYPE:
            raise FeedbackValidationError(SKU_GATE_MESSAGE)
        if draft.feedback_type not in WRITABLE_FEEDBACK_TYPES:
            raise FeedbackValidationError(f"未授权的 feedback_type: {draft.feedback_type!r}")

        key = build_feedback_idempotency_key(
            draft.source_snapshot_id, draft.feedback_type, draft.subject_type,
            draft.subject_key, draft.aggregation_version)

        params = {
            "tenant_id": draft.tenant_id, "account_id": draft.account_id,
            "shop_id": draft.shop_id, "shop_listing_id": draft.shop_listing_id,
            "shop_listing_sku_id": draft.shop_listing_sku_id,
            "product_id": draft.product_id, "campaign_id": draft.campaign_id,
            "asset_binding_id": draft.asset_binding_id,
            "source_snapshot_id": draft.source_snapshot_id,
            "window_start": draft.window_start, "window_end": draft.window_end,
            "attribution_mode": draft.attribution_mode,
            "feedback_type": draft.feedback_type, "subject_type": draft.subject_type,
            "subject_key": draft.subject_key, "value": draft.value,
            "extra_explanation": _jsonb(draft.extra_explanation),
            "aggregation_version": draft.aggregation_version, "idempotency_key": key,
        }
        cols = ", ".join(_INSERT_COLS)
        binds = ", ".join(":" + c for c in _INSERT_COLS)
        inserted = self._conn.execute(text(
            f"INSERT INTO app.roi_feedback_events ({cols}) VALUES ({binds}) "
            "ON CONFLICT DO NOTHING RETURNING id"), params).first()
        if inserted is not None:
            return FeedbackWriteResult(ledger_id=_as_int(inserted[0]), created=True)
        return self._resolve_existing(draft, key)

    # ---- 冲突解析：两键分别查回 + key 复算 + NULL-safe 内容比较 ----
    def _resolve_existing(self, draft: FeedbackDraft, key: str) -> FeedbackWriteResult:
        natural = self._select_by_natural_key(draft)
        by_key = self._select_by_tenant_key(draft.tenant_id, key)

        if natural is None and by_key is None:
            # 冲突已发生但两侧行不可见/不可序列化：不得伪造成功
            raise FeedbackInvisibleConflict(
                "INSERT 冲突后既无自然键行也无 tenant+key 行（可见性/序列化异常），"
                "传播为可重试事务异常")
        if natural is None or by_key is None:
            raise FeedbackContentConflict(
                "冲突行不唯一：自然键与 (tenant_id, idempotency_key) 指向不同对象")
        if _as_int(natural["id"]) != _as_int(by_key["id"]):
            raise FeedbackContentConflict(
                f"双唯一键指向不同 ledger 行: natural_id={natural['id']} key_id={by_key['id']}")
        recomputed = build_feedback_idempotency_key(
            natural["source_snapshot_id"], str(natural["feedback_type"]),
            str(natural["subject_type"]), str(natural["subject_key"]),
            str(natural["aggregation_version"]))
        if recomputed != str(natural["idempotency_key"]):
            raise FeedbackContentConflict(
                "既有行 idempotency_key 与按自然键现场复算值不一致（数据损坏防御）")
        if not _content_equal(draft, natural):
            raise FeedbackContentConflict("既有 ledger 行与本 draft 完整业务内容不同")
        return FeedbackWriteResult(ledger_id=_as_int(natural["id"]), created=False)

    def _select_all_cols(self) -> str:
        return ", ".join(("id", "idempotency_key") + REPLAY_COLS)

    def _select_by_natural_key(self, draft: FeedbackDraft) -> Optional[Dict[str, Any]]:
        where = " AND ".join(f"{c} = :{c}" for c in NATURAL_KEY_COLS)
        row = self._conn.execute(text(
            f"SELECT {self._select_all_cols()} FROM app.roi_feedback_events WHERE {where}"),
            {"source_snapshot_id": draft.source_snapshot_id,
             "feedback_type": draft.feedback_type, "subject_type": draft.subject_type,
             "subject_key": draft.subject_key,
             "aggregation_version": draft.aggregation_version}).mappings().first()
        return dict(row) if row is not None else None

    def _select_by_tenant_key(self, tenant_id: int, key: str) -> Optional[Dict[str, Any]]:
        row = self._conn.execute(text(
            f"SELECT {self._select_all_cols()} FROM app.roi_feedback_events "
            "WHERE tenant_id = :tenant_id AND idempotency_key = :key"),
            {"tenant_id": tenant_id, "key": key}).mappings().first()
        return dict(row) if row is not None else None
