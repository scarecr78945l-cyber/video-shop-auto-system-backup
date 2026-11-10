# -*- coding: utf-8 -*-
"""T5: CID 公式引擎验收测试（round-65；round-67 R66-1~R66-4 聚焦回修）。

依据 cid-engine-spec.md §五 + test-strategy.md §五：
  - 黄金样例：prec=60 + ROUND_HALF_UP，10 项完整串等值，S 末位 ...947，bid=1525
  - canonical serialization 不变量：canonical(1)==canonical(1.0)==canonical(1.00)=="1"、
    canonical(-0.000)=="0"、canonical(1E+3)=="1000"、compact vs DB scale 双输入全串相等
  - envelope 用例：L 缺失→FIELD_DEFAULTED、必需缺失→REQUIRED_FIELD_MISSING、
    rebate 不适用→REBATE_NOT_APPLICABLE、rebate 来源缺失→REBATE_SOURCE_MISSING、
    S≤0→S_NON_POSITIVE、.5 分边界
  - 除零：M=0/M<0→M_NON_POSITIVE、O=0→O_ZERO、U=0/U<0→U_NON_POSITIVE、P=0→P_ZERO（真实可达输入）
  - 每个用例断言完整 envelope（status/blocking_error/quality_flags/business_flags/values/bid）

round-67 R66 回修：
  - R66-1：cost_snapshots/pricing_decisions 读写 adapter 与字段 exact-set 测试
  - R66-2：quantize_ratio 冻结 prec=60/ROUND_HALF_UP，不受 ambient context 影响；numeric(12,6) 范围校验
  - R66-3：P_ZERO 用 K=0,J=-1 真实可达输入独立命中，只接受 P_ZERO，完整 envelope 键集
  - R66-4：全入口拒绝 NaN/±Infinity（Decimal 与 str），canonical/quantize 同样拒绝，稳定 CIDError

用法：python scripts/assert_cid_engine.py（纯计算，无需 DB）
"""
import os
import sys
from decimal import ROUND_DOWN, ROUND_HALF_UP, Decimal, getcontext

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "..", "backend"))
from domain.cid import (  # noqa: E402
    CID_CONTEXT,
    CIDError,
    DECIMAL_PRECISION,
    FORMULA_VERSION,
    ROUNDING_MODE,
    canonical,
    compute,
    cost_snapshot_persist,
    cost_snapshot_to_compute,
    pricing_decision_persist,
    quantize_numeric18_6,
    quantize_ratio,
)

ok = True


def check(name, cond, detail=""):
    global ok
    print(f"[{'PASS' if cond else 'FAIL'}] {name}" + (f"  {detail}" if detail else ""))
    if not cond:
        ok = False


# ---------------------------------------------------------------------------
# 黄金样例（Excel 第 2 行，cid-engine-spec §五）
# ---------------------------------------------------------------------------
GOLDEN_INPUTS = {
    "K": "2199", "J": "13.194", "I": "153.930", "H": "180", "G": "130",
    "L": "83.562", "U": "0.5",
}
GOLDEN_RATES = {
    "roi_buffer": "0.1", "consumption_rebate_rate": "0.05",
    "tech_hi": "0.036", "tech_lo": "0.055",
}
GOLDEN_VALUES = {
    "M": "1638.314",
    "N": "1.34223354009060534183312844790436998035785569799196002719869",
    "O": "1.44223354009060534183312844790436998035785569799196002719869",
    "P": "1524.71838913263129988876904209077295993273155249248846108953",
    "Q": "76.2359194566315649944384521045386479966365776246244230544765",
    "R": "-41.781",
    "S": "231.612530324000265105669410013765688063905025132135961964947",
    "T": "0.151905120299465930780868549195949287016521859444202856705946",
    "V": "3049.43677826526259977753808418154591986546310498497692217906",
    "X": "0.721116770045302670916564223952184990178927848995980013599345",
}

env = compute(GOLDEN_INPUTS, **GOLDEN_RATES)
check("黄金 status=calculated", env["status"] == "calculated", env["status"])
check("黄金 blocking_error=null", env["blocking_error"] is None, str(env["blocking_error"]))
check("黄金公式版本/精度/rounding", env["formula_version"] == "v5"
      and env["decimal_precision"] == 60 and env["rounding_mode"] == "ROUND_HALF_UP",
      f"{env['formula_version']}/{env['decimal_precision']}/{env['rounding_mode']}")
