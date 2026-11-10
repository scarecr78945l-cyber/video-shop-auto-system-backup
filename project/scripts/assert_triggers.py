# -*- coding: utf-8 -*-
"""T4: 17 trigger catalog 定义级 exact-set 断言（round-59 初版；round-61 R60-1/R60-3/R60-4 重写）。

以 `scripts/trg_expected.py`（round-61 独立冻结快照，来源 15-数据字典.md v6 §8 + ddl-order.md §六 +
error-codes.yaml）为唯一 expected-set，与 pg_catalog 逐项比对（不从生成器导入，避免同源假通过）：

  1. 17 user trigger 精确集合（名称/表）
  2. 安装顺序 == G7 冻结顺序（ddl-order §六）；downgrade == 严格逆序（AST 校验 migration）
  3. 每项普通 BEFORE INSERT OR UPDATE、FOR EACH ROW、enabled='O'、非 constraint trigger、绑定 fn_<name>
  4. UPDATE OF 事件列 exact-set（pg_get_triggerdef 解析 + tgattr 列序）
  5. 每函数 LANGUAGE plpgsql / RETURNS trigger；函数体含业务错误码 + 自定义 SQLSTATE（机械签名）
  6. SQLSTATE 全部为 ZT 自定义类且不落入 PL/pgSQL 已登记条件（R60-3）
  7. asset_reviews 无 trigger（应用层断言，不建第 18 个）

用法：python scripts/assert_triggers.py（需 DATABASE_URL）
"""
import ast
import os
import re
import sys

from sqlalchemy import create_engine, text

URL = os.environ.get("DATABASE_URL", "").strip()
if not URL:
    print("[FAIL] 缺少 DATABASE_URL", file=sys.stderr)
    sys.exit(1)

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)
import trg_expected as E  # noqa: E402

ok = True


def check(name, cond, detail=""):
    global ok
    print(f"[{'PASS' if cond else 'FAIL'}] {name}" + (f"  {detail}" if detail else ""))
    if not cond:
        ok = False


def parse_update_of(triggerdef):
    """从 pg_get_triggerdef 提取 UPDATE OF 列（保持顺序）；无 OF 子句返回 None。"""
    m = re.search(r"BEFORE INSERT OR UPDATE(?: OF ([a-z_ ,]+))? ON ", triggerdef)
    if not m:
        return None
    cols = m.group(1)
    if cols is None:
        return None
    return tuple(c.strip() for c in cols.split(","))


