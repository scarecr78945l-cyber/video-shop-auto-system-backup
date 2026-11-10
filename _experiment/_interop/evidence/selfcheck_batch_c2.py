# -*- coding: utf-8 -*-
"""P0-0 批 C 契约 round-39 回修自检：C1~C4 断言 + 哈希。只读。"""
import hashlib, re, sys, os

BASE = r"E:\新建文件夹 (6)\视频号小店全自动系统-方案文档\docs\contracts"
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

with open(ACT, encoding="utf-8") as f:
    a = f.read()
with open(IDP, encoding="utf-8") as f:
    i = f.read()
with open(AUT, encoding="utf-8") as f:
    u = f.read()

# ---- ACT 结构 ----
actions = re.findall(r"^\s+- action_id: (\w+)$", a, re.M)
check("ACT 动作数=20", len(actions) == 20, f"got {len(actions)}")
check("ACT action_id 唯一", len(set(actions)) == len(actions))
blocks = re.split(r"^\s+- action_id:", a, flags=re.M)[1:]
write_blocks = [b for b in blocks if re.search(r"read_or_write: write", b)]
check("ACT write 动作=11", len(write_blocks) == 11, f"got {len(write_blocks)}")

# ---- C1: compensation 闭包 ----
comp_refs = set()
comp_bad = []
for b in blocks:
    m = re.search(r"^\s+compensation_action_id:\s*(\S+)", b, re.M)
    if not m:
        comp_bad.append((b[:30], "missing"))
        continue
    v = m.group(1)
    if v == "null" or v == "None":
        continue
    v = v.split("#")[0].strip()  # 剥离行尾注释
    if v not in actions:
        comp_bad.append((b[:30], v))
    else:
        comp_refs.add(v)
check("C1 compensation 值域=null|已登记 action_id（闭包）", not comp_bad, str(comp_bad[:5]))
check("C1 material_delete 已登记", "material_delete" in actions)
check("C1 无人工说明混入 ID 字段", all("（" not in re.search(r"^\s+compensation_action_id:\s*(\S+)", b, re.M).group(1) for b in blocks))

# ---- C2: write 幂等映射到注册键 ----
write_specs = {}
for b in write_blocks:
    m = re.search(r"^\s+idempotency_key_spec:\s*(.+)$", b, re.M)
    write_specs[b.strip().split("\n")[0].strip()] = m.group(1) if m else ""
# 10 个非创建 write 映射到 workflow_steps.action_idempotency_key 或注册键
reg_keys = ["workflow_steps.action_idempotency_key","shop_listings.idempotency_key",
            "ad_campaigns.idempotency_key","supplier_offers.idempotency_key",
            "selection_decisions.selection_batch_key","cost_snapshots.idempotency_key",
            "pricing_decisions.idempotency_key","listing_events.request_id",
            "ad_report_snapshots.report_version_key","roi_feedback_events.idempotency_key",
            "workflow_runs.idempotency_key"]
bad_map = [(k, v[:40]) for k, v in write_specs.items() if not any(rk in v for rk in reg_keys)]
check("C2 11 个 write 幂等规格均引用注册键", not bad_map, str(bad_map[:5]))
# material_upload/product_update/submit/close/start/tune/pause/stop 均用 step key
step_actions = ["material_upload","material_delete","product_update","product_submit_audit",
                "product_close","campaign_start","campaign_tune","campaign_pause","campaign_stop"]
missing_step = [k for k in write_specs if any(sa in k for sa in step_actions)
                and "workflow_steps.action_idempotency_key" not in write_specs[k]]
check("C2 8+ 个非创建 write 映射到 workflow_steps key", not missing_step, str(missing_step))
# logical_action_slot + target 均有
no_slot = [k for k in write_specs if "workflow_steps.action_idempotency_key" in write_specs[k]
           and ("logical_action_slot" not in write_specs[k] or "target=" not in write_specs[k])]
check("C2 step key 均含 logical_action_slot+target", not no_slot, str(no_slot[:3]))

# ---- C3: 稳定 token 持久化对象 ----
check("C3 四元组模板", "source_kind" in i and "source_object" in i and "create_before_side_effect" in i and "retry_lookup" in i)
check("C3 observed_at/snapshot_at 落点", "supplier_offers.observed_at" in i and "cost_snapshots.snapshot_at" in i)
check("C3 submit_intent 落点", "listing_submit" in i)
check("C3 pricing intent 落点", "pricing_apply" in i)
check("C3 create_intent 落点", "manual_tasks.public_id" in i and "ads_confirm" in i)
check("C3 workflow_runs input_ref 落点", "workflow_runs.input_ref" in i)
check("C3 复用既有对象（无新列）", "无需新增专用列" in i)

# ---- C4: key 公式/前缀/黄金向量 ----
check("C4 hash_key 公式", "hash_key = <domain>:v1:<lower_hex_sha256(canonical_join(fields))>" in i)
check("C4 supersedes 连字符前缀", "supersede 旧连字符写法" in i)
check("C4 request_id 不拼接前缀", "不额外拼接前缀" in i and "不改写 caller token" in i)
check("C4 report_version 三源", "id:<platform_version_id>" in i and "ts:<canonical_time>" in i and "hash:<raw_evidence_hash>" in i)
check("C4 黄金向量", "黄金向量" in i and "重试取新" in i and "等值不同 scale" in i and "同一逻辑重试" in i)
check("C4 转义规则", "canonical_join" in i and "nil" in i)

# ---- AUT 回归 ----
check("AUT better-auth gate", "选择并锁定 better-auth version/plugins" in u and "Codex diff 通过" in u)
check("AUT Alembic 唯一入口", "Alembic 为唯一部署入口" in u)
check("AUT actor 双来源", "恰好命中一个来源" in u and "0 或 2 都拒绝" in u)

print()
print("external-actions.yaml  bytes:", os.path.getsize(ACT), " sha256:", sha256(ACT))
print("idempotency.md         bytes:", os.path.getsize(IDP), " sha256:", sha256(IDP))
print("auth-boundary.md       bytes:", os.path.getsize(AUT), " sha256:", sha256(AUT))
print()
print("SELF-CHECK:", "PASS" if ok else "FAIL")
sys.exit(0 if ok else 1)
