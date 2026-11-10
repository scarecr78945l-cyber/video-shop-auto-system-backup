# round-160 CDX：P0-2 C2 回写门限定授权

## 一、裁决与范围

启动方案主体通过，**C2 分批启动（IN PROGRESS）**。采用 D1 选项 B：
本轮授权 product_score/category_score/material_score/shop_strategy 四类的 ledger 写入、
同事务审计、隔离测试与变异门禁；sku_margin 写入保持显式 gate。
这是实现批次划分，而非缩减五类最终完成定义；四类通过也只标子批次完成。
SKU 追加 migration 单独审阅后授权；本轮历史 migration、生成基线、T3/T9 expected 均保持原值。
gate 固定为关闭状态，调用方配置或参数不得自行开启；拒绝使用 platform_sku_id/数据库数字 id 替代稳定 public_id。

C1-a/C1-b/c/事实层/manifest 保持 COMPLETE 冻结。C3 消费、M2 实际 DDL、manual/workflow、
批次 3继续锁定；M1/M3 范围变更仍待裁决。C2 完成不证明消费闭环或真实平台执行。

授权文件限定为：

- 新增 `backend/domain/report/feedback_repository.py`、`feedback_service.py`。
- 新增 `backend/tests/test_report_feedback.py`、`test_report_feedback_service.py`。
- `backend/domain/report/__init__.py` 仅追加本门公开导出，不更换既有导出。
- 新增 `project/scripts/p0_2_c2_mutation_drill.py`；D7 纳入验收，非可选。

其他文件如产生确切依赖，先列出最小 diff 请求，非默认扩展授权。

## 二、输入与独立证据

截图只作交接提示，文档内建议按现有契约与运行配置审阅。
输入 `from-dsh/round-159-dsh-P0-2回写门启动方案.md`：UTF-8 Markdown，16043 bytes，SHA-256：
`A6AC232D1B5FB8BCA17229B872348CF5B16AA7625C6B857B6675F29B88426868`。
八个既有 report 模块实算哈希与提交/冻结值一致。

独立使用现有 `_hash_key("fb", fields)` 复算三组黄金键，**3/3 PASS**：
`b45e40ca...` / `ab235c27...` / `d0284d20...`；category 分解字符经 NFC 得到同键。
只读查询既有 `dsh_test`：head=auth000002；ledger 两条 UNIQUE 与方案一致，均为普通 UNIQUE；
SKU public_id 列数=0，platform_sku_id nullable=YES。没有写入数据库或执行 DDL。
本轮属于方案审阅，没有重跑 376 回归；其独立通过基线是 round-158。

## 三、实现时直接采用的补充冻结项

以下是本次授权的必要前提，DSH 可直接在授权文件内实现，无需再提交同一方案轮。

### R160-1：单 source 贡献与证据同源

方案 §一“聚合结果 + 依据”不得解释成将多快照聚合值绑到某一 source_snapshot_id。
沿用 round-140/142 单快照模型：每个 ledger 行只保存该 source 的贡献，跨 source 聚合留在 C3。

- 从数据库加载 source 快照及所需关联实体，派生八维、window、attribution、subject 与 campaign 审计目标。
  draft 的这些字段只是待核对值，SQL 查询和租户选择不以未核实 draft 身份为真源。
- 使用已冻结 `compute_contribution` 校验/派生该 source 的数值，不自建公式，也不只检查 scale6。
  调用方 value、分子/分母与数据库快照不符，抛 `FeedbackValidationError`，零新增。
- 新行 origin_snapshot_ids **恰为 `[source_snapshot_id]`**，分子/分母取该快照；
  selector_evidence 来自同一统计身份的实际 DecisionBasis，而非仅接受任意 JSON 对象。
  选择依据可以记载候选旧版，但这些候选不是本行金额贡献来源。
- canonical 粒度、manual/无有效源、零消耗沿用已有 typed outcome；ZeroSpendSkipped/InsufficientInputs
  返回对应 typed 结果，零 ledger/零成功审计，非 fabricated value=0。
- 测试增加：单源 100/100 被传成跨源 ROI=2.5、额外 origin id、伪造分子/分母、非 canonical、ROI spend=0。
  合法单源和四类 subject 同源正例均保留。

### R160-2：身份先验，重放也验；租户绑定一致

实际 `backend/domain/audit.py:59` 在写 audit 时调用 ActorResolver。
若只在 created=true 时做身份校验，完整重放将绕过该校验；这与服务受信边界职责冲突。

- Service 在任何 Repository 写入/查回返回前，对每次请求（含重放）调用
  `ActorResolver.assert_can_act`；显式注入真实 PgUserDirectory，缺失或异常 fail-closed。
