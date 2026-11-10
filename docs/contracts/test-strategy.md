# test-strategy.md — P0-0 批 B 契约：测试策略与真实能力门禁

> 来源：round-18 §5.4（六层矩阵）+ round-20 §5.4（downgrade 演练修正）+ round-21 §四（隐式租约协议）+ `14-新立项最终方案.md` §14.0（资源未确认）。
> 用途：P0-1 全部实现包（T1~T9）的测试分层、mock/live 门禁与验收执行依据。

---

## 一、测试分层矩阵（冻结）

| 层 | 可用输入 | 证明内容 | 不证明内容 |
|---|---|---|---|
| unit | 纯值/fixture | CID、幂等 key、状态机、canonical serialization | DB/平台 |
| migration | 本地 PG15 临时库 | upgrade/downgrade、`pg_catalog` exact-set（60/31/17/58/4/17/2/15） | 平台 |
| repository/trigger | 本地 PG15 | FK、隔离、trigger（17 项正反例）、幂等 | 平台 |
| fixture-e2e | mock/fixtures | 内部流程与失败分流 | 真实读写 |
| contract | 脱敏响应样本 | parser/adapter 契约 | 当前登录态与权限 |
| live-gate | 真实账号/店铺/证据 | P0-3/P0-4 指定能力 | 未执行的其他能力 |

> **门禁原则（硬）**：`mode/provider/model/source/evidence` 必须随每个测试结果携带；CI 的 fixture 通过**不得更新 live capability 状态**；P0-3/P0-4 资源仍未确认（§14.0），P0-1 全绿也不解锁真实平台能力。

---

## 二、migration 演练流程（round-20 §5.4 修正，冻结）

round-17 的 `alembic upgrade head && pytest && alembic downgrade base && pytest` **不成立**（降到 base 后依赖 schema 的全量 pytest 理应失败）。正确流程：

```text
1. 空库 upgrade head
   → pg_catalog exact-set 断言（ddl-order §九）
   → 行为 pytest（repository/trigger/fixture-e2e）
2. downgrade base
   → 空库断言（对象清零：表=0 业务、enum=0、trigger=0、索引=0）
3. 再 upgrade head
   → pg_catalog exact-set + 行为 pytest
4. 可选 upgrade-from-previous-revision（升级路径演练）
```

---

## 三、真实能力门禁清单（mock/live 分离）

| 能力 | 可 mock/fixtures 验收 | 必须 live-gate（资源未确认） |
|---|---|---|
| 微信小店报表回读 | 快照解析/去重/窗口/回写（P0-2） | 真实报表抓取（P0-3） |
| 商品上架 | 状态机/门禁/幂等（P0-2） | 真实创建/审核/链接（P0-4） |
| 小店投放 | 预算/止损/ROI 计算（P0-2） | 真实托管写入与报表（P0-4） |
| 素材上传 | 素材库模型/去重/审核（P0-2） | 真实素材库上传 |
| 榜单/报价采集 | 解析器/账本/熔断（P0-2） | 真实页面抓取与登录态 |
| OpenAPI 契约 | 请求构造/签名/错误映射 | 官方接口路径与真实凭据（P0-3.5） |

> fixtures/mock 只证明内部模型、迁移、计算或流程；真实平台能力状态由 §14.0 资源清单独立追踪。

---

## 四、隐式租约测试断言（round-21 §四 → 机械测试，round-33 B5 补齐）

入 P0-1 T8 测试，至少断言：

1. 两 worker 并发 claim，仅一方成功（`FOR UPDATE SKIP LOCKED`）；
2. **claim 必须返回 `id + attempt` 作为 fencing token**（round-33 补）；
3. 首次 claim attempt 保持 1；重试/过期回收恰增 1；
4. stale attempt 的条件更新（`WHERE id=? AND status='running' AND attempt=?`）覆盖 **heartbeat / complete / fail / gate_retry** 四类，受影响行数≠1 即拒绝写入（round-33 补 gate_retry）；
5. heartbeat 延长 `updated_at`，45 分钟内不被回收；**heartbeat 周期上限 15 分钟**（round-33 补，round-21 冻结值）；
6. **不可领取状态矩阵**（round-33 补）：`manual_review / done / failed` 一律不可 claim；`failed` 为终态（不回收不重试）；
7. `gate_retry` 按 error-codes.yaml retry_policies 的 backoff 到期（机器可读），到期进入新 attempt 恰增 1；
8. `action_idempotency_key` 在所有 attempt 中恒定（不含 attempt）；
9. 索引覆盖 `(status, updated_at)` claim/recover 路径（index-registry N1）。

---

## 五、CID 引擎测试（P0-1 T5）

- 黄金样例：`Context(prec=60, rounding=ROUND_HALF_UP)` + 裸运算符链（或等价显式作用域 context），10 项完整串等值、S 末位 `...947`、bid=1525（cid-engine-spec §五）；
- canonical serialization 不变量（cid-engine-spec 2.1）：
  `canonical(1)==canonical(1.0)==canonical(1.00)=="1"`、`canonical(-0.000)=="0"`、`canonical(1E+3)=="1000"`、compact vs DB scale 双输入全串相等；
- envelope 用例：L 缺失→FIELD_DEFAULTED、必需缺失→REQUIRED_FIELD_MISSING、rebate 不适用→REBATE_NOT_APPLICABLE、S≤0→S_NON_POSITIVE、.5 分边界；
- 每个用例断言完整 envelope（status/blocking_error/quality_flags/business_flags/values/bid）。

---

## 六、trigger 测试（P0-1 T4）

- 17 项各至少一个正例 + 一个反例；
- 反例覆盖：跨租户 policy 引用（INVALID_POLICY_REF）、SKU/产品不一致（SKU_PRODUCT_MISMATCH）、context 不一致（CONTEXT_MISMATCH）、账号/店铺不一致（ACCOUNT_SHOP_MISMATCH）、scope 不一致（SCOPE_MISMATCH）、维度不一致（DIMENSION_MISMATCH）、supersede 不一致（SUPERSEDE_MISMATCH）；
- 断言稳定错误码（SQLSTATE/错误码），不依赖自然语言错误文本；
- `asset_reviews.scope_ref_id` 不生成第 18 个 trigger（应用层断言测试）。

---

## 七、幂等测试（P0-1 各包）

- selection：同批次重放不新增（selection_batch_key）；
- campaign：重试/超时先查本地 key + 平台证据，不换 key 重建（idempotency_key）；
- report：重复抓取不新增、真实版本变化可新增（report_version_key canonical）；
- feedback：同 source_snapshot+feedback_type+subject 不重复回写（idempotency_key + 第二唯一键）；
- listing/pricing/cost/workflow：各自 idempotency_key/request_id/action_idempotency_key 重放语义。

---

## 八、测试结果纪律与 CI 顺序（round-33 B6 回修）

- 所有测试结果携带 `mode/provider/model/source/evidence`；
- **CI job 顺序（与 §二 migration 演练一致，禁止未分层 pytest 同时表示 unit 与依赖 schema 测试）**：
  ```text
  job1 lint
  job2 unit（无 DB 依赖，纯值/fixture）
  job3 empty DB + alembic upgrade head
  job4 pg_catalog exact-set 断言 + repository/trigger/fixture-e2e pytest
  job5 alembic downgrade base + 空库断言（表/枚举/trigger/索引清零）
  job6 re-upgrade head + catalog/behavior 回归
  ```
- migration 检查与行为测试分离（job3/job4 独立），migration 失败即阻断合并；
- 任何 mock/fixtures 成功不更新真实平台能力状态（§14.0 资源清单独立追踪）。
