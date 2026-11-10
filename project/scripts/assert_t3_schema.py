# -*- coding: utf-8 -*-
"""T3: 31 表 + 约束 定义级 catalog exact-set 断言（round-55 R54-3 重写；round-57 R56-1 门禁扩展）。

以 `scripts/t3_expected.py`（round-55 生成、round-57 R56-1 扩展的独立期望快照，来源 15-数据字典.md v6）
为唯一 expected-set，与 pg_catalog 逐项比对（不 import 生成器，避免「生成器与自身一致」假通过）：

  1. 31 业务表 exact-set（排除 alembic_version）
  2. 503 列定义 exact-set：udt 类型、NULL、DEFAULT（规范化）、identity ALWAYS、generated 表达式
  3. 28 基础 FK + 58 组合 FK 全定义 exact-set：child/parent、双端列序、约束名、ON DELETE action
  4. 17 父候选键 UNIQUE(tenant_id,id) exact table/name
  5. 4 × UNIQUE NULLS NOT DISTINCT（表/索引名/列序）
  6. 2 exclusion（表 + 约束名 + pg_get_constraintdef 规范结构）
  7. 15 部分唯一索引（表/名/列/谓词）+ 8 普通索引（表/名/列）
  8. 27 列级 CHECK + 1 具名 CHECK（规范化表达式）
  9. 31 业务 PK（表/名/列）
 10. 34 普通 UNIQUE（表/列；不含 17 父候选键）
 11. user trigger = 0（正确 join pg_class.relnamespace + NOT tgisinternal）
 12. 生成器数据 与 t3_expected 同源一致性（防止生成器漂移而断言仍过）
 13. norm_expr 保留逻辑分组不变量：(a AND b) OR c != a AND (b OR c)

用法：python scripts/assert_t3_schema.py（需 DATABASE_URL）
"""
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
import t3_expected as E  # noqa: E402

ok = True


def check(name, cond, detail=""):
    global ok
    print(f"[{'PASS' if cond else 'FAIL'}] {name}" + (f"  {detail}" if detail else ""))
    if not cond:
        ok = False


# ---------------------------------------------------------------------------
# catalog 类型/默认/表达式规范化
# ---------------------------------------------------------------------------
def norm_type(ftype):
    """format_type -> t3_expected 类型表示。"""
    ftype = ftype.strip()
    if ftype.startswith("app."):  # enum 渲染为 app.enum_xxx
        return ftype[4:]
    m = re.match(r"^character varying\((\d+)\)$", ftype)
    if m:
        return ("varchar", int(m.group(1)))
    if ftype == "character varying":
        return "varchar"
    m = re.match(r"^numeric\((\d+),(\d+)\)$", ftype)
    if m:
        return ("numeric", int(m.group(1)), int(m.group(2)))
    if ftype == "numeric":
        return "numeric"
    return {
        "bigint": "int8", "integer": "int4", "uuid": "uuid", "jsonb": "jsonb",
        "timestamp with time zone": "timestamptz", "boolean": "bool", "text": "text",
        "bytea": "bytea",
    }.get(ftype, ftype)


def norm_default(defexpr):
    """pg_get_expr 默认值 -> 规范化 token（去 ::cast 与引号；期望侧同规约）。"""
    if defexpr is None:
        return None
    s = defexpr.strip()
    s = re.sub(r"::[a-zA-Z_. ]+$", "", s)        # 去尾部 ::app.enum_xxx / ::numeric / ::character varying
    s = s.strip()
    if len(s) >= 2 and s.startswith("'") and s.endswith("'"):
        s = s[1:-1]
    return s


def _matching_paren(s, i):
    depth = 0
    for j in range(i, len(s)):
        if s[j] == "(":
            depth += 1
        elif s[j] == ")":
            depth -= 1
            if depth == 0:
                return j
    return -1


def _has_top_bool(s):
    depth = 0
    i = 0
    while i < len(s):
        c = s[i]
        if c == "(":
            depth += 1
            i += 1
            continue
        if c == ")":
            depth -= 1
            i += 1
            continue
        if depth == 0:
            if s.startswith("AND", i) or s.startswith("OR", i):
                return True
        i += 1
    return False