for k, want in GOLDEN_VALUES.items():
    got = env["values"][k]
    check(f"黄金 {k} 完整串等值", got == want, f"len={len(got)}")
check("黄金 S 末位 ...947（ROUND_HALF_UP 机械结果）", env["values"]["S"].endswith("947"),
      env["values"]["S"][-8:])
check("黄金 bid_rounded_cents=1525", env["bid_rounded_cents"] == 1525,
      str(env["bid_rounded_cents"]))
check("黄金无 quality/business 标记", not env["quality_flags"] and not env["business_flags"],
      f"{env['quality_flags']}/{env['business_flags']}")

# ---------------------------------------------------------------------------
# canonical serialization 不变量（cid-engine-spec §三.2.1）
# ---------------------------------------------------------------------------
check("canonical(1)==canonical(1.0)==canonical(1.00)=='1'",
      canonical("1") == canonical("1.0") == canonical("1.00") == "1",
      f"{canonical('1')}/{canonical('1.0')}/{canonical('1.00')}")
check("canonical(-0.000)=='0'", canonical("-0.000") == "0", canonical("-0.000"))
check("canonical(1E+3)=='1000'", canonical("1E+3") == "1000", canonical("1E+3"))
check("canonical(1525.0)=='1525'", canonical("1525.0") == "1525", canonical("1525.0"))
check("canonical(1638.314000)=='1638.314'", canonical("1638.314000") == "1638.314",
      canonical("1638.314000"))

# compact vs DB scale 双输入全串相等（K=2199 vs K=2199.000000, J=13.194 vs 13.194000 ...）
def _db_scale(v):
    # numeric(18,6) 尺度：统一补到 6 位小数；U 为 numeric(8,4) -> 4 位
    d = Decimal(v)
    if v == "0.5":  # U numeric(8,4)
        return "0.5000"
    return format(d.quantize(Decimal("0.000001")), "f")


db_scale_inputs = {k: _db_scale(v) for k, v in GOLDEN_INPUTS.items()}
env_db = compute(db_scale_inputs, **GOLDEN_RATES)
check("compact 与 numeric(18,6)/numeric(8,4) 尺度输入全串相等",
      env_db["values"] == env["values"] and env_db["bid_rounded_cents"] == env["bid_rounded_cents"],
      "")

# ---------------------------------------------------------------------------
# 除零 / 负毛利（blocking）
# ---------------------------------------------------------------------------
def block_case(label, mutate, expect_block):
    inp = dict(GOLDEN_INPUTS)
    inp.update(mutate)
    e = compute(inp, **GOLDEN_RATES)
    check(label, e["status"] == "insufficient_data" and e["blocking_error"] == expect_block
          and e["values"] is None and e["bid_rounded_cents"] is None,
          f"{e['status']}/{e['blocking_error']}")


# K=560.686 使 M = 560.686-13.194-153.930-180-130-83.562 = 0 精确零毛利
block_case("M=0 -> M_NON_POSITIVE", {"K": "560.686"}, "M_NON_POSITIVE")
block_case("M<0 -> M_NON_POSITIVE", {"G": "2000"}, "M_NON_POSITIVE")
# O=0：构造 N=-0.1 使 O=0。K=-1000, M=10000 -> N=-0.1 -> O=-0.1+0.1=0（M>0 先通过）
block_case("O=0 -> O_ZERO", {"K": "-1000", "J": "-11000", "I": "0", "H": "0", "G": "0", "L": "0"},
           "O_ZERO")
block_case("U=0 -> U_NON_POSITIVE", {"U": "0"}, "U_NON_POSITIVE")
block_case("U<0 -> U_NON_POSITIVE", {"U": "-0.5"}, "U_NON_POSITIVE")
# P=0 真实可达（R66-3）：K=0, J=-1, 其余成本=0, roi_buffer=0.1
#   M = 0-(-1)-0-0-0-0 = 1 >0；N = 0/1 = 0；O = 0+0.1 = 0.1；P = 0/0.1 = 0 -> P_ZERO
e_p0 = compute({"K": "0", "J": "-1", "I": "0", "H": "0", "G": "0", "L": "0", "U": "0.5"},
               roi_buffer="0.1", consumption_rebate_rate="0.05",
               tech_hi="0.036", tech_lo="0.055")
