# -*- coding: utf-8 -*-
"""P0-2 批次 2（C1-b/c）：有效 source 集合与 scoped 聚合（round-153 实现；round-155 R154-1~3 回修）。

依据 round-147 §2.1/§2.2 / round-148 R148-1 / round-152 §三 / round-154 R154-1~3：

- **有效 source 集合 = 各统计身份 S 的 `select_final` 输出**（已冻结选择器），
  **不是 ledger `SELECT DISTINCT source_snapshot_id`**；
- **候选来自事实快照**（ad_report_snapshots 的全部版本），不只是已产反馈的快照——
  新版 spend=0 未产 event 也淘汰旧版有效性；
- canonical-only：product/category/shop=campaign、material=campaign_asset、sku_margin=shop_listing_sku，无 fallback；
- 作用域隔离：tenant_id / feedback_type / subject_type / subject_key / window_start / window_end /
  attribution_mode / aggregation_version；
- **按 scoped event 身份去重（R154-1）**：同身份完整重放只贡献一次；同身份内容不同 → 确定性输入冲突，
  不静默求和；
- **Decimal 全部算术置于 manifest 的 prec=60/ROUND_HALF_UP 上下文（R154-2）**，含 SKU 差额，
  不受调用方 context 影响；
- **公开输入校验（R154-3）**：元素类型、正 int 标识、非负 int 金额（bool 拒绝）、时间窗口、
  五类 feedback↔subject 配对、未知 aggregation_version 拒绝；
- **PG 只读接线使用 REPEATABLE READ 单一读取基准（R154-3）** 且 `app` schema 限定；
- 本模块只输出计算结果/依据（只读），**不执行反馈 INSERT/审计写入**（C2/C3 锁定）。
"""
from __future__ import annotations

import datetime
import decimal
from dataclasses import dataclass
from decimal import Decimal
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from .aggregation_manifest import (
    AGGREGATION_VERSION,
    CANONICAL_GRANULARITY,
    CATEGORY_MIN_PRODUCTS,
    FEEDBACK_TYPES,
    MIN_SAMPLE_SNAPSHOT,
    ROI_TYPES,
    SKU_TYPES,
    STORAGE_SCALE,
)
from .calculator import _quantize6
from .selector import SnapshotCandidate, select_final_from_candidates

# 五类 feedback ↔ subject 配对（对齐 ck_feedback_subject_map）
SUBJECT_BY_FEEDBACK = {
    "product_score": "product",
    "category_score": "category",
    "material_score": "material",
    "sku_margin": "sku",
    "shop_strategy": "shop",
}
# 支持的算法版本（未知版本没有对应 manifest → 确定拒绝，不套用 aggr_v1）
SUPPORTED_AGGREGATION_VERSIONS = {AGGREGATION_VERSION}


class AggregationInputError(ValueError):
    """aggregation 输入非法（未知 feedback_type/subject 配对/金额/版本、重复身份内容冲突等）。"""


def _is_aware(dt) -> bool:
    return isinstance(dt, datetime.datetime) and dt.tzinfo is not None and dt.utcoffset() is not None


@dataclass(frozen=True)
class SourceEvent:
    """ledger 事件行（只读输入）：单 source 派生 + 作用域字段 + 事实金额。

    R154-3：构造即校验（类型/正 int 标识/非负 int 金额/aware 窗口/五类配对/已知版本）。"""
    tenant_id: int
    feedback_type: str
    subject_type: str
    subject_key: str
    window_start: datetime.datetime
    window_end: datetime.datetime
    attribution_mode: str
    aggregation_version: str
    source_snapshot_id: int
    granularity: str
    gmv: int
    spend: int

    def __post_init__(self):
        _validate_event(self)


