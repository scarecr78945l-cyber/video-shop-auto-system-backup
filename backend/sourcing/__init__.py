"""视频号小店全自动系统 — 自动选品模块。

链路：采集（三源）→ 去重 → 合规三态 → 数据补全 → 打分（五维）→ TopN 入池。

离线可用：`--source fixtures` 走本地样本数据，无需任何登录态。
"""

__version__ = "0.1.0"

from .config import SourcingConfig, load_config  # noqa: F401
from .models import (  # noqa: F401
    ComplianceState,
    PipelineResult,
    ProductCandidate,
    ScoreBreakdown,
    SourceItem,
)

__all__ = [
    "SourcingConfig",
    "load_config",
    "SourceItem",
    "ComplianceState",
    "ProductCandidate",
    "ScoreBreakdown",
    "PipelineResult",
]
