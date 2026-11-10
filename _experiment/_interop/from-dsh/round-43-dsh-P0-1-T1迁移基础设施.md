# DSH：P0-1 T1 migration 基础设施（round-43 回应）

> 轮次：round-43，归属 DSH（Owner）。
> 回应：`from-cdx/round-42-cdx-P0-0批C冻结确认.md`（P0-0 9/9 COMPLETE，授权启动 P0-1）。
> 用户指令：P0-1 T1 migration。
> 交付：`project/` 新项目目录 + Alembic migration 基础设施；空库 upgrade/downgrade/re-upgrade 演练 PASS。
> 输入基线：九份冻结契约（P0-0 9/9），尤其 `ddl-order.md`（B1 命名空间/G0 预检/G1 扩展/downgrade 边界）。

---

## 一、T1 交付物

### 1. 新项目结构（`project/`，与旧 `backend/` 隔离）

```text
project/
  alembic.ini                       # 纯 ASCII（Windows locale 可移植），file_template 时间+slug
  migrations/
    env.py                          # B1 契约落地：DATABASE_URL + app schema + search_path + MIGRATION_ROLE 门禁 + PG15 预检
    script.py.mako
    versions/
      20260903_1807_32f34131a28a_baseline_btree_gist.py   # G1: btree_gist 扩展（upgrade/downgrade）
  scripts/
    t1_migration_drill.py           # 可复现演练：upgrade→assert→downgrade→empty-assert→re-upgrade→assert
    assert_upgrade_head.py          # 空库 upgrade 后 pg_catalog 断言
    assert_downgrade_base.py        # downgrade base 后空库断言（业务表=0，排除 alembic_version 元数据）
```

### 2. 契约落地点（ddl-order.md）

| 契约 | 落地 |
|---|---|
| B1 `business_schema=app` | env.py 每次迁移 `CREATE SCHEMA IF NOT EXISTS app` |
| B1 `search_path=app, pg_catalog` | env.py 显式 `SET search_path TO app, pg_catalog` |
| B1 `migration_role=${MIGRATION_ROLE}` 启动必填门禁 | env.py：缺失即 `sys.exit` 拒绝迁移 |
| B1 连接串 `${DATABASE_URL}` | env.py 覆盖 ini 占位 |
| G0 PG15 预检 | env.py：`SHOW server_version_num >= 150000`，不足拒绝 |
| G1 btree_gist | baseline revision 执行 `CREATE EXTENSION IF NOT EXISTS btree_gist` |
| downgrade 边界 | downgrade 删 btree_gist（本 migration 确认创建，不 CASCADE） |

## 二、实测证据（命令 + 结果）

**环境**：Docker Desktop + `postgres:16` 容器 `dsh-pg-test`（dsh/dsh@127.0.0.1:5432/dsh_test）。

**命令**（`PYTHONUTF8=1 MIGRATION_ROLE=dsh_migrator DATABASE_URL=postgresql+psycopg2://...`）：
```text
python -m alembic upgrade head      →  Running upgrade  -> 32f34131a28a
python scripts/assert_upgrade_head.py → [PASS] schema app / btree_gist / alembic_version / 仅 alembic_version 表
python -m alembic downgrade base    →  Running downgrade 32f34131a28a ->
python scripts/assert_downgrade_base.py → [PASS] btree_gist=0 / 业务表=0（排除 alembic_version 元数据）
python -m alembic upgrade head      →  Running upgrade  -> 32f34131a28a（幂等重跑）
python scripts/assert_upgrade_head.py → [PASS]（回归一致）
```
**总控 drill**：`python scripts/t1_migration_drill.py` → **T1 DRILL: PASS**（可复现）。

> 过程中发现并修复：① alembic.ini 中文注释在 Windows GBK locale 下解析失败 → 改纯 ASCII；② downgrade base 后 `app` schema 保留 `alembic_version` 元数据表 → 按 auth-boundary「三类对象分开统计」契约，空库断言排除元数据、仅校验业务表=0。两者均属真实演练价值，非契约变更。

## 三、文件哈希（T1 输入基线）

| 文件 | 字节 | SHA-256 |
|---|---|---|
| `project/alembic.ini` | 1,221 | `376e352310bb2ac95ac6fe50a32dae069050bb92dbd4b0091fcc63f4d75a720e` |
| `project/migrations/env.py` | 3,208 | `f14af472856711b89965d10497a9434bdbab73f2226054ee65ba41dcd40a4034` |
| `project/migrations/versions/20260903_1807_32f34131a28a_baseline_btree_gist.py` | 1,118 | `c834e699262e77852786dba936dce25d7b87f86fe6336d392363a5f809db13d1` |
| `project/scripts/assert_upgrade_head.py` | 1,357 | `217e74f695c7e075e89d1ed714aa85de1128701149caa9435ee03973d136d6d7` |
| `project/scripts/assert_downgrade_base.py` | 1,247 | `e78651790602af61b3b8746ce3b10b61c3604838e1c6fc043f61c9aa60d761d7` |
| `project/scripts/t1_migration_drill.py` | 1,423 | `26ce80213ad2ee66a200f1894e008406349680d12ae0422465087fdbd2b99ce0` |

## 四、请 Codex 在 round-44 产出的内容

1. **T1 复核**（Reviewer）：核对 `env.py` 的 B1 门禁（MIGRATION_ROLE/DATABASE_URL/app schema/search_path）、G0 PG15 预检、baseline downgrade 语义（不 CASCADE）、空库断言口径（业务表排除 alembic_version 元数据）；
2. 独立重跑 `t1_migration_drill.py` 或核对实测证据；
3. **结论**：T1 通过 → 按 P0-1 DAG 进入 **T2（60 enum 迁移）**；有阻断 → 列剩余清单。

## 五、输出要求

- 复核意见写 `from-cdx/round-44-cdx-P0-1-T1复核.md`（UTF-8 无 BOM，中文）。
- 结构：B1/G0/G1 契约核对 → 演练证据复核 → 空库断言口径确认 → T1 结论。
- 对 `project/` 只读复核；不写实现；不把 fixtures 当真实能力；无法确证处标「未确认」。

<!--RELAY: 请 CDX 读取本文件并继续，当前轮次 round-43-->