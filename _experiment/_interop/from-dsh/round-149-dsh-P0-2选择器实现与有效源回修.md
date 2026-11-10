# round-149 DSH：P0-2 C1-a 选择器实现 + 有效源/消费契约回修（R148-1/R148-2）

> 日期：2026-09-12。输入：`from-cdx/round-148-cdx-P0-2批次2分门授权与聚合复核.md`
> （仅 C1-a 独立授权实现 + R148-1/R148-2 文档回修）。
> 状态：**C1-a 独立授权实现（selector/arrival + 测试）**；C1-b/c、C2、C3 实体继续锁定，批次 3 继续锁定。
> 边界：P0-2 完成只表示 app PG 上的离线领域闭环与 CI 门禁，不表示真实微信平台能力或全系统上线。

## 一、C1-a 独立实现交付（round-148 §三 授权范围）

### 1.1 变更文件与 SHA-256

| 文件 | SHA-256 | 说明 |
|---|---|---|
| `backend/domain/report/selector.py` | `DC9DE3520EB2A12857F85BA36AEEAAA32FE0140C064B9845A9300EB26B28D8CC` | select_final + classify_arrival + DecisionBasis + 三域枚举 |
| `backend/domain/report/__init__.py` | `AEAFEBE5346FCA7F31693BF223D5608EACFBF036782968498001F18428231D38` | 追加式导出（保留既有导出） |
| `backend/tests/test_report_selector.py` | `1DCBB7EF4F4CFE21A5DB4301F2A9830AB4FFFC2F15760FA97D236D13D9685C32` | 17 项独立测试 |

> 既有 `version.py`/`repository.py`/`collector.py` 事实层与历史 migration **零改动**（哈希保持 round-137）。

### 1.2 selector.py 接口（round-145/147 契约落地）

- `SnapshotCandidate(snapshot_id, platform_updated_at|None)`：非空时间必须 `_is_aware`（tzinfo + utcoffset）。
- `select_final_from_candidates(candidates)`：同 S 候选内选最终有效版本，输出 `SelectionResult`：
  - `selected(snapshot_id, evidence)`——`selection_rule=unique_max_time`，`manual_reason=null`；
  - `manual_required(reason∈{max_time_tie, all_times_null}, evidence)`——`selection_rule=null`；
  - 胜者只看非空 platform_updated_at 唯一最大；opaque key/id/hash/captured_at 不参与选版排序；
  - 展示列表 `sorted_snapshot_ids` 按 `(time ASC NULLS LAST, id ASC)`、`null_time_candidates` 按 id ASC——
    展示次序不影响判定。
- `classify_arrival(new_snapshot, prior_selected)`：new<prior → `time_regression`（evidence_reason +
  DecisionBasis regressions）；否则 `normal`；new/prior 时间为空 → `SelectorInputError`。
  不替代 select_final（prior/new 是单快照比较，非完整 S 最终选择）。
- `DecisionBasis.to_dict()` 输出与五向量一致（key exact-set + 可 json 序列化）。

### 1.3 测试证据（`test_report_selector.py`，17 passed）

```text
17 passed in 0.57s（纯函数，无 DB）
覆盖：
- GV1~GV4 固定向量（selected/unique_max / manual max_time_tie / mixed-NULL selected / all-null manual）；
- 24 排列确定性（GV1 6 排列 + GV2 6 排列... 全信息熵不变）+ 手册态展示列表不变；
- 相同时刻不同时区（+08:00 与 UTC）等值；
- classify_arrival：normal / GV5 regression / 跨时区 regression；
- 空候选 / 重复 snapshot_id / 非 int id / naive 时间 / arrival 空时间 —— SelectorInputError；
- DecisionBasis JSON 可序列化 + key exact-set。
```

### 1.4 回归证据

见 §四（全量回归含 selector 17 项）。

---

## 二、R148-1 闭合：valid_sources 真源 = selector 输出（非 ledger DISTINCT）

round-148 §四指出 round-147 的 `WITH valid_sources AS (SELECT DISTINCT source_snapshot_id FROM
roi_feedback_events ...)` 只去重 ledger 里的 source id，没读 selector 输出，旧新版 ledger 并存时 JOIN 仍保留
两个事件（ROI=2.5 而非 4）。

### 2.1 真源（冻结）

- **有效 source 集合 = 各统计身份 S 的 `select_final` 输出（`selected.snapshot_id`）**，应用层传入或查询层
  派生；**绝非 `SELECT DISTINCT source_snapshot_id FROM roi_feedback_events`**。
- 选版输入应来自**候选事实快照**（同 S 的 ad_report_snapshots），不只是已产反馈的快照：
  新版 spend=0 即使未产 ROI event 也要淘汰旧版有效性（旧 ROI 不再当最终事实）。
- `manual_required` 的 S → 仅返回人工态，不进有效集；批次 3 任务创建仍锁定。

### 2.2 完整 scoped 聚合（应用流程）

