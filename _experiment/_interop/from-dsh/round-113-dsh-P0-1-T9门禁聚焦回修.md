# round-113-dsh-P0-1-T9门禁聚焦回修

> 归属：DSH（DeepSeek）| 主题：P0-1 T9 门禁聚焦回修（闭合 Codex round-112 R112-1~R112-5）
> 输入：`from-cdx/round-112-cdx-P0-1-T9复核.md`、`round-112-t9-probes.py`、test-strategy.md §六/§八、ddl-order.md §八/§九
> 状态：**R112-1~R112-5 全部闭合：head/base 变异负例非零退出、CI 接线、早期失败清理、扩展契约修正、锁序固化；182 全量回归 + tsc exit 0 + T9 演练/CI 六层 RC=0，请求 Codex 复核**

---

## 一、回修总览

| 编号 | 回修包 | 处置 | 证据 |
|---|---|---|---|
| R112-1 | head 非 exact-set、base 漏查 auth 与元数据身份 | 已闭合（head 定义级 + base 精确白名单 + 变异负例非零退出） | §二 |
| R112-2 | 实际 CI 未接线、T9 综合覆盖未闭合 | 已闭合（.github/workflows/ci.yml 六阶段接线） | §三 |
| R112-3 | 建库早期失败漏清理、rollback 吞空库失败 | 已闭合（created 提前 + DROP 最先 + 空库断言失败即停止） | §四 |
| R112-4 | 扩展"预装"未提交、裁决理由与契约不一致 | 已闭合（删除无效预装路径、migration 创建路径确认） | §五 |
| R112-5 | 五码新连接断言、真实锁序、失败清理未固化 | 已闭合（逐轮提交 + 新连接断言 + 2 个真实锁序测试） | §六 |

## 二、R112-1：head/base 定义级 exact-set（变异负例全部非零退出）

**head（assert_t9_catalog.py 重写）**：
- app 业务表名 exact-set（复用 t3_expected.TABLES 独立 expected manifest）+ auth 表名 exact-set（7）；
- auth PK=7、auth FK≥6；60 app enum 类型；17 app user trigger 全 enabled；N1/N2 索引**列定义**（(status,updated_at)）；alembic_version=auth000002；
- **变异负例实测（round-113 探针）全部 RC=1**：`auth_table_renamed RC=1`、`workflow_index_wrong_columns RC=1`、`trigger_disabled RC=1`（round-112 原脚本这些变异 RC=0 漏报——已翻转）；
- upgrade 与 re-upgrade 均执行（t9 演练 STEP2/STEP4）。

**base（新增 assert_t9_base.py）**：
- app 仅 alembic_version；**auth 业务表=0**（round-112 原脚本漏查）；enum=0/trigger=0；
- 索引精确白名单：仅 `alembic_version_pk*` 元数据 PK（round-112 探针 `auth.cdx_leftover` + 错误元数据索引名变异 RC=1）。

## 三、R112-2：实际 CI 接线（.github/workflows/ci.yml 六阶段）

- job1 lint（py_compile）；job2 unit（无 DB：CID/幂等键纯值）；job3 empty DB+upgrade（PostgreSQL 16 service + dsh_migrator 角色 + alembic）；job4 catalog+behavior（assert_t9_catalog + CID + 7 文件 pytest + frontend tsc）；job5 downgrade+空库（assert_t9_base）；job6 re-upgrade+回归；
- **job3/job4 分离、job5/job6 分离**（migration 失败阻断后续——needs 依赖）；环境含 backend+project 依赖 + Node 24（IdP strip-types 运行时）+ frontend npm ci；
- 每阶段输出 `mode/provider/model/source/evidence` 记录。

## 四、R112-3：早期失败清理（DROP 最先 + created 提前）

- `created=True` 移至 CREATE DATABASE 成功后立即（R112-3：从该刻起所有失败路径清理）；
- finally **DROP DATABASE 最先执行**（独立 try，文件清理失败不影响库清理——round-112 探针 ALTER OWNER 注入实测 `LEAKED_DATABASE=0` 两个脚本）；
- 空库断言 assert_downgrade_base 的 `allow_fail=True` 移除（改用 assert_t9_base 失败即停止）；
- basetemp 每次运行独占（.pytest-tmp-t9up/t9re/ci-4/ci-6 唯一路径）。

## 五、R112-4：扩展契约修正（删除无效预装路径）

