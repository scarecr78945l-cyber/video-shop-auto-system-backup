# -*- coding: utf-8 -*-
"""P0-2 批次 2（C1-b/c）：单 source 数值贡献计算（round-153 授权实现）。

依据 round-145 §三 / round-147 §2.3 / round-152 §三：

- **单 source 贡献**：每条 ledger 行严格由一个 source snapshot 派生（与批次 1/选择器同源）；
  本模块只输出数值结果/typed outcome，**不执行反馈 INSERT、不写审计、不建人工任务**（C2/C3 锁定）。
- 五类 formula（canonical-only，无 fallback）：
  - ROI 类（product_score/category_score/material_score/shop_strategy）：`Σgmv/Σspend`，
    spend=0 → `ZeroSpendSkipped`；
  - SKU 类（sku_margin）：`Σ(gmv−spend)`，单位分，允许负差额（亏损），spend=0 **不是** skip。
- Decimal 口径（与项目统一，round-152 §三.2）：`localcontext(prec=60, ROUND_HALF_UP)` 计算后
  `quantize(0.000001, ROUND_HALF_UP)` 落 scale=6（`1/3 → 0.333333`）。
- typed outcome 分层（round-147 §2.4）：
  - `roi` / `sku_margin`：可产出；
  - `zero_spend_skipped`：ROI 类 spend=0（非异常、非 rejected）；
  - `insufficient_inputs`：缺字段 / 无 canonical source / subject 不可解析（typed，非异常）。
"""
from __future__ import annotations

import decimal
from dataclasses import dataclass
from decimal import Decimal
from typing import Optional, Tuple

from .aggregation_manifest import (
    CANONICAL_GRANULARITY,
    FEEDBACK_TYPES,
    ROI_TYPES,
    SKU_TYPES,
    STORAGE_SCALE,
)

_INSUFFICIENT_REASONS = {"no_canonical_source", "subject_unresolvable", "missing_numerator_or_denominator"}
_QUANT = Decimal(1).scaleb(-STORAGE_SCALE)  # 0.000001


class CalculatorInputError(ValueError):
    """calculator 输入非法（未知 feedback_type、bool/负金额、非 int 等）。"""


# ---------------------------------------------------------------- typed outcomes
def _check_scale6(value: Decimal, label: str) -> None:
    """scale 校验（R154-2）：确认 finite 且恰为 6 位指数，不用数值相等判断（那会依赖调用方 context）。"""
    if not isinstance(value, Decimal) or not value.is_finite():
        raise CalculatorInputError(f"{label} 必须为 finite Decimal")
    if value.as_tuple().exponent != -STORAGE_SCALE:
        raise CalculatorInputError(f"{label} 必须为 scale={STORAGE_SCALE} canonical 表示")


@dataclass(frozen=True)
class RoiContribution:
    kind = "roi"
    feedback_type: str
    snapshot_id: int
    numerator_gmv: int
    denominator_spend: int
    value: Decimal            # scale=6 canonical

    def __post_init__(self):
        _check_scale6(self.value, "roi value")


@dataclass(frozen=True)
class SkuMarginContribution:
    kind = "sku_margin"
    feedback_type: str
    snapshot_id: int
    numerator_gmv: int
    denominator_spend: int
    value: Decimal            # 分；可为负（亏损）；scale=6 canonical

    def __post_init__(self):
        _check_scale6(self.value, "sku_margin value")


@dataclass(frozen=True)
class ZeroSpendSkipped:
    kind = "zero_spend_skipped"
    feedback_type: str
    snapshot_id: int
    reason: str = "denominator_spend_zero"


@dataclass(frozen=True)
class InsufficientInputs:
    kind = "insufficient_inputs"
    feedback_type: str
    snapshot_id: int
    reason: str
    missing_fields: Tuple[str, ...] = ()

    def __post_init__(self):
        if self.reason not in _INSUFFICIENT_REASONS:
            raise CalculatorInputError(f"insufficient reason 非法: {self.reason!r}")


# ---------------------------------------------------------------- 校验
def _check_nonneg_int(name: str, value) -> int:
    if type(value) is not int or value < 0:
        raise CalculatorInputError(f"{name} 必须为非负 int（bool 拒绝），got {value!r}")
    return value


def _quantize6(value: Decimal) -> Decimal:
    with decimal.localcontext() as ctx:
        ctx.prec = 60
        ctx.rounding = decimal.ROUND_HALF_UP
        return value.quantize(_QUANT, rounding=decimal.ROUND_HALF_UP)


def compute_contribution(
    feedback_type: str,
    *,
    snapshot_id: int,
    gmv,
    spend,
    granularity: Optional[str] = None,
) -> object:
    """单 source 贡献（纯函数）。返回 RoiContribution | SkuMarginContribution |
    ZeroSpendSkipped | InsufficientInputs。

    - `feedback_type` 必须属 aggr_v1 manifest 五类；
    - `gmv`/`spend` 非负 int（bool 拒绝）；None → insufficient(missing_*);
    - `granularity` 提供时须等于 canonical granularity，否则 insufficient(no_canonical_source)；
    - ROI 类 spend=0 → zero_spend_skipped；SKU 类 spend=0 → 正常差额（非 skip）。
    """
    if feedback_type not in FEEDBACK_TYPES:
        raise CalculatorInputError(f"未知 feedback_type: {feedback_type!r}")
    if type(snapshot_id) is not int or snapshot_id <= 0:
        raise CalculatorInputError(f"snapshot_id 必须为正 int，got {snapshot_id!r}")

    if granularity is not None and granularity != CANONICAL_GRANULARITY[feedback_type]:
        return InsufficientInputs(feedback_type, snapshot_id, "no_canonical_source",
                                  ("granularity",))

    missing = tuple(name for name, val in (("gmv", gmv), ("spend", spend)) if val is None)
    if missing:
        return InsufficientInputs(feedback_type, snapshot_id, "missing_numerator_or_denominator", missing)

    gmv_i = _check_nonneg_int("gmv", gmv)
    spend_i = _check_nonneg_int("spend", spend)

    if feedback_type in SKU_TYPES:
        # SKU：Σ(gmv − spend)，单位分；允许负差额；spend=0 非 skip
        with decimal.localcontext() as ctx:
            ctx.prec = 60
            ctx.rounding = decimal.ROUND_HALF_UP
            value = _quantize6(Decimal(gmv_i) - Decimal(spend_i))
        return SkuMarginContribution(feedback_type, snapshot_id, gmv_i, spend_i, value)

    # ROI 类：Σgmv/Σspend；spend=0 → typed skip
    if spend_i == 0:
        return ZeroSpendSkipped(feedback_type, snapshot_id)
    with decimal.localcontext() as ctx:
        ctx.prec = 60
        ctx.rounding = decimal.ROUND_HALF_UP
        value = _quantize6(Decimal(gmv_i) / Decimal(spend_i))
    return RoiContribution(feedback_type, snapshot_id, gmv_i, spend_i, value)
