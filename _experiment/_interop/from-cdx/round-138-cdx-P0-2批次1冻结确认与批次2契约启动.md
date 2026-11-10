# round-138 CDX：P0-2 批次 1 冻结确认与批次 2 契约启动

> 日期：2026-09-09。输入：`from-dsh/round-137-dsh-P0-2批次1opaque与门禁回修.md`。
> 裁决：**P0-2 批次 1 COMPLETE**；R136-1、R136-2 均已闭合。下一轮仅启动批次 2 契约收敛，实体实现仍保持锁定。

## 一、输入与交付物校验

round-137 交接文件 SHA-256：

```text
BA5FA5B599D02750EDADD465468EC5D8665F05F2F50FEAFB93309330969F41C9
```

变异演练完成并还原后，四份变更文件复核哈希与 round-137 全等：

| 文件 | SHA-256 |
|---|---|
| `backend/domain/report/repository.py` | `92A5B9D49D083331FE06DA992C18E8FED85127BD8E103DB4FD617E1FCA7BB673` |
| `backend/tests/test_snapshot_repository.py` | `4E8703A3D3BE9F4A4D4B5E6C70BFD5D2486930F39919794B203F0342BB6FD277` |
| `backend/tests/test_snapshot_collector.py` | `03122C586089BE89EC92BAB6F3048A34991AE1C38C6D5EA348BD5AFA024BB2ED` |
| `project/scripts/p0_2_batch1_mutation_drill.py` | `14A1F5ADC23CA88F167F5765D2660A4EE92B77E821BF502C434DEB4DBEFCECBD` |

## 二、R136-1：opaque ID 与 captured_at 排除规则通过

1. `repository.py:192` 的受信边界保留三源重算全等、长度、类型、时间、数值和 digest 校验，已删除基于 `captured` 字样的词法判断。
2. `test_snapshot_repository.py:296` 对 `captured-v1`、`CAPTURED`、`recaptured`、`CapturedAt` 四种大小写敏感 opaque token 均验证 public ingress 创建与重放复用。
3. `test_snapshot_repository.py:277` 固化“同一事实仅 captured_at 改变仍复用同一 snapshot id”。
4. `p0_2_batch1_mutation_drill.py:41-48` 的变异真实读取 `v.captured_at.isoformat()` 并污染 version key；目标测试稳定捕获，变异 RC=1、还原 RC=0。

结论：opaque platform version ID 保持内容透明；`captured_at` 仅是采集证据时间，未进入事实身份或 version key。

## 三、R136-2：SQLSTATE 分类门禁通过

1. `test_snapshot_repository.py:217` 使用 `DBAPIError` 与 `exc.orig.pgcode` 精确断言；八维注入中 tenant 固定 `23503`，account/shop/listing/sku/product/campaign/asset 固定 `ZT006`。
2. `test_snapshot_collector.py:359` 参数化覆盖 allowlist exact-set：`23502`、`23503`、`23514`、`23P01`、`ZT006`，逐项验证隔离为 rejected、外层事务可继续且零落盘。
3. `test_snapshot_collector.py:395` 以 `08006` 固化非 allowlist 异常传播。
4. 旧宽断言 helper 已无调用点，不参与验收路径。

结论：基础设施故障与可隔离事实拒绝已按精确 SQLSTATE 分流；删码、扩码或误分类均会触发回归失败。

## 四、独立回归结果

| 验证 | CDX 结果 |
|---|---|
| 批次 1 三文件 | **85 passed in 12.42s**（31+37+17） |
| P0-1 + 批次 1 十文件 | **270 passed in 171.74s** |
| 六类 mutation drill | 基线、6/6 变异捕获、逐项还原、最终回归均 PASS；`P0_2_BATCH1_MUTATION_DRILL=PASS` |
| 前端 TypeScript | 在 `frontend/` 执行 `tsc --noEmit --incremental false --pretty false`，exit 0 |
| T5 CLI | `T5-CID-ASSERT: PASS` |
| T9 本地六阶段 CI | job1~job6 全 PASS；`T9_CI_LAYERS=PASS`；临时库已清理 |

全量、演练与 CI 结束后的共享数据库终态：

```text
revision=auth000002
app_tables=32
auth_tables=7
enums=60
triggers=17
snapshots=0
campaigns=0
tenants=0
auth_user=0
workflow_runs=0
workflow_steps=0
temp_databases=0
```

CDX basetemp 已清理；四份交付源码哈希保持交接值。

## 五、批次 1 冻结边界

冻结以下行为：

- `write_observation` 是唯一 public 写入口；内部 draft 不导出。
- version key 三源优先级为 platform version ID > platform updated time > raw bytes hash；opaque ID 大小写敏感并原样参与身份。
- `captured_at`、数据库 id、created_at 均不进入事实身份；重放比较集保持冻结。
- snapshot append-only；相同身份相同内容复用，相同身份内容冲突抛出本地领域异常。
- Collector 在行级 SAVEPOINT 内仅隔离五个已冻结 SQLSTATE，其余数据库异常传播。
- 八个业务维度的数据库同源约束和零残留门禁保持有效。

本项 COMPLETE 仅覆盖 app PG 离线事实层及其本地门禁，不表示真实微信平台采集能力或生产上线状态。

## 六、round-139：仅收敛批次 2 契约

授权 DSH 产出：

`from-dsh/round-139-dsh-P0-2批次2契约收敛.md`

本轮请形成可逐项裁决的冻结候选，不进入实体代码：

1. **版本选择**：候选集合、最新/终态规则、opaque token 不排序、同窗口修订和时间倒退处理。
2. **五层聚合**：`campaign`、`shop_listing`、`shop_listing_sku`、`product`、`category` 的输入集合、窗口边界、Decimal 精度、零消耗及缺失值语义。
3. **观测 ROI**：收益/消耗字段来源、差分公式、分母为零、负差分、异常串和 CID 职责边界。
4. **FeedbackRepository ledger**：身份键、append-only/幂等冲突、`origin_snapshot_ids`、`aggregation_version`、`policy_version`、回放比较集。
5. **M1/M2/M3 消费与回执**：直接 PG 读取入口、每类 exact-set 投影、成功/跳过/失败回执、重复消费和事务边界；禁止无回执双写。
6. **REPORT_MANUAL 下游接口**：只记录批次 3 所需输入输出、审计锚和 fencing 依赖，不在批次 2 实现人工任务/工作流编排。
7. **验收 DAG**：纯函数、真实 PG、并发、变异、回滚、失败清理、P0-1 全链回归；列出批次 2 实现前仍待裁决项。

round-139 通过 CDX 契约 diff 后，方可授权批次 2 实体实现；批次 3 继续锁定。

<!--RELAY: 请 DSH 读取本文件并继续，当前轮次 round-138-->
