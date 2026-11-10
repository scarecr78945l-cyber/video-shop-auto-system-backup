# -*- coding: utf-8 -*-
"""P0-0 批 B 契约自检：ddl-order / index-registry / test-strategy 结构断言 + 哈希。只读。"""
import hashlib, re, sys, os

BASE = r"E:\新建文件夹 (6)\视频号小店全自动系统-方案文档\docs\contracts"
DDL = BASE + r"\ddl-order.md"
IDX = BASE + r"\index-registry.md"
TST = BASE + r"\test-strategy.md"

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

with open(DDL, encoding="utf-8") as f:
    d = f.read()
with open(IDX, encoding="utf-8") as f:
    x = f.read()
with open(TST, encoding="utf-8") as f:
    t = f.read()

# ---- ddl-order.md ----
check("DDL G0~G11 全部存在", all(f"G{i}" in d for i in range(0, 12)), [f"G{i}" for i in range(0,12) if f"G{i}" not in d])
check("DDL W0~W8 全部存在", all(f"W{i}" in d for i in range(0, 9)), [f"W{i}" for i in range(0,9) if f"W{i}" not in d])
check("DDL 17 父候选键", "17 父候选键" in d and all(
    tbl in d for tbl in ["platform_accounts","shops","suppliers","products","product_skus",
                         "supplier_offers","cost_snapshots","assets","asset_product_bindings",
                         "asset_shop_bindings","shop_listings","shop_listing_skus",
                         "ad_campaigns","ad_report_snapshots","workflow_runs",
                         "policy_versions","alert_events"]))
check("DDL 58 组合 FK 合计", "合计" in d and "58" in d)
check("DDL 17 trigger 顺序", d.count("trg_") >= 17 and "17 个 trigger" in d)
check("DDL 断言表含 60/31/17/58/4/17/2/15", all(s in d for s in ["60", "31", "17", "58", "4", "17", "2", "15"]))
check("DDL PG15 预检", "150000" in d or "server_version_num >= 150000" in d)
check("DDL downgrade 边界", "DROP TRIGGER" in d and "DROP TABLE" in d and "DROP TYPE" in d)
check("DDL 禁 CASCADE", "禁止 CASCADE" in d or "DROP EXTENSION ... CASCADE" in d)

# ---- index-registry.md ----
px = re.findall(r"^\| \d+ \| (\w+) \| (px_\w+)", x, re.M)
check("IDX 部分唯一索引 = 15", len(px) == 15, f"got {len(px)}")
names = [n for _, n in px]
check("IDX 索引名唯一", len(set(names)) == len(names))
check("IDX 覆盖 tenants.name", any("tenants" in tab for tab, _ in px))
nx = re.findall(r"^\| N\d+ \|", x, re.M)
check("IDX 普通索引 N1~N15", len(nx) == 15, f"got {len(nx)}")
check("IDX workflow_steps 状态索引", "ix_steps_status_updated" in x)
check("IDX FK 覆盖说明", "PostgreSQL 不自动" in x or "不自动为 FK 建索引" in x)

# ---- test-strategy.md ----
check("TST 六层矩阵", all(k in t for k in ["unit", "migration", "repository/trigger", "fixture-e2e", "contract", "live-gate"]))
check("TST downgrade 演练修正", "downgrade base" in t and "空库断言" in t)
check("TST mode/provider/model/source/evidence", "mode/provider/model/source/evidence" in t)
check("TST 隐式租约 7 断言", all(k in t for k in ["两 worker 并发", "attempt", "heartbeat", "gate_retry", "action_idempotency_key", "(status, updated_at)"]))
check("TST live-gate 门禁", "live-gate" in t and "资源未确认" in t)
check("TST 真实能力分离", "fixtures/mock 只证明" in t or "不更新 live capability" in t)

print()
print("ddl-order.md       bytes:", os.path.getsize(DDL), " sha256:", sha256(DDL))
print("index-registry.md  bytes:", os.path.getsize(IDX), " sha256:", sha256(IDX))
print("test-strategy.md   bytes:", os.path.getsize(TST), " sha256:", sha256(TST))
print()
print("SELF-CHECK:", "PASS" if ok else "FAIL")
sys.exit(0 if ok else 1)
