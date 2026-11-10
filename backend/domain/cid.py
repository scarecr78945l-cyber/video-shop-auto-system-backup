# -*- coding: utf-8 -*-
"""CID 公式引擎（P0-1 T5，round-65）。

唯一输入契约：docs/contracts/cid-engine-spec.md（冻结）。

要点：
- decimal context 唯一冻结：`Context(prec=60, rounding=ROUND_HALF_UP)`；输入为十进制字符串/Decimal
  （不经 binary float）；中间值同一 context 一次算完，后续项不读取已量化的中间投影；
- 公式（原件一致）：
      M = K - J - I - H - G - L
      N = K / M
      O = N + roi_buffer
      P = K / O
      Q = P * consumption_rebate_rate
      R = K * tech_hi - K * tech_lo        # 可为负
      S = K - P - J - I - H - G + R + Q    # 原件不减 L
      T = S / P
      V = P / U
      X = O * U
      bid_rounded_cents = ROUND_HALF_UP(P)
- canonical decimal serialization（round-27 数值级）：plain fixed-point、裁剪非显著尾随零、
  负零 -> "0"、exponent 展开、整数无小数点；
- envelope（round-23 A6）：status / blocking_error / quality_flags / business_flags /
  field_details / values / bid_rounded_cents / formula_version / decimal_precision / rounding_mode；
- 除零/负毛利/空值：M<=0 -> M_NON_POSITIVE；O=0 -> O_ZERO；U<=0 -> U_NON_POSITIVE；P=0 -> P_ZERO；
  必需 K/J/I/H/G/U 缺失 -> REQUIRED_FIELD_MISSING；L 缺失 -> 默认 0 + FIELD_DEFAULTED；
  rebate 费率=0 -> REBATE_NOT_APPLICABLE（Q=0 继续）；rebate 来源缺失 -> REBATE_SOURCE_MISSING；
  S<=0 -> 计算完成 + S_NON_POSITIVE（业务闸门，非引擎失败）。
"""
from __future__ import annotations

from decimal import Context, Decimal, InvalidOperation, ROUND_HALF_UP, localcontext
from typing import Any, Mapping, Optional, Union

CID_CONTEXT = Context(prec=60, rounding=ROUND_HALF_UP)
FORMULA_VERSION = "v5"
DECIMAL_PRECISION = 60
ROUNDING_MODE = "ROUND_HALF_UP"
RATIO_QUANTIZE = Decimal("0.000001")  # numeric(12,6) 投影（仅存储，不回流）

REQUIRED_FIELDS = ("K", "J", "I", "H", "G", "U")
L_FIELD = "L"
VALUE_KEYS = ("M", "N", "O", "P", "Q", "R", "S", "T", "V", "X")

# 错误/标记码（cid-engine-spec §四）
BLOCKING = {
    "M_NON_POSITIVE", "O_ZERO", "U_NON_POSITIVE", "P_ZERO", "REQUIRED_FIELD_MISSING",
}
QUALITY = {"FIELD_DEFAULTED", "REBATE_SOURCE_MISSING"}
BUSINESS = {"REBATE_NOT_APPLICABLE", "S_NON_POSITIVE"}


def _to_decimal(value: Any, field: str = "") -> Decimal:
    """输入必须为 Decimal 或十进制字符串且 finite；float 与 NaN/±Infinity 拒绝（R66-4）。"""
    if isinstance(value, Decimal):
        d = value
    elif isinstance(value, str):
        try:
            d = Decimal(value.strip())
        except InvalidOperation as exc:  # noqa: BLE001
            raise CIDError(f"非法十进制输入 {field}={value!r}") from exc
    else:
        raise CIDError(f"CID 输入必须是 Decimal/str（不经 binary float）：{field}={value!r}")
    if not d.is_finite():
        raise CIDError(f"CID 输入必须为有限十进制（拒绝 NaN/±Infinity）：{field}={value!r}")
    return d


