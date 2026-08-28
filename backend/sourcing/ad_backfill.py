"""M5 → M1 投放转化回写接入器（S2，ad_backfill）。

读取 M5 托管报表交换文件（契约 C-2：`_management/data-exchange/m5-ad-conversion.json`）
→ 校验 → 幂等导入两张 m1 表：

- `m1_ad_conversion_cache`：类目级打分输入缓存，唯一键 (category, period_start, period_end)；
- `m1_ad_conversion_ingests`：导入审计，唯一键 (source_file, period_start, period_end, generated_at)。

错误语义（设计决策，测试据此断言）：
- 结构级校验失败（顶层非对象 / schema_version≠1 / period 非法 / generated_at 非法）
  → `load_exchange` 抛 `AdBackfillError`（消息只含原因，不含输入值/敏感信息）；
- 文件不存在 / JSON 损坏 / 编码错误 → `load_exchange` 返回 None（调用方优雅降级，不抛异常）；
- 类目级脏数据（条目非对象 / roi≤0 / sales_amount 非 int / sample_count 非法）
  → 拒绝该条并计入 skipped + 审计 message（单条不污染整批，不强杀导入）；
- 弱样本（sample_count<5）**仍然导入缓存表留痕**；新鲜度/弱样本可用性判定
  属消费端 `SourcingPipeline._fresh_ad_by_category`（S1b 已实现并测试），本层不丢弃；
- `generated_at` 统一归一化为 aware datetime(UTC) 存储；period_start/end 原样字符串存储。
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from pydantic import BaseModel, Field, ValidationError, field_validator
from sqlalchemy import select

from . import tables as T
from .models import utcnow

log = logging.getLogger("sourcing.ad_backfill")


class AdBackfillError(Exception):
    """交换文件结构级校验失败。消息只含原因，不含输入值/敏感信息。"""


class PeriodRange(BaseModel):
    """快照期（YYYY-MM-DD，原样字符串存储）。"""

    start: str
    end: str

    @field_validator("start", "end")
    @classmethod
    def _check_date_format(cls, v: str) -> str:
        try:
            datetime.strptime(v, "%Y-%m-%d")
        except ValueError:
            raise ValueError(f"period 日期格式非法（应为 YYYY-MM-DD）: {v!r}")
        return v


class AdCategoryData(BaseModel):
    """单类目投放转化数据（C-2 口径，逐条校验用）。"""

    roi: float = Field(gt=0, description="期间托管 ROI（成交额/花费，比值无量纲，>0）")
    sales_amount: int = Field(ge=0, description="期间托管成交额（分，int，禁元/分混用）")
    sample_count: int = Field(default=0, ge=0, description="计入商品数（<5 弱样本，消费端过滤）")


class AdExchangeFile(BaseModel):
    """M5 交换文件校验模型（契约 C-2）。

    `data` 值保留原始 dict（类型/取值由 apply_exchange 逐条用 AdCategoryData 校验），
    使类目级脏数据可单条拒绝（skipped）；schema_version/period/generated_at 等结构级
    字段在本模型校验（失败由 load_exchange 包装为 AdBackfillError）。
    """

    schema_version: int
    period: PeriodRange
    generated_at: datetime
    data: dict[str, Any] = Field(default_factory=dict)

    @field_validator("generated_at", mode="before")
    @classmethod
    def _parse_generated_at(cls, v: Any) -> Any:
        """ISO 字符串（含尾部 Z → 替换 +00:00）或 datetime 统一解析为 datetime。"""
        if isinstance(v, str):
            try:
                return datetime.fromisoformat(v.replace("Z", "+00:00"))
            except ValueError:
                raise ValueError("generated_at 不是合法 ISO8601 时间")
        if isinstance(v, datetime):
            return v
        raise ValueError(f"generated_at 类型非法（应为 ISO8601 字符串或 datetime）: {type(v).__name__}")


def _validation_reason(err: ValidationError) -> str:
    """提取 pydantic 校验错误首条原因（不含输入值，避免敏感信息进入消息）。"""
    first = err.errors()[0]
    loc = ".".join(str(p) for p in first.get("loc", ()))
    msg = first.get("msg", "校验失败")
    return f"{loc}: {msg}" if loc else msg


def _normalize_generated_at(value: datetime) -> datetime:
    """统一转 aware datetime(UTC)：naive 按 UTC 补时区，其他时区转 UTC。"""
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def load_exchange(path: str | Path) -> Optional[AdExchangeFile]:
    """读 JSON → 校验 → 返回规范化结构（AdExchangeFile）。

    - 文件不存在 / JSON 损坏 / 编码错误 → 返回 None（调用方优雅降级）；
    - 结构级校验失败 → 抛 AdBackfillError（含原因，无敏感信息）。
    """
    p = Path(path)
    if not p.exists():
        log.warning("ad 交换文件不存在，跳过: %s", p)
        return None
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError, OSError) as e:
        log.warning("ad 交换文件解析失败，跳过: %s（%s）", p, e)
        return None
    try:
        exchange = AdExchangeFile.model_validate(raw)
    except ValidationError as e:
        raise AdBackfillError(f"ad 交换文件校验失败: {_validation_reason(e)}") from e
    if exchange.schema_version != 1:
        raise AdBackfillError(f"不支持的 schema_version={exchange.schema_version}（仅支持 1）")
    return exchange


def apply_exchange(db, exchange: AdExchangeFile, source_file: str) -> dict:
    """幂等导入 M5 交换数据。

    - 每个类目按唯一键 (category, period_start, period_end) upsert `m1_ad_conversion_cache`
      （存在则更新 roi/sales_amount/sample_count/generated_at/source_file/ingested_at，
      不存在则插入）；
    - 每次导入按唯一键 (source_file, period_start, period_end, generated_at) upsert
      `m1_ad_conversion_ingests`（存在则更新 rows_loaded/skipped/status/message，不存在则插入）；
    - 类目级脏数据 → 拒绝该条并计入 skipped（审计 message 记原因）；
    - 弱样本（sample_count<5）仍写入 cache 留痕（可用性由消费端判定）。

    返回统计 {categories, upserted, inserted, skipped, rows_loaded}。
    """
    stats = {"categories": 0, "upserted": 0, "inserted": 0, "skipped": 0, "rows_loaded": 0}
    generated = _normalize_generated_at(exchange.generated_at)
    now = utcnow()
    messages: list[str] = []
    with db.session() as session:
        for category, raw_data in exchange.data.items():
            try:
                entry = AdCategoryData.model_validate(raw_data)
            except ValidationError as e:
                stats["skipped"] += 1
                messages.append(f"{category}: {_validation_reason(e)}")
                continue
            row = session.execute(
                select(T.M1AdConversionCache).where(
                    T.M1AdConversionCache.category == category,
                    T.M1AdConversionCache.period_start == exchange.period.start,
                    T.M1AdConversionCache.period_end == exchange.period.end,
                )
            ).scalar_one_or_none()
            if row is None:
                row = T.M1AdConversionCache(
                    category=category,
                    period_start=exchange.period.start,
                    period_end=exchange.period.end,
                    generated_at=generated,
                    source_file=source_file,
                )
                session.add(row)
                stats["inserted"] += 1
            else:
                stats["upserted"] += 1
            row.roi = entry.roi
            row.sales_amount = entry.sales_amount
            row.sample_count = entry.sample_count
            row.generated_at = generated
            row.source_file = source_file
            row.ingested_at = now
            stats["rows_loaded"] += 1
        stats["categories"] = len(exchange.data)

        ingest = session.execute(
            select(T.M1AdConversionIngest).where(
                T.M1AdConversionIngest.source_file == source_file,
                T.M1AdConversionIngest.period_start == exchange.period.start,
                T.M1AdConversionIngest.period_end == exchange.period.end,
                T.M1AdConversionIngest.generated_at == generated,
            )
        ).scalar_one_or_none()
        if ingest is None:
            ingest = T.M1AdConversionIngest(
                source_file=source_file,
                schema_ver=exchange.schema_version,
                period_start=exchange.period.start,
                period_end=exchange.period.end,
                generated_at=generated,
                ingested_at=now,
            )
            session.add(ingest)
        ingest.rows_loaded = stats["rows_loaded"]
        ingest.skipped = stats["skipped"]
        ingest.status = "partial" if stats["skipped"] else "ok"  # ok | partial（failed 保留给后续整批失败场景）
        ingest.message = "; ".join(messages)[:2000]
        ingest.ingested_at = now
    return stats


def _empty_stats() -> dict:
    return {"categories": 0, "upserted": 0, "inserted": 0, "skipped": 0, "rows_loaded": 0}


def backfill(db, path: str | Path | None = None) -> dict:
    """从交换文件导入 M5 投放转化数据（幂等，程序化入口）。

    - path 缺省 → 读 db.config.ad_exchange_file（默认 ""=未配置）；
    - 无文件 / 解析失败 / 校验失败 → 返回空统计（优雅降级，log warning，不抛异常）。
    """
    if not path:
        config = getattr(db, "config", None)
        path = getattr(config, "ad_exchange_file", "") if config is not None else ""
    if not path:
        log.warning("未配置 ad_exchange_file（契约 C-2），跳过投放转化回写导入")
        return _empty_stats()
    try:
        exchange = load_exchange(path)
    except AdBackfillError as e:
        log.warning("ad 交换文件校验失败，跳过导入: %s", e)
        return _empty_stats()
    if exchange is None:
        return _empty_stats()
    return apply_exchange(db, exchange, str(path))
