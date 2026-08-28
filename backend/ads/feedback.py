"""M5 自动小店投放（商品托管）· 数据回写（v0.5 回流层）。

纯函数 + JSON 文件 IO 实现三类跨模块回写载体（**全部走 data-exchange JSON 载体，
宪法第 5 节，零数据库写，不碰任何其他模块的库/表**，M1/M2 侧写入由对方消费端负责）：

1. **M5-OUT-01 选品「投放转化」维度**（M5 → M1，契约 C-2）：
   `aggregate_by_category`（按 products.category 锚点聚合 ROI/成交额，弱样本仍输出、
   spend=0 类目与未知商品计入 skipped）→ `build_exchange_file`（结构严格对齐 C-2，
   可被 M1 `sourcing/ad_backfill.py` 的 `load_exchange` 直接校验消费）→
   `write_exchange_file`（UTF-8 无 BOM 幂等写出）。
2. **M5-OUT-02 素材评估回流**（M5 → M2）：`build_material_evaluation_file`——
   evaluation ∈ {exploring, efficient, potential}（镜像 M2 materials.config.EVALUATION_VALUES），
   evidence 对齐 `EvaluationFeedbackService.receive_evaluation` 的 evidence 语义（批次/报表快照摘要）。
3. **M5-OUT-03 托管失败原因回写**（M5 → M1 商品主表）：`build_review_reason_file`——
   product_id/review_reason 校验 + failed_at 默认当前 UTC。
4. `load_category_map`：加载 product→category 映射（两种形状），供调用方把 M1 products
   快照映射喂给 aggregate_by_category（本模块不从任何库读取，映射由 data-audit/总控协调提供）。

口径（DA-001 / REC-005）：金额一律「分」（int）；时间一律 UTC（ISO8601 带时区）存储；
枚举英文。本文件零 SQLAlchemy / 零 DB 依赖，可独立 import。

输入说明（调用方职责）：product_rows / material_rows / campaign_failures 均为 M5 自有数据
（从 ad_campaigns + ad_report_snapshots 等关联聚合后传入），本文件只做纯函数加工与文件 IO。
"""

from __future__ import annotations

import json
import logging
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

log = logging.getLogger("ads.feedback")

# 素材评估枚举（镜像 M2 materials/config.py EVALUATION_VALUES = ("exploring", "efficient", "potential")）
EVALUATION_VALUES: tuple[str, ...] = ("exploring", "efficient", "potential")

# 类目聚合跳过原因（skipped[].reason 取值）
_REASON_SPEND_ZERO = "spend=0"
_REASON_UNKNOWN_PRODUCT = "unknown product_id"
_REASON_INVALID_ROW = "invalid row"

__all__ = [
    "EVALUATION_VALUES",
    "aggregate_by_category",
    "build_exchange_file",
    "build_material_evaluation_file",
    "build_review_reason_file",
    "load_category_map",
    "write_exchange_file",
]


# ---------------------------------------------------------------- 时间/数值工具
def _as_utc(dt: datetime) -> datetime:
    """统一为 UTC 带时区：naive 视为 UTC 补时区；带偏移转 UTC（DA-001）。"""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _parse_generated_at(value: Any, field: str = "generated_at") -> datetime:
    """时间解析：datetime（naive 自动补 UTC）或 ISO8601 字符串（含 Z/偏移）→ aware UTC。

    非法输入抛 ValueError（消息只含原因与字段名，不含输入值，防敏感信息进入错误消息）。
    """
    if isinstance(value, datetime):
        return _as_utc(value)
    if isinstance(value, str):
        text = value.strip()
        if not text:
            raise ValueError(f"{field} 为空字符串")
        try:
            return _as_utc(datetime.fromisoformat(text.replace("Z", "+00:00")))
        except ValueError as exc:
            raise ValueError(f"{field} 不是合法 ISO8601 时间") from exc
    raise ValueError(f"{field} 类型非法（应为 datetime 或 ISO8601 字符串）: {type(value).__name__}")


def _to_int(value: Any) -> Optional[int]:
    """整型字段（id/金额/样本数）转 int；None/非法（含 bool）→ None（调用方决定跳过/抛错）。"""
    if value is None or isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