def _validate_event(e) -> None:
    """事件不变量（R154-3 + R156-1）：公开聚合入口与构造器共用。

    **任何字段访问前**先做运行时元素类型检查：非 `SourceEvent`（含字段齐全的 duck 对象或无字段
    object）→ `AggregationInputError`，不得抛 `AttributeError`、也不得被接受。"""
    if not isinstance(e, SourceEvent):
        raise AggregationInputError(
            f"元素必须是 SourceEvent，got {type(e).__name__}")
    if type(e.tenant_id) is not int or e.tenant_id <= 0:
        raise AggregationInputError("tenant_id 必须为正 int")
    if type(e.source_snapshot_id) is not int or e.source_snapshot_id <= 0:
        raise AggregationInputError("source_snapshot_id 必须为正 int")
    if e.feedback_type not in FEEDBACK_TYPES:
        raise AggregationInputError(f"未知 feedback_type: {e.feedback_type!r}")
    if e.aggregation_version not in SUPPORTED_AGGREGATION_VERSIONS:
        raise AggregationInputError(f"未知 aggregation_version: {e.aggregation_version!r}")
    if e.subject_type != SUBJECT_BY_FEEDBACK[e.feedback_type]:
        raise AggregationInputError(
            f"feedback/subject 配对非法: {e.feedback_type} + {e.subject_type!r}")
    if not isinstance(e.subject_key, str) or not e.subject_key.strip():
        raise AggregationInputError("subject_key 必须非空 str")
    if not isinstance(e.granularity, str) or not e.granularity:
        raise AggregationInputError("granularity 必须非空 str")
    if not isinstance(e.attribution_mode, str) or not e.attribution_mode.strip():
        raise AggregationInputError("attribution_mode 必须非空 str")
    for name in ("gmv", "spend"):
        val = getattr(e, name)
        if type(val) is not int or val < 0:
            raise AggregationInputError(f"{name} 必须为非负 int（bool 拒绝），got {val!r}")
    if not _is_aware(e.window_start) or not _is_aware(e.window_end):
        raise AggregationInputError("window_start/window_end 必须 timezone-aware")
    if not (e.window_start.astimezone(datetime.timezone.utc)
            < e.window_end.astimezone(datetime.timezone.utc)):
        raise AggregationInputError("window_start 必须 < window_end")


@dataclass(frozen=True)
class SubjectAggregate:
    """一个 scoped subject 的聚合结果与依据。"""
    tenant_id: int
    feedback_type: str
    subject_type: str
    subject_key: str
    window_start: datetime.datetime
    window_end: datetime.datetime
    attribution_mode: str
    aggregation_version: str
    outcome: str                 # "roi" | "sku_margin" | "zero_spend_skipped"
    value: Optional[Decimal]
    numerator_gmv: int
    denominator_spend: int
    sample_count: int            # distinct 有效参与 source id
    source_snapshot_ids: Tuple[int, ...]   # 有效参与且已排序


@dataclass(frozen=True)
class AggregationResult:
    """聚合输出 + 依据（有效 source 集合与人工态身份）。"""
    aggregates: Tuple[SubjectAggregate, ...]
    manual_identities: Tuple[str, ...]
    effective_sources: Tuple[Tuple[str, Optional[int]], ...]


# ---------------------------------------------------------------- 有效 source 集合
def effective_source_ids(
    candidates_by_identity: Dict[str, Sequence[SnapshotCandidate]],
) -> Dict[str, Optional[int]]:
    """按 S 调用已冻结 selector；返回 identity_key -> selected_id | None(manual)。"""
    out: Dict[str, Optional[int]] = {}
    for key, candidates in candidates_by_identity.items():
        result = select_final_from_candidates(list(candidates))
        out[key] = result.snapshot_id if result.kind == "selected" else None
    return out


def _event_identity(e):
    """scoped event 身份（R154-1）：与 ledger 唯一键域一致（不含可变金额）。"""
    return (e.tenant_id, e.source_snapshot_id, e.feedback_type, e.subject_type, e.subject_key,
            e.window_start, e.window_end, e.attribution_mode, e.aggregation_version)


def _event_content(e):
    return (e.granularity, e.gmv, e.spend)


