# -*- coding: utf-8 -*-
"""T9: 全量 head（auth000002）pg_catalog 定义级 exact-set 断言（round-121 R120-1 定稿）。

复用冻结 expected manifests + 成熟完整比较器（不重造弱比较）：
  - **完整 T3/T4 定义比较**：子进程调用 assert_t3_schema.py（T4_TRIGGER_EXPECT=17，head 模式：
    28 基础 FK/58 组合 FK/17 父键/4 NULLS/2 exclusion/15 partial/503 列/31 PK/34 UNIQUE/CHECK 全定义）
    + assert_triggers.py（17 trigger 完整 tgtype/函数签名/事件列）——R120-1：不再按样例弱计数；
  - 60 enum 类型名+值集：docs/contracts/enum-registry.yaml（entries name/values）；
  - auth 7 表名 + PK + FK 级联；
  - N1/N2 索引：所属表/列/**无谓词**（R114-1/R116-1：WHERE false/wrong_table 变异必须失败）；
  - trigger 函数绑定逐项（fn_<trigger> + 函数体非空操作）+ FK_ACTIONS DELETE action + partial 谓词
    （R118-1 三项补充——t3_schema 不覆盖的 head 特有检查）；
  - alembic_version = auth000002。

变异负例必须非零退出：见各检查 FAIL 条件。
"""
import os
import subprocess
import sys

import yaml
from sqlalchemy import create_engine, text

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from t3_expected import (  # noqa: E402
    TABLES as APP_TABLES,
)
from trg_expected import TRIGGERS as TRG_EXPECTED  # noqa: E402

URL = os.environ.get("DATABASE_URL", "").strip()
if not URL:
    print("[FAIL] 缺少 DATABASE_URL", file=sys.stderr)
    sys.exit(1)

ok = True


def check(name, cond, detail=""):
    global ok
    print(f"[{'PASS' if cond else 'FAIL'}] {name}" + (f"  {detail}" if detail else ""))
    if not cond:
        ok = False


AUTH_TABLES = ['user', 'session', 'account', 'verification', 'organization',
               'member', 'invitation']