# ===========================================================================
# 一、M5-OUT-01：类目级投放转化聚合 + C-2 交换文件（M5 → M1）
# ===========================================================================
def aggregate_by_category(product_rows: list[dict], category_map: dict[int, str]) -> dict:
    """按商品类目聚合托管转化数据（纯函数，零库访问，锚点=M1 products.category）。

    输入（M5 自有数据，调用方从 ad_campaigns + ad_report_snapshots 聚合后传入）：
        product_rows: [{product_id, gmv_fen, spend_fen, sample_count}]（金额分 int）；
        category_map : {product_id: category}（来自 M1 products 快照，经 data-audit/总控
                      协调提供；本函数只接收映射，不从任何库读取）。

    规则（与 M1 context C-2 口径一致）：
    - 按 category 聚合：sales_amount=Σgmv_fen、spend=Σspend_fen、sample_count=Σsample_count；
    - spend=0 的类目跳过（ROI 无意义），计入 skipped（product_id 取该类目首个商品）；
    - 未知 product_id（不在 category_map）→ 跳过计入 skipped；
    - 弱样本（sample_count<5）**仍输出**（消费端 M1 过滤，本层不丢弃）；
    - spend>0 时 roi = 总gmv/总spend（float，>0；金额无混用）。

    返回 {"data": {category: {"roi": float, "sales_amount": int, "sample_count": int}},
          "skipped": [{"product_id", "reason"}]}。
    """
    buckets: dict[str, dict[str, int]] = {}  # category -> {sales_amount, spend, sample_count}
    first_product: dict[str, int] = {}       # category -> 该类目首个 product_id
    skipped: list[dict] = []

    for row in product_rows:
        if not isinstance(row, dict):
            skipped.append({"product_id": None, "reason": _REASON_INVALID_ROW})
            continue
        pid = _to_int(row.get("product_id"))
        category = category_map.get(pid) if pid is not None else None
        if pid is None or not category:
            # 缺失/未知 product_id：跳过计入 skipped（不进任何类目桶）
            skipped.append({"product_id": pid, "reason": _REASON_UNKNOWN_PRODUCT})
            continue
        gmv = _to_int(row.get("gmv_fen"))
        spend = _to_int(row.get("spend_fen"))
        count = _to_int(row.get("sample_count"))
        if gmv is None or spend is None or count is None:
            skipped.append({"product_id": pid, "reason": _REASON_INVALID_ROW})
            continue
        if category not in buckets:
            buckets[category] = {"sales_amount": 0, "spend": 0, "sample_count": 0}
            first_product[category] = pid
        buckets[category]["sales_amount"] += gmv
        buckets[category]["spend"] += spend
        buckets[category]["sample_count"] += count

    data: dict[str, dict[str, Any]] = {}
    for category, agg in buckets.items():
        if agg["spend"] == 0:
            # 类目级跳过：ROI 无意义（该条目 product_id 取类目首个商品，便于追溯）
            skipped.append({"product_id": first_product[category], "reason": _REASON_SPEND_ZERO})
            continue
        data[category] = {
            "roi": agg["sales_amount"] / agg["spend"],
            "sales_amount": agg["sales_amount"],
            "sample_count": agg["sample_count"],
        }
    return {"data": data, "skipped": skipped}