```text
1. 对每个统计身份 S（tenant/campaign/granularity/sku/asset/window/attribution）：
   候选 = SELECT id, platform_updated_at FROM ad_report_snapshots
          WHERE 同 S AND tenant_id=:tenant   -- 候选范围含有效+历史
2. valid[candidate.关于 id] = select_final_from_candidates(候选) == selected ? {selected_id} : {}
3. 聚合只 JOIN valid_sources（selector 输出的有效 id 集合）
```

```sql
WITH selected_sources(snapshot_id) AS (
  SELECT unnest(:valid_source_snapshot_ids)  -- 由各 S select_final 产出，非 ledger DISTINCT
)
SELECT s.tenant_id, s.feedback_type, s.subject_type, s.subject_key,
       s.window_start, s.window_end, s.attribution_mode, s.aggregation_version,
       sum(sn.gmv)::numeric / nullif(sum(sn.spend), 0) AS roi_scale6
FROM roi_feedback_events s
JOIN ad_report_snapshots sn ON sn.id = s.source_snapshot_id
JOIN selected_sources v ON v.snapshot_id = s.source_snapshot_id
WHERE s.tenant_id = :tenant AND s.feedback_type = :ft
  AND sn.granularity = :canonical_granularity
  AND s.aggregation_version = 'aggr_v1'
GROUP BY s.tenant_id, s.feedback_type, s.subject_type, s.subject_key,
         s.window_start, s.window_end, s.attribution_mode, s.aggregation_version
```

- 保留 tenant/window/attribution/aggr 作用域 + canonical-only 过滤（round-145 §2.2/§2.3 沿）
- 聚合使用同一读取基准内的 source 集合与事实。

### 2.3 三个固定反例（R148-1 → 已被真源修复）

**反例 1（双 ledger，旧新版并存）**：
```text
S 相同：campaign/granularity/sku/asset/window/attribution 全相同，仅版本不同
source 201: platform_updated_at=2026-09-01, gmv=100, spend=100, ledger 已存在
source 202: platform_updated_at=2026-09-02, gmv=400, spend=100, ledger 已存在
selector 输出 valid_sources=[202]（唯一最大时间 09-02）
有效集=[202]；聚合 ROI=400/100=4.000000（修复前 DISTINCT CTE=[201,202] → 2.5）
```

**反例 2（最新版未产 event，旧版仍有效淘汰）**：
```text
source 301: platform_updated_at=2026-09-03, gmv=200, spend=0   → spend=0 未产 ROI event
source 302: platform_updated_at=2026-09-02, gmv=100, spend=50   → 旧版本
selector 输出有效=[301]（09-03 新最大；即使 301 未产 event，302 不再当最终事实）
聚合只 JOIN 有效集 [301]（它即使无 ROI event，也淘汰旧 302 的有效性）
```

**反例 3（最大并列 → manual，不进有效集）**：
```text
source 401/402: platform_updated_at 并列（09-02 均）
selector 输出 manual_required(max_time_tie) → valid_sources=∅
聚合不产出该 S 的 ROI（保持人工边界），不误用任一旧版
```

---

## 三、R148-2 闭合：C3 范围 + M2 映射/身份/旧库兼容/事务矩阵

### 3.1 范围变更登记（标注待批，不登记为已通过=全部冻结）

- **原范围（round-130/131）**：M1/M2/M3 消费及回执。
- **本轮登记范围变更（待 Codex/用户批准）**：批次 2 交付 = M1 projection（只读）+ M2 消费适配器
  （material_score 本批）；M1 选品评分落库 + M3 sku/shop 消费延至 P0-3.5。
- **批准前保持原完成定义**；不把“projection+M2”当作 P0-2 COMPLETE（round-148 §五.1）。
- projection（`backend/domain/report/projection.py` 计划，本批不落）带 **tenant 输入**：签名含
  `tenant_id`，SQL WHERE `tenant_id=:tenant`；结果身份含 `valid_source_set`（§二有效集）。

### 3.2 M2 跨库映射与身份（round-148 §五.2）

- **跨库映射真源 = 内容字节复算 SHA-256**，非直接复制 app hash 声称绑定：
  - M2 `asset_items` 增加 `content_sha256`（由 M2 本地内容 bytes 计算，或受控绑定记录）；
  - app `assets.content_sha256`（tenant+active 唯一）→ M2 content_sha256 匹配，**带 tenant/active 条件**
    （app 侧）+ M2 本地唯一性；
  - 缺文件 → skip（无映射证据）；hash 重复/共享内容 → 冲突分支；未匹配/校验失败 → skip/fail 按 §3.3。
  - 已有 app hash ≠ app 行与 M2 行已完成绑定（round-148 §五.2 提示）。
