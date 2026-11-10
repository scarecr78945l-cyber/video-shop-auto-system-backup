# -*- coding: utf-8 -*-
"""P0-0 批 A 契约 round-25 二次回修自检：R24-1~R24-4 全部断言 + 哈希。只读。"""
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

def code_block(txt, code):
    parts = re.split(r"^\s+- code:", txt, flags=re.M)[1:]
    for p in parts:
        if re.match(rf"\s*{code}\b", p):
            return p
    return ""

# ---------- 回归：A1 enum defaults ----------
with open(ENUM, encoding="utf-8") as f:
    et = f.read()
names = re.findall(r"^\s+- name: (enum_\w+)$", et, re.M)
check("A1 enum entries=60", len(names) == 60, f"got {len(names)}")
m = re.search(r"default_count:\s*(\d+)", et)
check("A1 default_count=32", m and int(m.group(1)) == 32, m.group(1) if m else "missing")
dm = re.search(r"^defaults:\n((?:  \S+: .*\n?)+)", et, re.M)
defaults_raw = {}
if dm:
    for line in dm.group(1).splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            defaults_raw[k.strip()] = v.strip()
check("A1 defaults=32 项", len(defaults_raw) == 32, f"got {len(defaults_raw)}")

# ---------- R24-1: supersedes schema（9 必需 + 可选） ----------
with open(ERR, encoding="utf-8") as f:
    et2 = f.read()
codes = re.findall(r"^\s+- code: (\w+)$", et2, re.M)
check("A2 error entries=16", len(codes) == 16, f"got {len(codes)}")
REQ_ATTRS = ["category","retryable","backoff_seconds","manual_takeover","terminal","http_mapping","owner","evidence_required"]
schema_bad = []
supersede_codes = []
for c in codes:
    blk = code_block(et2, c)
    missing = [a for a in REQ_ATTRS if not re.search(rf"^\s+{a}:", blk, re.M)]
    if missing:
        schema_bad.append((c, missing))
    # 允许的额外字段：仅 supersedes（字符串）
    keys = re.findall(r"^\s+([a-z_]+):", blk, re.M)
    extra = [k for k in keys if k not in REQ_ATTRS and k != "supersedes" and k != "code"]
    if extra:
        schema_bad.append((c, "unknown-extra:" + str(extra)))
    if "supersedes" in keys:
        supersede_codes.append(c)
check("R24-1 每项 9 必需属性无缺失、无未知字段", not schema_bad, str(schema_bad[:4]))
check("R24-1 supersedes 仅 UNEXPECTED/PAGE_CHANGED", set(supersede_codes) == {"UNEXPECTED","PAGE_CHANGED"}, str(supersede_codes))
# supersedes 值为字符串
sup_bad = []
for c in supersede_codes:
    blk = code_block(et2, c)
    sv = re.search(r"^\s+supersedes: (.+)$", blk, re.M)
    if not sv or not sv.group(1).strip().startswith('"'):
        sup_bad.append(c)
check("R24-1 supersedes 为字符串", not sup_bad, str(sup_bad))

# ---------- 回归：A2/A3/A4 ----------
rm = re.search(r"^retry_policies:\n((?:  \w+: \{.*\}\n?)+)", et2, re.M)
pol = {}
if rm:
    for line in rm.group(1).splitlines():
        k, v = line.split(":", 1)
        pol[k.strip()] = v.strip()
retryable_codes = [c for c in codes if re.search(r"retryable: true", code_block(et2, c))]
expected_retry = {"RATE_LIMIT","TIMEOUT","NO_MATCH","INSUFFICIENT_REFERENCES","UNEXPECTED"}
check("A2 retryable exact-set=5", set(retryable_codes) == expected_retry, str(retryable_codes))
check("A2 retry_policies 双向 exact-set", set(pol.keys()) == expected_retry, str(pol.keys()))
ue = code_block(et2, "UNEXPECTED")
check("A3 UNEXPECTED retryable=true/backoff=60/terminal=false", "retryable: true" in ue and "backoff_seconds: 60" in ue and "terminal: false" in ue)
owners = re.findall(r"owner: (\S+)", et2)
check("A4 无 owner=dsh", "dsh" not in owners, str(set(owners)))

# ---------- R24-2: 显式 ROUND_HALF_UP 完整串复算 ----------
# 注：必须设置全局 getcontext().prec=60 + rounding=ROUND_HALF_UP，并用裸运算符链
#     （不要混用 ctx.divide/ctx.multiply 与裸 +/-，否则中间量化不一致）。
getcontext().prec = 60
getcontext().rounding = ROUND_HALF_UP
K = Decimal("2199"); J = Decimal("13.194"); I = Decimal("153.930")
H = Decimal("180"); G = Decimal("130"); L = Decimal("83.562")
U = Decimal("0.5"); buf = Decimal("0.1"); rebate = Decimal("0.05")
thi = Decimal("0.036"); tlo = Decimal("0.055")
M = K - J - I - H - G - L
N = K / M; O = N + buf; P = K / O
Q = P * rebate; R = K * thi - K * tlo
S = K - P - J - I - H - G + R + Q
T = S / P; V = P / U; X = O * U
bid = P.quantize(Decimal("1"), rounding=ROUND_HALF_UP)

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
actual = {"M": M, "N": N, "O": O, "P": P, "Q": Q, "R": R, "S": S, "T": T, "V": V, "X": X}
diff = {k: (GOLDEN[k], str(actual[k])) for k in GOLDEN if str(actual[k]) != GOLDEN[k]}
check("R24-2 显式 ROUND_HALF_UP 完整串等值（10 项）", not diff, str(diff))
check("R24-2 S 末位 ...947", str(S).endswith("947"), str(S)[-6:])
check("R24-2 bid=1525", bid == Decimal("1525"))

# ---------- R24-3: canonical serialization 规则存在 ----------
with open(CID, encoding="utf-8") as f:
    ct = f.read()
check("R24-3 canonical serialization 段存在", "canonical decimal serialization" in ct)
check("R24-3 禁 exponent/科学计数法", "exponent" in ct and "科学计数法" in ct)
check("R24-3 负零归一", "负零" in ct)
check("R24-3 完整串等值（非前缀）", "完整字符串等值" in ct and "非前缀匹配" in ct)

# ---------- R24-4: L 缺失标记 FIELD_DEFAULTED ----------
check("R24-4 L 行 FIELD_DEFAULTED（无 FIELD_MISSING）", "FIELD_DEFAULTED(field=L)" in ct and "标记 FIELD_MISSING" not in ct)

# ---------- 回归：A5/A6 ----------
check("A5 precision=60", "precision = 60" in ct)
check("A6 envelope 分离", "blocking_error" in ct and "quality_flags" in ct and "business_flags" in ct)

print()
print("enum-registry.yaml  bytes:", os.path.getsize(ENUM), " sha256:", sha256(ENUM))
print("error-codes.yaml    bytes:", os.path.getsize(ERR), " sha256:", sha256(ERR))
print("cid-engine-spec.md  bytes:", os.path.getsize(CID), " sha256:", sha256(CID))
print()
print("SELF-CHECK:", "PASS" if ok else "FAIL")
sys.exit(0 if ok else 1)