def load_enum_registry():
    """enum-registry.yaml -> {typname: [values...]}（60 项）。"""
    p = os.path.join(ROOT, "..", "docs", "contracts", "enum-registry.yaml")
    with open(p, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return {e["name"]: list(e["values"]) for e in data["entries"]}


try:
    # R120-1：复用成熟完整比较器（head 模式）——assert_t3_schema（T4_TRIGGER_EXPECT=17：
    # 28 基础 FK/58 组合 FK/17 父键/4 NULLS/2 exclusion/15 partial/503 列/31 PK/34 UNIQUE/CHECK 全定义，
    # 含 DELETE action 与 partial 列序/谓词逐项）+ assert_triggers（17 trigger 完整 tgtype/函数签名/事件列）。
    # 任一非零即本门禁失败（消除样例增补式弱比较）。
    _env = dict(os.environ)
    _env["T4_TRIGGER_EXPECT"] = "17"
    _env["DATABASE_URL"] = URL
    _env["PYTHONUTF8"] = "1"
    for _script in ("assert_t3_schema.py", "assert_triggers.py"):
        _r = subprocess.run([sys.executable, os.path.join(ROOT, "scripts", _script)],
                            env=_env, capture_output=True, text=True, encoding="utf-8", timeout=180)
        if _r.returncode != 0:
            check(f"复用 {_script}（head 完整定义比较）", False,
                  f"rc={_r.returncode}\n{_r.stdout[-800:]}\n{_r.stderr[-800:]}")
        else:
            print(f"[PASS] 复用 {_script}（head 完整定义比较）")
    e = create_engine(URL)
    with e.connect() as c:
        # --- app 表名 exact-set ---
        app_names = [r[0] for r in c.execute(text(
            "SELECT tablename FROM pg_tables WHERE schemaname='app' "
            "AND tablename<>'alembic_version' ORDER BY tablename")).all()]
        check("app 业务表名 exact-set（31）", app_names == sorted(APP_TABLES),
              f"missing={set(APP_TABLES)-set(app_names)} extra={set(app_names)-set(APP_TABLES)}")
        # --- auth 表名 exact-set ---
        auth_names = [r[0] for r in c.execute(text(
            "SELECT tablename FROM pg_tables WHERE schemaname='auth' ORDER BY tablename")).all()]
        check("auth 表名 exact-set（7）", auth_names == sorted(AUTH_TABLES), f"got={auth_names}")
        # --- 60 enum 类型名 + 值集 exact-set（R114-1：改名/值集变异必须失败）---
        expected_enums = load_enum_registry()
        got_enums = {}
        for row in c.execute(text(
                "SELECT t.typname, e.enumlabel FROM pg_enum e "
                "JOIN pg_type t ON t.oid=e.enumtypid "
                "JOIN pg_namespace n ON n.oid=t.typnamespace "
                "WHERE n.nspname='app' ORDER BY t.typname, e.enumsortorder")).all():
            got_enums.setdefault(row[0], []).append(row[1])
        check("app enum 类型名 exact-set（60）", set(got_enums) == set(expected_enums),
              f"missing={set(expected_enums)-set(got_enums)} extra={set(got_enums)-set(expected_enums)}")
        enum_value_mismatch = {t: (expected_enums[t], got_enums[t])
                               for t in expected_enums if expected_enums[t] != got_enums.get(t)}
        check("app enum 值集 exact-set（60 项）", not enum_value_mismatch,
              f"mismatch={dict(list(enum_value_mismatch.items())[:3])}")
        # --- 17 trigger 定义级（R118-1：name/table/事件列/enabled/tgtype/函数绑定逐项等值）---
        got_trg = {}
        for row in c.execute(text(
                "SELECT t.tgname, x.relname, t.tgenabled, "
                "       (SELECT string_agg(a.attname, ',' ORDER BY k.ord) "
                "        FROM unnest(t.tgattr) WITH ORDINALITY k(attnum, ord) "
                "        JOIN pg_attribute a ON a.attrelid=t.tgrelid AND a.attnum=k.attnum), "
                "       t.tgtype, p.proname, pg_get_functiondef(p.oid) "
                "FROM pg_trigger t JOIN pg_class x ON x.oid=t.tgrelid "
                "JOIN pg_namespace n ON n.oid=x.relnamespace "
                "JOIN pg_proc p ON p.oid=t.tgfoid "
                "WHERE n.nspname='app' AND NOT t.tgisinternal")).all():
            got_trg[row[0]] = (row[1], row[2], row[3], row[4], row[5], row[6])
        expected_names = {t[0] for t in TRG_EXPECTED}
        check("trigger 名 exact-set（17）", set(got_trg) == expected_names,
              f"missing={expected_names-set(got_trg)} extra={set(got_trg)-expected_names}")
        disabled = [t for t, v in got_trg.items() if v[1] != 'O']
        check("trigger 全 enabled", not disabled, f"disabled={disabled}")
        trig_mismatch = []
        for name, table, cols, code, sqlstate in TRG_EXPECTED:
            got = got_trg.get(name)
            if not got:
                trig_mismatch.append((name, "missing", None))
                continue
            # 所属表不匹配必须失败
            if got[0] != table:
                trig_mismatch.append((name, table, got[0]))
                continue
            db_cols = got[2].split(",") if got[2] else None
            exp_cols = list(cols) if cols else None
            if db_cols != exp_cols:
                trig_mismatch.append((name, exp_cols, db_cols))
            # tgtype 必须 BEFORE ROW（bit1=2）
            tg = int(got[3]) if got[3] is not None else 0
            if not (tg & 2):
                trig_mismatch.append((name, "BEFORE", f"非BEFORE(tgtype={got[3]})"))
            # R118-1：函数绑定逐项等值——函数名 = fn_<trigger 去 trg_ 前缀>（migration 冻结命名）
            exp_fn = "fn_" + name[len("trg_"):]
            if got[4] != exp_fn:
                trig_mismatch.append((name, exp_fn, got[4]))
            # R118-1/R120-1：函数定义非空操作——body 仅 RETURN NEW（± RAISE NOTICE）视为空；
            # 业务函数应含条件/赋值/RAISE EXCEPTION 等逻辑
            fdef = got[5] or ""
            import re as _re
            # 定界符支持 $$ 与 $function$（pg_get_functiondef 用 $function$）
            _m = _re.search(r"AS\s+(\$\w*\$)(.*?)\1\s*$", fdef, _re.S)
            body = _m.group(2) if _m else ""
            _b = _re.sub(r"RAISE\s+NOTICE[^;]*;", "", body)  # 去 NOTICE
            _b = _re.sub(r"RAISE\s+NOTICE\s+.*", "", _b)
            _b = _re.sub(r"BEGIN|END|RETURN\s+NEW;|;", "", _b)
            _b = _re.sub(r"\s+", "", _b)
            if not _b:  # 无业务逻辑（仅 NOTICE+RETURN NEW）
                trig_mismatch.append((name, "业务函数体", "空操作函数体(仅NOTICE+RETURN NEW)"))
        check("trigger 定义级（表/事件列/tgtype/函数绑定/函数体）", not trig_mismatch,
              f"mismatch={trig_mismatch[:4]}")
        # R120-1：FK/父键/NULLS/exclusion/partial/FK action 完整定义由上方 assert_t3_schema
        # （T4_TRIGGER_EXPECT=17）逐项比较覆盖（28 基础 FK+58 组合 FK+action/17 父键/4 NULLS/
        # 2 exclusion/15 partial 列序+谓词）——此处仅保留 head 特有检查。
        # --- FK validity（R116-1：NOT VALID 变异必须失败）---
        invalid_fk = c.execute(text(
            "SELECT count(*) FROM pg_constraint con JOIN pg_class t ON t.oid=con.conrelid "
            "JOIN pg_namespace n ON n.oid=t.relnamespace "
            "WHERE n.nspname='app' AND con.contype='f' AND NOT con.convalidated")).scalar()
        check("FK 全 validated（无 NOT VALID）", int(invalid_fk) == 0, f"got {invalid_fk}")
        # --- N1/N2：所属表/列/唯一性/无谓词（R116-1：wrong_table/假谓词变异必须失败）---
        n1 = c.execute(text(
            "SELECT indexdef FROM pg_indexes WHERE schemaname='app' "
            "AND indexname='ix_steps_status_updated'")).scalar()
        check("N1 所属表 workflow_steps + 列 (status, updated_at) 无谓词",
              n1 is not None and "ON app.workflow_steps" in n1 and
              "(status, updated_at)" in n1 and " WHERE " not in n1, str(n1))
        n2 = c.execute(text(
            "SELECT indexdef FROM pg_indexes WHERE schemaname='app' "
            "AND indexname='ix_runs_status_updated'")).scalar()
        check("N2 所属表 workflow_runs + 列 (status, updated_at) 无谓词",
              n2 is not None and "ON app.workflow_runs" in n2 and
              "(status, updated_at)" in n2 and " WHERE " not in n2, str(n2))
        # --- auth 定义级 exact-set 集合闭包（R122-1 + R124-1 加固：列/PK/UNIQUE/FK 全等）---
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import auth_expected as AE  # noqa: E402
        # auth 列定义（每表列名集合全等 + type/null/default 逐项等值）
        auth_cols = {}
        for row in c.execute(text(
                "SELECT x.relname, a.attname, format_type(a.atttypid, a.atttypmod), a.attnotnull, "
                "       pg_get_expr(d.adbin, d.adrelid) "
                "FROM pg_attribute a "
                "JOIN pg_class x ON x.oid=a.attrelid "
                "JOIN pg_namespace n ON n.oid=x.relnamespace "
                "LEFT JOIN pg_attrdef d ON d.adrelid=a.attrelid AND d.adnum=a.attnum "
                "WHERE n.nspname='auth' AND a.attnum>0 AND NOT a.attisdropped")).all():
            auth_cols.setdefault(row[0], {})[row[1]] = (row[2], not row[3], row[4])
        col_mismatch = []
        for table, expected_cols in AE.COLUMNS.items():
            got = auth_cols.get(table, {})
            if set(got) != set(expected_cols):  # R124-1：列名集合闭包（拒绝额外/缺失列）
                col_mismatch.append((table, "colnames-set",
                                     f"extra={sorted(set(got) - set(expected_cols))} "
                                     f"missing={sorted(set(expected_cols) - set(got))}"))
                continue
            for col, (typ, nullable, default) in expected_cols.items():
                g = got[col]
                # 类型规范化（uuid/text/boolean/timestamptz 映射差异）——两边都压到短名
                e_typ = typ.replace("timestamp with time zone", "timestamp") \
                           .replace("timestamp without time zone", "timestamp")
                g_typ = g[0].replace("character varying", "text") \
                           .replace("character(36)", "char") \
                           .replace("timestamp with time zone", "timestamp") \
                           .replace("timestamp without time zone", "timestamp")
                if g_typ != e_typ:
                    col_mismatch.append((table, col, f"type {g_typ} != {e_typ}"))
                if g[1] != nullable:
                    col_mismatch.append((table, col, f"null {g[1]} != {nullable}"))
                # default 规范化（now()/false/'x'::text/gen_random_uuid() 字面比较）
                g_def, e_def = g[2], default
                if (g_def is None) != (e_def is None):
                    col_mismatch.append((table, col, f"default None-ness {g_def} != {e_def}"))
                elif g_def is not None and g_def != e_def:
                    # 两侧都非空：字面须一致（R122-1：id 缺 gen_random_uuid 默认必须失败）
                    col_mismatch.append((table, col, f"default {g_def} != {e_def}"))
        check("auth 列定义 exact-set（7 表列名集合全等+type/null/default）",
              not col_mismatch, f"mismatch={col_mismatch[:6]}")
        # auth PK（(table,name)->cols 键集合与定义全等）
        auth_pkmap = {}
        for row in c.execute(text(
                "SELECT x.relname, con.conname, array_agg(a.attname ORDER BY k.ord) "
                "FROM pg_constraint con JOIN pg_class x ON x.oid=con.conrelid "
                "JOIN pg_namespace n ON n.oid=x.relnamespace "
                "JOIN unnest(con.conkey) WITH ORDINALITY k(attnum, ord) ON true "
                "JOIN pg_attribute a ON a.attrelid=con.conrelid AND a.attnum=k.attnum "
                "WHERE n.nspname='auth' AND con.contype='p' GROUP BY x.relname, con.conname")).all():
            auth_pkmap[(row[0], row[1])] = tuple(row[2])
        exp_pk = {(t, n): tuple(cols) for t, n, cols in AE.PRIMARY_KEYS}
        pk_mismatch = []
        for key, exp in exp_pk.items():
            if auth_pkmap.get(key) != exp:
                pk_mismatch.append((key, exp, auth_pkmap.get(key)))
        for key, got in auth_pkmap.items():
            if key not in exp_pk:
                pk_mismatch.append((key, None, got, "extra"))
        check("auth PK exact-set（7 名称+列键集合与定义全等）", not pk_mismatch,
              f"mismatch={pk_mismatch[:4]}")
        # auth UNIQUE（非 PK 约束+唯一索引合并为单一映射；不含 PK 与谓词/表达式过滤；
        # 键集合与定义全等，拒绝任何未列入清单的额外唯一索引/带谓词索引）
        auth_uniq_src = {}
        for row in c.execute(text(
                "SELECT x.relname, con.conname, array_agg(a.attname ORDER BY k.ord), "
                "       false AS partial "
                "FROM pg_constraint con JOIN pg_class x ON x.oid=con.conrelid "
                "JOIN pg_namespace n ON n.oid=x.relnamespace "
                "JOIN unnest(con.conkey) WITH ORDINALITY k(attnum, ord) ON true "
                "JOIN pg_attribute a ON a.attrelid=con.conrelid AND a.attnum=k.attnum "
                "WHERE n.nspname='auth' AND con.contype='u' GROUP BY x.relname, con.conname")).all():
            auth_uniq_src[(row[0], row[1])] = (tuple(row[2]), row[3])
        # 非 PK 唯一索引：不含 indisprimary/不按 indpred 过滤（谓词索引进入拒绝路径）；
        # 表达式列（attnum=0）以哨兵标记，无法与预期列匹配 -> 命中拒绝
        for row in c.execute(text(
                "SELECT x.relname, i.relname, "
                "       array_agg(CASE WHEN k.attnum > 0 THEN a.attname "
                "                     ELSE '__expr__' || k.ord END ORDER BY k.ord), "
                "       (idx.indpred IS NOT NULL) "
                "FROM pg_index idx JOIN pg_class x ON x.oid=idx.indrelid "
                "JOIN pg_class i ON i.oid=idx.indexrelid "
                "JOIN pg_namespace n ON n.oid=x.relnamespace "
                "JOIN unnest(idx.indkey) WITH ORDINALITY k(attnum, ord) ON true "
                "LEFT JOIN pg_attribute a ON a.attrelid=idx.indrelid AND a.attnum=k.attnum "
                "WHERE n.nspname='auth' AND idx.indisunique AND NOT idx.indisprimary "
                "GROUP BY x.relname, i.relname, idx.indpred")).all():
            auth_uniq_src.setdefault((row[0], row[1]), (tuple(row[2]), row[3]))
        exp_u = {(t, n): tuple(cols) for t, n, cols in AE.UNIQUES}
        uniq_mismatch = []
        for key, (cols, is_partial) in sorted(auth_uniq_src.items()):
            if is_partial:  # R124-1：预期无部分唯一索引——任何谓词唯一索引都要拒绝
                uniq_mismatch.append((key, "partial-unexpected", (cols, True)))
                continue
            if key not in exp_u:
                uniq_mismatch.append((key, None, cols, "extra"))
            elif auth_uniq_src[key][0] != exp_u[key]:
                uniq_mismatch.append((key, exp_u[key], cols, "cols"))
        for key in exp_u:
            if key not in auth_uniq_src:
                uniq_mismatch.append((key, exp_u[key], None, "missing"))
        check("auth UNIQUE exact-set（4 约束+account idx 键集合与定义全等，拒绝额外/部分索引）",
              not uniq_mismatch, f"mismatch={uniq_mismatch[:4]}")
        # auth FK（对象级 exact-set：以 (child_table, constraint_name) 为键——PG 仅要求约束名
        # 在所属 relation 内唯一，不要求 schema 唯一，故跨表同名合法，须用复合键避免覆盖漏报）
        auth_fks = {}
        for row in c.execute(text(
                "SELECT x.relname, con.conname, "
                "       (SELECT array_agg(a.attname ORDER BY k.ord) FROM unnest(con.conkey) "
                "        WITH ORDINALITY k(attnum, ord) "
                "        JOIN pg_attribute a ON a.attrelid=con.conrelid AND a.attnum=k.attnum), "
                "       rt.relname, "
                "       (SELECT array_agg(a.attname ORDER BY k.ord) FROM unnest(con.confkey) "
                "        WITH ORDINALITY k(attnum, ord) "
                "        JOIN pg_attribute a ON a.attrelid=con.confrelid AND a.attnum=k.attnum), "
                "       CASE con.confdeltype WHEN 'c' THEN 'CASCADE' WHEN 'r' THEN 'RESTRICT' "
                "            WHEN 'a' THEN 'NO ACTION' WHEN 'n' THEN 'SET NULL' "
                "            WHEN 'd' THEN 'SET DEFAULT' END "
                "FROM pg_constraint con JOIN pg_class x ON x.oid=con.conrelid "
                "JOIN pg_class rt ON rt.oid=con.confrelid "
                "JOIN pg_namespace n ON n.oid=x.relnamespace "
                "WHERE n.nspname='auth' AND con.contype='f' "
                "ORDER BY x.relname, con.conname")).all():
            auth_fks[(row[0], row[1])] = (tuple(row[2]), row[3], tuple(row[4]), row[5])
        fk_mismatch = []
        exp_fk = {(c, n): (tuple(cc), p, tuple(pc), a)
                  for c, n, cc, p, pc, a in AE.FOREIGN_KEYS}
        for key, exp in exp_fk.items():
            got = auth_fks.get(key)
            if got != exp:  # 缺失或 child 列/父表/父列/action 差异
                fk_mismatch.append((key, exp, got))
        for key, got in sorted(auth_fks.items()):
            if key not in exp_fk:  # 额外 FK（含跨表复用 expected 名称）必须进入拒绝路径
                fk_mismatch.append((key, None, got, "extra"))
        check("auth FK exact-set（(child_table,conname) 键集合与定义全等，拒绝额外/缺失/同名）",
              not fk_mismatch, f"mismatch={fk_mismatch[:4]}")
        ver = c.execute(text("SELECT version_num FROM app.alembic_version")).scalar()
        check("alembic_version = auth000002", ver == "auth000002", str(ver))
except Exception as exc:  # noqa: BLE001
    check("连接失败", False, f"{type(exc).__name__}: {exc}")

print("T9-CATALOG-ASSERT:", "PASS" if ok else "FAIL")
sys.exit(0 if ok else 1)