# ---------------------------------------------------------------- scoped 聚合（纯函数）
def aggregate_events(
    events: Iterable[SourceEvent],
    *,
    candidates_by_identity: Dict[str, Sequence[SnapshotCandidate]],
    feedback_type: str,
    identity_of_source: Dict[int, str],
    subject_type: Optional[str] = None,
    subject_key: Optional[str] = None,
    tenant_of_source: Optional[Dict[int, int]] = None,
) -> AggregationResult:
    """候选事实 → selector 有效集 → scoped 聚合（按事件身份去重，金额只计一次）。

    - `identity_of_source`: source_snapshot_id -> identity_key；
    - `tenant_of_source`: source_snapshot_id -> 事实所属 tenant（R154-3 伪造同源负例：
      event.tenant_id 与 source 事实 tenant 不符 → 确定性拒绝）；
    - 只有 `source_snapshot_id ∈ 有效集`、granularity == canonical、作用域匹配的 event 参与；
    - manual_required 的 S 不产出自动结果；
    - **同 scoped 身份完整重放 → 只计一次；同身份内容不同 → AggregationInputError（不静默求和）**；
    - 跨 source 聚合按分子/分母求和，禁平均 event.value。
    """
    if feedback_type not in FEEDBACK_TYPES:
        raise AggregationInputError(f"未知 feedback_type: {feedback_type!r}")
    canonical = CANONICAL_GRANULARITY[feedback_type]

    effective = effective_source_ids(candidates_by_identity)
    manual_identities = tuple(sorted(k for k, v in effective.items() if v is None))

    seen: Dict[tuple, tuple] = {}
    accepted: List[SourceEvent] = []
    for e in events:
        _validate_event(e)  # R154-3：公开入口重验（防御非构造路径）
        if e.feedback_type != feedback_type:
            continue
        if e.granularity != canonical:
            continue
        identity = identity_of_source.get(e.source_snapshot_id)
        if identity is None:
            continue
        if effective.get(identity) != e.source_snapshot_id:
            continue  # 非有效版本或 manual 身份
        if tenant_of_source is not None:
            src_tenant = tenant_of_source.get(e.source_snapshot_id)
            if src_tenant is not None and src_tenant != e.tenant_id:
                raise AggregationInputError(
                    f"event tenant={e.tenant_id} 与 source {e.source_snapshot_id} 事实 tenant="
                    f"{src_tenant} 不符（伪造同源）")
        if subject_type is not None and e.subject_type != subject_type:
            continue
        if subject_key is not None and e.subject_key != subject_key:
            continue
        # R154-1：按 scoped 身份去重；同身份内容不同 → 确定性冲突
        ident = _event_identity(e)
        content = _event_content(e)
        if ident in seen:
            if seen[ident] != content:
                raise AggregationInputError(
                    f"同一 event 身份内容冲突: {ident} {seen[ident]!r} != {content!r}")
            continue  # 完整重放：只贡献一次
        seen[ident] = content
        accepted.append(e)

    groups: Dict[tuple, dict] = {}
    for e in accepted:
        gkey = (e.tenant_id, e.feedback_type, e.subject_type, e.subject_key,
                e.window_start, e.window_end, e.attribution_mode, e.aggregation_version)
        g = groups.setdefault(gkey, {"gmv": 0, "spend": 0, "ids": set()})
        g["gmv"] += e.gmv
        g["spend"] += e.spend
        g["ids"].add(e.source_snapshot_id)

    aggregates: List[SubjectAggregate] = []
    for key in sorted(groups, key=lambda k: (k[0], k[2], k[3], str(k[4]), str(k[5]), k[6], k[7])):
        tenant_id, ft, stype, skey, ws, we, am, av = key
        g = groups[key]
        gmv, spend = g["gmv"], g["spend"]
        ids = tuple(sorted(g["ids"]))
        sample_count = len(ids)
        # R154-2：全部 Decimal 算术在 prec60/ROUND_HALF_UP 上下文内完成
        with decimal.localcontext() as ctx:
            ctx.prec = 60
            ctx.rounding = decimal.ROUND_HALF_UP
            if sample_count < MIN_SAMPLE_SNAPSHOT:
                outcome, value = "insufficient_inputs", None
            elif ft in SKU_TYPES:
                value = _quantize6(Decimal(gmv) - Decimal(spend))
                outcome = "sku_margin"
            elif spend == 0:
                value, outcome = None, "zero_spend_skipped"
            else:
                value = _quantize6(Decimal(gmv) / Decimal(spend))
                outcome = "roi"
        aggregates.append(SubjectAggregate(
            tenant_id=tenant_id, feedback_type=ft, subject_type=stype, subject_key=skey,
            window_start=ws, window_end=we, attribution_mode=am, aggregation_version=av,
            outcome=outcome, value=value, numerator_gmv=gmv, denominator_spend=spend,
            sample_count=sample_count, source_snapshot_ids=ids))

    return AggregationResult(
        aggregates=tuple(aggregates),
        manual_identities=manual_identities,
        effective_sources=tuple(sorted((k, v) for k, v in effective.items())))


