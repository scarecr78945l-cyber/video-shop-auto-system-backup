"""M4 自动上架公共服务（services）。

`listing_gate`：上架前校验硬门禁（ListingGate）—— 流水线第一道关卡，
六项硬门禁全部通过才允许入队。门禁是前置校验，不套 WorkflowJob 执行期
错误码（那是流水线运行期用）；拒绝返回结构化原因（GateResult.items 逐项
passed/reason/evidence + rejected_reason_codes）。
"""

from .listing_gate import (
    GateItemResult,
    GateResult,
    ListingCandidate,
    ListingGate,
    ListingGateConfig,
    PurchaseSettings,
    SkuInput,
)

__all__ = [
    "GateItemResult",
    "GateResult",
    "ListingCandidate",
    "ListingGate",
    "ListingGateConfig",
    "PurchaseSettings",
    "SkuInput",
]