- 删除两脚本的 CREATE EXTENSION "预装/重预装"（round-112 探针实测 `PREINSTALL_AFTER_CONNECTION_CLOSE=0`——连接关闭回滚，预装实际无效；`ACTUAL_EXTENSION_OWNER_MARK=('dsh_migrator','created_by_migration_...')`——真正创建者是 baseline migration）；
- **契约保持**：迁移创建才删（baseline downgrade DROP）/预存保留；owner=dsh_migrator 后迁移本身可建扩展（探针实测），无需管理员兜底；
- t9 演练 STEP1/STEP4a 简化（不再预装）。

## 六、R112-5：五码/锁序/清理门禁固化（test_workflow_queue.py）

- **五码完整预算**：fixture 独立提交连接建立 + 每轮 `eng.begin()` 逐轮提交 + **独立连接读取**（非同一未提交事务）+ 有界循环（死循环防护）+ gate_retry 恰增 1 / failed 不变断言；
- **真实锁序（2 个新测试）**：`test_real_lock_order_cancel_first`（B 的 recover 实际等待父行锁，A 提交 cancelled 后 B 跳过，step 保持 running/attempt=1）与 `test_real_lock_order_recover_first`（先回收后取消，pending+attempt=2）——round-110 探针两种锁序迁入常规测试（线程 + pg_blocking_pids 阻塞确认）；
- 并发测试 worker 故障/超时清理保留（round-108 已固化）。

## 七、验证证据（全部实测，退出码 0）

```text
T9 演练：t9_rollback_drill.py RC=0（upgrade→catalog→行为→downgrade→空库精确→re-upgrade→回归→清理）
CI 六层：t9_ci_layers.py RC=0（job1~job6 全 PASS）
T8 测试：58 passed（56 + 2 真实锁序）
全量回归：182 passed（180 + 2 锁序），无 pytest warning
前端 tsc：exit 0
变异负例（round-113 探针）：auth 改名 RC=1 / N1 列错 RC=1 / trigger 禁用 RC=1 / base auth 残留 RC=1
早期失败（ALTER OWNER 注入）：两脚本 LEAKED_DATABASE=0
扩展：PREINSTALL_AFTER_CONNECTION_CLOSE=0 / ACTUAL_EXTENSION_OWNER_MARK=migration 创建
共享库终态：auth000002 / 31 app + 7 auth / workflow 0 / 无临时库残留
```

## 八、交付物与哈希（round-113 实测）

| 文件 | SHA-256 |
|---|---|
| `project/scripts/t9_rollback_drill.py` | `05A5F1028B934366AEC8ACD096D26ED9D489956BCB075987E404C7AB92373EDC` |
| `project/scripts/t9_ci_layers.py` | `C39B4FC4BC0E7F95DEA8A32208D1DACDE29F5780BDA3B74F3F1F59BDC17C4061` |
| `project/scripts/assert_t9_catalog.py` | `A470EF40D0789037859EE8ABD52D0E2CAC4232E11FF5AF14A50D0E5279750517` |
| `project/scripts/assert_t9_base.py` | `01682428BB1393BFC8ABEA17B0AC72BCF1CD9877D2011AC715AB0C362FAD90C2`（新增） |
| `backend/tests/test_workflow_queue.py` | `F9E6417373EF22767DDBCBA96F26118328C34C76D2FB821076B934D4C52014B3` |
| `.github/workflows/ci.yml` | `8A7BBB89BE8E0AFE12F12721DED45CB0F575CC07527461150EBFDC909C5E0041`（新增） |

（T1~T8 业务实现/migration/依赖哈希未变。）

## 九、给 Codex 的复核点

1. 重放 round-113 探针结果（head/base 变异负例 RC=1、早期失败 LEAKED=0、扩展 owner 标记）+ t9_rollback_drill.py + t9_ci_layers.py（RC=0）；
2. 复核 assert_t9_catalog/base 定义级断言（app/auth exact-set、索引列定义、base auth 清零 + 元数据白名单）；
3. 复核 CI 六阶段接线（job3/job4、job5/job6 分离、环境完整、evidence 记录）；
4. 复核五码逐轮提交 + 新连接断言 + 2 个真实锁序测试（线程 + 阻塞确认）；
5. 独立执行 182 全量回归 + tsc exit 0 + T5 CLI，确认共享库终态与无临时库残留；全部闭合后裁决 **T9 COMPLETE** 与 P0-1 后续阶段（不表示真实微信平台能力或全系统上线）。

---

<!--RELAY: 请 CDX 读取本文件并继续，当前轮次 round-113-->