def canonical(value: Any) -> str:
    """canonical decimal serialization（round-27 R24-3 数值级回修）。

    规则（数值等价类唯一）：
      1. plain fixed-point 输出（禁 exponent / 科学计数法 / 前导正号 / 千分位 / 空白）；
      2. 裁剪小数部分所有非显著尾随零（Decimal("1.00") -> "1"）；
      3. 裁剪后小数部分为空则同时移除小数点（Decimal("1525.0") -> "1525"）；
      4. 数值为零（含负零）统一输出 "0"（Decimal("-0.000") -> "0"）；
      5. exponent 输入先展开为 fixed-point（Decimal("1E+3") -> "1000"）；
      6. 整数无小数点；小数至少一位小数位。
    """
    d = _to_decimal(value)
    if d.is_zero():
        return "0"
    s = format(d, "f")  # plain fixed-point，展开 exponent
    if "." in s:
        s = s.rstrip("0").rstrip(".")
    return s


def _quantize(value: Decimal, quantum: Decimal, field: str, max_int_digits: int) -> Decimal:
    """在冻结 Context(prec=60, ROUND_HALF_UP) 内量化并校验整数位上限（R66-2）。

    覆盖 ambient context 污染：quantize 不使用调用线程全局 precision，而是 localcontext(CID_CONTEXT)。
    max_int_digits 用于校验存储列宽（numeric(12,6)=6 位整数；numeric(18,6)=12 位整数）。
    """
    with localcontext(CID_CONTEXT):
        q = value.quantize(quantum, rounding=ROUND_HALF_UP)
    limit = Decimal(10) ** max_int_digits
    if q.copy_abs() >= limit:
        raise CIDError(
            f"{field} 量化结果超出 {max_int_digits} 位整数上限：{q} (abs >= {limit})"
        )
    return q


def quantize_ratio(value: Any) -> Decimal:
    """N/O/T/X 持久化量化 numeric(12,6)（ROUND_HALF_UP；冻结 prec=60；仅存储投影，不回流）。"""
    return _quantize(_to_decimal(value), RATIO_QUANTIZE, "ratio", max_int_digits=6)


def quantize_numeric18_6(value: Any) -> Decimal:
    """金额项 M/Q/R 持久化量化 numeric(18,6)（ROUND_HALF_UP；冻结 prec=60）。"""
    return _quantize(_to_decimal(value), Decimal("0.000001"), "amount", max_int_digits=12)


class CIDError(Exception):
    """CID 输入契约错误（引擎不负责平台/策略；仅输入非法时抛出）。"""