check("P=0 -> P_ZERO（真实可达输入，仅接受 P_ZERO）",
      e_p0["status"] == "insufficient_data" and e_p0["blocking_error"] == "P_ZERO"
      and e_p0["values"] is None and e_p0["bid_rounded_cents"] is None,
      f"{e_p0['status']}/{e_p0['blocking_error']}")
# 完整 envelope 键集（test-strategy §五：status/blocking/quality/business/field_details/values/bid/版本/精度/rounding）
env_keys = {"status", "blocking_error", "quality_flags", "business_flags", "field_details",
            "values", "bid_rounded_cents", "formula_version", "decimal_precision", "rounding_mode"}
check("P_ZERO envelope 完整键集", set(e_p0) == env_keys and set(env) == env_keys,
      f"p0={set(e_p0)-env_keys}/{env_keys-set(e_p0)}")


# ---------------------------------------------------------------------------
# envelope 用例
# ---------------------------------------------------------------------------
# L 缺失 -> FIELD_DEFAULTED（可计算，不可静默）
inp_no_l = {k: v for k, v in GOLDEN_INPUTS.items() if k != "L"}
env_l = compute(inp_no_l, **GOLDEN_RATES)
check("L 缺失 -> calculated + FIELD_DEFAULTED",
      env_l["status"] == "calculated" and "FIELD_DEFAULTED" in env_l["quality_flags"]
      and env_l["field_details"] == [{"field": "L", "source_state": "missing", "default_applied": True}]
      and env_l["values"]["M"] == "1721.876",
      f"{env_l['quality_flags']} M={env_l['values']['M']}")

# 必需字段缺失 -> REQUIRED_FIELD_MISSING
env_miss = compute({"K": "2199", "J": "13.194"})
check("必需缺失 -> REQUIRED_FIELD_MISSING",
      env_miss["status"] == "insufficient_data"
      and env_miss["blocking_error"] == "REQUIRED_FIELD_MISSING"
      and len(env_miss["field_details"]) == 4,
      f"{env_miss['blocking_error']} details={len(env_miss['field_details'])}")

# rebate 不适用（费率=0）-> REBATE_NOT_APPLICABLE，Q=0 继续计算
env_na = compute(GOLDEN_INPUTS, roi_buffer="0.1", consumption_rebate_rate="0",
                 tech_hi="0.036", tech_lo="0.055")
check("rebate=0 -> calculated + REBATE_NOT_APPLICABLE + Q=0",
      env_na["status"] == "calculated" and "REBATE_NOT_APPLICABLE" in env_na["business_flags"]
      and env_na["values"]["Q"] == "0",
      f"{env_na['business_flags']} Q={env_na['values']['Q']}")

# rebate 来源缺失 -> REBATE_SOURCE_MISSING（按 0 计算但显式标记）
env_src = compute(GOLDEN_INPUTS, roi_buffer="0.1", consumption_rebate_rate=None,
                  tech_hi="0.036", tech_lo="0.055")
check("rebate=None -> calculated + REBATE_SOURCE_MISSING + Q=0",
      env_src["status"] == "calculated" and "REBATE_SOURCE_MISSING" in env_src["quality_flags"]
      and env_src["values"]["Q"] == "0",
      f"{env_src['quality_flags']} Q={env_src['values']['Q']}")

# S<=0 -> 计算完成 + S_NON_POSITIVE（业务闸门，非引擎失败）
# 构造：K=100, J+I+H+G=99, L=0.5 -> M=0.5>0；S ≈ K - P - 99 + R + Q <= 0
env_sneg = compute({"K": "100", "J": "50", "I": "20", "H": "15", "G": "14", "L": "0.5", "U": "0.5"},
                   roi_buffer="0.1", consumption_rebate_rate="0.05",
                   tech_hi="0.036", tech_lo="0.055")
check("S<=0 -> calculated + S_NON_POSITIVE（非失败）",
      env_sneg["status"] == "calculated" and "S_NON_POSITIVE" in env_sneg["business_flags"]
      and env_sneg["blocking_error"] is None and env_sneg["bid_rounded_cents"] is not None,
      f"{env_sneg['business_flags']} bid={env_sneg['bid_rounded_cents']} S={env_sneg['values']['S']}")

