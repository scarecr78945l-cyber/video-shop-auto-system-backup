# -*- coding: utf-8 -*-
"""P0-2 批次 2（C2）：FeedbackService——受信边界 + 同事务审计（round-161 实现）。

依据 round-160 R160-1/2/3：

- **R160-1 单 source 贡献与证据同源**：从数据库加载 source 快照及关联实体派生八维/window/
  attribution/subject/campaign 审计目标（draft 只是待核对值，DB 为真源）；用已冻结
  `compute_contribution` 校验该 source 的数值（不只看 scale6）；typed skip/insufficient →
  零 ledger、零成功审计（非 fabricated value=0）。
- **R160-2 身份先验，重放也验**：任何 Repository 写入/查回返回前，对**每次请求（含完整重放）**
  调用 `ActorResolver.assert_can_act`（显式注入真实 UserDirectory，缺失/异常 fail-closed）；
  由 `tenant_public_id` 解析的 app tenant 必须等于 source 与 draft 的 tenant_id；actor/request
  原样贯通；user 写入要求 `required_role="operator"`；采用 service/system 可信 actor 时，Service
  **额外强制**可信 `worker_scope_tenant_public_id` 与实际 tenant UUID 值相等（非仅传参给审计）。
- **R160-3 异常后原子回滚**：要求调用方已开启外层事务，Service 不自行 commit/rollback 外层；
  在自有 `begin_nested()` savepoint 内完成校验 + ledger INSERT + created=true 的 audit INSERT；
  任何异常回滚该 savepoint；外层提交决定最终可见性。

本模块是**唯一授权写入口**；`FeedbackRepository` 为内部层，不从 `report/__init__` 导出。
"""
from __future__ import annotations

import datetime
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Dict, Optional, Union

from sqlalchemy import text
from sqlalchemy.engine import Connection

from domain.report.aggregation_manifest import CANONICAL_GRANULARITY
from domain.report.calculator import (
    InsufficientInputs,
    RoiContribution,
    SkuMarginContribution,
    ZeroSpendSkipped,
    compute_contribution,
)
from domain.report.feedback_repository import (
    FEEDBACK_TYPES,
    SKU_FEEDBACK_TYPE,
    SUBJECT_BY_FEEDBACK,
    WRITABLE_FEEDBACK_TYPES,
    FeedbackContentConflict,
    FeedbackDraft,
    FeedbackRepository,
    FeedbackValidationError,
    FeedbackWriteResult,
    _validate_draft,
)

# 注意：`domain.audit` 与 `infra.auth.actor` 存在包级循环（infra.auth.__init__ → organization →
# domain.audit），因此这里**延迟导入**，并保证先进入 `infra.auth.actor`（其 __init__ 先加载 .actor
# 再加载 .organization），避免 `domain.report` 导入期触发部分初始化模块错误。


def _actor_api():
    from infra.auth.actor import ActorResolver, canonical_uuid
    return ActorResolver, canonical_uuid


def _audit_writer():
    from domain.audit import write_audit_event
    return write_audit_event

AUDIT_ACTION = "p0_2.feedback_write"
AUDIT_TARGET_TYPE = "ad_campaign"
REQUIRED_ROLE = "operator"
TRUSTED_ACTOR_KINDS = frozenset({"service", "system"})


class FeedbackRequestError(FeedbackValidationError):
    """请求级非法（缺 actor/request/tenant、租户不一致等，零落盘）。"""


@dataclass(frozen=True)
class FeedbackSkipped:
    """typed 结果：ROI 零消耗跳过 / 输入不足——零 ledger、零成功审计。"""
    outcome: str
    reason: Optional[str] = None


@dataclass(frozen=True)
class SourceContext:
    """source 快照真源及派生的核对值。"""
    tenant_id: int
    account_id: int
    shop_id: int
    shop_listing_id: int
    shop_listing_sku_id: Optional[int]
    product_id: int
    campaign_id: int
    asset_binding_id: Optional[int]
    window_start: datetime.datetime
    window_end: datetime.datetime
    attribution_mode: str
    granularity: str
    gmv: int
    spend: int
    campaign_public_id: str
    subject_key: str
    subject_resolvable: bool


_SOURCE_SQL = text(
    "SELECT s.tenant_id, s.account_id, s.shop_id, s.shop_listing_id, s.shop_listing_sku_id, "
    "       s.product_id, s.campaign_id, s.asset_binding_id, s.window_start, s.window_end, "
    "       s.attribution_mode, s.granularity, s.gmv, s.spend, "
    "       c.public_id AS campaign_public_id, p.public_id AS product_public_id, "
    "       p.category_id AS product_category_id, sh.public_id AS shop_public_id, "
    "       a.public_id AS asset_public_id "
    "FROM app.ad_report_snapshots s "
    "JOIN app.ad_campaigns c ON c.tenant_id = s.tenant_id AND c.id = s.campaign_id "
    "JOIN app.products p ON p.tenant_id = s.tenant_id AND p.id = s.product_id "
    "JOIN app.shops sh ON sh.tenant_id = s.tenant_id AND sh.id = s.shop_id "
    "LEFT JOIN app.asset_shop_bindings asb "
    "       ON asb.tenant_id = s.tenant_id AND asb.id = s.asset_binding_id "
    "LEFT JOIN app.assets a ON a.tenant_id = asb.tenant_id AND a.id = asb.asset_id "
    "WHERE s.tenant_id = :t AND s.id = :sid")


