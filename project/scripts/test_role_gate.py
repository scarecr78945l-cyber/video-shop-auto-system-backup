# -*- coding: utf-8 -*-
"""T1 R46-1 专项测试：角色门禁必须前置且零副作用。

正例：正确角色 -> alembic 成功，且 revision 对象 owner = MIGRATION_ROLE
负例1：角色不存在 -> 失败，且 app schema / ACL / 扩展 catalog 零差异
负例2：角色不可切换（存在但连接用户未获成员）-> 失败，且 catalog 零差异
负例3：空 MIGRATION_ROLE -> 失败

用法：python scripts/test_role_gate.py（需 MIGRATION_ROLE/DATABASE_URL；测试库需允许创建受限角色）
"""
import os
import subprocess
import sys

from sqlalchemy import create_engine, text

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PY = sys.executable
URL = os.environ.get("DATABASE_URL", "").strip()
if not URL:
    print("[FAIL] 需要 DATABASE_URL", file=sys.stderr)
    sys.exit(1)

ok = True


def check(name, cond, detail=""):
    global ok
    print(f"[{'PASS' if cond else 'FAIL'}] {name}" + (f"  {detail}" if detail else ""))
    if not cond:
        ok = False


def alembic(role, *args, url=URL):
    env = dict(os.environ)
    env["MIGRATION_ROLE"] = role
    env["DATABASE_URL"] = url
    r = subprocess.run([PY, "-m", "alembic"] + list(args), cwd=BASE, capture_output=True, text=True, env=env)
    return r


def catalog_app_state(url=URL):
    """返回 (schema_exists, acl_rows, btree_gist_exists, version_exists)。"""
    with create_engine(url).connect() as c:
        schema = c.execute(text(
            "SELECT count(*) FROM information_schema.schemata WHERE schema_name='app'"
        )).scalar()
        acl = c.execute(text(
            "SELECT count(*) FROM information_schema.schemata WHERE schema_name='app' AND nspacl IS NOT NULL"
        )).scalar() if schema else 0
        ext = c.execute(text(
            "SELECT count(*) FROM pg_extension WHERE extname='btree_gist'"
        )).scalar()
        ver = c.execute(text(
            "SELECT count(*) FROM information_schema.tables WHERE table_schema='app' AND table_name='alembic_version'"
        )).scalar()
        return (schema, acl, ext, ver)


# ---- 准备：确保干净 base（无 app schema） ----
with create_engine(URL).connect() as c:
    c.execute(text("DROP SCHEMA IF EXISTS app CASCADE"))
    c.commit()

# ---- 负例1：角色不存在 ----
r1 = alembic("ROLE_DOES_NOT_EXIST", "current")
check("负例1：不存在的角色必须失败", r1.returncode != 0, f"rc={r1.returncode}")
s, a, e, v = catalog_app_state()
check("负例1：失败后 catalog 零差异（app=0/ACL=0/ext=0/ver=0）", (s, a, e, v) == (0, 0, 0, 0), str((s, a, e, v)))

# ---- 负例2：角色不可切换（受限 runner 未获目标角色成员） ----
# 创建受限 runner（非 superuser、非成员）+ 目标角色（存在但不授予 runner）
admin = create_engine(URL)
with admin.connect() as c:
    c.execute(text("DROP ROLE IF EXISTS cdx47_runner"))
    c.execute(text("DROP ROLE IF EXISTS cdx47_target"))
    c.execute(text("CREATE ROLE cdx47_runner LOGIN PASSWORD 'p'"))
    c.execute(text("CREATE ROLE cdx47_target NOLOGIN"))
    c.commit()
runner_url = URL.replace("//dsh:dsh@", "//cdx47_runner:p@")
r2 = alembic("cdx47_target", "current", url=runner_url)
check("负例2：不可切换角色必须失败", r2.returncode != 0, f"rc={r2.returncode}, {r2.stderr[-160:]}")
s, a, e, v = catalog_app_state(runner_url)
check("负例2：失败后 catalog 零差异（app=0/ACL=0/ext=0/ver=0）", (s, a, e, v) == (0, 0, 0, 0), str((s, a, e, v)))

# ---- 负例3：空 MIGRATION_ROLE ----
env_empty = dict(os.environ)
env_empty["MIGRATION_ROLE"] = ""
r3 = subprocess.run([PY, "-m", "alembic", "current"], cwd=BASE, capture_output=True, text=True, env=env_empty)
check("负例3：空 MIGRATION_ROLE 必须失败", r3.returncode != 0, f"rc={r3.returncode}")

# ---- 正例：正确角色成功（upgrade head），且对象 owner = MIGRATION_ROLE ----
r_ok = alembic("dsh_migrator", "upgrade", "head")
check("正例：dsh_migrator upgrade head 成功", r_ok.returncode == 0, f"rc={r_ok.returncode}, {r_ok.stderr[-160:]}")
with create_engine(URL).connect() as c:
    owner = c.execute(text(
        "SELECT tableowner FROM pg_tables WHERE schemaname='app' AND tablename='alembic_version'"
    )).scalar()
    check("正例：alembic_version owner = dsh_migrator", owner == "dsh_migrator", str(owner))

# ---- 清理受限角色 ----
with admin.connect() as c:
    c.execute(text("DROP ROLE IF EXISTS cdx47_runner"))
    c.execute(text("DROP ROLE IF EXISTS cdx47_target"))
    c.commit()

print("ROLE-GATE-TEST:", "PASS" if ok else "FAIL")
sys.exit(0 if ok else 1)
