"""M3 A/B 闭环 · M5 投放快照摄取适配器（v1.1 联调契约消费入口）。

跨模块数据联动（宪法第 5 节 / data-audit 登记）：M5 投放报表回读
（ad_report_snapshots）经总控协调以 JSON 载体回写本模块（规划载体
``_management/data-exchange/m5-to-m3-evaluation.json``），本模块以
``ingest_m5_record`` / ``ingest_m5_batch`` 消费，把投放效果换算后落
``opt_evaluation_feedback``，驱动评估标签（高效/潜力/探索期）与模板重训练。

契约字段（对齐 M5 context 数据字典与 DA-001 口径）：
- ``platform_material_id``：小店素材库素材 ID（= 本模块 opt_video_variants.platform_material_id），回写主键；
- ``report_date``：UTC 日期 YYYY-MM-DD（幂等键 (variant_id, report_date)）；
- ``impressions``：曝光（int）；
- ``clicks``：点击（可选，M5 快照暂缺省 0 → CTR 分量按 0，评分由 ROI/诊断主导）；
- ``spend_cents`` / ``gmv_cents``：金额「分」int（DA-001）→ 元 = /100；
- ``orders``：成交单数（可选，缺省 0）；
- ``diagnosis``：M5 中文枚举（优秀/良好/1项待优化/N项待优化）→ ab.scoring 兼容。

换算规则：``spend_yuan = spend_cents / 100``；``roi = gmv_cents / spend_cents``
（spend>0，否则 0）。platform_material_id 反查不到本地版本 → 不落库，
返回 unmatched（失败隔离，不阻塞批次其他记录）。
"""

from __future__ import annotations

from typing import Any, Optional

from ..db import Database
from ..repo import VideoVariantRepo
from .evaluate import EvaluationService


def ingest_m5_record(
    db: Database,
    record: dict[str, Any],
    *,
    repo: Optional[VideoVariantRepo] = None,
    service: Optional[EvaluationService] = None,
) -> tuple[bool, str]:
    """摄取单条 M5 快照回写。返回 (ingested, feedback_id 或错误说明)。"""
    material_id = str(record.get("platform_material_id") or "").strip()
    if not material_id:
        return False, "missing_platform_material_id"
    vrepo = repo or VideoVariantRepo(db)
    variant = vrepo.get_by_platform_material_id(material_id)
    if variant is None:
        return False, f"unmatched_platform_material_id:{material_id}"

    spend_cents = int(record.get("spend_cents") or 0)
    gmv_cents = int(record.get("gmv_cents") or 0)
    roi = (gmv_cents / spend_cents) if spend_cents > 0 else 0.0

    # M5 中文诊断（字符串枚举）→ 字典形状（EvaluationSnapshot.diagnosis 为 dict，
    # ab.scoring.diag_score 兼容 {"level": "优秀"}）
    diag = record.get("diagnosis")
    diagnosis = {"level": str(diag)} if isinstance(diag, str) and diag.strip() else (diag or {})

    ev = service or EvaluationService(db)
    feedback_id = ev.record_metrics(
        variant["variant_id"],
        str(record.get("report_date") or ""),
        exposure=record.get("impressions") or 0,
        clicks=record.get("clicks") or 0,
        spend=spend_cents / 100.0,          # DA-001：分 → 元
        orders=record.get("orders") or 0,
        roi=roi,
        diagnosis=diagnosis,                # 字典形状，scoring 兼容
        platform_material_id=material_id,
    )
    return True, feedback_id


def ingest_m5_batch(
    db: Database,
    records: list[dict[str, Any]],
    *,
    repo: Optional[VideoVariantRepo] = None,
    service: Optional[EvaluationService] = None,
) -> dict[str, Any]:
    """批量摄取（失败隔离）：单条 unmatched/缺字段不影响其余记录。

    返回 {"ingested": int, "unmatched": [说明...], "feedback_ids": [str...]}。
    """
    result: dict[str, Any] = {"ingested": 0, "unmatched": [], "feedback_ids": []}
    for rec in records or []:
        ok, info = ingest_m5_record(db, rec, repo=repo, service=service)
        if ok:
            result["ingested"] += 1
            result["feedback_ids"].append(info)
        else:
            result["unmatched"].append(info)
    return result
