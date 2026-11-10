# -*- coding: utf-8 -*-
"""P0-0 批 A 契约 round-27 回修自检：R24-3 数值级 canonical 不变量 + 回归。只读。"""
import hashlib, re, sys, os
from decimal import Decimal, ROUND_HALF_UP, getcontext

BASE = r"E:\新建文件夹 (6)\视频号小店全自动系统-方案文档\docs\contracts"
ENUM = BASE + r"\enum-registry.yaml"
ERR = BASE + r"\error-codes.yaml"
CID = BASE + r"\cid-engine-spec.md"

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

ok = True
def check(name, cond, detail=""):
    global ok
    print(f"[{'PASS' if cond else 'FAIL'}] {name}" + (f"  {detail}" if detail else ""))
    if not cond:
        ok = False

def sha256(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()

def canonical(d: Decimal) -> str:
    """规范十进制序列化：数值等价类唯一（round-27 R24-3）。
    - exponent 先展开为 fixed-point；禁前导正号/千分位/空白
    - 裁剪小数非显著尾随零；空小数部分移除小数点
    - 负零统一 '0'
    """
    if d.is_zero():
        return "0"
    s = format(d, "f")          # plain fixed-point（exponent 展开）
    if "." in s:
        s = s.rstrip("0")       # 裁剪小数尾随零
        if s.endswith("."):
            s = s[:-1]          # 空小数部分移除小数点
    return s

def cid_chain(K, J, I, H, G, L, U, buf, rebate, thi, tlo):
    M = K - J - I - H - G - L
    N = K / M; O = N + buf; P = K / O
    Q = P * rebate; R = K * thi - K * tlo
    S = K - P - J - I - H - G + R + Q
    T = S / P; V = P / U; X = O * U
    return {"M": M, "N": N, "O": O, "P": P, "Q": Q, "R": R, "S": S, "T": T, "V": V, "X": X}

# ---------- R24-3 数值级不变量 ----------
check("R24-3 canonical(1)==canonical(1.0)==canonical(1.00)=='1'",
      canonical(Decimal("1")) == canonical(Decimal("1.0")) == canonical(Decimal("1.00")) == "1",
      f"{canonical(Decimal('1'))}/{canonical(Decimal('1.0'))}/{canonical(Decimal('1.00'))}")
check("R24-3 canonical(-0.000)=='0'", canonical(Decimal("-0.000")) == "0", canonical(Decimal("-0.000")))
check("R24-3 canonical(1E+3)=='1000'", canonical(Decimal("1E+3")) == "1000", canonical(Decimal("1E+3")))
check("R24-3 canonical(1638.314000)=='1638.314'", canonical(Decimal("1638.314000")) == "1638.314", canonical(Decimal("1638.314000")))
check("R24-3 canonical(-41.781000000000) 裁剪", canonical(Decimal("-41.781000000000")) == "-41.781", canonical(Decimal("-41.781000000000")))
check("R24-3 canonical(1525.0)=='1525'", canonical(Decimal("1525.0")) == "1525", canonical(Decimal("1525.0")))

# ---------- R24-3 compact vs DB-scale 输入完整串相等 ----------
getcontext().prec = 60
getcontext().rounding = ROUND_HALF_UP
# compact 输入（业务示例表示）
c1 = cid_chain(Decimal("2199"), Decimal("13.194"), Decimal("153.930"),
               Decimal("180"), Decimal("130"), Decimal("83.562"),
               Decimal("0.5"), Decimal("0.1"), Decimal("0.05"),
               Decimal("0.036"), Decimal("0.055"))
# DB 字段尺度输入（numeric(18,6)/numeric(8,4)）
c2 = cid_chain(Decimal("2199.000000"), Decimal("13.194000"), Decimal("153.930000"),
               Decimal("180.000000"), Decimal("130.000000"), Decimal("83.562000"),
               Decimal("0.5000"), Decimal("0.1"), Decimal("0.05"),
               Decimal("0.036"), Decimal("0.055"))
diff = {k: (canonical(c1[k]), canonical(c2[k])) for k in c1 if canonical(c1[k]) != canonical(c2[k])}
check("R24-3 compact 输入 == DB scale 输入（canonical 后 10 项全等）", not diff, str(diff))

# ---------- R24-2 黄金串回归（canonical 后与黄金区一致） ----------
GOLDEN = {
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
gdiff = {k: (GOLDEN[k], canonical(c1[k])) for k in GOLDEN if canonical(c1[k]) != GOLDEN[k]}
check("R24-2 黄金串（canonical 后）10 项等值", not gdiff, str(gdiff))
bid = c1["P"].quantize(Decimal("1"), rounding=ROUND_HALF_UP)
check("R24-2 bid=1525", bid == Decimal("1525"))

# ---------- 回归：A1/A2/A3/A4/R24-1/R24-4 ----------
with open(ENUM, encoding="utf-8") as f:
    et = f.read()
names = re.findall(r"^\s+- name: (enum_\w+)$", et, re.M)
check("A1 enum entries=60", len(names) == 60, f"got {len(names)}")
check("A1 default_count=32", "default_count: 32" in et)

with open(ERR, encoding="utf-8") as f:
    et2 = f.read()
codes = re.findall(r"^\s+- code: (\w+)$", et2, re.M)
check("A2 error entries=16", len(codes) == 16, f"got {len(codes)}")
def _blk(txt, code):
    for p in re.split(r"^\s+- code:", txt, flags=re.M)[1:]:
        if re.match(rf"\s*{code}\b", p):
            return p
    return ""
retryable_codes = [c for c in codes if re.search(r"retryable: true", _blk(et2, c))]
check("A2 retryable exact-set=5", set(retryable_codes) == {"RATE_LIMIT","TIMEOUT","NO_MATCH","INSUFFICIENT_REFERENCES","UNEXPECTED"}, str(retryable_codes))
ue = _blk(et2, "UNEXPECTED")
check("A3 UNEXPECTED 语义", "retryable: true" in ue and "backoff_seconds: 60" in ue and "terminal: false" in ue)
owners = re.findall(r"owner: (\S+)", et2)
check("A4 无 owner=dsh", "dsh" not in owners, str(set(owners)))
sup = [c for c in codes if re.search(r"^\s+supersedes:", _blk(et2, c), re.M)]
check("R24-1 supersedes 仅 UNEXPECTED/PAGE_CHANGED", set(sup) == {"UNEXPECTED","PAGE_CHANGED"}, str(sup))

with open(CID, encoding="utf-8") as f:
    ct = f.read()
check("R24-4 L 行 FIELD_DEFAULTED", "FIELD_DEFAULTED(field=L)" in ct and "标记 FIELD_MISSING" not in ct)

print()
print("enum-registry.yaml  bytes:", os.path.getsize(ENUM), " sha256:", sha256(ENUM))
print("error-codes.yaml    bytes:", os.path.getsize(ERR), " sha256:", sha256(ERR))
print("cid-engine-spec.md  bytes:", os.path.getsize(CID), " sha256:", sha256(CID))
print()
print("SELF-CHECK:", "PASS" if ok else "FAIL")
sys.exit(0 if ok else 1)