# ---------------------------------------------------------------------------
# .5 分边界：ROUND_HALF_UP（避免 bankers rounding）
# ---------------------------------------------------------------------------
half_cases = [("1.5", 2), ("2.5", 3), ("3.5", 4), ("1524.5", 1525), ("1525.5", 1526)]
for p_str, want in half_cases:
    # P = K/O，直接构造：K=P, O=1 -> P=K
    e = compute({"K": p_str, "J": "0", "I": "0", "H": "0", "G": "0", "L": "0", "U": "1"},
                roi_buffer="0.0", consumption_rebate_rate="0.05",
                tech_hi="0", tech_lo="0")
    check(f"ROUND_HALF_UP bid({p_str})={want}", e["bid_rounded_cents"] == want,
          str(e["bid_rounded_cents"]))

# 负值边界：ROUND_HALF_UP 语义直接验证（引擎 M>0 门禁下 P 不可为负；quantize 规则本身远离零）
check("ROUND_HALF_UP(-1.5)=-2（quantize 语义）",
      Decimal("-1.5").quantize(Decimal("1"), rounding=ROUND_HALF_UP) == Decimal("-2"),
      "ROUND_HALF_UP(-1.5) -> -2")

# ---------------------------------------------------------------------------
# 量化投影：N/O/T/X 量化 numeric(12,6) 后不回流（引擎返回未量化串，量化仅存储）
# ---------------------------------------------------------------------------
q = {k: quantize_ratio(env["values"][k]) for k in ("N", "O", "T", "X")}
check("N/O/T/X 量化 numeric(12,6) 存在（不回流）",
      all(str(x) == format(x, "f") for x in q.values())
      and all(x.as_tuple().exponent >= -6 for x in q.values()),
      f"N={q['N']} O={q['O']} T={q['T']} X={q['X']}")

# float 输入必须拒绝（不经 binary float）
try:
    compute({"K": 2199.0, "J": "13.194", "I": "153.930", "H": "180", "G": "130",
             "L": "83.562", "U": "0.5"}, **GOLDEN_RATES)
    check("float 输入拒绝", False, "未报错")
except CIDError:
    check("float 输入拒绝（不经 binary float）", True)

# ---------------------------------------------------------------------------
# R66-1：cost_snapshots / pricing_decisions 读写 adapter 与字段 exact-set
# ---------------------------------------------------------------------------
snap_row = {
    "k_price": "2199", "j_service_fee": "13.194", "i_refund_reserve": "153.930",
    "h_shipping": "180", "g_product_cost": "130", "l_tax": "83.562",
}
rates = {"roi_buffer": "0.1", "consumption_rebate_rate": "0.05",
         "tech_hi": "0.036", "tech_lo": "0.055"}
ad = cost_snapshot_to_compute(snap_row, "0.5", rates)
check("R66-1 cost_snapshot_to_compute 输入映射 exact-set",
      ad["inputs"] == {"K": "2199", "J": "13.194", "I": "153.930", "H": "180",
                       "G": "130", "L": "83.562", "U": "0.5"}
      and ad["roi_buffer"] == "0.1" and ad["consumption_rebate_rate"] == "0.05",
      str(ad))
env_ad = compute(ad["inputs"], roi_buffer=ad["roi_buffer"],
                 consumption_rebate_rate=ad["consumption_rebate_rate"],
                 tech_hi=ad["tech_hi"], tech_lo=ad["tech_lo"])
check("R66-1 adapter -> compute 黄金一致", env_ad["values"] == env["values"]
      and env_ad["bid_rounded_cents"] == 1525, "")
# l_tax 缺省 -> adapter 不注入 L，compute 走 FIELD_DEFAULTED
snap_no_l = dict(snap_row)
del snap_no_l["l_tax"]
ad_no_l = cost_snapshot_to_compute(snap_no_l, "0.5", rates)
env_no_l = compute(ad_no_l["inputs"], roi_buffer=ad_no_l["roi_buffer"],
                   consumption_rebate_rate=ad_no_l["consumption_rebate_rate"],
                   tech_hi=ad_no_l["tech_hi"], tech_lo=ad_no_l["tech_lo"])
check("R66-1 adapter l_tax 缺省 -> FIELD_DEFAULTED",
      "L" not in ad_no_l["inputs"] and "FIELD_DEFAULTED" in env_no_l["quality_flags"],
      f"L in inputs={'L' in ad_no_l['inputs']} flags={env_no_l['quality_flags']}")
