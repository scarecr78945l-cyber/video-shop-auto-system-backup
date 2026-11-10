# -*- coding: utf-8 -*-
"""P0-0 批 A 契约 round-23 回修自检：A1~A6 全部断言 + 哈希。只读。"""
import hashlib, re, sys, os
from decimal import Decimal, ROUND_HALF_UP, getcontext

# 强制 stdout UTF-8，避免 Windows GBK 控制台编码失败
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

BASE = r"E:\新建文件夹 (6)\视频号小店全自动系统-方案文档\docs\contracts"
ENUM = BASE + r"\enum-registry.yaml"
ERR = BASE + r"\error-codes.yaml"
CID = BASE + r"\cid-engine-spec.md"

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
    """取 YAML 中指定 code 的条目块。"""
    parts = re.split(r"^\s+- code:", txt, flags=re.M)[1:]
    for p in parts:
        if re.match(rf"\s*{code}\b", p):
            return p
    return ""

# ---------- A1: enum defaults ----------
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
entry_blocks = re.split(r"^\s+- name:", et, flags=re.M)[1:]
enums = {}
for b in entry_blocks:
    nm = re.match(r"\s*(\w+)", b)
    if not nm:
        continue
    nm = nm.group(1)
    vu = re.search(r"values: \[([^\]]*)\]", b)
    bu = re.search(r"used_by: \[([^\]]*)\]", b)
    enums[nm] = (vu.group(1) if vu else "", bu.group(1) if bu else "")
bad_defaults = []
for field, val in defaults_raw.items():
    owner_enum = None
    for en, (vals, used) in enums.items():
        if field in [x.strip() for x in used.split(",")]:
            owner_enum = en
            break
    if owner_enum is None:
        bad_defaults.append((field, "no-owner-enum"))
        continue
    vals = [x.strip().strip('"\'') for x in enums[owner_enum][0].split(",")]
    if val not in vals:
        bad_defaults.append((field, val, "not-in-values"))
check("A1 default 字段归属与值集", not bad_defaults, str(bad_defaults[:5]))

# ---------- A2: retry_policies ----------
with open(ERR, encoding="utf-8") as f:
    et2 = f.read()
codes = re.findall(r"^\s+- code: (\w+)$", et2, re.M)
check("A2 error entries=16", len(codes) == 16, f"got {len(codes)}")
rm = re.search(r"^retry_policies:\n((?:  \w+: \{.*\}\n?)+)", et2, re.M)
pol = {}
if rm:
    for line in rm.group(1).splitlines():
        k, v = line.split(":", 1)
        pol[k.strip()] = v.strip()
retryable_codes = []
for c in codes:
    blk = code_block(et2, c)
    if re.search(r"retryable: true", blk):
        retryable_codes.append(c)
expected_retry = {"RATE_LIMIT", "TIMEOUT", "NO_MATCH", "INSUFFICIENT_REFERENCES", "UNEXPECTED"}
check("A2 retryable code exact-set=5", set(retryable_codes) == expected_retry, str(retryable_codes))
check("A2 retry_policies 覆盖 5 个 retryable", set(pol.keys()) == expected_retry, str(pol.keys()))
check("A2 双向 exact-set(retryable<->policy)", set(retryable_codes) == set(pol.keys()))

# ---------- A3: UNEXPECTED 语义 ----------
ue = code_block(et2, "UNEXPECTED")
check("A3 UNEXPECTED retryable=true", "retryable: true" in ue)
check("A3 UNEXPECTED backoff=60", re.search(r"backoff_seconds: 60", ue) is not None)
check("A3 UNEXPECTED terminal=false", "terminal: false" in ue)
check("A3 UNEXPECTED supersedes 记录", "supersedes" in ue)
pc = code_block(et2, "PAGE_CHANGED")
check("A3 PAGE_CHANGED supersedes 记录", "supersedes" in pc)

# ---------- A4: owner 运行时责任域 ----------
owners = re.findall(r"owner: (\S+)", et2)
check("A4 无 owner=dsh（文档角色）", "dsh" not in owners, str(set(owners)))
allowed = {"database/domain_integrity","platform_session_or_adapter","platform_adapter","domain_workflow","platform_action","workflow_runtime"}
check("A4 owner 均为运行时责任域且=16", set(owners) <= allowed and len(owners) == 16, str(set(owners)))

# ---------- A5: precision=60 唯一 ----------
with open(CID, encoding="utf-8") as f:
    ct = f.read()
check("A5 decimal_context.precision=60", re.search(r"precision = 60", ct) is not None)
check("A5 无'至少 50 位'残留", "至少 50 位" not in ct and "至少 50" not in ct)

# ---------- A6: envelope 分离 ----------
check("A6 blocking_error 存在", "blocking_error" in ct)
check("A6 quality_flags 存在", "quality_flags" in ct)
check("A6 business_flags 存在", "business_flags" in ct)
check("A6 S_NON_POSITIVE 归 business", "S_NON_POSITIVE" in ct and "business_flags" in ct)
check("A6 REBATE_NOT_APPLICABLE 归 business", "REBATE_NOT_APPLICABLE" in ct and "business_flags" in ct)
check("A6 REQUIRED_FIELD_MISSING 归 blocking", "REQUIRED_FIELD_MISSING" in ct and "blocking_error" in ct)

# ---------- 黄金样例复算（precision=60） ----------
getcontext().prec = 60
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
check("CID M=1638.314", M == Decimal("1638.314"))
check("CID bid=1525", bid == Decimal("1525"))
check("CID P 规范串首段", str(P).startswith("1524.71838913263129988876904209077295993273155249248846108953"))
check("CID S 不减 L", str(S).startswith("231.612530324000265105669410013765688063905025132135961964946"))
check("CID T/X 首段", str(T).startswith("0.1519051202994659") and str(X).startswith("0.7211167700453026"))

print()
print("enum-registry.yaml  bytes:", os.path.getsize(ENUM), " sha256:", sha256(ENUM))
print("error-codes.yaml    bytes:", os.path.getsize(ERR), " sha256:", sha256(ERR))
print("cid-engine-spec.md  bytes:", os.path.getsize(CID), " sha256:", sha256(CID))
print()
print("SELF-CHECK:", "PASS" if ok else "FAIL")
sys.exit(0 if ok else 1)