def compute(
    inputs: Mapping[str, Any],
    roi_buffer: Any = "0.1",
    consumption_rebate_rate: Optional[Any] = "0.05",
    tech_hi: Any = "0.036",
    tech_lo: Any = "0.055",
    formula_version: str = FORMULA_VERSION,
) -> dict[str, Any]:
    """执行 CID 公式链，返回结构化 envelope（cid-engine-spec §四）。

    inputs 键：K/J/I/H/G/L/U（L 可缺省 -> 默认 0 + FIELD_DEFAULTED）。
    费率参数：roi_buffer 默认 0.1；consumption_rebate_rate 允许 None（来源缺失 -> 标记且按 0 计算）
    或显式 0（REBATE_NOT_APPLICABLE）；tech_hi/tech_lo 默认 0.036/0.055。
    """
    # ---- 输入解析与必需性（_to_decimal 负责 Decimal/str + finite 校验，R66-4）----
    values_in: dict[str, Decimal] = {}
    missing = [f for f in REQUIRED_FIELDS if inputs.get(f) is None]
    if missing:
        return {
            "status": "insufficient_data",
            "blocking_error": "REQUIRED_FIELD_MISSING",
            "quality_flags": [],
            "business_flags": [],
            "field_details": [
                {"field": f, "source_state": "missing", "default_applied": False} for f in missing
            ],
            "values": None,
            "bid_rounded_cents": None,
            "formula_version": formula_version,
            "decimal_precision": DECIMAL_PRECISION,
            "rounding_mode": ROUNDING_MODE,
        }
    for f in REQUIRED_FIELDS:
        values_in[f] = _to_decimal(inputs[f], f)

    quality: list[str] = []
    business: list[str] = []
    field_details: list[dict[str, Any]] = []

    # L 缺省 -> 0 + FIELD_DEFAULTED
    if inputs.get(L_FIELD) is None:
        values_in[L_FIELD] = Decimal("0")
        quality.append("FIELD_DEFAULTED")
        field_details.append({"field": L_FIELD, "source_state": "missing", "default_applied": True})
    else:
        values_in[L_FIELD] = _to_decimal(inputs[L_FIELD], L_FIELD)

    # 费率参数（默认值；rebate 允许 None=来源缺失）
    rb = _to_decimal(roi_buffer, "roi_buffer")
    if consumption_rebate_rate is None:
        rebate = Decimal("0")
        quality.append("REBATE_SOURCE_MISSING")
        field_details.append(
            {"field": "consumption_rebate_rate", "source_state": "missing", "default_applied": True}
        )
    else:
        rebate = _to_decimal(consumption_rebate_rate, "consumption_rebate_rate")
        if rebate.is_zero():
            business.append("REBATE_NOT_APPLICABLE")
    hi = _to_decimal(tech_hi, "tech_hi")
    lo = _to_decimal(tech_lo, "tech_lo")

    K, J, I = values_in["K"], values_in["J"], values_in["I"]
    H, G, L, U = values_in["H"], values_in["G"], values_in["L"], values_in["U"]

    def insufficient(blocking: str) -> dict[str, Any]:
        return {
            "status": "insufficient_data",
            "blocking_error": blocking,
            "quality_flags": quality,
            "business_flags": business,
            "field_details": field_details,
            "values": None,
            "bid_rounded_cents": None,
            "formula_version": formula_version,
            "decimal_precision": DECIMAL_PRECISION,
            "rounding_mode": ROUNDING_MODE,
        }

    # ---- 同一 Context(prec=60, ROUND_HALF_UP) 一次算完 ----
    with localcontext(CID_CONTEXT):
        M = K - J - I - H - G - L
        if M <= 0:
            return insufficient("M_NON_POSITIVE")
        N = K / M
        O = N + rb
        if O == 0:
            return insufficient("O_ZERO")
        P = K / O
        if P == 0:
            return insufficient("P_ZERO")
        if U <= 0:
            return insufficient("U_NON_POSITIVE")
        Q = P * rebate
        R = K * hi - K * lo
        S = K - P - J - I - H - G + R + Q  # 原件不减 L
        T = S / P
        V = P / U
        X = O * U
        bid = P.quantize(Decimal("1"), rounding=ROUND_HALF_UP)

    if S <= 0:
        business.append("S_NON_POSITIVE")

    return {
        "status": "calculated",
        "blocking_error": None,
        "quality_flags": quality,
        "business_flags": business,
        "field_details": field_details,
        "values": {k: canonical(v) for k, v in [("M", M), ("N", N), ("O", O), ("P", P),
                                                ("Q", Q), ("R", R), ("S", S), ("T", T),
                                                ("V", V), ("X", X)]},
        "bid_rounded_cents": int(bid),
        "formula_version": formula_version,
        "decimal_precision": DECIMAL_PRECISION,
        "rounding_mode": ROUNDING_MODE,
    }


def cid_results_payload(envelope: Mapping[str, Any]) -> dict[str, Any]:
    """pricing_decisions.cid_results 持久化 JSON 形状（values + 公式版本 + 精度 + rounding）。"""
    return {
        "values": envelope.get("values"),
        "formula_version": envelope.get("formula_version"),
        "decimal_precision": envelope.get("decimal_precision"),
        "rounding_mode": envelope.get("rounding_mode"),
    }


# ---------------------------------------------------------------------------
# R66-1：cost_snapshots / pricing_decisions 读写 adapter（纯 Mapping，不经 ORM/float）
# ---------------------------------------------------------------------------
# cost_snapshots 输入列 -> CID 字母（v6 §2.5）
COST_SNAPSHOT_INPUT_COLS = {
    "k_price": "K",
    "j_service_fee": "J",
    "i_refund_reserve": "I",
    "h_shipping": "H",
    "g_product_cost": "G",
    "l_tax": "L",
}


