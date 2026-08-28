"""M3 主图/详情图管线 · 类目记忆（category_listing_memory）。

对齐方案文档 06 第二节：按类目累积「人工通过/平台拒审」经验，自动调整生图策略。

- record(passed/reject_reason)：累计通过/拒审次数，拒审原因统计（dict 计数）；
- auto_adjust / update_strategy：拒审率 ≥ 阈值（默认 0.5，样本 ≥ 3）时，
  按 background 轮换切换生图背景策略（white → scenario → gradient → lifestyle）落库；
  切换后的策略由 planner 读取（KimiImagePlanner(plan, memory=...) 覆盖背景短语）；
- 阈值/最小样本走环境变量 M3_MEMORY_REJECT_RATE_THRESHOLD / M3_MEMORY_MIN_SAMPLES
  （配置化，默认 0.5 / 3），可用 MemoryPolicy 注入覆盖；
- 读写复用骨架 repo.CategoryMemoryRepo（opt_category_memory 表），只使用不修改骨架。
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Optional

from ..config import M3Config, load_config
from ..db import Database
from ..models import CategoryMemory
from ..repo import CategoryMemoryRepo

BACKGROUND_ROTATION: tuple[str, ...] = ("white", "scenario", "gradient", "lifestyle")

ENV_REJECT_THRESHOLD = "M3_MEMORY_REJECT_RATE_THRESHOLD"
ENV_MIN_SAMPLES = "M3_MEMORY_MIN_SAMPLES"


@dataclass
class MemoryPolicy:
    """类目记忆调整策略参数（可注入覆盖，默认从环境变量读取）。"""

    reject_rate_threshold: float = 0.5   # 拒审率 ≥ 阈值触发策略切换
    min_samples: int = 3                 # 最少样本数（通过+拒审）才触发
    background_rotation: tuple[str, ...] = BACKGROUND_ROTATION

    @classmethod
    def from_env(cls) -> "MemoryPolicy":
        try:
            threshold = float(os.environ.get(ENV_REJECT_THRESHOLD, "0.5"))
        except ValueError:
            threshold = 0.5
        try:
            min_samples = int(os.environ.get(ENV_MIN_SAMPLES, "3"))
        except ValueError:
            min_samples = 3
        return cls(reject_rate_threshold=threshold, min_samples=min_samples)


class CategoryListingMemory:
    """类目记忆：统计 + 拒审原因 + 生图策略自动调整。"""

    def __init__(
        self,
        db: Database,
        config: Optional[M3Config] = None,
        policy: Optional[MemoryPolicy] = None,
    ):
        self.db = db
        self.config: M3Config = config or load_config()
        self.repo = CategoryMemoryRepo(db)
        self.policy = policy or MemoryPolicy.from_env()

    # ---------- 读 ----------

    def get(self, category: str) -> CategoryMemory:
        """当前类目记忆（无则初始化空记录，不计数）。"""
        row = self.repo.get_or_create(category)
        return CategoryMemory(
            category=category,
            pass_count=row.pass_count,
            reject_count=row.reject_count,
            reject_reasons=dict(row.reject_reasons_json or {}),
            image_strategy=dict(row.image_strategy_json or {}),
        )

    def strategy_for(self, category: str) -> dict[str, Any]:
        """当前生图策略 JSON（未调整时为空 dict）。"""
        return self.get(category).image_strategy

    # ---------- 写 ----------

    def record(
        self, category: str, *, passed: bool = True, reject_reason: str = ""
    ) -> None:
        """记录一次人工通过 / 平台拒审（累计计数 + 拒审原因统计）。"""
        self.repo.record(category, passed=passed, reject_reason=reject_reason)
        if not passed:
            self.auto_adjust(category)  # 拒审后立即评估是否切策略

    def update_strategy(self, category: str, strategy: dict[str, Any]) -> None:
        """显式写入/覆盖生图策略 JSON。"""
        self.repo.update_strategy(category, strategy)

    # ---------- 策略调整 ----------

    def auto_adjust(self, category: str) -> Optional[dict[str, Any]]:
        """拒审率高的类目切换背景策略；未达阈值/无轮换余地返回 None。"""
        mem = self.get(category)
        total = mem.pass_count + mem.reject_count
        if total < self.policy.min_samples:
            return None
        rate = mem.reject_count / total
        if rate < self.policy.reject_rate_threshold:
            return None

        rotation = self.policy.background_rotation or BACKGROUND_ROTATION
        if len(rotation) < 2:
            return None
        cur = mem.image_strategy or {}
        bg = cur.get("background", rotation[0])
        if bg not in rotation:
            bg = rotation[0]
        idx = rotation.index(bg)
        new_bg = rotation[(idx + 1) % len(rotation)]
        if new_bg == bg:
            return None

        strategy = dict(cur)
        strategy["background"] = new_bg
        strategy["reject_rate"] = round(rate, 3)
        strategy["note"] = (
            f"auto_adjust: 拒审率 {rate:.0%} ≥ {self.policy.reject_rate_threshold:.0%}，"
            f"背景策略 {bg} → {new_bg}"
        )
        self.repo.update_strategy(category, strategy)
        return strategy
