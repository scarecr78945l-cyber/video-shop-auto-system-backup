# -*- coding: utf-8 -*-
"""P0-0 批 C 契约自检：external-actions / idempotency / auth-boundary 结构断言 + 哈希。只读。"""
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

# ---- external-actions.yaml ----
actions = re.findall(r"^\s+- action_id: (\w+)$", a, re.M)
check("ACT 动作数=19", len(actions) == 19, f"got {len(actions)}")
check("ACT action_id 唯一", len(set(actions)) == len(actions))
REQ_FIELDS = ["platform","capability","read_or_write","account_scope","credential_ref",
              "input_schema","output_schema","gate","idempotency_key_spec",
              "timeout_reconcile_probe","retry_class","evidence_ref","mode",
              "provider","model","source","compensation_action_id",
              "irreversible_effect","owner","current_status"]
bad = []
blocks = re.split(r"^\s+- action_id:", a, flags=re.M)[1:]
for b in blocks:
    missing = [f for f in REQ_FIELDS if not re.search(rf"^\s+{f}:", b, re.M)]
    if missing:
        bad.append((b.strip().split("\n")[0][:30], missing))
check("ACT 每项 21 字段齐全", not bad, str(bad[:3]))
# write 动作必须有 gate + compensation
write_blocks = [b for b in blocks if re.search(r"read_or_write: write", b)]
write_bad = [b.strip().split("\n")[0][:30] for b in write_blocks
             if not re.search(r"^\s+gate:", b, re.M) or not re.search(r"^\s+compensation_action_id:", b, re.M)]
check("ACT write 动作均有 gate+compensation", not write_bad, str(write_bad))
# 官方路径 current_status=unconfirmed
unconf = re.findall(r"current_status: (\w+)", a)
check("ACT 全部 current_status=unconfirmed", set(unconf) == {"unconfirmed"}, str(set(unconf)))
# 覆盖最小动作面
cov = ["acc_login_probe","shop_list_read","category_qualification_read","board_snapshot_read",
       "supplier_quote_read","material_read","material_upload","product_schema_read",
       "product_create","product_update","product_submit_audit","product_status_read",
       "product_close","ads_report_read","campaign_create","campaign_start",
       "campaign_tune","campaign_pause","campaign_stop"]
check("ACT 最小动作面覆盖", set(cov) <= set(actions), str(set(cov) - set(actions)))

# ---- idempotency.md ----
check("IDP 11 键注册表", all(k in i for k in ["supplier_offers.idempotency_key",
    "cost_snapshots.idempotency_key","selection_decisions.selection_batch_key",
    "shop_listings.idempotency_key","pricing_decisions.idempotency_key",
    "listing_events.request_id","ad_campaigns.idempotency_key",
    "ad_report_snapshots.report_version_key","roi_feedback_events.idempotency_key",
    "workflow_runs.idempotency_key","workflow_steps.action_idempotency_key"]))
check("IDP action key 排除 attempt", "不含 attempt" in i)
check("IDP 超时先查", "超时先查" in i and "不换 key 重建" in i)
check("IDP 稳定时间", "首次接收/计算前固定" in i or "首次执行前固定" in i)
check("IDP 冲突返回原资源", "冲突返回原资源" in i)
check("IDP intent 三来源", "workflow logical action slot" in i and "manual task/approval" in i and "API caller" in i)

# ---- auth-boundary.md ----
check("AUT better-auth gate", "选择并锁定 better-auth version/plugins" in u and "Codex diff 通过" in u)
check("AUT Alembic 唯一部署入口", "Alembic 为唯一部署入口" in u)
check("AUT 三类对象分开统计", "31 张业务表" in u and "alembic_version" in u and "better-auth 表" in u)
check("AUT actor 双来源唯一命中", "恰好命中一个来源" in u and "0 或 2 都拒绝" in u)
check("AUT 四类验收", all(k in u for k in ["伪造 actor_id","跨 tenant membership","停用用户","后台 worker"]))
check("AUT 四补项", all(k in u for k in ["双命中 actor","未知 tenant_public_id","role 越权","request_id 贯通"]))
check("AUT 真实微信登录态不属本包", "真实微信登录态" in u and "不属本包" in u)

print()
print("external-actions.yaml  bytes:", os.path.getsize(ACT), " sha256:", sha256(ACT))
print("idempotency.md         bytes:", os.path.getsize(IDP), " sha256:", sha256(IDP))
print("auth-boundary.md       bytes:", os.path.getsize(AUT), " sha256:", sha256(AUT))
print()
print("SELF-CHECK:", "PASS" if ok else "FAIL")
sys.exit(0 if ok else 1)