def _split_top(s):
    """按顶层 AND/OR 切分，返回 [(term, sep), ...]，sep 为 'AND'/'OR'/''。"""
    depth = 0
    i = 0
    cur = []
    parts = []
    while i < len(s):
        c = s[i]
        if c == "(":
            depth += 1
            cur.append(c)
            i += 1
            continue
        if c == ")":
            depth -= 1
            cur.append(c)
            i += 1
            continue
        if depth == 0 and (s.startswith("AND", i) or s.startswith("OR", i)):
            parts.append(("".join(cur), s[i:i + 3]))
            cur = []
            i += 3
            continue
        cur.append(c)
        i += 1
    parts.append(("".join(cur), ""))
    return parts


def _strip_atomic(s):
    """剥离嵌入表达式内部的原子包裹括号（内部无嵌套括号且无顶层 AND/OR），保留函数调用/IN/分组括号。"""
    out = []
    i = 0
    n = len(s)
    while i < n:
        ch = s[i]
        if ch == "(":
            j = _matching_paren(s, i)
            if j < 0:
                out.append(ch)
                i += 1
                continue
            inner = s[i + 1:j]
            prev_is_ident = i > 0 and (s[i - 1].isalnum() or s[i - 1] == "_")
            if prev_is_ident:
                out.append("(" + _strip_atomic(inner) + ")")  # 函数调用/IN(...) 括号保留
            elif not _has_top_bool(inner) and "(" not in inner:
                out.append(_strip_atomic(inner))              # 原子包裹：剥离
            else:
                out.append("(" + _strip_atomic(inner) + ")")  # 分组括号：保留
            i = j + 1
        else:
            out.append(ch)
            i += 1
    return "".join(out)


def _canon(s):
    """保留逻辑分组的表达式规范化核心。

    - PG 对整条谓词/CHECK 外层稳定加一层包裹括号：剥离；
    - 原子比较/字面量的包裹括号（内部无顶层 AND/OR、无嵌套）：剥离；
    - 函数调用/IN(...)/分组括号（内部含顶层 AND/OR）：保留，
      确保 (a AND b) OR c != a AND (b OR c)。
    """
    if not s:
        return s
    if s[0] == "(":
        j = _matching_paren(s, 0)
        if j == len(s) - 1:
            return _canon(s[1:-1])  # PG 整条表达式外层包裹：剥离
    parts = _split_top(s)
    if len(parts) == 1:
        return _strip_atomic(parts[0][0])
    out = []
    for term, sep in parts:
        t = term
        if t.startswith("(") and _matching_paren(t, 0) == len(t) - 1:
            inner = t[1:-1]
            if _has_top_bool(inner):
                t = "(" + _canon(inner) + ")"  # 分组括号：保留
            else:
                t = _canon(inner)              # 原子包裹：剥离
        else:
            t = _canon(t)
        out.append(t)
        if sep:
            out.append(sep)
    return "".join(out)


def norm_expr(expr):
    """表达式规范化（R56-1：保留内部逻辑分组，只去 PG 稳定外层括号/原子包裹括号/无关 cast）。

    - 去 CHECK 前缀；去 ::cast（含 app. 前缀与 with time zone）；
    - PostgreSQL 的 IN 渲染为 = ANY (ARRAY[...])，统一为 IN(...)；
    - PG 把字面量渲染为 (0)::numeric 等，折叠 (N) -> N；
    - 分组结构经 _canon 保留。
    """
    if expr is None:
        return None
    s = expr.strip()
    s = re.sub(r"^CHECK\s+", "", s)
    s = re.sub(r"::[a-zA-Z_. ]+", "", s)                         # 去 ::cast
    s = re.sub(r"=\s*ANY\s*\(\s*ARRAY\[([^\]]*)\]\)", r"IN(\1)", s)  # IN 渲染统一
    s = re.sub(r"\((-?\d+(?:\.\d+)?)\)", r"\1", s)               # (0)::numeric -> 0
    s = re.sub(r"\s+", "", s)
    return _canon(s)