def build_exchange_file(
    category_data: dict,
    period_start: str,
    period_end: str,
    generated_at: datetime | str,
) -> dict:
    """构造 M5 → M1 投放转化交换文件（契约 C-2，返回 dict 可 json.dumps 直写）。

    category_data：aggregate_by_category 返回的 "data"（或等结构
        {category: {"roi", "sales_amount", "sample_count"}}）；
    period_start/end：YYYY-MM-DD（非法抛 ValueError）；
    generated_at：aware datetime（naive 自动补 UTC）或 ISO8601 字符串 → 序列化为
        ISO8601 字符串（统一 UTC）。

    逐条校验（与 M1 AdCategoryData 口径对齐）：roi≤0 / sales_amount 非 int /
    sample_count 非 int → 抛 ValueError（整批拒绝，避免 M1 消费端逐条 skipped）。
    输出结构严格对齐 C-2：schema_version=1 / period{"start","end"} / generated_at / data。
    """
    for field_name, value in (("period_start", period_start), ("period_end", period_end)):
        if not isinstance(value, str):
            raise ValueError(f"{field_name} 必须为 YYYY-MM-DD 字符串")
        try:
            datetime.strptime(value, "%Y-%m-%d")
        except ValueError as exc:
            raise ValueError(f"{field_name} 日期格式非法（应为 YYYY-MM-DD）") from exc

    generated = _parse_generated_at(generated_at)

    out_data: dict[str, dict[str, Any]] = {}
    for category, entry in category_data.items():
        if not isinstance(entry, dict):
            raise ValueError(f"类目数据必须为 dict: {category!r}")
        roi = entry.get("roi")
        sales = entry.get("sales_amount")
        count = entry.get("sample_count")
        if (
            isinstance(roi, bool)
            or not isinstance(roi, (int, float))
            or not math.isfinite(float(roi))
            or roi <= 0
        ):
            raise ValueError(f"类目 {category!r} roi 非法（应为 >0 数值）")
        if isinstance(sales, bool) or not isinstance(sales, int):
            raise ValueError(f"类目 {category!r} sales_amount 非法（应为 int，金额分）")
        if isinstance(count, bool) or not isinstance(count, int):
            raise ValueError(f"类目 {category!r} sample_count 非法（应为 int）")
        out_data[category] = {
            "roi": float(roi),
            "sales_amount": sales,
            "sample_count": count,
        }

    return {
        "schema_version": 1,
        "period": {"start": period_start, "end": period_end},
        "generated_at": generated.isoformat(),
        "data": out_data,
    }


def write_exchange_file(data: dict, path: str | Path) -> dict:
    """JSON 交换文件写出：UTF-8（ensure_ascii=False，中文原样）、父目录自动创建、幂等覆盖。

    返回 {"path": str, "bytes": int(写入字节数), "written_at": ISO8601(UTC)}。
    """
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    content = json.dumps(data, ensure_ascii=False, indent=2)
    p.write_text(content, encoding="utf-8")
    return {
        "path": str(p),
        "bytes": len(content.encode("utf-8")),
        "written_at": datetime.now(timezone.utc).isoformat(),
    }


# ===========================================================================
# 二、M5-OUT-02：素材评估回流文件（M5 → M2）
# ===========================================================================
def build_material_evaluation_file(
    material_rows: list[dict], generated_at: datetime | str | None = None
) -> dict:
    """素材评估回流文件（M5 → M2，对齐 EvaluationFeedbackService.receive_evaluation 的 evidence 语义）。

    material_rows（M5 自有：从 ad_materials + ad_report_snapshots 关联，调用方聚合传入）：
        [{asset_id, evaluation, impressions, gmv_fen, spend_fen}]；
    校验：evaluation ∈ {exploring, efficient, potential}（镜像 M2 EVALUATION_VALUES）→
    非法抛 ValueError；asset_id 缺失/非法 → 抛 ValueError。
    输出：{"schema_version": 1, "generated_at": ISO8601,
          "data": [{"asset_id", "evaluation",
                    "evidence": {"impressions", "gmv_fen", "spend_fen", "source_agent": "M5"}}]}
    （evidence 为回流批次/报表快照摘要，M2 receive_evaluation 原样存 evidence_json；
    impressions/gmv_fen/spend_fen 缺省 0。）
    """
    generated = (
        _parse_generated_at(generated_at)
        if generated_at is not None
        else datetime.now(timezone.utc)
    )
    out_rows: list[dict[str, Any]] = []
    for row in material_rows:
        if not isinstance(row, dict):
            raise ValueError("material_rows 每项必须为 dict")
        asset_id_raw = row.get("asset_id")
        if asset_id_raw is None:
            raise ValueError("asset_id 缺失")
        asset_id = _to_int(asset_id_raw)
        if asset_id is None:
            raise ValueError("asset_id 非法")
        evaluation = row.get("evaluation")
        if evaluation not in EVALUATION_VALUES:
            raise ValueError(f"evaluation 非法（允许: {', '.join(EVALUATION_VALUES)}）")
        out_rows.append(
            {
                "asset_id": asset_id,
                "evaluation": evaluation,
                "evidence": {
                    "impressions": row.get("impressions", 0),
                    "gmv_fen": row.get("gmv_fen", 0),
                    "spend_fen": row.get("spend_fen", 0),
                    "source_agent": "M5",
                },
            }
        )
    return {"schema_version": 1, "generated_at": generated.isoformat(), "data": out_rows}


