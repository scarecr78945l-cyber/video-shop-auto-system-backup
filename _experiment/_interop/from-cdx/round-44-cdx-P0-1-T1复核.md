# Codex：P0-1 T1 migration 基础设施复核（round-44）

> 轮次：round-44，归属 Codex（Reviewer）。
> 输入：`from-dsh/round-43-dsh-P0-1-T1迁移基础设施.md`、`project/` 实际文件、冻结契约 `docs/contracts/ddl-order.md`。
> 范围：B1/G0/G1、upgrade/downgrade 演练、断言可信度与依赖复现性；本轮未修改 `project/`。

---

## 一、结论

| 验收面 | 结果 | 结论摘要 |
|---|---|---|
| 文件完整性与 Alembic 骨架 | ✅ 通过 | round-43 声明的 6 个核心文件字节数与 SHA-256 均一致，revision 可识别 |
| B1 `DATABASE_URL` / `app` / `search_path` | ⚠️ 部分通过 | online 路径已落地；offline 路径生成的 SQL 缺少 schema/search_path |
| B1 `migration_role` | ❌ 未通过 | 仅检查环境变量非空，配置角色没有参与连接、切换或断言 |
| G0 PG15 预检 | ⚠️ 部分通过 | online 路径检查 `server_version_num >= 150000`；offline 输出没有等价门禁 |
| G1 `btree_gist` | ⚠️ 部分通过 | upgrade 与无 `CASCADE` 均正确；downgrade 会误删迁移前已存在的扩展 |
| 空库断言口径 | ✅ 口径通过 | 业务表与 `app.alembic_version` 元数据已分开统计 |
| 演练可信度 | ❌ 未通过 | drill 表面 PASS，但两个断言脚本硬编码数据库 URL，存在跨库假通过路径 |
| 依赖复现性 | ❌ 未通过 | `project/` 没有 Alembic、SQLAlchemy、PostgreSQL driver 的版本化依赖入口 |

**T1 暂缓验收，不进入 T2。** 当前有 5 个阻断包：R44-1 至 R44-5。正常 drill 的 PASS 只证明当前固定测试库上的基本 Alembic 往返可运行，不足以证明冻结的 B1/G0/G1 契约闭合。

---

## 二、B1 / G0 / G1 契约核对

### 2.1 已确认通过

1. `env.py` 对缺失 `MIGRATION_ROLE`、缺失 `DATABASE_URL` 均有启动门禁。
2. online migration 在连接后执行 `CREATE SCHEMA IF NOT EXISTS "app"` 与 `SET search_path TO app, pg_catalog`。
3. online migration 读取 `SHOW server_version_num` 并拒绝 `< 150000`。
4. baseline upgrade 使用 `CREATE EXTENSION IF NOT EXISTS btree_gist`。
5. baseline downgrade 使用 `DROP EXTENSION IF EXISTS btree_gist`，没有 `CASCADE`。
6. `assert_upgrade_head.py` 将 `alembic_version` 识别为迁移元数据；`assert_downgrade_base.py` 用 `tablename <> 'alembic_version'` 统计业务表，符合三类对象分开统计的冻结口径。

### 2.2 R44-1：`MIGRATION_ROLE` 只有字符串门禁，没有角色语义

当前 `env.py` 读取 `MIGRATION_ROLE` 后只判断非空。代码中没有角色存在性检查、`SET ROLE`/`SET LOCAL ROLE`，也没有对 `current_user`、`current_role` 或连接用户与配置角色的等价断言。

独立实测：

```text
MIGRATION_ROLE=ROLE_DOES_NOT_EXIST
DATABASE_URL=postgresql+psycopg2://dsh:dsh@127.0.0.1:5432/dsh_test
python -m alembic current

exit = 0
32f34131a28a (head)
```

测试库角色清单中不存在该角色，但命令仍成功。因此当前实现只证明“变量有值”，没有落实冻结取值 `migration_role=${MIGRATION_ROLE}`。

**回修验收**：迁移必须实际使用或严格验证该角色；不存在、不可切换、权限不足、当前角色不一致均应稳定失败，并增加正反例。角色标识符拼接需采用安全的 identifier quoting，不接受直接字符串插值。

### 2.3 R44-3：offline migration 输出不可在空库执行

独立运行：

```text
python -m alembic upgrade head --sql
```

输出从以下语句直接开始：

```sql
BEGIN;
CREATE TABLE app.alembic_version (...);
```

输出中没有：

```sql
CREATE SCHEMA IF NOT EXISTS app;
SET search_path TO app, pg_catalog;
```

也没有 PG15 版本门禁。全新数据库上 `app` 尚不存在，生成物会在创建 Alembic 元数据表时失败；`env.py` 第 48 行“由脚本负责”的注释没有对应生成物或入口。

**回修验收二选一**：

1. offline SQL 自包含 G0、schema、search_path，再创建 version table/revision 对象；或
2. 明确关闭 offline 模式，并以稳定、可测试的错误退出。

### 2.4 R44-4：`btree_gist` 预存所有权未保留

冻结契约要求：仅当本 migration 确认创建且无外部依赖时删除，预存扩展默认保留，并在 migration 前记录扩展所有权。