def cost_snapshot_to_compute(
    row: Mapping[str, Any],
    u: Any,
    rates: Mapping[str, Any],
    formula_version: str = FORMULA_VERSION,
) -> dict[str, Any]:
    """cost_snapshots 行 -> compute() 入参 bundle（R66-1 / R68-1）。

    row 键：k_price/j_service_fee/i_refund_reserve/h_shipping/g_product_cost 必需；l_tax 可缺省
      （缺省由 compute() 走 FIELD_DEFAULTED）；u=回传数（numeric(8,4)）；
    rates 键：roi_buffer/consumption_rebate_rate/tech_hi/tech_lo（rebate 可 None=来源缺失）。
    返回 dict：{"inputs": {...}, "roi_buffer":..., "consumption_rebate_rate":..., "tech_hi":...,
                "tech_lo":..., "formula_version":...}，可直接 **result 解包给 compute()；
    该 bundle 也是 pricing_decision_persist() 的完整输入（R68-1：12 键 cid_inputs 唯一来源）。
    """
    missing = [c for c in COST_SNAPSHOT_INPUT_COLS if c != "l_tax" and row.get(c) is None]
    if missing:
        raise CIDError(f"cost_snapshots 缺必需输入列: {missing}")
    inputs = {key: row[col] for col, key in COST_SNAPSHOT_INPUT_COLS.items()
              if key != "L" or row.get(col) is not None}
    inputs["U"] = u
    return {
        "inputs": inputs,
        "roi_buffer": rates["roi_buffer"],
        "consumption_rebate_rate": rates.get("consumption_rebate_rate"),
        "tech_hi": rates["tech_hi"],
        "tech_lo": rates["tech_lo"],
        "formula_version": formula_version,
    }


def cost_snapshot_persist(envelope: Mapping[str, Any]) -> dict[str, Any]:
    """cost_snapshots 存储投影：M->ad_pre_margin、Q->consumption_rebate、R->technical_rebate（numeric(18,6)）。

    calculated 时返回三键投影；否则返回空 dict（引擎不产生部分投影）。全程 Decimal，不经 float。
    """
    if envelope.get("status") != "calculated":
        return {}
    return {
        "ad_pre_margin": quantize_numeric18_6(envelope["values"]["M"]),
        "consumption_rebate": quantize_numeric18_6(envelope["values"]["Q"]),
        "technical_rebate": quantize_numeric18_6(envelope["values"]["R"]),
    }


# pricing_decisions.cid_inputs 冻结键集（15-数据字典.md:579「含费率 + 公式版本」；R68-1 12 键 exact-set）
CID_INPUT_KEYS = ("K", "J", "I", "H", "G", "L", "U",
                  "roi_buffer", "consumption_rebate_rate", "tech_hi", "tech_lo",
                  "formula_version")


def pricing_decision_persist(
    envelope: Mapping[str, Any],
    compute_bundle: Mapping[str, Any],
) -> dict[str, Any]:
    """pricing_decisions 存储投影（R66-1 / R68-1）。

    输入必须是 cost_snapshot_to_compute() 的完整 bundle（inputs + 4 费率 + formula_version）；
    calculated 时：
      - bid_unrounded = P numeric(18,6)；bid_rounded_cents；rounding_mode；
      - cid_inputs = 12 键 exact-set：K/J/I/H/G/L/U 走 canonical（L 缺省按 0），
        roi_buffer/tech_hi/tech_lo canonical，consumption_rebate_rate canonical（None -> JSON null，
        语义由 envelope.REBATE_SOURCE_MISSING 保留），formula_version 原样保存；
      - cid_results = 既有 payload。
    非 calculated：返回空 dict（**不创建 pricing_decisions**，避免违反 cid_inputs/cid_results NOT NULL）。
    """
    if envelope.get("status") != "calculated":
        return {}
    inputs = compute_bundle["inputs"]
    cid_inputs: dict[str, Any] = {}
    for k in ("K", "J", "I", "H", "G", "U"):
        cid_inputs[k] = canonical(inputs[k])
    cid_inputs["L"] = canonical(inputs.get("L", "0"))  # L 缺省由 compute 走 FIELD_DEFAULTED
    cid_inputs["roi_buffer"] = canonical(compute_bundle["roi_buffer"])
    rebate = compute_bundle.get("consumption_rebate_rate")
    cid_inputs["consumption_rebate_rate"] = None if rebate is None else canonical(rebate)
    cid_inputs["tech_hi"] = canonical(compute_bundle["tech_hi"])
    cid_inputs["tech_lo"] = canonical(compute_bundle["tech_lo"])
    cid_inputs["formula_version"] = compute_bundle.get(
        "formula_version", envelope.get("formula_version", FORMULA_VERSION)
    )
    return {
        "bid_unrounded": quantize_numeric18_6(envelope["values"]["P"]),
        "bid_rounded_cents": envelope["bid_rounded_cents"],
        "rounding_mode": envelope["rounding_mode"],
        "cid_inputs": cid_inputs,
        "cid_results": cid_results_payload(envelope),
    }
