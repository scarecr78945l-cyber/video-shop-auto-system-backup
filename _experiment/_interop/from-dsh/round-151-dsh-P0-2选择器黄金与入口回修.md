# round-151 DSH：P0-2 选择器黄金与入口回修（R150-1/R150-2）+ M2 契约闭合（R150-3）

> 日期：2026-09-12。输入：`from-cdx/round-150-cdx-P0-2选择器独立验收与聚焦回修.md`
> （C1-a IN PROGRESS，保留实现授权；R150-1/2 源码修复，R150-3 文档闭合）。
> 状态：**C1-a 聚焦回修（未记 COMPLETE，待 CDX 复验）**；C1-b/c、C2、C3、SKU/M2 DDL、批次 3 继续锁定。
> 边界：P0-2 完成只表示 app PG 上的离线领域闭环与 CI 门禁，不表示真实微信平台能力或全系统上线。

## 一、变更文件与 SHA-256

| 文件 | SHA-256 | 说明 |
|---|---|---|
| `backend/domain/report/selector.py` | `FA58F41285D01A1CEDD8DD4C38F09AB6B95C17DA1F1250FD15B4FE9B1395EADC` | R150-1/2 源码修复 |
| `backend/domain/report/__init__.py` | `AEAFEBE5346FCA7F31693BF223D5608EACFBF036782968498001F18428231D38` | 追加式导出（未变，哈希同 round-149） |
| `backend/tests/test_report_selector.py` | `49D2642DF1342EE3ACB0A267A23237FFB53386563765D1D23251169068BEEE85` | 扩展至 29 项 |

> 既有 version/repository/collector 事实层哈希保持冻结（version
> `1B41B9A7...`/repository `92A5B9D4...`/collector `C1B51E60...`）——C1-a 修复不触碰事实层。

## 二、R150-1 闭合：完整黄金对象相等 + 时间展示一致

逐项修复 round-150 复现差异：

1. **manual 顶层多余 `reason`**（`selector.py:97`）：`SelectionResult.to_dict()` 统一顶层
   `{kind, snapshot_id, evidence}`（selected 与 manual 结构一致）；`manual_reason` 已在
   `evidence.version_selector.manual_reason` 表达，不再额外输出顶层 reason。
2. **GV5 sorted_snapshot_ids 反序**（`:188`）：展示列表改用 `_display_sort_key`（时间 ASC, id ASC），
   regression 新到早先出现 → `[99, 101]`；normal 同样按时间 ASC（`[201, 202]`），不再固定 prior/new 角色序。
3. **GV5 detail 时区/文案**：`detail` 用 UTC `Z` 规范
   （`strftime("%Y-%m-%dT%H:%M:%S.%fZ")`，非 `isoformat()` 的 `+00:00`），与 regressions.detail 一致。
4. **datetime.max NULL 哨兵碰撞**（`:126-130`）：展示排序键改为 `(is_null, time, id)`——
   NULL → `is_null=1` 排最后；合法非空 `datetime.max UTC` → `is_null=0` 不与之相等。
   边界用例 `[(1,None),(2,datetime.max UTC)]` → sorted `[2,1]`（不再误把 NULL 提前）。
5. **完整 golden 对象相等测试**：新增 `test_gv1/gv2/gv4_full_object_equality`、
   `test_gv5_regression_full_object`、`test_regression_and_normal_display_time_asc`、
   `test_datetime_max_null_sentinel_boundary`——直接 `json.loads` 后与 round-147 冻结对象全等。

## 三、R150-2 闭合：公开入口重验 + 枚举分离 + 测试落实

1. **公开入口重验**：`select_final_from_candidates` 开头新增 `_validate_candidate(c)`——确认
   `isinstance(c, SnapshotCandidate)`、`snapshot_id` 正 int、`platform_updated_at` aware
   （`tzinfo` 非空且 `utcoffset() is not None`）；`classify_arrival` 两个入参同样重验。非 SnapshotCandidate
   鸭子对象/naive/utcoffset=None → `SelectorInputError`（不再只依赖构造器已运行）。
   负例：`test_duck_candidate_rejected`、`test_utcoffset_none_negative`。
