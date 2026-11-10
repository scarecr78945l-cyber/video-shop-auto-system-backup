# -*- coding: utf-8 -*-
"""P0-0 批 A 契约自检：CID 黄金样例复算 + YAML 计数 + 哈希。只读，不修改任何文件。"""
import hashlib, re, sys
from decimal import Decimal, ROUND_HALF_UP, getcontext

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

# ---------- 1. CID 黄金样例复算 ----------
getcontext().prec = 60
K = Decimal("2199"); J = Decimal("13.194"); I = Decimal("153.930")
H = Decimal("180"); G = Decimal("130"); L = Decimal("83.562")
U = Decimal("0.5"); buf = Decimal("0.1"); rebate = Decimal("0.05")
thi = Decimal("0.036"); tlo = Decimal("0.055")
M = K - J - I - H - G - L
N = K / M
O = N + buf
P = K / O
Q = P * rebate
R = K * thi - K * tlo
S = K - P - J - I - H - G + R + Q
T = S / P
V = P / U
X = O * U
bid = P.quantize(Decimal("1"), rounding=ROUND_HALF_UP)
check("CID M=1638.314", M == Decimal("1638.314"), str(M))
check("CID bid_rounded_cents=1525", bid == Decimal("1525"), str(bid))
check("CID P 高精度首段 1524.718389132631", str(P).startswith("1524.718389132631"), str(P)[:40])
check("CID S 不减 L（S 首段 231.6125303240002）", str(S).startswith("231.6125303240002"), str(S)[:40])
check("CID T 首段 0.1519051202994659", str(T).startswith("0.1519051202994659"), str(T)[:40])
check("CID X 首段 0.7211167700453026", str(X).startswith("0.7211167700453026"), str(X)[:40])

# ---------- 2. enum-registry.yaml 计数 ----------
with open(ENUM, encoding="utf-8") as f:
    et = f.read()
names = re.findall(r"^\s+- name: (enum_\w+)$", et, re.M)
check("enum-registry 条目=60", len(names) == 60, f"got {len(names)}")
check("enum-registry 名称唯一", len(set(names)) == len(names))
vals = re.findall(r"values: \[([^\]]+)\]", et)
check("enum-registry 每项有 values", len(vals) == 60)
used = re.findall(r"used_by: \[([^\]]+)\]", et)
check("enum-registry 每项有 used_by", len(used) == 60)
# 每个 values 至少一个元素
empty_vals = [n for n, v in zip(names, vals) if not v.strip()]
check("enum-registry 无空 values", not empty_vals, str(empty_vals))

# ---------- 3. error-codes.yaml 计数与 9 属性 ----------
with open(ERR, encoding="utf-8") as f:
    et2 = f.read()
codes = re.findall(r"^\s+- code: (\w+)$", et2, re.M)
check("error-codes 条目=16", len(codes) == 16, f"got {len(codes)}")
check("error-codes 名称唯一", len(set(codes)) == len(codes))
check("error-codes 长度<=32", all(len(c) <= 32 for c in codes))
# 每个 code 块内 9 属性
blocks = re.split(r"^\s+- code:", et2, flags=re.M)[1:]
attrs = ["category", "retryable", "backoff_seconds", "manual_takeover", "terminal", "http_mapping", "owner", "evidence_required"]
bad = []
for b in blocks:
    missing = [a for a in attrs if not re.search(rf"^\s+{a}:", b, re.M)]
    if missing:
        bad.append((b.strip().split("\n")[0][:30], missing))
check("error-codes 每项 9 属性", not bad, str(bad[:3]))
# trigger 码 retryable=false
trig = {c for c in codes if c in {"INVALID_POLICY_REF","SKU_PRODUCT_MISMATCH","CONTEXT_MISMATCH","ACCOUNT_SHOP_MISMATCH","SCOPE_MISMATCH","DIMENSION_MISMATCH","SUPERSEDE_MISMATCH"}}
trig_retryable = re.findall(r"code: (\w+).*?retryable: (\w+)", et2, re.S)
viol = [c for c, r in trig_retryable if c in trig and r != "false"]
check("trigger 7 码 retryable=false", not viol, str(viol))
# AUTH_REQUIRED / VERIFICATION_REQUIRED 不自动重试
auth_viol = [c for c, r in trig_retryable if c in {"AUTH_REQUIRED","VERIFICATION_REQUIRED"} and r != "false"]
check("AUTH/VERIFICATION 不自动重试", not auth_viol, str(auth_viol))

# ---------- 4. 哈希 ----------
print()
print("enum-registry.yaml  bytes:", __import__("os").path.getsize(ENUM), " sha256:", sha256(ENUM))
print("error-codes.yaml    bytes:", __import__("os").path.getsize(ERR), " sha256:", sha256(ERR))
print("cid-engine-spec.md  bytes:", __import__("os").path.getsize(CID), " sha256:", sha256(CID))

print()
print("SELF-CHECK:", "PASS" if ok else "FAIL")
sys.exit(0 if ok else 1)