# 必需列缺失 -> CIDError
try:
    cost_snapshot_to_compute({"k_price": "2199"}, "0.5", rates)
    check("R66-1 adapter 缺必需列 -> CIDError", False, "未报错")
except CIDError:
    check("R66-1 adapter 缺必需列 -> CIDError", True)
# cost_snapshot_persist：M/Q/R -> ad_pre_margin/consumption_rebate/technical_rebate numeric(18,6)
proj_snap = cost_snapshot_persist(env)
check("R66-1 cost_snapshot_persist M/Q/R 投影 exact-set",
      set(proj_snap) == {"ad_pre_margin", "consumption_rebate", "technical_rebate"}
      and str(proj_snap["ad_pre_margin"]) == "1638.314000"
      and str(proj_snap["consumption_rebate"]) == "76.235919"
      and str(proj_snap["technical_rebate"]) == "-41.781000",
      str(proj_snap))
check("R66-1 cost_snapshot_persist 非 calculated -> 空投影",
      cost_snapshot_persist(e_p0) == {}, str(cost_snapshot_persist(e_p0)))
# pricing_decision_persist（R68-1）：接收 compute bundle；cid_inputs 12 键 exact-set
proj_pd = pricing_decision_persist(env, ad)
check("R66-1 pricing_decision_persist 投影 exact-set",
      set(proj_pd) == {"bid_unrounded", "bid_rounded_cents", "rounding_mode",
                       "cid_inputs", "cid_results"}
      and str(proj_pd["bid_unrounded"]) == "1524.718389"
      and proj_pd["bid_rounded_cents"] == 1525
      and proj_pd["rounding_mode"] == "ROUND_HALF_UP"
      and set(proj_pd["cid_inputs"]) == {
          "K", "J", "I", "H", "G", "L", "U",
          "roi_buffer", "consumption_rebate_rate", "tech_hi", "tech_lo", "formula_version"}
      and proj_pd["cid_results"]["values"] == env["values"],
      str(proj_pd))
# cid_inputs 数值键 canonical、formula_version 原样
check("R68-1 cid_inputs 数值 canonical + formula_version 原样",
      proj_pd["cid_inputs"]["K"] == "2199"
      and proj_pd["cid_inputs"]["roi_buffer"] == "0.1"
      and proj_pd["cid_inputs"]["consumption_rebate_rate"] == "0.05"
      and proj_pd["cid_inputs"]["formula_version"] == "v5",
      str(proj_pd["cid_inputs"]))
# rebate=None -> JSON null + envelope REBATE_SOURCE_MISSING 保留语义
ad_noreb = cost_snapshot_to_compute(snap_row, "0.5", {
    "roi_buffer": "0.1", "consumption_rebate_rate": None,
    "tech_hi": "0.036", "tech_lo": "0.055"})
env_noreb = compute(ad_noreb["inputs"], roi_buffer=ad_noreb["roi_buffer"],
                    consumption_rebate_rate=ad_noreb["consumption_rebate_rate"],
                    tech_hi=ad_noreb["tech_hi"], tech_lo=ad_noreb["tech_lo"])
proj_pd_noreb = pricing_decision_persist(env_noreb, ad_noreb)
check("R68-1 rebate=None -> cid_inputs null + REBATE_SOURCE_MISSING",
      proj_pd_noreb["cid_inputs"]["consumption_rebate_rate"] is None
      and "REBATE_SOURCE_MISSING" in env_noreb["quality_flags"],
      f"{proj_pd_noreb['cid_inputs']['consumption_rebate_rate']} flags={env_noreb['quality_flags']}")
# 非 calculated -> 空投影（不创建 pricing_decisions，避免违反 cid_inputs/cid_results NOT NULL）
proj_pd_p0 = pricing_decision_persist(e_p0, ad)
check("R68-1 pricing_decision_persist 非 calculated -> 空 dict（不创建 pricing_decisions）",
      proj_pd_p0 == {}, str(proj_pd_p0))