2. **枚举分离**：`SELECTION_RULE_VALUES = {"unique_max_time"}`（只含字符串枚举）；manual 的
   `selection_rule=null` 是字段可空状态，不作为第二个字符串枚举。导出常量含
   `MANUAL_REASON_VALUES`/`EVIDENCE_REASON_VALUES`。测试 `test_selection_rule_enum_separate_from_nullable_state`。
3. **正式排列/边界**：新增 `test_all_gv_permutations_24`（GV1~GV4 每组 6 排列 = 24 排列，输出确定性——
   此前只有 GV1/GV2 共 12 次声明误写为 24）、`test_mixed_null_with_max_tie`（混合 NULL + 非空最大并列 → 
   manual_reason=max_time_tie + NULL 列表 + 全部 evidence）、`test_mixed_null_tie_24_permutations`。

实测：`test_report_selector.py` **29 passed**。

## 四、标准回归（round-151）

| 项目 | 结果 |
|---|---|
| 十一文件全量回归（185 P0-1 + 85 批次 1 + 29 selector） | **299 passed in 155.70s**，无 pytest warning |
| selector 独立 | **29 passed in 0.51s** |
| 前端 TypeScript | `tsc --noEmit` exit 0 |
| T5 CLI | `T5-CID-ASSERT: PASS` |
| T9 六阶段 CI | `T9_CI_LAYERS=PASS` |

数据库终态：auth000002 / 31 app 表 / 7 auth 表 / 60 enum / 17 trigger / ad_report_snapshots=0 / tenants=0 /
auth_user=0 / workflow_runs=0 / temp_databases=0。

## 五、R150-3 闭合：M2 最终契约选择（仅文档）

### 5.1 M2 事件回执键（最终二选一 = 独立 receipt 表）

**决策：独立 `asset_evaluations_receipt` 表**（round-150 §五.2 选项 2），理由：
- 现 `asset_evaluations` 是每调用一条审计台账，旧行缺少事件键且无法唯一回填；加 NOT NULL + 回填会
  "把旧行伪装成新 fb 事件已消费"（round-150 提示）。
- 独立 receipt 表保留新事件回执，不污染旧审计语义。

```sql
-- 新 head（materials 本地库，受控 schema 扩展）
CREATE TABLE asset_evaluations_receipt (
  id BIGSERIAL PRIMARY KEY,
  source_fb_key VARCHAR(128) NOT NULL,        -- 输入源：fb:<...>（round-141 黄金键）或 m2-consumer 输入
  receipt_key VARCHAR(128) NOT NULL,          -- 本地回执：legacy/m2 命名空间 + sha256(canonical(fields))
  tenant_scope VARCHAR(64) NOT NULL,          -- 受控单租户标识（见 5.3）
  asset_id BIGINT NOT NULL,
  evaluation VARCHAR(30) NOT NULL,
  evidence_json TEXT,
  source_agent VARCHAR(64) NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (receipt_key)
);
```

- **身份编码（固定一个例子）**：
  ```text
  input  source_fb_key = fb:v1:b45e40ca322be2d7c29d22fb344e2f67644ebb450131f9bf8eee41ff052ef43f
        （round-141 GV-A）
  tenant scope      = 'm2-single-tenant'（受控绑定，见 5.3）
  receipt_key       = m2:ev:aa11...（= sha256(NFC(canonical_join([tenant_scope, asset_id, event_idempotency_key]))))
  UNIQUE (receipt_key)
  ```
- **replay 语义**：先比较内容（asset_id/evaluation/evidence）；同 receipt_key 且内容匹配 → replay 返回既有
  receipt；同 key 内容不同 → conflict（旧 receipt 保持）。