def _subject_for_row(feedback_type: str, row: Dict[str, Any]):
    if feedback_type == "product_score":
        return row.get("product_public_id")
    if feedback_type == "category_score":
        return row.get("product_category_id")
    if feedback_type == "material_score":
        return row.get("asset_public_id")
    if feedback_type == "shop_strategy":
        return row.get("shop_public_id")
    return None


def load_source_context(conn: Connection, *, tenant_id: int, source_snapshot_id: int,
                        feedback_type: str) -> Optional[SourceContext]:
    """加载 source 快照真源 + 派生 subject / campaign 审计目标（只读）。"""
    row = conn.execute(_SOURCE_SQL, {"t": tenant_id, "sid": source_snapshot_id}).mappings().first()
    if row is None:
        return None
    data = dict(row)
    raw_subject = _subject_for_row(feedback_type, data)
    subject_key = "" if raw_subject is None else str(raw_subject)
    return SourceContext(
        tenant_id=int(data["tenant_id"]), account_id=int(data["account_id"]),
        shop_id=int(data["shop_id"]), shop_listing_id=int(data["shop_listing_id"]),
        shop_listing_sku_id=(None if data["shop_listing_sku_id"] is None
                             else int(data["shop_listing_sku_id"])),
        product_id=int(data["product_id"]), campaign_id=int(data["campaign_id"]),
        asset_binding_id=(None if data["asset_binding_id"] is None
                          else int(data["asset_binding_id"])),
        window_start=data["window_start"], window_end=data["window_end"],
        attribution_mode=str(data["attribution_mode"]), granularity=str(data["granularity"]),
        gmv=int(data["gmv"]), spend=int(data["spend"]),
        campaign_public_id=str(data["campaign_public_id"]),
        subject_key=subject_key, subject_resolvable=raw_subject is not None)