def norm_expr_flat(expr):
    """生成列表达式专用扁平规范化：去 CHECK 前缀/cast/ANY->IN/(N)->N 后删除全部括号与空白。

    生成列（CASE/encode/sha256）里的括号是 PG 对 cast/条件稳定添加的包裹，非逻辑分组，
    不适用 grouping-preserving 规则；两侧同规约后精确比对。
    """
    if expr is None:
        return None
    s = expr.strip()
    s = re.sub(r"^CHECK\s+", "", s)
    s = re.sub(r"::[a-zA-Z_. ]+", "", s)
    s = re.sub(r"=\s*ANY\s*\(\s*ARRAY\[([^\]]*)\]\)", r"IN(\1)", s)
    s = re.sub(r"\((-?\d+(?:\.\d+)?)\)", r"\1", s)
    s = s.replace("(", "").replace(")", "")
    return re.sub(r"\s+", "", s)


def _check_norm_expr_invariants():
    """R56-1 §4.4：不同 AND/OR 分组不得规范化等价。"""
    a = norm_expr("(a AND b) OR c")
    b = norm_expr("a AND (b OR c)")
    return a != b, f"(a AND b) OR c -> {a!r}; a AND (b OR c) -> {b!r}"


# ---------------------------------------------------------------------------
# 1. 31 业务表
# ---------------------------------------------------------------------------
with create_engine(URL).connect() as c:
    tables = [r[0] for r in c.execute(text(
        "SELECT tablename FROM pg_tables WHERE schemaname='app' AND tablename <> 'alembic_version' ORDER BY tablename"
    )).fetchall()]
    check("31 业务表 exact-set", set(tables) == set(E.TABLES),
          f"missing={set(E.TABLES)-set(tables)} extra={set(tables)-set(E.TABLES)}")

    # -----------------------------------------------------------------------
    # 2. 503 列定义 exact-set
    # -----------------------------------------------------------------------
    rows = c.execute(text(
        "SELECT c.relname AS tbl, a.attname, pg_catalog.format_type(a.atttypid, a.atttypmod) AS ftype, "
        "a.attnotnull, a.attidentity, a.attgenerated, "
        "pg_get_expr(d.adbin, d.adrelid) AS defexpr "
        "FROM pg_attribute a "
        "JOIN pg_class c ON c.oid = a.attrelid "
        "JOIN pg_namespace n ON n.oid = c.relnamespace "
        "LEFT JOIN pg_attrdef d ON d.adrelid = a.attrelid AND d.adnum = a.attnum "
        "WHERE n.nspname='app' AND c.relkind='r' AND c.relname <> 'alembic_version' "
        "AND a.attnum > 0 AND NOT a.attisdropped "
        "ORDER BY c.relname, a.attnum"
    )).fetchall()

    db_cols = {}
    for tbl, attname, ftype, notnull, attident, attgen, defexpr in rows:
        is_gen = attgen == "s"
        db_cols.setdefault(tbl, []).append({
            "name": attname,
            "type": norm_type(ftype),
            "notnull": bool(notnull),
            "identity": attident == "a",  # ALWAYS
            "generated": is_gen,
            # generated 列的 pg_get_expr 是生成表达式，不是 DEFAULT；非 generated 才比较默认值
            "default": None if is_gen else norm_default(defexpr),
            "gen_expr": defexpr if is_gen else None,
        })

    total_db = sum(len(v) for v in db_cols.values())
    check("catalog 列总数 = 503", total_db == 503, f"got {total_db}")
    check("catalog 表数（含列）匹配 31", set(db_cols) == set(E.TABLES))

    col_fail = []
    for tbl in E.TABLES:
        exp = E.COLUMNS[tbl]
        got = db_cols.get(tbl, [])
        if len(exp) != len(got):
            col_fail.append(f"{tbl}: exp {len(exp)} got {len(got)}")
            continue
        for e, g in zip(exp, got):
            name, udt, notnull, default, ident, gen, ck = e
            if g["name"] != name:
                col_fail.append(f"{tbl}.{g['name']} != {name}")
                continue
            if g["type"] != udt:
                col_fail.append(f"{tbl}.{name} type {g['type']} != {udt}")
            if g["notnull"] != notnull:
                col_fail.append(f"{tbl}.{name} notnull {g['notnull']} != {notnull}")
            if g["identity"] != ident:
                col_fail.append(f"{tbl}.{name} identity {g['identity']} != {ident}")
            if g["generated"] != (gen is not None):
                col_fail.append(f"{tbl}.{name} generated {g['generated']} != {gen is not None}")
            if gen is None:
                if norm_default(default) != g["default"]:
                    col_fail.append(f"{tbl}.{name} default {g['default']!r} != {norm_default(default)!r}")
            else:
                # 生成列表达式：PG 的括号是 cast/条件包裹，非逻辑分组，用扁平规范化
                gexpr = norm_expr_flat(g["gen_expr"])
                eexpr = norm_expr_flat(gen)
                if gexpr != eexpr:
                    col_fail.append(f"{tbl}.{name} gen_expr {gexpr!r} != {eexpr!r}")
    check("503 列定义 exact-set（type/null/default/identity/generated）", not col_fail,
          "; ".join(col_fail[:8]))

    ident_always = sum(1 for v in db_cols.values() for col in v if col["identity"])
    jsonb_cols = sum(1 for v in db_cols.values() for col in v if col["type"] == "jsonb")
    uuid_defaults = sum(1 for v in db_cols.values() for col in v
                        if col["name"] == "public_id" and col["default"] == "gen_random_uuid()")
    check("31 identity 全为 GENERATED ALWAYS", ident_always == 31, f"got {ident_always}")
    check("23 jsonb 字段", jsonb_cols == 23, f"got {jsonb_cols}")
    check("14 public_id 默认 gen_random_uuid()", uuid_defaults == 14, f"got {uuid_defaults}")

    # -----------------------------------------------------------------------
    # 3. FK 全定义 exact-set（28 基础 + 58 组合）
    # -----------------------------------------------------------------------
    fk_rows = c.execute(text(
        "SELECT cr.relname AS child, cp.relname AS parent, "
        "pc.conname, pc.confdeltype, "
        "(SELECT string_agg(a.attname, ',' ORDER BY k.ord) FROM unnest(pc.conkey) WITH ORDINALITY k(attnum, ord) "
        "  JOIN pg_attribute a ON a.attrelid = pc.conrelid AND a.attnum = k.attnum) AS ccols, "
        "(SELECT string_agg(a.attname, ',' ORDER BY k.ord) FROM unnest(pc.confkey) WITH ORDINALITY k(attnum, ord) "
        "  JOIN pg_attribute a ON a.attrelid = pc.confrelid AND a.attnum = k.attnum) AS pcols "
        "FROM pg_constraint pc "
        "JOIN pg_class cr ON cr.oid = pc.conrelid "
        "JOIN pg_class cp ON cp.oid = pc.confrelid "
        "JOIN pg_namespace ns ON ns.oid = cr.relnamespace "
        "WHERE ns.nspname='app' AND pc.contype='f' "
        "ORDER BY cr.relname, pc.conname"
    )).fetchall()

    db_fk = {}
    for child, parent, conname, confdel, ccols, pcols in fk_rows:
        db_fk.setdefault((child, parent), []).append({
            "name": conname,
            "ccols": tuple(ccols.split(",")) if ccols else (),
            "pcols": tuple(pcols.split(",")) if pcols else (),
            "action": {"a": "NO ACTION", "r": "RESTRICT", "c": "CASCADE", "n": "SET NULL", "d": "SET DEFAULT"}[confdel],
        })

    # 28 基础 FK 全定义：table/name/columns/action（R56-1 §4.1）
    base_fail = []
    got_base = {}
    for t in E.TABLES:
        entries = db_fk.get((t, "tenants"), [])
        single = [e for e in entries if e["ccols"] == ("tenant_id",) and e["pcols"] == ("id",)]
        if single:
            got_base[t] = single[0]
    for t, name, cols, action in E.BASE_FKS:
        e = got_base.get(t)
        if e is None:
            base_fail.append(f"{t}: 缺基础 FK")
            continue
        if e["name"] != name:
            base_fail.append(f"{t} name {e['name']} != {name}")
        if tuple(cols) != e["ccols"]:
            base_fail.append(f"{t} cols {e['ccols']} != {cols}")
        if e["action"] != action:
            base_fail.append(f"{t} action {e['action']} != {action}")
    if set(got_base) != {t for t, _n, _c, _a in E.BASE_FKS}:
        extra = set(got_base) - {t for t, _n, _c, _a in E.BASE_FKS}
        base_fail.append(f"extra={extra}")
    check("28 基础 FK 全定义 exact-set（table/name/columns/action）", not base_fail,
          "; ".join(base_fail[:8]))

    # 58 组合 FK
    comp_fail = []
    for child, parent, cc, pc, _n in E.COMPOSITE_FKS:
        entries = db_fk.get((child, parent), [])
        want = (tuple(cc), tuple(pc))
        matched = [e for e in entries if (e["ccols"], e["pcols"]) == want]
        if len(matched) != 1:
            comp_fail.append(f"{child}->{parent}: {want} not found; got {[(e['ccols'], e['pcols']) for e in entries]}")
            continue
        e = matched[0]
        if e["name"] != f"fk_{child}_{parent}":
            comp_fail.append(f"{child}->{parent} name {e['name']} != fk_{child}_{parent}")
        action = E.FK_ACTIONS.get((child, parent), "NO ACTION")
        if e["action"] != action:
            comp_fail.append(f"{child}->{parent} action {e['action']} != {action}")
    check("58 组合 FK 全定义 exact-set（列序/名称/action）", not comp_fail, "; ".join(comp_fail[:8]))

    total_fk = sum(len(v) for v in db_fk.values())
    check("总 FK = 86", total_fk == 86, f"got {total_fk}")

    # -----------------------------------------------------------------------
    # 4. 17 父候选键 UNIQUE(tenant_id,id)
    # -----------------------------------------------------------------------
    parent_uniq = c.execute(text(
        "SELECT cr.relname, pc.conname FROM pg_constraint pc "
        "JOIN pg_class cr ON cr.oid = pc.conrelid "
        "JOIN pg_namespace ns ON ns.oid = cr.relnamespace "
        "WHERE ns.nspname='app' AND pc.contype='u' AND array_length(pc.conkey,1)=2 "
        "AND (SELECT attname FROM pg_attribute WHERE attrelid=pc.conrelid AND attnum=pc.conkey[1])='tenant_id' "
        "AND (SELECT attname FROM pg_attribute WHERE attrelid=pc.conrelid AND attnum=pc.conkey[2])='id' "
        "ORDER BY cr.relname"
    )).fetchall()
    got_pk = {(t, n) for t, n in parent_uniq}
    want_pk = {(t, f"uq_{t}_tenant_id_id") for t in E.PARENT_KEYS}
    check("17 父候选键 UNIQUE(tenant_id,id) exact table/name", got_pk == want_pk,
          f"missing={want_pk-got_pk} extra={got_pk-want_pk}")

    # -----------------------------------------------------------------------
    # 5. 4 × UNIQUE NULLS NOT DISTINCT（表/索引名/列序；R56-1 §4.2）
    # -----------------------------------------------------------------------
    nulls = c.execute(text(
        "SELECT cr.relname, i.indexrelid::regclass::text, "
        "(SELECT string_agg(a.attname, ',' ORDER BY k.ord) FROM unnest(i.indkey) WITH ORDINALITY k(attnum, ord) "
        "  JOIN pg_attribute a ON a.attrelid = i.indrelid AND a.attnum = k.attnum WHERE k.attnum > 0) AS cols "
        "FROM pg_index i JOIN pg_class cr ON cr.oid = i.indrelid "
        "JOIN pg_namespace ns ON ns.oid = cr.relnamespace "
        "WHERE ns.nspname='app' AND i.indnullsnotdistinct ORDER BY cr.relname"
    )).fetchall()
    got_nulls = {(r[0], r[1].split(".")[-1], tuple(r[2].split(","))) for r in nulls if r[2]}
    want_nulls = {(t, idx, tuple(cols)) for t, idx, cols in E.NULLS_UNIQUE}
    check("4 × UNIQUE NULLS NOT DISTINCT exact-set（表/索引名/列序）", got_nulls == want_nulls,
          f"missing={want_nulls-got_nulls} extra={got_nulls-want_nulls}")

    # -----------------------------------------------------------------------
    # 6. 2 exclusion（表 + 约束名 + 完整定义规范化；R56-1 §4.2）
    # -----------------------------------------------------------------------
    excl_rows = c.execute(text(
        "SELECT cr.relname, pc.conname, pg_get_constraintdef(pc.oid) "
        "FROM pg_constraint pc JOIN pg_class cr ON cr.oid = pc.conrelid "
        "JOIN pg_namespace ns ON ns.oid = cr.relnamespace "
        "WHERE ns.nspname='app' AND pc.contype='x' ORDER BY cr.relname, pc.conname"
    )).fetchall()
    got_excl = {(r[0], r[1], norm_expr(r[2])) for r in excl_rows}
    want_excl = {(t, n, norm_expr(d)) for t, n, d in E.EXCLUSIONS}
    check("2 exclusion 全定义 exact-set（表/名/pg_get_constraintdef 规范化）", got_excl == want_excl,
          f"missing={want_excl-got_excl} extra={got_excl-want_excl}")

    # -----------------------------------------------------------------------
    # 7. 15 部分唯一 + 8 普通索引（表/名/列/谓词）
    # -----------------------------------------------------------------------
    idx_rows = c.execute(text(
        "SELECT cr.relname, i.indexrelid::regclass::text AS idxname, i.indisunique, "
        "pg_get_expr(i.indpred, i.indrelid) AS pred, "
        "(SELECT string_agg(a.attname, ',' ORDER BY k.ord) FROM unnest(i.indkey) WITH ORDINALITY k(attnum, ord) "
        "  JOIN pg_attribute a ON a.attrelid = i.indrelid AND a.attnum = k.attnum WHERE k.attnum > 0) AS cols "
        "FROM pg_index i JOIN pg_class cr ON cr.oid = i.indrelid "
        "JOIN pg_namespace ns ON ns.oid = cr.relnamespace "
        "WHERE ns.nspname='app' AND i.indisunique AND i.indpred IS NOT NULL ORDER BY cr.relname"
    )).fetchall()
    db_partial = {(r[0], r[1].split(".")[-1]): (tuple(r[4].split(",")), norm_expr(r[3])) for r in idx_rows if r[3]}
    partial_fail = []
    for t, idx, cols, where in E.PARTIAL_UNIQUE:
        key = (t, idx)
        if key not in db_partial:
            partial_fail.append(f"{key} missing")
            continue
        got_cols, got_pred = db_partial[key]
        if tuple(cols) != got_cols:
            partial_fail.append(f"{key} cols {got_cols} != {tuple(cols)}")
        if norm_expr(where) != got_pred:
            partial_fail.append(f"{key} pred {got_pred!r} != {norm_expr(where)!r}")
    check("15 部分唯一索引 exact-set（表/名/列/谓词）", len(idx_rows) == 15 and not partial_fail,
          f"got {len(idx_rows)}; {'; '.join(partial_fail[:6])}")

    plain_rows = c.execute(text(
        "SELECT cr.relname, i.indexrelid::regclass::text AS idxname, "
        "(SELECT string_agg(a.attname, ',' ORDER BY k.ord) FROM unnest(i.indkey) WITH ORDINALITY k(attnum, ord) "
        "  JOIN pg_attribute a ON a.attrelid = i.indrelid AND a.attnum = k.attnum WHERE k.attnum > 0) AS cols "
        "FROM pg_index i JOIN pg_class cr ON cr.oid = i.indrelid "
        "JOIN pg_namespace ns ON ns.oid = cr.relnamespace "
        "WHERE ns.nspname='app' AND NOT i.indisunique AND i.indpred IS NULL "
        "AND NOT EXISTS (SELECT 1 FROM pg_constraint pc WHERE pc.conindid = i.indexrelid AND pc.contype='x') "
        "ORDER BY cr.relname"
    )).fetchall()
    db_plain = {(r[0], r[1].split(".")[-1]): tuple(r[2].split(",")) for r in plain_rows if r[2]}
    plain_fail = []
    for t, idx, cols in E.PLAIN_INDEXES:
        key = (t, idx)
        if key not in db_plain:
            plain_fail.append(f"{key} missing")
        elif tuple(cols) != db_plain[key]:
            plain_fail.append(f"{key} cols {db_plain[key]} != {tuple(cols)}")
    check("8 普通索引 exact-set（表/名/列）", len(plain_rows) == 8 and not plain_fail,
          f"got {len(plain_rows)}; {'; '.join(plain_fail[:6])}")

    # -----------------------------------------------------------------------
    # 8. 27 列级 CHECK + 1 具名 CHECK
    # -----------------------------------------------------------------------
    ck_rows = c.execute(text(
        "SELECT cr.relname, pc.conname, pg_get_constraintdef(pc.oid) AS def "
        "FROM pg_constraint pc JOIN pg_class cr ON cr.oid = pc.conrelid "
        "JOIN pg_namespace ns ON ns.oid = cr.relnamespace "
        "WHERE ns.nspname='app' AND pc.contype='c' ORDER BY cr.relname, pc.conname"
    )).fetchall()
    db_checks = {(r[0], norm_expr(r[2])) for r in ck_rows}
    named = [r for r in ck_rows if r[1] == E.NAMED_CHECK]
    check("具名 CHECK ck_feedback_subject_map", len(named) == 1, str([r[1] for r in ck_rows]))
    ck_fail = []
    for (t, cname), expr in E.COLUMN_CHECKS.items():
        if (t, norm_expr(f"CHECK (({expr}))")) not in db_checks and (t, norm_expr(f"CHECK ({expr})")) not in db_checks:
            ck_fail.append(f"{t}.{cname}: {expr}")
    check("27 列级 CHECK exact-set", len(ck_rows) == 28 and not ck_fail,
          f"got {len(ck_rows)} ck; missing={ck_fail[:6]}")

    # -----------------------------------------------------------------------
    # 9. 31 业务 PK（表/名/列；R56-1 §4.3）
    # -----------------------------------------------------------------------
    pk_rows = c.execute(text(
        "SELECT cr.relname, pc.conname, "
        "(SELECT string_agg(a.attname, ',' ORDER BY k.ord) FROM unnest(pc.conkey) WITH ORDINALITY k(attnum, ord) "
        "  JOIN pg_attribute a ON a.attrelid = pc.conrelid AND a.attnum = k.attnum) AS cols "
        "FROM pg_constraint pc JOIN pg_class cr ON cr.oid = pc.conrelid "
        "JOIN pg_namespace ns ON ns.oid = cr.relnamespace "
        "WHERE ns.nspname='app' AND pc.contype='p' AND cr.relname <> 'alembic_version' ORDER BY cr.relname"
    )).fetchall()
    got_pk_all = {(r[0], r[1], tuple(r[2].split(","))) for r in pk_rows}
    want_pk_all = {(t, n, tuple(cols)) for t, n, cols in E.PRIMARY_KEYS}
    check("31 业务 PK exact-set（表/名/列）", got_pk_all == want_pk_all,
          f"missing={want_pk_all-got_pk_all} extra={got_pk_all-want_pk_all}")

    # -----------------------------------------------------------------------
    # 10. 34 普通 UNIQUE（表/列；不含 17 父候选键；R56-1 §4.3）
    # -----------------------------------------------------------------------
    uniq_rows = c.execute(text(
        "SELECT cr.relname, "
        "(SELECT string_agg(a.attname, ',' ORDER BY k.ord) FROM unnest(pc.conkey) WITH ORDINALITY k(attnum, ord) "
        "  JOIN pg_attribute a ON a.attrelid = pc.conrelid AND a.attnum = k.attnum) AS cols "
        "FROM pg_constraint pc JOIN pg_class cr ON cr.oid = pc.conrelid "
        "JOIN pg_namespace ns ON ns.oid = cr.relnamespace "
        "WHERE ns.nspname='app' AND pc.contype='u' "
        "AND NOT (array_length(pc.conkey,1)=2 "
        "  AND (SELECT attname FROM pg_attribute WHERE attrelid=pc.conrelid AND attnum=pc.conkey[1])='tenant_id' "
        "  AND (SELECT attname FROM pg_attribute WHERE attrelid=pc.conrelid AND attnum=pc.conkey[2])='id') "
        "ORDER BY cr.relname, cols"
    )).fetchall()
    got_uniq = {(r[0], tuple(r[1].split(","))) for r in uniq_rows}
    want_uniq = {(t, tuple(cols)) for t, cols in E.UNIQUE_CONSTRAINTS}
    check("34 普通 UNIQUE exact-set（表/列，排除父候选键）", got_uniq == want_uniq,
          f"missing={want_uniq-got_uniq} extra={got_uniq-want_uniq}")

    # -----------------------------------------------------------------------
    # 11. user trigger = 0（正确 join；T4 安装后可配为 17）
    # -----------------------------------------------------------------------
    trg = c.execute(text(
        "SELECT count(*) FROM pg_trigger t "
        "JOIN pg_class c ON c.oid = t.tgrelid "
        "JOIN pg_namespace n ON n.oid = c.relnamespace "
        "WHERE n.nspname='app' AND NOT t.tgisinternal AND t.tgname NOT LIKE 'pg_%'"
    )).scalar()
    expect_trg = int(os.environ.get("T4_TRIGGER_EXPECT", "0"))
    check(f"user trigger = {expect_trg}（正确 join）", trg == expect_trg, f"got {trg}")

    # -----------------------------------------------------------------------
    # 12. 生成器数据 vs t3_expected 同源一致性
    # -----------------------------------------------------------------------
    import gen_t3_migration as G  # noqa: E402

    gen_fail = []
    gen_fks = {(c, p) for c, p, _cc, _pc, _n in G.COMPOSITE_FKS}
    if gen_fks != {(c, p) for c, p, _cc, _pc, _n in E.COMPOSITE_FKS}:
        gen_fail.append("COMPOSITE_FKS 不一致")
    if set(G.PARENT_KEYS) != set(E.PARENT_KEYS):
        gen_fail.append("PARENT_KEYS 不一致")
    if G.FK_ACTIONS != E.FK_ACTIONS:
        gen_fail.append("FK_ACTIONS 不一致")
    if {t for w in G.WAVES for t in w} != set(E.TABLES):
        gen_fail.append("WAVES/TABLES 不一致")
    if G.COLUMN_CHECKS != E.COLUMN_CHECKS:
        gen_fail.append("COLUMN_CHECKS 不一致")
    check("生成器数据 与 t3_expected 同源一致", not gen_fail, "; ".join(gen_fail))

# ---------------------------------------------------------------------------
# 13. norm_expr 逻辑分组不变量（纯函数，不依赖 DB）
# ---------------------------------------------------------------------------
ok_inv, detail = _check_norm_expr_invariants()
check("norm_expr 保留逻辑分组（(a AND b) OR c != a AND (b OR c)）", ok_inv, detail)

print("T3-SCHEMA-ASSERT:", "PASS" if ok else "FAIL")
sys.exit(0 if ok else 1)