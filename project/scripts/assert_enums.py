# -*- coding: utf-8 -*-
"""T2: enum exact-set 断言（app schema，名称+label 顺序与 enum-registry.yaml 一致）。

用法：python scripts/assert_enums.py（需 DATABASE_URL）
"""
import os
import re
import sys

from sqlalchemy import create_engine, text

URL = os.environ.get("DATABASE_URL", "").strip()
if not URL:
    print("[FAIL] 缺少 DATABASE_URL", file=sys.stderr)
    sys.exit(1)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REGISTRY = os.path.join(ROOT, "..", "docs", "contracts", "enum-registry.yaml")

ok = True


def check(name, cond, detail=""):
    global ok
    print(f"[{'PASS' if cond else 'FAIL'}] {name}" + (f"  {detail}" if detail else ""))
    if not cond:
        ok = False


def parse_entries(text):
    entries = []
    blocks = re.split(r"^\s+- name:", text, flags=re.M)[1:]
    for b in blocks:
        m = re.match(r"\s*(\w+)", b)
        if not m:
            continue
        name = m.group(1)
        vm = re.search(r"values: \[([^\]]*)\]", b)
        if not vm:
            continue
        values = [p.strip().strip('"\'') for p in vm.group(1).split(",") if p.strip().strip('"\'')]
        entries.append((name, values))
    return entries


# 读取 registry（唯一输入）
reg = parse_entries(open(REGISTRY, encoding="utf-8").read())
check("registry entries=60", len(reg) == 60, f"got {len(reg)}")

# 查询 pg_catalog：app schema 下 enum 类型及其 label（按类型名排序）
with create_engine(URL).connect() as c:
    rows = c.execute(text(
        "SELECT t.typname, e.enumlabel "
        "FROM pg_type t "
        "JOIN pg_enum e ON e.enumtypid = t.oid "
        "JOIN pg_namespace n ON n.oid = t.typnamespace "
        "WHERE n.nspname = 'app' AND t.typtype = 'e' "
        "ORDER BY t.typname, e.enumsortorder"
    )).fetchall()

db_map = {}
for typname, label in rows:
    db_map.setdefault(typname, []).append(label)

check("app schema enum 数量=60", len(db_map) == 60, f"got {len(db_map)}")

# 逐项核对：名称集、label 集、label 顺序
missing = [n for n, _ in reg if n not in db_map]
extra = [n for n in db_map if n not in dict(reg)]
check("无缺失 enum", not missing, str(missing))
check("无多余 enum", not extra, str(extra))

order_bad = []
for name, values in reg:
    got = db_map.get(name)
    if got != values:
        order_bad.append((name, values, got))
check("每 enum label 顺序与 registry 一致", not order_bad, str(order_bad[:3]))

print("ENUM-ASSERT:", "PASS" if ok else "FAIL")
sys.exit(0 if ok else 1)
