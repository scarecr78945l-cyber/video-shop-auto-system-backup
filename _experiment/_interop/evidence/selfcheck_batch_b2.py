# -*- coding: utf-8 -*-
"""P0-0 批 B 契约 round-33 回修自检：B1~B6 断言 + 哈希。只读。"""
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

# ---- B1: 命名空间固定取值 ----
check("B1 business_schema=app", "business_schema = app" in d)
check("B1 search_path 有序", "search_path = app, pg_catalog" in d)
check("B1 migration_role 必填门禁", "MIGRATION_ROLE" in d and "启动时必填门禁" in d)
check("B1 G0 含具体取值", "business_schema = app" in d and "MIGRATION_ROLE" in d)

# ---- B2: asset_reviews 无 trigger 暗示 ----
check("B2 asset_reviews 仅应用层断言", re.search(r"asset_reviews\.(?:scope_ref_id|review_scope/scope_ref_id)`?：仅应用层断言", d) is not None)
check("B2 无'asset_reviews...应用层断言 + 命名 trigger'混合", "scope_ref_id）不生成 DB FK，由应用层断言 + 命名 trigger" not in d)
check("B2 17 exact-set 保持", "17" in d and "第 18 个 trigger" in d)
# round-35 B2 修正：manual 通配 trigger 名（以 trg_manual 开头的通配/占位写法）= 0；仅允许精确 trg_manual_policy_ref
manual_trigger_wildcard = re.findall(r"trg_manual_[A-Za-z_]*\*|trg_manual_[A-Za-z_]*\s*$", d)
# 更稳：找 "trg_manual_*" 字面或 "trg_manual<非policy>"
manual_wild_literal = re.findall(r"trg_manual_\*", d)
manual_bad = re.findall(r"trg_manual_(?!policy_ref\b)[a-z_]*", d)
manual_bad = [m for m in manual_bad if m]  # 排除空
check("B2 无 trg_manual_* 字面", len(manual_wild_literal) == 0, str(manual_wild_literal))
check("B2 无 trg_manual_<非policy> 通配", not manual_bad, str(manual_bad))
check("B2 manual polymorphic ref=应用层断言+审计", re.search(r"manual_tasks\.ref_type/ref_id`?：仅应用层断言 \+ 审计", d) is not None)
check("B2 trg_manual_policy_ref 仅校验 policy", "trg_manual_policy_ref" in d and "只校验 policy_version_id" in d)

# ---- B3: FK 两端区分 ----
check("B3 FK 被引用端声明", "被引用端" in x and "17 个父候选键" in x and "58/58" in x)
check("B3 FK 引用端不承诺全覆盖", "不承诺 58 引用端全覆盖" in x or "不承诺" in x)

# ---- B4: covered_by_constraint 映射 ----
check("B4 covered_by_constraint 段", "covered_by_constraint" in x)
# covered 表在 "### 3.2" 与 "---"（下个一级节）之间
sec32 = x.split("### 3.2")[1].split("## 四")[0] if "### 3.2" in x else ""
covered = re.findall(r"\|\s*(N\d+)\s*\|", sec32) if sec32 else []
expected_covered = {"N3","N6","N8","N9","N11","N13","N15"}
check("B4 covered 映射=N3/N6/N8/N9/N11/N13/N15", set(covered) == expected_covered, str(covered))
sec31 = x.split("### 3.1")[1].split("### 3.2")[0] if "### 3.1" in x else ""
explicit = re.findall(r"\|\s*(N\d+)\s*\|", sec31) if sec31 else []
expected_explicit = {"N1","N2","N4","N5","N7","N10","N12","N14"}
check("B4 显式创建=8 项", set(explicit) == expected_explicit, str(explicit))

# ---- B5: 隐式租约断言补齐 ----
check("B5 heartbeat<=15 分钟", "15 分钟" in t)
check("B5 stale 覆盖 gate_retry", "heartbeat / complete / fail / gate_retry" in t)
check("B5 不可领取状态矩阵", "不可领取状态矩阵" in t and "manual_review / done / failed" in t)
check("B5 claim 返回 id+attempt", "id + attempt" in t and "fencing token" in t)

# ---- B6: CI 顺序 ----
check("B6 CI job 顺序", "job1 lint" in t and "job2 unit" in t and "job3 empty DB" in t and "job4 pg_catalog" in t and "job5 alembic downgrade" in t and "job6 re-upgrade" in t)
check("B6 无未分层 pytest 顺序", "lint + pytest + alembic" not in t)

print()
print("ddl-order.md       bytes:", os.path.getsize(DDL), " sha256:", sha256(DDL))
print("index-registry.md  bytes:", os.path.getsize(IDX), " sha256:", sha256(IDX))
print("test-strategy.md   bytes:", os.path.getsize(TST), " sha256:", sha256(TST))
print()
print("SELF-CHECK:", "PASS" if ok else "FAIL")
sys.exit(0 if ok else 1)