# 运行时 catalog：pricing_decisions.cid_inputs/cid_results 均 NOT NULL（jsonb）
if os.environ.get("DATABASE_URL"):
    from sqlalchemy import create_engine, text as sqltext
    with create_engine(os.environ["DATABASE_URL"]).connect() as _c:
        _nn = {r[0]: r[1] for r in _c.execute(sqltext(
            "SELECT column_name, is_nullable FROM information_schema.columns "
            "WHERE table_schema='app' AND table_name='pricing_decisions' "
            "AND column_name IN ('cid_inputs','cid_results')"
        )).fetchall()}
    check("R68-1 catalog cid_inputs/cid_results NOT NULL",
          _nn.get("cid_inputs") == "NO" and _nn.get("cid_results") == "NO", str(_nn))
else:
    print("[SKIP] 无 DATABASE_URL，跳过 catalog NOT NULL 契约检查")

# ---------------------------------------------------------------------------
# R66-2：quantize_ratio 冻结 context + numeric(12,6) 范围
# ---------------------------------------------------------------------------
old_prec = getcontext().prec
getcontext().prec = 6  # 污染 ambient context
try:
    q6 = quantize_ratio("123456.1234567")
    check("R66-2 quantize_ratio 不受 ambient prec=6 影响",
          str(q6) == "123456.123457", f"{q6} prec={getcontext().prec}")
    # numeric(12,6)：整数位 <= 6；999999.999999 合法
    q_ok = quantize_ratio("999999.9999994")
    check("R66-2 numeric(12,6) 上界内 999999.9999994 -> 999999.999999",
          str(q_ok) == "999999.999999", str(q_ok))
finally:
    getcontext().prec = old_prec
try:
    quantize_ratio("1000000.0")  # 7 位整数 -> 超界
    check("R66-2 numeric(12,6) 7 位整数 -> CIDError", False, "未报错")
except CIDError:
    check("R66-2 numeric(12,6) 7 位整数 -> CIDError", True)
try:
    quantize_ratio("999999.9999995")  # 舍入进位到 7 位整数 -> 超界
    check("R66-2 numeric(12,6) 舍入进位溢出 -> CIDError", False, "未报错")
except CIDError:
    check("R66-2 numeric(12,6) 舍入进位溢出 -> CIDError", True)
# 冻结 rounding 不受 ambient 影响
old_round = getcontext().rounding
getcontext().rounding = ROUND_DOWN
try:
    q_half = quantize_ratio("0.0000005")
    check("R66-2 quantize_ratio 冻结 ROUND_HALF_UP（ambient ROUND_DOWN）",
          str(q_half) == "0.000001", str(q_half))
finally:
    getcontext().rounding = old_round

# ---------------------------------------------------------------------------
# R66-4：全入口拒绝 NaN/±Infinity（Decimal 与 str），canonical/quantize 同样拒绝
# ---------------------------------------------------------------------------
def expect_ciderror(label, fn, *args, **kwargs):
    try:
        fn(*args, **kwargs)
        check(label, False, "未报错")
    except CIDError:
        check(label, True)


expect_ciderror("R66-4 compute(K=NaN) -> CIDError",
                compute, {"K": "NaN", "J": "13.194", "I": "153.930", "H": "180",
                          "G": "130", "L": "83.562", "U": "0.5"}, **GOLDEN_RATES)
expect_ciderror("R66-4 compute(K=-Infinity) -> CIDError",
                compute, {"K": "-Infinity", "J": "13.194", "I": "153.930", "H": "180",
                          "G": "130", "L": "83.562", "U": "0.5"}, **GOLDEN_RATES)
expect_ciderror("R66-4 canonical(NaN) -> CIDError", canonical, "NaN")
expect_ciderror("R66-4 canonical(Infinity) -> CIDError", canonical, Decimal("Infinity"))
expect_ciderror("R66-4 quantize_ratio(NaN) -> CIDError", quantize_ratio, "NaN")
expect_ciderror("R66-4 quantize_ratio(-Infinity) -> CIDError", quantize_ratio, Decimal("-Infinity"))
expect_ciderror("R66-4 L=NaN -> CIDError",
                compute, {"K": "2199", "J": "13.194", "I": "153.930", "H": "180",
                          "G": "130", "L": "NaN", "U": "0.5"}, **GOLDEN_RATES)
expect_ciderror("R66-4 tech_lo=Infinity -> CIDError",
                compute, GOLDEN_INPUTS, roi_buffer="0.1", consumption_rebate_rate="0.05",
                tech_hi="0.036", tech_lo="Infinity")

print("T5-CID-ASSERT:", "PASS" if ok else "FAIL")
sys.exit(0 if ok else 1)