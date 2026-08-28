"""M4 → M5 衔接：销售中商品候选池只读视图 + 错峰窗口（P6）。

07 文档六节 / 10 文档二节契约（context/README.md 5.3 节「向 M5 提供」）：
- 候选池口径：**仅已上架商品**（status == "listed" 且 link_verified_at 非空且
  product_link 非空）；草稿/审核中/驳回/人工/待重提一律不出现；
- product_link 为已验证真实链接（R22 判据落库）；
- 错峰约束：上架批次与 M5 托管提交互斥时段（peak_avoid_window，参数化）。

本模块纯只读：不修改任何任务状态；重复调用返回一致（幂等）。
金额单位一律「分」（DA-001 全局口径）。
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, time as dt_time
from typing import Any, Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import select

from .repo import ListingRepo
from .tables import ListingSkuRow, ListingSpuRow, ListingTaskRow


class CandidatePoolConfig(BaseSettings):
    """候选池/错峰配置（环境变量前缀 LISTING_）。

    - candidate_batch_max：候选池导出上限（≤50，错峰批量，P-006）；
    - peak_avoid_window：上架批次与 M5 托管提交互斥时段 {"start","end"}，
      HH:MM 格式；start > end 视为跨天窗口（如 22:00 → 02:00）按环形处理。
    """

    model_config = SettingsConfigDict(
        env_prefix="LISTING_", env_file=".env", extra="ignore"
    )

    candidate_batch_max: int = Field(
        default=50,
        ge=1,
        le=50,
        description="候选池导出上限（≤50 错峰批量，P-006）",
    )
    peak_avoid_window: dict[str, str] = Field(
        default={"start": "10:00", "end": "12:00"},
        description="上架批次与 M5 托管提交互斥时段 {start, end}（HH:MM；"
        "start > end 为跨天窗口按环形处理）",
    )


class CandidatePool:
    """销售中商品候选池只读视图（07 文档六节：仅已上架商品，错峰导出）。

    纯只读：不修改任何任务状态；幂等（重复调用返回一致）。
    """

    def __init__(
        self,
        repo: ListingRepo,
        config: Optional[CandidatePoolConfig] = None,
    ):
        self.repo = repo
        self.config = config or CandidatePoolConfig()
        self._window_start, self._window_end = self._parse_window(
            self.config.peak_avoid_window
        )
        # 最近一次导出的截断证据（超出 candidate_batch_max 时提示）：
        # {truncated, requested, applied, total_matched}
        self.last_evidence: Optional[dict[str, Any]] = None

    # ------------------------------------------------------------ 候选池查询

    def get_sale_candidates(self, limit: int | None = None) -> list[dict]:
        """只读查询销售中商品候选（status=listed 且链接已验证）。

        - 过滤：status == "listed" 且 link_verified_at 非空且 product_link 非空；
        - 关联 listing_spus 取 title/category_id（无 SPU 置 None）；
        - 关联 listing_skus 聚合 price_min_cents/price_max_cents（单位：分，
          无 SKU 置 None）；
        - 返回字段：{product_id, task_id, title, category_id, product_link,
          link_verified_at, price_min_cents, price_max_cents}；
        - 按 link_verified_at 升序（先上架先出）；
        - limit 生效且不超过 candidate_batch_max（超出截断，截断证据写入
          self.last_evidence）。
        """
        batch_max = self.config.candidate_batch_max
        if limit is None:
            applied = batch_max
        else:
            applied = max(0, min(int(limit), batch_max))

        with self.repo.database.session() as session:
            task_rows = (
                session.execute(
                    select(ListingTaskRow)
                    .where(
                        ListingTaskRow.status == "listed",
                        ListingTaskRow.link_verified_at.is_not(None),
                        ListingTaskRow.product_link.is_not(None),
                        ListingTaskRow.product_link != "",
                    )
                    .order_by(ListingTaskRow.link_verified_at.asc())
                )
                .scalars()
                .all()
            )
            total_matched = len(task_rows)
            task_rows = task_rows[:applied]

            task_ids = [t.task_id for t in task_rows]
            spu_rows: list[ListingSpuRow] = []
            if task_ids:
                spu_rows = (
                    session.execute(
                        select(ListingSpuRow)
                        .where(ListingSpuRow.task_id.in_(task_ids))
                        .order_by(ListingSpuRow.created_at.asc())
                    )
                    .scalars()
                    .all()
                )

            # task_id -> 最早创建 SPU（标题/类目）；task_id -> 全部 spu_id 清单（价格聚合）
            first_spu_by_task: dict[str, ListingSpuRow] = {}
            spu_ids_by_task: dict[str, list[str]] = defaultdict(list)
            for spu in spu_rows:
                first_spu_by_task.setdefault(spu.task_id, spu)
                spu_ids_by_task[spu.task_id].append(spu.spu_id)

            spu_ids = [sid for ids in spu_ids_by_task.values() for sid in ids]
            sku_rows: list[ListingSkuRow] = []
            if spu_ids:
                sku_rows = (
                    session.execute(
                        select(ListingSkuRow).where(ListingSkuRow.spu_id.in_(spu_ids))
                    )
                    .scalars()
                    .all()
                )
            prices_by_spu: dict[str, list[int]] = defaultdict(list)
            for sku in sku_rows:
                prices_by_spu[sku.spu_id].append(sku.price_cents)

        results: list[dict[str, Any]] = []
        for t in task_rows:
            spu = first_spu_by_task.get(t.task_id)
            prices: list[int] = []
            for spu_id in spu_ids_by_task.get(t.task_id, []):
                prices.extend(prices_by_spu.get(spu_id, []))
            results.append(
                {
                    "product_id": t.product_id,
                    "task_id": t.task_id,
                    "title": spu.title if spu is not None else None,
                    "category_id": spu.category_id if spu is not None else None,
                    "product_link": t.product_link,
                    "link_verified_at": t.link_verified_at,
                    "price_min_cents": min(prices) if prices else None,
                    "price_max_cents": max(prices) if prices else None,
                }
            )

        self.last_evidence = {
            "truncated": total_matched > applied,
            "requested": limit,
            "applied": applied,
            "total_matched": total_matched,
        }
        return results

    # ------------------------------------------------------------ 错峰窗口

    def in_peak_avoid_window(self, now: Optional[datetime] = None) -> bool:
        """now（本地时区 datetime，默认 datetime.now()）的 HH:MM 是否落在
        peak_avoid_window [start, end) 内（错峰：该时段不执行上架批次，让位
        M5 托管提交）。

        - 左闭右开：start 时刻包含，end 时刻不包含；
        - 跨天窗口（start > end，如 22:00 → 02:00）按环形处理；
        - 比较粒度为 HH:MM（now 的秒/微秒截断）。
        """
        now = now or datetime.now()
        now_t = now.time().replace(second=0, microsecond=0)
        if self._window_start <= self._window_end:
            return self._window_start <= now_t < self._window_end
        # 跨天窗口：环形——now >= start 或 now < end
        return now_t >= self._window_start or now_t < self._window_end

    # ------------------------------------------------------------ 内部工具

    @staticmethod
    def _parse_window(window: dict[str, str]) -> tuple[dt_time, dt_time]:
        try:
            start = _parse_hhmm(window["start"])
            end = _parse_hhmm(window["end"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(
                f"peak_avoid_window 必须为 {{'start','end'}} 且为 HH:MM 字符串，"
                f"实际: {window!r}"
            ) from exc
        return start, end


def _parse_hhmm(value: Any) -> dt_time:
    if isinstance(value, dt_time):
        return value
    return dt_time.fromisoformat(str(value))