# ===========================================================================
# 三、M5-OUT-03：托管失败/不可投放原因回写文件（M5 → M1 商品主表）
# ===========================================================================
def build_review_reason_file(
    campaign_failures: list[dict], generated_at: datetime | str | None = None
) -> dict:
    """托管失败/不可投放原因回写文件（M5 → M1 products.review_reason，写入由 M1 消费端负责）。

    campaign_failures：[{product_id, review_reason, campaign_id, failed_at}]；
    校验：product_id 非空（缺失/非法 → ValueError）、review_reason 非空字符串；
    failed_at 缺省 → 当前 UTC（naive 补 UTC、带偏移转 UTC）。
    输出：{"schema_version": 1, "generated_at": ISO8601,
          "data": [{"product_id", "review_reason", "campaign_id", "failed_at"}]}
    （campaign_id 可选，缺省输出 None，供审计追溯。）
    """
    generated = (
        _parse_generated_at(generated_at)
        if generated_at is not None
        else datetime.now(timezone.utc)
    )
    out_rows: list[dict[str, Any]] = []
    for row in campaign_failures:
        if not isinstance(row, dict):
            raise ValueError("campaign_failures 每项必须为 dict")
        pid_raw = row.get("product_id")
        if pid_raw is None:
            raise ValueError("product_id 缺失")
        product_id = _to_int(pid_raw)
        if product_id is None:
            raise ValueError("product_id 非法")
        reason = row.get("review_reason")
        if reason is None or not isinstance(reason, str) or not reason.strip():
            raise ValueError("review_reason 缺失或为空")
        failed_at_raw = row.get("failed_at")
        failed_at = (
            _parse_generated_at(failed_at_raw, field="failed_at")
            if failed_at_raw is not None
            else datetime.now(timezone.utc)
        )
        out_rows.append(
            {
                "product_id": product_id,
                "review_reason": reason.strip(),
                "campaign_id": row.get("campaign_id"),
                "failed_at": failed_at.isoformat(),
            }
        )
    return {"schema_version": 1, "generated_at": generated.isoformat(), "data": out_rows}


# ===========================================================================
# 四、product→category 映射加载（供调用方把 M1 快照映射喂给 aggregate_by_category）
# ===========================================================================
def load_category_map(path: str | Path | None) -> dict[int, str]:
    """加载 product→category 映射（来自 M1 products 快照，经 data-audit/总控协调提供）。

    支持两种形状：
    - dict 形状：{"product_id 字符串": "category"}；
    - list 形状：[{"product_id": 123, "category": "..."}]。
    product_id 统一转 int；无文件 / JSON 损坏 / 结构非法 → 返回 {}（log warning，不抛）；
    单条非法（id 非数字 / 缺字段 / 空类目）→ 跳过该条并 log warning（尽力而为，不整份丢弃）。
    """
    if path is None:
        return {}
    p = Path(path)
    if not p.exists():
        log.warning("category_map 文件不存在，返回空映射: %s", p)
        return {}
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError, OSError) as e:
        log.warning("category_map 解析失败，返回空映射: %s（%s）", p, e)
        return {}

    mapping: dict[int, str] = {}
    if isinstance(raw, dict):
        for key, category in raw.items():
            try:
                pid = int(key)
            except (TypeError, ValueError):
                log.warning("category_map 跳过非法 product_id 键: %r", key)
                continue
            if not isinstance(category, str) or not category:
                log.warning("category_map 跳过空类目: %s", pid)
                continue
            mapping[pid] = category
        return mapping
    if isinstance(raw, list):
        for item in raw:
            if not isinstance(item, dict):
                log.warning("category_map 跳过非法条目（非 dict）")
                continue
            try:
                pid = int(item.get("product_id"))
            except (TypeError, ValueError):
                log.warning("category_map 跳过非法 product_id 条目")
                continue
            category = item.get("category")
            if not isinstance(category, str) or not category:
                log.warning("category_map 跳过空类目条目: %s", pid)
                continue
            mapping[pid] = category
        return mapping
    log.warning("category_map 结构非法（应为 dict 或 list），返回空映射: %s", p)
    return {}
