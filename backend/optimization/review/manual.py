"""M3 自动素材优化模块 · 审核闸门（review）第三步：人工复核抽检（子代理-D · v1.0）。

对齐 06 文档第四节第 3 步与 10 文档第五节「人工闸门」：
- 按 ``config.review.sample_rate``（默认 0.1）抽检——**确定性**：对素材 id
  做 sha256 取模，同 id 同结果（可复现、可测试）；
- 高风险类目（``config.review.high_risk_categories``，可从 app_config 读或配置注入）
  **强制人工**，不受 sample_rate 影响；
- 抽中 → 状态 manual_review 待人工；未抽中 → 放行。

零网络、零跨库访问；本模块只读 import 公共骨架 config。
"""

from __future__ import annotations

import hashlib
from typing import Iterable, Optional

from ..config import M3Config, load_config


class ManualSampler:
    """人工复核抽检器（确定性哈希取模）。

    注入优先级：构造参数 > config.review（sample_rate / high_risk_categories）。
    high_risk_categories 的扩展点：生产可从 app_config 读取后经构造参数注入，
    本模块不直读 app_config（归 M0 只读，写入需总控协调）。
    """

    def __init__(
        self,
        config: Optional[M3Config] = None,
        sample_rate: Optional[float] = None,
        high_risk_categories: Optional[Iterable[str]] = None,
    ):
        self.config: M3Config = config or load_config()
        self.sample_rate: float = (
            float(sample_rate)
            if sample_rate is not None
            else float(self.config.review.sample_rate)
        )
        self.high_risk_categories: tuple[str, ...] = tuple(
            high_risk_categories
            if high_risk_categories is not None
            else self.config.review.high_risk_categories
        )
        if not (0.0 <= self.sample_rate <= 1.0):
            raise ValueError(f"sample_rate 必须在 [0,1]，收到 {self.sample_rate}")

    # ---------- 判定 ----------

    def is_high_risk(self, category: str) -> bool:
        """类目是否命中高风险列表（去空白精确匹配）。"""
        return str(category or "").strip() in self.high_risk_categories

    def should_manual(self, target_id: str, category: str = "") -> bool:
        """是否需要人工复核：高风险类目强制；否则按 sample_rate 哈希抽检。"""
        if self.is_high_risk(category):
            return True
        if self.sample_rate <= 0.0:
            return False
        if self.sample_rate >= 1.0:
            return True
        return self._ratio(str(target_id)) < self.sample_rate

    # ---------- 确定性哈希 ----------

    @staticmethod
    def _ratio(target_id: str) -> float:
        """sha256(target_id) 前 8 字节 → [0,1) 均匀值（同 id 恒定）。"""
        digest = hashlib.sha256(target_id.encode("utf-8")).hexdigest()
        return int(digest[:8], 16) / 0xFFFFFFFF


def should_manual_review(
    target_id: str,
    category: str = "",
    config: Optional[M3Config] = None,
) -> bool:
    """模块级便捷入口：人工抽检判定。"""
    return ManualSampler(config).should_manual(target_id, category)