with create_engine(URL).connect() as c:
    # ---------- 1+2. 17 user trigger 精确集合 + G7 顺序 ----------
    trg_rows = c.execute(text(
        "SELECT t.tgname, cr.relname, t.tgtype, t.tgenabled, t.tgconstraint, p.proname, pg_get_triggerdef(t.oid) "
        "FROM pg_trigger t "
        "JOIN pg_class cr ON cr.oid = t.tgrelid "
        "JOIN pg_namespace ns ON ns.oid = cr.relnamespace "
        "JOIN pg_proc p ON p.oid = t.tgfoid "
        "WHERE ns.nspname='app' AND NOT t.tgisinternal "
        "ORDER BY t.tgname"
    )).fetchall()
    got = {(r[0], r[1]) for r in trg_rows}
    want = {(n, t) for n, t, *_ in E.TRIGGERS}
    check("17 user trigger 精确集合（名称/表）", got == want,
          f"missing={want-got} extra={got-want}")

    # 安装顺序：pg_trigger 按 tgrelid/tgid 无直接安装序号；改用 pg_get_triggerdef 顺序无法可靠还原。
    # 采用生成器数据层顺序断言（INSTALL_ORDER 即 TRIGGERS 顺序）+ migration AST 断言（见下方）。
    check("expected TRIGGERS 顺序 == G7 INSTALL_ORDER",
          [n for n, *_ in E.TRIGGERS] == E.INSTALL_ORDER,
          "")

    # ---------- 3+4. 每项属性 + UPDATE OF 事件列 exact-set ----------
    bad = []
    ev_fail = []
    for name, tbl, ev_cols, code, state in E.TRIGGERS:
        row = [r for r in trg_rows if r[0] == name]
        if not row:
            bad.append(f"{name}: missing")
            continue
        _n, table, tgtype, enabled, tgconstraint, proname, defn = row[0]
        is_row = tgtype & 1 == 1
        is_before = tgtype & 2 == 2
        is_after = tgtype & 128 == 128
        has_insert = tgtype & 4 == 4
        has_update = tgtype & 16 == 16
        has_delete = tgtype & 8 == 8
        fn_expect = "fn_" + name[len("trg_"):]
        if table != tbl:
            bad.append(f"{name} table {table} != {tbl}")
        if (not is_row or not is_before or is_after or not has_insert or not has_update
                or has_delete or enabled != "O" or tgconstraint != 0 or proname != fn_expect):
            bad.append(f"{name}: row={is_row} before={is_before} after={is_after} "
                       f"ins={has_insert} upd={has_update} del={has_delete} "
                       f"enabled={enabled} constr={tgconstraint} fn={proname} != {fn_expect}")
        # UPDATE OF 事件列 exact-set（顺序敏感）
        got_ev = parse_update_of(defn)
        if got_ev != ev_cols:
            ev_fail.append(f"{name}: got {got_ev} != expect {ev_cols}")
    check("每项普通 BEFORE FOR EACH ROW / enabled='O' / 非 constraint / 绑定 fn_<name>", not bad,
          "; ".join(bad[:8]))
    check("UPDATE OF 事件列 exact-set（含列序）", not ev_fail, "; ".join(ev_fail[:8]))

    # tgattr 列序补充核验（PostgreSQL 事件列精确来源）
    tga_rows = c.execute(text(
        "SELECT t.tgname, "
        "(SELECT string_agg(a.attname, ',' ORDER BY k.ord) FROM unnest(t.tgattr) WITH ORDINALITY k(attnum, ord) "
        "  JOIN pg_attribute a ON a.attrelid = t.tgrelid AND a.attnum = k.attnum) AS cols "
        "FROM pg_trigger t JOIN pg_class cr ON cr.oid=t.tgrelid "
        "JOIN pg_namespace ns ON ns.oid=cr.relnamespace "
        "WHERE ns.nspname='app' AND NOT t.tgisinternal"
    )).fetchall()
    tga_map = {r[0]: tuple(r[1].split(",")) if r[1] else None for r in tga_rows}
    tga_fail = []
    for name, _t, ev_cols, _code, _state in E.TRIGGERS:
        if tga_map.get(name) != ev_cols:
            tga_fail.append(f"{name}: tgattr={tga_map.get(name)} != {ev_cols}")
    check("tgattr 事件列 exact-set", not tga_fail, "; ".join(tga_fail[:8]))

    # ---------- 5. 函数：语言/返回类型 + 函数体含业务错误码与自定义 SQLSTATE ----------
    fn_rows = c.execute(text(
        "SELECT p.proname, l.lanname, p.prorettype::regtype::text, pg_get_functiondef(p.oid) "
        "FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace "
        "LEFT JOIN pg_language l ON l.oid=p.prolang "
        "WHERE n.nspname='app' AND p.proname LIKE 'fn\\_%' AND p.prokind='f' ORDER BY p.proname"
    )).fetchall()
    got_fn = {r[0] for r in fn_rows}
    want_fn = {"fn_" + name[len("trg_"):] for name, _t, *_ in E.TRIGGERS}
    check("17 函数 fn_<name> 精确集合", got_fn == want_fn,
          f"missing={want_fn-got_fn} extra={got_fn-want_fn}")
    fn_def_map = {r[0]: r[3] for r in fn_rows}
    fn_bad = []
    sig_bad = []
    for name, _t, _ev, code, state in E.TRIGGERS:
        fn = "fn_" + name[len("trg_"):]
        row = [r for r in fn_rows if r[0] == fn]
        if not row:
            fn_bad.append(f"{fn}: missing")
            continue
        _n, lang, ret, defn = row[0]
        if lang != "plpgsql" or ret != "trigger":
            fn_bad.append(f"{fn}: lang={lang} ret={ret}")
        # 函数体机械签名：必须含业务错误码与自定义 SQLSTATE
        if code not in defn or state not in defn:
            sig_bad.append(f"{fn}: body 缺 code={code} 或 sqlstate={state}")
    check("每函数 LANGUAGE plpgsql / RETURNS trigger", not fn_bad, "; ".join(fn_bad[:6]))
    check("函数体含业务错误码 + 自定义 SQLSTATE（机械签名）", not sig_bad, "; ".join(sig_bad[:8]))

    # ---------- 6. SQLSTATE 无冲突（R60-3）----------
    import psycopg2.errorcodes as _ec
    registered = {v for v in vars(_ec).values() if isinstance(v, str) and len(v) == 5}
    conflict = {s for s in E.SQLSTATE_MAP.values() if s in registered}
    check("SQLSTATE 全部为 ZT 自定义类且不与 PL/pgSQL 已登记条件冲突", not conflict,
          f"conflict={conflict}")
    for code, state in E.SQLSTATE_MAP.items():
        if not state.startswith("ZT"):
            check(f"{code} 使用自定义类", False, state)

    # ---------- 7. asset_reviews 无第 18 个 trigger ----------
    ar_trg = c.execute(text(
        "SELECT count(*) FROM pg_trigger t JOIN pg_class cr ON cr.oid=t.tgrelid "
        "JOIN pg_namespace ns ON ns.oid=cr.relnamespace "
        "WHERE ns.nspname='app' AND cr.relname='asset_reviews' AND NOT t.tgisinternal"
    )).scalar()
    check("asset_reviews 无 trigger（应用层断言）", ar_trg == 0, f"got {ar_trg}")