class FeedbackService:
    """唯一授权写入口：受信边界 + 单 source 校验 + 同事务审计。"""

    def __init__(self, conn: Connection, *, user_directory: Optional[Any] = None):
        self._conn = conn
        self._users = user_directory
        self._repo = FeedbackRepository(conn)

    # ---- R160-2：身份先验（每次请求，含重放） ----
    def _authorize(self, *, actor_id, tenant_public_id, request_id,
                   worker_scope_tenant_public_id):
        if not isinstance(request_id, str) or request_id == "":
            raise FeedbackRequestError("request_id 必须为非空字符串")
        if not isinstance(actor_id, str) or actor_id == "":
            raise FeedbackRequestError("actor_id 必须为非空字符串（禁止自行生成默认 actor）")
        if not isinstance(tenant_public_id, str) or tenant_public_id == "":
            raise FeedbackRequestError("tenant_public_id 必须为非空字符串")
        actor_api = _actor_api()
        resolver = actor_api[0](self._conn, user_directory=self._users)
        rec = resolver.assert_can_act(
            actor_id, tenant_public_id,
            required_role=REQUIRED_ROLE,
            worker_scope_tenant_public_id=worker_scope_tenant_public_id)
        if rec.kind in TRUSTED_ACTOR_KINDS:
            # actor.py 中 system/service 分支本身免 scope；此处额外强制可信 scope 与实际 tenant 相等
            if worker_scope_tenant_public_id is None:
                raise FeedbackRequestError(
                    f"{rec.kind} actor 必须提供可信 worker_scope（fail closed）")
            canonical_uuid = actor_api[1]
            if canonical_uuid(worker_scope_tenant_public_id) != canonical_uuid(tenant_public_id):
                raise FeedbackRequestError(
                    f"{rec.kind} actor 可信 scope 与实际 tenant 不一致")
        return rec

    def _resolve_tenant_id(self, tenant_public_id: str) -> int:
        canonical_uuid = _actor_api()[1]
        row = self._conn.execute(
            text("SELECT id FROM app.tenants WHERE public_id = :t"),
            {"t": canonical_uuid(tenant_public_id)}).first()
        if row is None:
            raise FeedbackRequestError(f"tenant_public_id 不存在: {tenant_public_id}")
        return int(row[0])

    # ---- 主入口 ----
    def write_event(
        self,
        draft: FeedbackDraft,
        *,
        actor_id: str,
        tenant_public_id: str,
        request_id: str,
        worker_scope_tenant_public_id: Optional[str] = None,
    ) -> Union[FeedbackWriteResult, FeedbackSkipped]:
        """写入单 source 贡献（append-only）+ created=true 同事务审计。"""
        _validate_draft(draft)
        if draft.feedback_type == SKU_FEEDBACK_TYPE:
            # D1 选项 B：固定关闭 gate（不接受调用方参数开启）
            return FeedbackSkipped(outcome="sku_gate_closed", reason="SKU_PUBLIC_ID_PENDING")
        if draft.feedback_type not in WRITABLE_FEEDBACK_TYPES:
            raise FeedbackValidationError(f"未授权的 feedback_type: {draft.feedback_type!r}")

        # R160-2：先身份，后任何 Repository 动作（含重放）
        self._authorize(
            actor_id=actor_id, tenant_public_id=tenant_public_id, request_id=request_id,
            worker_scope_tenant_public_id=worker_scope_tenant_public_id)

        tenant_id = self._resolve_tenant_id(tenant_public_id)
        if tenant_id != draft.tenant_id:
            raise FeedbackRequestError(
                f"tenant_public_id 解析的 tenant_id={tenant_id} 与 draft.tenant_id="
                f"{draft.tenant_id} 不一致")

        # R160-1：DB 为真源，派生八维/window/attribution/subject
        ctx = load_source_context(self._conn, tenant_id=tenant_id,
                                  source_snapshot_id=draft.source_snapshot_id,
                                  feedback_type=draft.feedback_type)
        if ctx is None or ctx.tenant_id != tenant_id:
            raise FeedbackValidationError(
                f"source_snapshot_id={draft.source_snapshot_id} 在 tenant 内不存在")

        if not ctx.subject_resolvable:
            return FeedbackSkipped(outcome="insufficient_inputs", reason="subject_unresolvable")

        expected_subject = ctx.subject_key
        # 同源比较使用同一合法化函数
        from domain.report.feedback_repository import normalize_subject_key

        if normalize_subject_key(draft.feedback_type, expected_subject) != draft.subject_key:
            raise FeedbackValidationError(
                f"subject 同源校验失败: draft.subject_key={draft.subject_key!r} 与 "
                f"source 派生={expected_subject!r} 不符")

        for name, expected in (
            ("account_id", ctx.account_id), ("shop_id", ctx.shop_id),
            ("shop_listing_id", ctx.shop_listing_id),
            ("shop_listing_sku_id", ctx.shop_listing_sku_id),
            ("product_id", ctx.product_id), ("campaign_id", ctx.campaign_id),
            ("asset_binding_id", ctx.asset_binding_id),
            ("window_start", ctx.window_start), ("window_end", ctx.window_end),
            ("attribution_mode", ctx.attribution_mode),
        ):
            if getattr(draft, name) != expected:
                raise FeedbackValidationError(
                    f"draft.{name}={getattr(draft, name)!r} 与 source 真源 {expected!r} 不符")

        # R160-1：冻结 calculator 校验/派生该 source 的数值（不自建公式）
        outcome = compute_contribution(
            draft.feedback_type, snapshot_id=draft.source_snapshot_id,
            gmv=ctx.gmv, spend=ctx.spend,
            granularity=ctx.granularity)
        if isinstance(outcome, ZeroSpendSkipped):
            return FeedbackSkipped(outcome="zero_spend_skipped", reason=outcome.reason)
        if isinstance(outcome, InsufficientInputs):
            return FeedbackSkipped(outcome="insufficient_inputs", reason=outcome.reason)
        if outcome.value != draft.value:
            raise FeedbackValidationError(
                f"value 与冻结 calculator 结果不符: draft={draft.value} expected={outcome.value}")
        if draft.extra_explanation["numerator_gmv"] != outcome.numerator_gmv:
            raise FeedbackValidationError("numerator_gmv 与 source 快照不符")
        if draft.extra_explanation["denominator_spend"] != outcome.denominator_spend:
            raise FeedbackValidationError("denominator_spend 与 source 快照不符")
        origin = draft.extra_explanation["origin_snapshot_ids"]
        if list(origin) != [draft.source_snapshot_id]:
            raise FeedbackValidationError(
                f"origin_snapshot_ids 必须恰为 [source_snapshot_id]，got {origin!r}")

        # R160-3：自有 savepoint；不提交/回滚外层事务
        with self._conn.begin_nested():
            result = self._repo.write(draft)
            if result.created:
                _audit_writer()(
                    self._conn,
                    actor_id=actor_id,
                    tenant_public_id=tenant_public_id,
                    action=AUDIT_ACTION,
                    target_type=AUDIT_TARGET_TYPE,
                    target_public_id=ctx.campaign_public_id,
                    request_id=request_id,
                    before=None,
                    after={
                        "ledger_id": result.ledger_id,
                        "source_snapshot_id": draft.source_snapshot_id,
                        "value": f"{draft.value:.6f}",
                        "aggregation_version": draft.aggregation_version,
                        "subject_key": draft.subject_key,
                    },
                    required_role=REQUIRED_ROLE,
                    worker_scope_tenant_public_id=worker_scope_tenant_public_id,
                    user_directory=self._users,
                )
        return result