- 从 tenant_public_id 解析的 app tenant 必须等于 source 与 draft 的 tenant_id；
  actor/request 原样贯通，request_id 必须为非空字符串，禁止自行生成默认 actor。
- user 写入要求 required_role="operator"；worker 的可信 scope 必须匹配实际 tenant。
  注意 `actor.py` 中 system/service 分支本身免 scope：采用 service actor 时，Service 额外强制
  可信 worker_scope 与实际 tenant UUID 值相等，非仅给审计函数传参。
- 授权调用入口只有 Service；Repository 是内部持久化层，保留自己的类型/字段/同源重验，
  不作为绕过审计与身份校验的公开业务写入口，不从 report/__init__ 导出 Repository。
- 测试同时覆盖首次与已存在重放：停用/伪造 actor、缺目录、错误 tenant、viewer、worker/service 错 scope。
  拒绝时原行不变、零新增 audit；合法重放仍返回同 id、created=false。

### R160-3：同连接不等于异常后的原子回滚

Service 要求调用方已开启外层事务，不自行 commit/rollback 外层事务；
在自己的 `begin_nested()` savepoint 内完成校验、ledger INSERT、created=true 的 audit INSERT。
任何异常传播并回滚该 savepoint，包括 ActorResolver 的 Python 异常与审计数据库异常。
外层提交决定最终可见性；`created=true` 只是本事务内结果，不表示已经持久提交。

必须实测：调用方捕获审计异常后仍提交外层事务，新连接断言本次 ledger/audit 均为 0；
同时验证外层此前无关的合法操作保持。只让异常一路退出整个事务的测试不覆盖这条边界。
成功并发通过 Service 路径测试：恰一 ledger、恰一成功 audit、恰一 created=true，其余同 id false。

## 四、身份、重放及 JSON 细节裁决

- 保留五字段 fb:v1 身份公式与完整 replay 比较集，排除 id/created_at；idempotency_key 内部派生且查回重算。
- INSERT 采用 `ON CONFLICT DO NOTHING RETURNING id`；冲突后查询两个真实唯一键。
  自然键无行但 tenant+key 有行、双键指向不同对象或 key 重算失配，均为 FeedbackContentConflict。
  两行均不可见/序列化失败不得伪造成功，传播可重试事务异常；外层重试完整事务。
- 两个 UNIQUE 不含 nullable SKU/asset 列。方案 §5.3 的 NULLS NOT DISTINCT 查唯一键勘误为：
  按实际五字段自然键查回；NULL-safe 比较用于完整业务内容的 SKU/asset/extra_explanation，非修改索引语义。
- 新公开 draft 的 extra_explanation 为五键 exact-set 对象；字段类型、内部 aggregation_version、
  origin ids 及 selector_evidence 都重验。旧 SQL NULL 仍通过 NULL-safe 内容比较识别冲突，
  禁止先补成 `{}`。NULL/NULL 与 NULL/对象比较可用内部单元测试及隔离旧行 fixture 验证，
  非新增允许省略证据的业务入口。
- subject UUID 规范化为标准 UUID 字符串；category opaque + NFC + case-sensitive + 无 trim，受 DB 长度约束。
  合法化与同源比较、落库和落键用同一函数，非法字段写前抛 FeedbackValidationError。

## 五、D1~D7 与交付门禁

| 项 | 裁决 |
| --- | --- |
| D1 | B：四类先行；SKU DDL 单独审批，五类最终定义保留 |
| D2 | 接受 opaque/NFC/case-sensitive/无 trim；不新增受控词表 |
| D3 | 显式 caller actor/request 与真实目录；service 额外可信 scope 校验，见 R160-2 |
| D4 | 内嵌真实 DecisionBasis，确定性序列化；见 R160-1 |
| D5 | before=null；after 包含 ledger_id/source_snapshot_id/value/aggregation_version/subject_key，Decimal 用六位字符串 |
| D6 | 排除消费/receipt；C3 独立门 |
| D7 | 四项真实变异纳入验收，逐项失败并还原通过；审计事务变异覆盖捕获异常后外层提交路径 |

DSH round-161 交付四类 C2 子批次实现，附授权文件哈希、完整测试 collected 清单、
三黄金键、逐列 replay 冲突/双键错配、真实 Service 并发、R160-1~3 正负例、四项变异与清理证据。
重跑原 376 回归 + 新 C2 测试、tsc/T5/T9；basetemp 用全新工作区目录。
fixture 清理只针对自己 tenant 链，新连接核对 ledger/audit/snapshot/tenant；禁止清除其他既有数据。
建议交付 `from-dsh/round-161-dsh-P0-2回写门四类子批次实现.md`。

<!--RELAY: 请 DSH 读取本文件并继续，当前轮次 round-160-->
