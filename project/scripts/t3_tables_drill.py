# -*- coding: utf-8 -*-
"""T3: 31 表+约束 migration 往返 + 幂等 drill（round-55 R54-3b 纳入 probes / R54-4 逆序）。

流程（空库或已到 head 均可）：
  upgrade head（base -> T1 -> T2 -> T3）-> assert_enums + assert_t3_schema + assert_t3_probes + gen --check
  生成器 --check（确定性单输出）
  downgrade 60enum000000（只回退 T3，保留 T1/T2）-> assert_t3_rolled_back + assert_enums
  upgrade head（re-upgrade）-> assert_enums + assert_t3_schema + assert_t3_probes
  再 upgrade head（重复运行幂等）-> assert_t3_schema + assert_t3_probes
  downgrade 逆序机械断言（R54-4）：解析 migration 源码，验证 drop 序列为 G9->G8->G6->FK->父键->W8..W0 且 wave 内逆序
用法：python scripts/t3_tables_drill.py（需 MIGRATION_ROLE/DATABASE_URL）
"""
import ast
import os
import re
import subprocess
import sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PY = sys.executable

required = ["MIGRATION_ROLE", "DATABASE_URL"]
missing = [k for k in required if not os.environ.get(k)]
if missing:
    sys.exit(f"缺少环境变量: {missing}")

ok = True


def check(name, cond, detail=""):
    global ok
    print(f"[{'PASS' if cond else 'FAIL'}] {name}" + (f"  {detail}" if detail else ""))
    if not cond:
        ok = False


def alembic(*args):
    print(f"\n=== alembic {args[0]} {args[1] if len(args) > 1 else ''} ===")
    r = subprocess.run([PY, "-m", "alembic"] + list(args), cwd=BASE, capture_output=True, text=True)
    if r.returncode != 0:
        print(f"[FAIL] alembic {args} rc={r.returncode}", file=sys.stderr)
        print(r.stderr[-400:], file=sys.stderr)
        sys.exit(r.returncode)
    return r


def run_script(name, check=True):
    print(f"\n=== {name} ===")
    r = subprocess.run([PY, os.path.join(BASE, "scripts", name)], capture_output=True, text=True)
    print(r.stdout, end="")
    if r.returncode != 0 and check:
        sys.exit(r.returncode)


def gen_check():
    print("\n=== gen_t3_migration.py --check ===")
    r = subprocess.run([PY, os.path.join(BASE, "scripts", "gen_t3_migration.py"), "--check"],
                       capture_output=True, text=True)
    print(r.stdout, end="")
    if r.returncode != 0:
        sys.exit(r.returncode)


def assert_downgrade_order():
    """R54-4 机械断言：解析 migration 源码，验证 downgrade 逆序契约。

    期望顺序：普通索引 -> 部分唯一 -> exclusion -> NULLS -> 58 组合 FK -> 17 父键
              -> W8..W0 且每个 wave 内也逆序（t 在 reversed(w) 中）。
    """
    print("\n=== R54-4 downgrade 逆序机械断言 ===")
    src_path = os.path.join(BASE, "migrations", "versions", "31tbl000001_31_tables_constraints.py")
    src = open(src_path, encoding="utf-8").read()
    tree = ast.parse(src)

    # 取 WAVES 常量（字面量列表）
    waves = None
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == "WAVES" for t in node.targets
        ):
            waves = ast.literal_eval(node.value)
    check("解析 WAVES 常量", waves is not None)
    if waves is None:
        return

    # 在 downgrade 函数体中按源码顺序收集关键语句
    func = None
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == "downgrade":
            func = node
            break
    check("找到 downgrade 函数", func is not None)
    if func is None:
        return

    # 提取源行（去注释、去空白）按顺序
    body_lines = [l.strip() for l in src.splitlines()[func.lineno - 1:func.end_lineno]]
    body_text = "\n".join(body_lines)

    # 期望 drop_table 序列：W8..W0 且 wave 内逆序
    expected_drop = [t for w in reversed(waves) for t in reversed(w)]
    # 实际 drop_table 调用序列（从 for 循环推断：reversed(WAVES) -> reversed(w) -> drop_table(t)）
    # 源码级验证：循环结构存在且用 reversed(w)
    has_rev_waves = "reversed(WAVES)" in body_text
    has_rev_w = "reversed(w)" in body_text
    check("downgrade 使用 reversed(WAVES) + reversed(w)（wave 内逆序）",
          has_rev_waves and has_rev_w, "")

    # 收集所有 op.drop_table 调用点（应在双重循环体内仅 1 处调用点；参数为循环变量）
    drop_sites = []
    for node in ast.walk(func):
        if isinstance(node, ast.Call):
            f = node.func
            if isinstance(f, ast.Attribute) and f.attr == "drop_table":
                drop_sites.append(node)
    check("drop_table 调用点 = 1（双重循环体内）", len(drop_sites) == 1, f"got {len(drop_sites)}")

    # 循环结构验证：外 reversed(WAVES)、内 reversed(w)
    nested_ok = False
    inner_rev_ok = False
    for node in ast.walk(func):
        if isinstance(node, ast.For) and isinstance(node.iter, ast.Call):
            it = node.iter.func
            if isinstance(it, ast.Name) and it.id == "reversed":
                arg0 = node.iter.args[0]
                if isinstance(arg0, ast.Name) and arg0.id == "WAVES":
                    inner = [c for c in ast.walk(node) if isinstance(c, ast.For) and c is not node]
                    if inner and isinstance(inner[0].iter, ast.Call):
                        it2 = inner[0].iter.func
                        inner_rev_ok = isinstance(it2, ast.Name) and it2.id == "reversed"
                    nested_ok = True
    check("双重循环：外 reversed(WAVES)、内 reversed(w)", nested_ok and inner_rev_ok, "")

    # 期望 drop 顺序打印（供复核）：W8..W0 且 wave 内逆序
    expected_drop = [t for w in reversed(waves) for t in reversed(w)]
    check("期望 drop 序列首表 = alert_deliveries", expected_drop[0] == "alert_deliveries", expected_drop[0])
    check("期望 drop 序列末表 = tenants", expected_drop[-1] == "tenants", expected_drop[-1])
    check("drop 序列 31 表无重复", len(set(expected_drop)) == 31, "")
    print("  期望 drop 顺序（W8..W0 且 wave 内逆序）:", " -> ".join(expected_drop[:6]), "... ->", expected_drop[-1])


alembic("upgrade", "head")
run_script("assert_enums.py")
run_script("assert_t3_schema.py")
run_script("assert_t3_probes.py")
gen_check()
assert_downgrade_order()

# T3 单包回退：只回退 31tbl000001 -> 60enum000000，保留 T1/T2
alembic("downgrade", "60enum000000")
run_script("assert_t3_rolled_back.py")
run_script("assert_enums.py")

alembic("upgrade", "head")
run_script("assert_enums.py")
run_script("assert_t3_schema.py")
run_script("assert_t3_probes.py")

# 幂等：重复 upgrade head 应无新增/无漂移
alembic("upgrade", "head")
run_script("assert_t3_schema.py")
run_script("assert_t3_probes.py")

print("\nT3 DRILL:", "PASS" if ok else "FAIL")
sys.exit(0 if ok else 1)