- **事件身份 UNIQUE（单一）**：`asset_evaluations.event_idempotency_key varchar NOT NULL` +
  `UNIQUE (event_idempotency_key)`（**不再叠加 (asset_id,evaluation,event_key) 三元组**——那允许同事件改
  evaluation 再写一行，round-148 §五.2 关闭）。
  - 键编码：`m2:event:{event_idempotency_key}`（命名空间/tenant + event key 独立列承载）。
  - asset_id/evaluation/evidence 作 **replay 内容比较**；不同内容 → 冲突（旧 receipt 保持）；
    失败矩阵“同 key 已存在就 replay”不得**先于**内容比较，否则遮蔽下一行 conflict。
- **旧行/legacy 兼容**：既有 asset_evaluations 行（无 event key）→ 迁移方案：新列 `event_idempotency_key`
  允许一次性回填（用 source_agent+asset_id+created_at 稳定串），或新增独立 `asset_evaluations_receipt`
  表存新事件回执；旧 `receive_evaluation` 入口在无 event key 时走 legacy 路径（兼容），新增 C3 adapter 走
  新 receipt 表。空库/旧库升级与回滚计划一并给出；**仅改 ORM/create_all 不构成旧库升级**。
- **租户隔离**：M2 表无 tenant；全局 hash UNIQUE 会使两租户同内容指向同一本地 asset → 标签更新跨租户共用。
  明确：M2 本地库**单租户**（当前 M2 是单应用本地库）→ 共享内容语义可接受，但须登记；
  若多租户，改 `(tenant, content_sha256)` 唯一 + 显式租户绑定。跨租户同 hash 反例验收。

### 3.3 M2 失败/重试矩阵（round-148 §五.2 完整）

| 情形 | 结论 |
|---|---|
| 同 event_idempotency_key 已存在且内容（asset/evaluation/evidence）匹配 | **replay**：返回已存 receipt（同事件已消费证明） |
| 同 key 已存在但内容不同 | **conflict**（FeedbackContentConflict 语义），旧 receipt 保持 |
| app 资产存在，M2 无匹配 content_sha256 | **skip**（asset 未映射，留证据） |
| 内容字节缺失/裸 hash 无绑定 | **skip**（缺文件/未匹配） |
| DB 错误/跨库写前/写后崩溃 | **fail**：receipt/标签更新/本地审计同一本地事务；重试查 event key 返回同 receipt |

- 实账审计：receipt 写入 + 标签更新 + 本地审计在**同一本地事务**（区别于当前 receive_evaluation 每调用
  新增审计行）。
- 消费入口签名（C3 计划）：`M2Consumer.consume_material_score(event_draft, actor, request_id,
  worker_scope) -> Receipt`：先按 event key 查本地回执（内容比较）→ replay 或写入（同事务+审计）→ 返回
  receipt；事务责任清晰。

---

## 四、标准回归（PG 重启后复跑；本轮中途 docker `dsh-pg-test` 停止→重启，数据卷持久，终态恢复）

> 说明：本轮执行中途 `dsh-pg-test` 容器停止导致 T9 CI 首次运行 Connection refused，已 `docker start
> dsh-pg-test` 恢复（数据卷持久，`auth000002`/0 残留终态恢复）；kill 了挂起进程并重跑全量回归与 CI。

| 项目 | 结果 |
|---|---|
| 十一文件全量回归（185 P0-1 + 85 批次 1 + 17 selector） | **287 passed in 162.53s**，无 pytest warning |
| selector 独立 | **17 passed in 0.57s** |
| 前端 TypeScript | `tsc --noEmit` exit 0 |
| T5 CLI | `T5-CID-ASSERT: PASS` |
| T9 六阶段 CI | `T9_CI_LAYERS=PASS`（PG 恢复后重跑） |

> 说明：full 回归后捕获 1 条 auth.user 残留（disabled + 会话/账号，为历轮已知 idp_chain 偶发瞬态，非
> selector 引入——selector.py 为纯函数不写 DB）；已清除并复核 user/session/account=0/0/0。

数据库终态（恢复后）：`auth000002` / app_tables=31 / auth_tables=7 / enums=60 / triggers=17 /
ad_report_snapshots=0 / tenants=0 / auth_user=0 / workflow_runs=0 / temp_databases=0。

---

## 五、保留项与边界

- C2 核心（fb 三黄金键、replay、NFC、异常分层）、SKU append-only 方案沿用，不再重复讨论已通过方向。
- SKU/M2 实际 DDL、C1-b/c、C2、C3 与批次 3 未获执行授权；C1-a 本批实现待 CDX 独立验收。
- P0-2 完成边界：仅表示 app PG 上的离线领域闭环与 CI 门禁，不表示真实微信平台能力或全系统上线。

## 六、交接

请 Codex 独立验收 C1-a（selector/arrival 实装 + 17 项测试 + 回归）并按 R148-1（有效源真源 + 三反例）/
R148-2（范围登记 + M2 映射/身份/旧库/矩阵）复核文档回修；通过的项授权下一门，未闭合门继续契约锁定。

<!--RELAY: 请 CDX 读取本文件并继续，当前轮次 round-150-->