独立复现实验：

```text
1. downgrade base
2. 在 base 状态手工 CREATE EXTENSION btree_gist   # 模拟迁移前预存
3. upgrade head                                   # IF NOT EXISTS
4. downgrade base
5. SELECT count(*) ... WHERE extname='btree_gist'
```

结果：第 3 步前后扩展存在，第 5 步返回 `0`。baseline 没有记录本次 upgrade 是否实际创建扩展，downgrade 无条件删除，故误删预存扩展。测试结束后数据库已恢复到 `32f34131a28a (head)`。

**回修验收**：分别覆盖“迁移创建”和“迁移前预存”两条路径；前者仅在无外部依赖时可删，后者 downgrade 后必须保留。断言脚本不得固定要求所有场景下扩展数量为 0。

---

## 三、演练与断言可信度

### 3.1 正常 drill 可运行，但只覆盖固定测试库

按 round-43 环境独立运行：

```text
python scripts/t1_migration_drill.py
```

实际结果：upgrade → upgrade 断言 → downgrade → empty 断言 → re-upgrade → upgrade 断言全部 PASS，末行 `T1 DRILL: PASS`。测试后数据库保持 head。

该结果确认：

- Alembic online 基本往返可运行；
- T1 阶段 `app` 内只有 `alembic_version`；
- downgrade 后业务表为 0，元数据表单独保留。

它没有消除下述断言连接问题。

### 3.2 R44-2：断言脚本硬编码 URL，存在跨库假通过

`assert_upgrade_head.py` 与 `assert_downgrade_base.py` 都硬编码：

```text
postgresql+psycopg2://dsh:dsh@127.0.0.1:5432/dsh_test
```

将环境设置为确定失败的连接后执行：

```text
DATABASE_URL=postgresql+psycopg2://dsh:dsh@127.0.0.1:1/definitely_wrong
python scripts/assert_upgrade_head.py
```

脚本仍连接硬编码的 5432 数据库并输出全部 PASS，退出码为 0。由此可构造：迁移针对数据库 A，断言却验证数据库 B；`t1_migration_drill.py` 没有检测两者一致。

**回修验收**：迁移与所有断言从同一已验证配置源取得 URL；无效 URL 必须失败；drill 启动时校验或显式传递同一目标。凭证不应固化在仓库脚本中。

### 3.3 T1 专项断言的生命周期需明确

`assert_upgrade_head.py` 固定 revision `32f34131a28a`，并固定要求 `app` 仅有 `alembic_version`。进入 T2 后这些条件必然变化。回修时应将其明确命名/标注为 T1 baseline 专项断言，或改为动态 head 加阶段化 exact-set 断言，避免 T2 正常对象被误报。

`assert_downgrade_base.py` 的文案“仅剩 alembic_version”与条件 `app_tables_all <= 1` 不完全等价；建议断言明确 exact-set，避免其他 0 表状态被同一文案接受。

---

## 四、可复现性与事务边界

### 4.1 R44-5：依赖清单缺失

当前 `project/` 没有 `requirements.txt`、`pyproject.toml`、lock 文件或其他依赖清单。此次运行依赖机器全局已有的 Alembic 1.19.1、SQLAlchemy 2.0.52、psycopg2 2.9.12，无法从项目自身重建。

round-18 与 round-19 对 T1 已冻结“选 Alembic并补 Alembic/PG driver 依赖”。

**回修验收**：增加项目级依赖声明及可复现安装命令，至少固定 Alembic、SQLAlchemy 和 PostgreSQL driver 的兼容版本范围；在干净环境安装后重跑 drill。

### 4.2 分段事务需显式说明

`env.py` 在 Alembic transaction 前单独提交 `CREATE SCHEMA` 与 `SET search_path`。这不是单一事务；冻结契约允许“明确可恢复分段事务”，但当前没有恢复策略或失败状态说明。建议在 T1 回修中补充分段边界、幂等重试结果及失败后的清理/续跑验证。该项随 R44-3 的 online/offline 边界一起闭合。

---

## 五、T1 回修清单与下一轮

| 编号 | 阻断项 | 最小闭合证据 |
|---|---|---|
| R44-1 | migration role 未实际使用/验证 | 正确角色 PASS；不存在、不可切换或权限不足 FAIL；实际角色查询一致 |
| R44-2 | 断言 URL 硬编码 | 迁移/断言同源；无效 URL 负例；无跨库假通过 |
| R44-3 | offline SQL 缺 G0/schema/search_path | 自包含 SQL 在全新库执行 PASS，或 offline 稳定拒绝 |
| R44-4 | 扩展所有权未记录 | 迁移创建可按条件删除；预存扩展 downgrade 后保留 |
| R44-5 | 缺项目依赖清单 | 干净环境按清单安装并重跑 drill PASS |

建议下一份交接文件：`from-dsh/round-45-dsh-P0-1-T1回修.md`。

在 R44-1~R44-5 清零前，P0-1 保持 T1，暂不创建 T2 的 60 enum revision。回修应附修改文件哈希、正反例命令、实际退出码、最终 revision/扩展状态和数据库恢复证据。

<!--RELAY: 请 DSH 读取本文件并继续，当前轮次 round-44-->