# ---------- migration 顺序断言（upgrade=G7 序，downgrade=严格逆序）----------
src_path = os.path.join(ROOT, "..", "migrations", "versions", "17trg000001_17_triggers.py")
src = open(src_path, encoding="utf-8").read()

# 从源码文本按出现顺序提取 upgrade 的 CREATE TRIGGER 与 downgrade 的 DROP TRIGGER
def _text_order(keyword):
    if keyword == "CREATE TRIGGER":
        return re.findall(r"CREATE TRIGGER\s+(\w+)", src)
    return re.findall(r"DROP TRIGGER(?:\s+IF EXISTS)?\s+(\w+)", src)

upg_triggers = _text_order("CREATE TRIGGER")
dow_triggers = _text_order("DROP TRIGGER")
check("migration upgrade 安装顺序 == G7 冻结顺序", upg_triggers == E.INSTALL_ORDER,
      f"actual={upg_triggers}")
check("migration downgrade == G7 严格逆序", dow_triggers == list(reversed(E.INSTALL_ORDER)),
      f"actual={dow_triggers}")

# ---------- R62-3：generator manifest ↔ expected 三向交叉（生成器与验收快照分离）----------
import gen_trg_migration as G  # noqa: E402

manifest_fail = []
if [t[0] for t in G.TRIGGERS] != E.INSTALL_ORDER:
    manifest_fail.append("generator TRIGGERS 顺序 != expected INSTALL_ORDER")
if G.TRIGGERS != E.TRIGGERS:
    manifest_fail.append("generator TRIGGERS（name/table/event/code/sqlstate）!= expected TRIGGERS")
if G.INSTALL_ORDER != E.INSTALL_ORDER:
    manifest_fail.append("generator INSTALL_ORDER != expected INSTALL_ORDER")
if G.SQLSTATE_MAP != E.SQLSTATE_MAP:
    manifest_fail.append("generator SQLSTATE_MAP != expected SQLSTATE_MAP")
if G.BUSINESS_CODES != E.BUSINESS_CODES:
    manifest_fail.append("generator BUSINESS_CODES != expected BUSINESS_CODES")
check("generator manifest ↔ expected 三向一致（R62-3）", not manifest_fail,
      "; ".join(manifest_fail[:8]))

print("T4-TRIGGER-ASSERT:", "PASS" if ok else "FAIL")
sys.exit(0 if ok else 1)