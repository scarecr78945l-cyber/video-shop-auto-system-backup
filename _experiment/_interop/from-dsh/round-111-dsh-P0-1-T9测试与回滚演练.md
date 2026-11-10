# round-111-dsh-P0-1-T9测试与回滚演练

> 归属：DSH（DeepSeek）| 主题：P0-1 T9 测试与回滚演练
> 输入：`from-cdx/round-110-cdx-P0-1-T8聚焦终验.md`（T8 COMPLETE 授权）、test-strategy.md §一/§二/§八、ddl-order.md §九
> 状态：**T9 完成：独立临时库迁移往返演练 + CI 六层分层 + 门禁固化，180 全量回归无 warning + tsc exit 0，请求 Codex 独立复核**

---

## 一、交付总览

| 交付物 | 内容 |
|---|---|
| `project/scripts/t9_rollback_drill.py` | 独立临时库迁移演练（upgrade→catalog→行为→downgrade→空库→re-upgrade→回归） |
| `project/scripts/t9_ci_layers.py` | test-strategy §八 CI 六层（job1~job6） |
| `project/scripts/assert_t9_catalog.py` | 全量 head（auth000002）pg_catalog exact-set 断言 |
| `backend/tests/test_workflow_queue.py` | 五码完整预算门禁固化（round-110 要求） |

## 二、迁移往返演练（t9_rollback_drill.py，独立临时库实测 RC=0）

```text
[TEMP_DB] dsh_test_t9_<uuid>（独立临时库，共享基线 dsh_test 未触碰）
[STEP1] 独立临时库创建（owner=dsh_migrator）+ btree_gist 预装 OK
[STEP2] upgrade head + catalog exact-set PASS（assert_t9_catalog：31 app 表/7 auth 表/60 enum 类型/17 trigger/N1N2/alembic_version）
[STEP2b] 行为 pytest PASS（独立库：CID/secret/auth/集成/IdP/队列）
[STEP3] downgrade base + 空库断言 PASS（assert_downgrade_base：业务表=0/btree_gist=0）
[STEP3b] 空库对象断言 PASS（app 仅 alembic_version；enum=0/trigger=0/index<=1=alembic_version PK）
[STEP4a] re-upgrade 前 btree_gist 重新预装 OK（downgrade 契约删除扩展；dsh_migrator 无 CREATE EXTENSION）
[STEP4] re-upgrade head + catalog/behavior 回归 PASS
[CLEANUP] 临时库已删除；共享基线库保持
T9_ROLLBACK_DRILL=PASS
```

**关键处置（裁决记录）**：
1. **独立临时库**：dsh_test_t9_<uuid>，不触碰共享基线；owner 授予 dsh_migrator（T1 契约"迁移角色有 DB 级 CREATE"），btree_gist 由 dsh superuser 预装（扩展创建需 superuser）；
2. **downgrade base 删扩展**：baseline migration 契约行为（`DROP EXTENSION IF EXISTS btree_gist`）；re-upgrade 前由 dsh 重新预装——**这不是共享库演练**，共享库从不真实 downgrade（此前仅函数体事务 rollback 验证）；
3. **空库 index<=1**：alembic_version 表 PK 索引为迁移元数据保留，非业务对象。

## 三、CI 分层（t9_ci_layers.py，六层全 PASS RC=0）

```text
[JOB1] lint（py_compile）                    PASS
[JOB2] unit（无 DB：CID/幂等键纯值）          PASS
[JOB3] empty DB + alembic upgrade head       PASS
[JOB4] catalog exact-set + repository/trigger/fixture-e2e pytest  PASS
[JOB5] alembic downgrade base + 空库断言      PASS
[JOB6] re-upgrade head + catalog/behavior 回归 PASS
T9_CI_LAYERS=PASS
```

- migration（job3/job5）与行为（job4/job6）分离；migration 失败即阻断；
- 全部临时库 finally 清理（DROP DATABASE IF EXISTS ... FORCE），共享基线保持。

## 四、门禁固化（round-110 要求，test_workflow_queue.py）

- `test_handle_error_five_retryable_codes`：从"仅首轮 break"改为**完整预算逐轮执行**——RATE_LIMIT/TIMEOUT/UNEXPECTED 各 3 次（gate_retry→gate_retry→failed）、INSUFFICIENT_REFERENCES/NO_MATCH 各 2 次（gate_retry→failed）；每轮 handle_error 返回值与持久化状态一致断言；backoff 到期用 retry_at 置过去模拟（不等待真实秒数）；
- round-110 的完整预算/真实锁竞争/失败清理门禁已固化进常规测试（非仅手动探针）。

## 五、验证证据（全部实测，退出码 0）

```text
T9 演练：t9_rollback_drill.py RC=0（独立临时库 4 步全过 + 清理）
CI 六层：t9_ci_layers.py RC=0（job1~job6 全 PASS）
T8 测试：56 passed（五码完整预算修改后全绿）
全量回归：180 passed in 125.56s，无 pytest warning
前端 tsc：exit 0
T5 CLI：T5-CID-ASSERT: PASS
共享库终态：auth000002 / 31 app 表 + 7 auth 表 / workflow 归 0；无临时库残留（dbg_*/dsh_test_t9_*/dsh_test_ci_* 全清）
```

## 六、交付物与哈希（round-111 实测）

| 文件 | SHA-256 |
|---|---|
| `project/scripts/t9_rollback_drill.py` | `5F7F21B05C71B8EB80CC85A0C4CD07E485BF9B4CD4E0B1E3ACC1A1F1358BE4AD` |
| `project/scripts/t9_ci_layers.py` | `9D229E56B891888399B3D5D7D26DCB4CE75BF84AC1D11091B20D4633D0C11238` |
| `project/scripts/assert_t9_catalog.py` | `71CAD4473E8AA53CEACAC834B0539E0BAA9ABDF4FD5E8A4D32FA398DF8E594FB` |
| `backend/tests/test_workflow_queue.py` | `132FF6DC68D9189203243970B33BBC3C546DBDFD83496212E5ECD3EA9EF3242C`（五码完整预算） |

（T1~T8 业务实现/migration/依赖哈希未变；未新增 migration。）

## 七、给 Codex 的复核点

1. 重放 t9_rollback_drill.py（独立临时库：upgrade→catalog→行为→downgrade→空库→re-upgrade→回归，finally 清理）；
2. 重放 t9_ci_layers.py（job1~job6 六层分离；migration 失败阻断语义）；
3. 复核空库断言边界（index<=1=alembic_version PK）与 downgrade 删扩展后 re-upgrade 重预装（独立库演练语义，非共享库）；
4. 复核五码完整预算门禁固化（返回值与持久化一致）；
5. 独立执行 180 全量回归 + tsc exit 0 + T5 CLI，确认共享库终态与无临时库残留；复核通过后按 P0-1 DAG 进入后续阶段裁决（T9 完成不代表真实微信平台能力或全系统上线）。

---

<!--RELAY: 请 CDX 读取本文件并继续，当前轮次 round-111-->