# ---------------------------------------------------------------- PG 只读接线
def load_candidates_from_pg(conn, *, tenant_id: int, feedback_type: str,
                            aggregation_version: str = AGGREGATION_VERSION):
    """只读加载：以 feedback_type 的 ledger event 定位 S，再取该 S 的**全部事实快照**版本。

    返回 (candidates_by_identity, identity_of_source, tenant_of_source)。schema 显式限定 `app.`。
    """
    from sqlalchemy import text

    ev = conn.execute(text(
        "SELECT DISTINCT sn.campaign_id, sn.granularity, sn.shop_listing_sku_id, "
        "       sn.asset_binding_id, sn.window_start, sn.window_end, sn.attribution_mode "
        "FROM app.roi_feedback_events e "
        "JOIN app.ad_report_snapshots sn ON sn.id = e.source_snapshot_id "
        "WHERE e.tenant_id = :t AND e.feedback_type = :ft AND e.aggregation_version = :av"),
        {"t": tenant_id, "ft": feedback_type, "av": aggregation_version}).all()

    candidates_by_identity: Dict[str, List[SnapshotCandidate]] = {}
    identity_of_source: Dict[int, str] = {}
    tenant_of_source: Dict[int, int] = {}
    for row in ev:
        key = "|".join(str(v) for v in row)
        if key in candidates_by_identity:
            continue
        params = {"t": tenant_id, "c": row[0], "g": row[1], "sku": row[2], "ab": row[3],
                  "ws": row[4], "we": row[5], "am": row[6]}
        rows = conn.execute(text(
            "SELECT id, platform_updated_at FROM app.ad_report_snapshots "
            "WHERE tenant_id = :t AND campaign_id = :c AND granularity = :g "
            "AND shop_listing_sku_id IS NOT DISTINCT FROM :sku "
            "AND asset_binding_id IS NOT DISTINCT FROM :ab "
            "AND window_start = :ws AND window_end = :we AND attribution_mode = :am"),
            params).all()
        candidates_by_identity[key] = [
            SnapshotCandidate(snapshot_id=int(r[0]), platform_updated_at=r[1]) for r in rows]
        for r in rows:
            identity_of_source[int(r[0])] = key
            tenant_of_source[int(r[0])] = tenant_id
    return candidates_by_identity, identity_of_source, tenant_of_source


def load_source_events_from_pg(conn, *, tenant_id: int, feedback_type: str,
                               aggregation_version: str = AGGREGATION_VERSION) -> List[SourceEvent]:
    """只读加载 ledger 事件 + 其 source snapshot 事实（金额/粒度）。schema 显式限定 `app.`。"""
    from sqlalchemy import text

    rows = conn.execute(text(
        "SELECT e.tenant_id, e.feedback_type, e.subject_type, e.subject_key, "
        "       e.window_start, e.window_end, e.attribution_mode, e.aggregation_version, "
        "       e.source_snapshot_id, sn.granularity, sn.gmv, sn.spend "
        "FROM app.roi_feedback_events e "
        "JOIN app.ad_report_snapshots sn ON sn.id = e.source_snapshot_id "
        "WHERE e.tenant_id = :t AND e.feedback_type = :ft AND e.aggregation_version = :av "
        "ORDER BY e.id"),
        {"t": tenant_id, "ft": feedback_type, "av": aggregation_version}).all()
    return [SourceEvent(
        tenant_id=int(r[0]), feedback_type=str(r[1]), subject_type=str(r[2]),
        subject_key=str(r[3]), window_start=r[4], window_end=r[5],
        attribution_mode=str(r[6]), aggregation_version=str(r[7]),
        source_snapshot_id=int(r[8]), granularity=str(r[9]),
        gmv=int(r[10]), spend=int(r[11])) for r in rows]


def aggregate_from_pg(conn, *, tenant_id: int, feedback_type: str,
                      aggregation_version: str = AGGREGATION_VERSION,
                      subject_type: Optional[str] = None,
                      subject_key: Optional[str] = None) -> AggregationResult:
    """PG 只读聚合：候选事实 → selector 有效集 → scoped 聚合（无任何写入）。

    **同一读取基准（R154-3）**：在 REPEATABLE READ 事务内执行全部 SELECT，
    三条查询共享同一已提交快照；调用方须传入**未开启事务**的新连接。
    """
    c = conn.execution_options(isolation_level="REPEATABLE READ")
    with c.begin():
        candidates, identity_of_source, tenant_of_source = load_candidates_from_pg(
            c, tenant_id=tenant_id, feedback_type=feedback_type,
            aggregation_version=aggregation_version)
        events = load_source_events_from_pg(
            c, tenant_id=tenant_id, feedback_type=feedback_type,
            aggregation_version=aggregation_version)
        return aggregate_events(
            events, candidates_by_identity=candidates, feedback_type=feedback_type,
            identity_of_source=identity_of_source, subject_type=subject_type,
            subject_key=subject_key, tenant_of_source=tenant_of_source)
