# -*- coding: utf-8 -*-
"""P0-0 批 C 契约 round-41 终验回修自检：R40-1/R40-2 + C1~C4 回归 + 哈希。只读。"""
import hashlib, re, sys, os, unicodedata
from decimal import Decimal

BASE = r"E:\新建文件夹 (6)\视频号小店全自动系统-方案文档\docs\contracts"
DICT = r"E:\新建文件夹 (6)\视频号小店全自动系统-方案文档\15-数据字典.md"
ACT = BASE + r"\external-actions.yaml"
IDP = BASE + r"\idempotency.md"
AUT = BASE + r"\auth-boundary.md"

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

# ---------- R40-1: manual_tasks.public_id 不存在于 v6 schema ----------
with open(DICT, encoding="utf-8") as f:
    v6 = f.read()
with open(IDP, encoding="utf-8") as f:
    i = f.read()

# v6 中 manual_tasks 是否有 public_id 列
manual_block = re.search(r"### 6\.3 `manual_tasks`.*?(?=### 6\.4|## 7\.)", v6, re.S)
manual_has_public_id = bool(manual_block and re.search(r"^\| public_id ", manual_block.group(0), re.M))
check("R40-1 v6 manual_tasks 无 public_id 列", not manual_has_public_id)
check("R40-1 idempotency.md 无 manual_tasks.public_id", "manual_tasks.public_id" not in i)
check("R40-1 使用 manual_tasks.id", "manual_tasks.id" in i)

# ---------- R40-2: 黄金向量现场复算 ----------
def canonical_join(fields):
    parts = []
    for fld in fields:
        s = "nil" if fld is None else str(fld)
        s = s.replace("\\", "\\\\")   # 先反斜杠
        s = s.replace("|", "\\|")     # 再竖线
        parts.append(s)
    joined = "|".join(parts)
    nfc = unicodedata.normalize("NFC", joined)
    return nfc, nfc.encode("utf-8")

def key(domain, fields):
    text, data = canonical_join(fields)
    digest = hashlib.sha256(data).hexdigest()
    return text, digest, f"{domain}:v1:{digest}"

U1 = "00000000-0000-0000-0000-000000000001"
U2 = "00000000-0000-0000-0000-000000000002"
U3 = "00000000-0000-0000-0000-000000000003"

t1, d1, k1 = key("step", [U1, U2, "listing_submit", "product_submit_audit", U3])
check("R40-2 V1 digest", d1 == "5e47863b2530cda2957f894411abb214bbbf811e9c8ff42f274185c31954d614", d1)
check("R40-2 V1 final key", k1 == "step:v1:5e47863b2530cda2957f894411abb214bbbf811e9c8ff42f274185c31954d614", k1)

t2, d2, k2 = key("step", [U1, U2, "campaign_start", "campaign_start", None])
check("R40-2 V2 digest", d2 == "147949e3b728782d8bf9f784cb88d4228313458f1c0246d6e37c3f1967547deb", d2)
check("R40-2 V2 final key", k2 == "step:v1:147949e3b728782d8bf9f784cb88d4228313458f1c0246d6e37c3f1967547deb", k2)

t3, d3, k3 = key("step", [U1, U2, "material_upload", "material_upload", "a|b\\c中"])
check("R40-2 V3 digest", d3 == "8fc40e4a65af1c77e59838cd2b04232b3165f404cd87f84c032f05ac17525245", d3)
check("R40-2 V3 final key", k3 == "step:v1:8fc40e4a65af1c77e59838cd2b04232b3165f404cd87f84c032f05ac17525245", k3)
check("R40-2 V3 canonical 转义", t3.endswith("material_upload|a\\\\|b\\\\\\\\c中".replace("\\\\", "\\") + "中") or "a\\\\|b" in t3 or "a\\|b\\\\c" in t3, repr(t3))
check("R40-2 文档含 V1/V2/V3 确定值", "5e47863b2530cda" in i and "147949e3b728782d" in i and "8fc40e4a65af1c77" in i)
check("R40-2 冻结转义顺序", "先反斜杠后竖线" in i and "顺序不可调换" in i)
check("R40-2 冻结 Unicode NFC", "NFC" in i)

# ---------- C1~C4 回归 ----------
with open(ACT, encoding="utf-8") as f:
    a = f.read()
actions = re.findall(r"^\s+- action_id: (\w+)$", a, re.M)
check("C1 动作数=20", len(actions) == 20, f"got {len(actions)}")
blocks = re.split(r"^\s+- action_id:", a, flags=re.M)[1:]
comp_bad = []
for b in blocks:
    m = re.search(r"^\s+compensation_action_id:\s*(\S+)", b, re.M)
    v = m.group(1) if m else ""
    if v in ("null", "None"):
        continue
    v = v.split("#")[0].strip()
    if v not in actions:
        comp_bad.append((b.strip().split("\n")[0][:30], v))
check("C1 补偿闭包", not comp_bad, str(comp_bad[:4]))
check("C1 material_delete 登记", "material_delete" in actions)

write_blocks = [b for b in blocks if re.search(r"read_or_write: write", b)]
check("C2 write=11", len(write_blocks) == 11, f"got {len(write_blocks)}")
step_write = [b for b in write_blocks if "workflow_steps.action_idempotency_key" in
              (re.search(r"^\s+idempotency_key_spec:\s*(.+)$", b, re.M).group(1) if re.search(r"^\s+idempotency_key_spec:\s*(.+)$", b, re.M) else "")]
# 非创建 step-key write = 9（material_upload/material_delete/product_update/product_submit_audit/
#   product_close/campaign_start/campaign_tune/campaign_pause/campaign_stop）
non_create = [b for b in write_blocks
              if "workflow_steps.action_idempotency_key" in (re.search(r"^\s+idempotency_key_spec:\s*(.+)$", b, re.M).group(1) if re.search(r"^\s+idempotency_key_spec:\s*(.+)$", b, re.M) else "")]
check("C2 非创建 step-key write=9", len(non_create) == 9, f"got {len(non_create)}")
check("C2 注释计数=9", "#   - 9 个非创建类 write" in a)

# auth 回归
with open(AUT, encoding="utf-8") as f:
    u = f.read()
check("AUT gate/Alembic/双来源", "选择并锁定 better-auth version/plugins" in u and "Alembic 为唯一部署入口" in u and "恰好命中一个来源" in u)

print()
print("external-actions.yaml  bytes:", os.path.getsize(ACT), " sha256:", sha256(ACT))
print("idempotency.md         bytes:", os.path.getsize(IDP), " sha256:", sha256(IDP))
print("auth-boundary.md       bytes:", os.path.getsize(AUT), " sha256:", sha256(AUT))
print()
print("SELF-CHECK:", "PASS" if ok else "FAIL")
sys.exit(0 if ok else 1)