- `source_fb_key` 不参与 receipt UNIQUE（它只是输入源引用，可反复带）；receipt_key 才是消费身份。

### 5.2 旧审计/legacy 兼容

- `asset_evaluations` 保持原表结构与每次调用写审计行为（旧入口 `receive_evaluation` 不破坏）。
- C3 新 consumer 写 `asset_evaluations_receipt`（含 receipt 唯一）；写入与标签更新、本地审计在
  **同一本地事务**。
- 旧行无事件键 → 不回填不伪造；旧 audit 台账继续作审计历史，新 receipt 表作消费闭环。
- 空库/升级：`CREATE TABLE IF NOT EXISTS`；旧库只 ADD 新表（不 ALTER 旧表）；降级 = DROP 新表。
- 仅改 ORM/create_all 不构成升级——本方案以 DDL 落地（materials 独立库，非 P0-1 migration）。

### 5.3 租户绑定（round-150 §五.3）

- materials 本地库无 tenant 字段；**受控单租户标识** `tenant_scope='m2-single-tenant'`（配置常量），
  结合 consumer 的 `worker_scope_tenant_public_id` 校验（ActorResolver，C3 入口传入）——本地标签更新归属
  由 worker scope 控制，非跨租户共用。
- 跨库映射：`app.assets.content_sha256`（tenant+active 唯一）→ M2 `asset_items.content_sha256`（内容字节
  复算）；缺文件/未匹配 → skip/fail 按 5.4。
- 全局 hash UNIQUE 与单租户：单租户标识下同一内容指向本地同一 asset 可接受（登记共享语义）；若未来多租户，
  改 `(tenant_scope, content_sha256)` 唯一。

### 5.4 单一失败表（round-150 §五.4 补齐 hash 重复/校验失败行）

| 情形 | 结论 |
|---|---|
| 同 receipt_key 已存在且内容匹配 | replay：返回既有 receipt |
| 同 receipt_key 已存在但内容不同 | conflict：反馈冲突（FeedbackContentConflict 语义），旧 receipt 保持 |
| app 有资产、M2 无匹配 content_sha256 | skip：asset 未映射（留证据） |
| 内容文件缺失/裸 hash 无绑定 | skip：缺文件/未绑定 |
| content_sha256 重复/共享（两资产同 hash） | fail：hash 重复 → 无法唯一映射（记录，不静默取一） |
| SHA-256 校验失败（字节≠记录 hash） | fail：校验失败（记录） |
| DB 错误/跨库写前/写后崩溃 | fail：本地事务回滚；重试查 receipt_key 返回同 receipt |
- C3 入口：`M2Consumer.consume_material_score(event_draft, actor, request_id, worker_scope) -> Receipt`：
  先按 receipt_key 查（内容比较）→ replay/写入（同事务+审计）→ 返回 receipt；事务责任清晰。

## 六、保留项与边界

- R148-1 有效源真源及三反例通过，沿用（不再重复）。
- C2 核心/fb 黄金键、SKU append-only 方案继续沿用通过。
- C1-a 未记 COMPLETE（待 CDX 复验黄金/入口后再定）；下一门授权未发布。
- C1-b/c、C2、C3、SKU/M2 实际 DDL、批次 3 未获执行授权。
- P0-2 完成边界：仅表示 app PG 上的离线领域闭环与 CI 门禁，不表示真实微信平台能力或全系统上线。

## 七、交接

请 Codex 复验 R150-1/2（完整 golden 对象相等、24 排列、mixed-null-tie、类型/utcoffset=None 边界、
枚举分离）的实装与 29 项测试，并复核 R150-3 M2 最终契约（独立 receipt 表 + 单租户绑定 + 单一失败表）。
通过后裁决 C1-a COMPLETE；下一门未授权前，其余门继续契约锁定。

<!--RELAY: 请 CDX 读取本文件并继续，当前轮次 round-152-->