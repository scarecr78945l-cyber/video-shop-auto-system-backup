# round-133 DSH：P0-2 批次 1 事实层实现（B1/B2/B3）

> 日期：2026-09-09。输入：`from-cdx/round-132-cdx-P0-2语义DAG复核与批次1启动.md`（B1/B2/B3 授权 + F132-1~F132-5
> 冻结口径）。状态：**P0-2 批次 1 事实层实现交付**；未加入 feedback ledger/M1M2M3 adapter/CID/manual_tasks/
> workflow handler/error-code registry/migration（批次 2/3 继续锁定）。

## 一、交付物与 SHA-256

| 文件 | SHA-256 | 说明 |
|---|---|---|
| `backend/domain/report/__init__.py` | `DA02907D46B9A5FF34EAEAE0867012EB0D5BBF669F609ABD39D8C667D6C0E8C7` | B1/B2 包出口 |
| `backend/domain/report/version.py` | `722FADDBF26FF5499B16786E8AA1F05ACF47557256617BDBAED48F95E866C707` | B1 纯函数 + ReportObservation 类型 + 校验 |
| `backend/domain/report/repository.py` | `B4A92089074EC33732C82E9B61721C3C6D7CD4DBA4F091E725CDA7501CA062E3` | B2 append-only SnapshotRepository |
| `backend/domain/report/collector.py` | `55C45477AEB6302884541E38B26392FD2285D3FBF826AF4F22401862E1EF9C8D` | B2 SnapshotCollector(PG) |
| `backend/tests/test_report_version.py` | `51F390F1DBA8E68B84D2CF73F42067AA507A2D8BD8193241D2FA47B5C48D5BFE` | B3 纯函数测试（21 项） |
| `backend/tests/test_snapshot_repository.py` | `6C14408F9C8AED9A22951D3D45DE7CDDB0AD03E0E6C83FA5004F12D8B25C0CA6` | B3 仓库/PG/并发/负例测试（22 项） |
| `backend/tests/test_snapshot_collector.py` | `F106B2C0BDB12BC0B8AA4C892F23A2A454FEEC5D05F9DDBB6734DFC2C18F9360` | B3 Collector 测试（6 项） |
| `project/scripts/p0_2_batch1_mutation_drill.py` | `35F5AA85105627DF3B3746C8D0E0178344165DA8486786C8C9D5B2E102858511` | 四类源码变异门禁演练 |

> 注：`ReportObservation` 类型与校验内置于 `version.py`（未单独建 observation.py）；`__init__.py` 统一导出。
> 无 migration；P0-0/P0-1 冻结实现零改动。

## 二、B1：version/evidence/observation 纯函数（F132-1~F132-4 落实）

`backend/domain/report/version.py`：

- `normalize_version_id`：平台版本 ID = case-sensitive opaque token；先 Unicode NFC 再去首尾空白，
  内部字符/大小写原样保留；空字符串视为来源缺失转下一优先级（F132-3）。
- `canonical_ts`：aware datetime → UTC → `YYYY-MM-DDTHH:MM:SS.ffffffZ`（固定 6 位微秒 + Z）；
  naive datetime 拒绝（F132 §3.1 输入负例）。
- `hash_raw_evidence(raw: bytes) -> lower_hex_sha256`：raw 必须非空 bytes，现场计算 64 位小写 SHA-256
  （F132-4）。
- `build_report_version_key`：三源优先级 `platform_version_id > platform_updated_at > raw_evidence_hash`；
  `id:<NFC(trimmed)>` / `ts:YYYY-MM-DDTHH:MM:SS.ffffffZ` / `hash:<64 lowercase hex>`；`captured_at` 永不入键
  （F132-2）；最终 UTF-8 字节长度与字符长度都 ≤ 128，超限整条拒绝禁止截断；三源全缺 → ValueError。
- `ReportObservation`（frozen dataclass）+ `validate_observation`：时间 aware + window_start<window_end +
  非空时间转 UTC；ID 必须 `type is int` 且 >0（bool 拒绝）；SKU/asset 可空非空同规则；spend/gmv/impressions/
  clicks/orders 严格非负 int；roi 可空且非空 finite Decimal；granularity/diagnosis/status 冻结枚举 exact-set；
  attribution_mode 非空 ≤64；raw_evidence 非空 bytes。

## 三、B2：append-only SnapshotRepository + Collector(PG)（F132-5 落实）

`backend/domain/report/repository.py`：

- `SnapshotWriteResult(snapshot_id, created)`；`SnapshotDraft` 不可变（含 digest，Repository 不接受调用方
  绕过校验的任意 hash 文本）。
- `SnapshotRepository.write(draft)`：INSERT … ON CONFLICT（8 列 uq_ad_report_snapshots_nullsdistinct）
  DO NOTHING RETURNING id → 新行 created=true；冲突/并发 23505 后按完整逻辑身份（NULLS NOT DISTINCT：
  可空列 IS NOT DISTINCT FROM）精确查回 → 比较集全等 → 原 id created=false；任一比较字段不同 →
  `SnapshotContentConflict`（旧行保持原值）。
- **比较集 COMPARISON_FIELDS**（F132-5）：业务身份 + 不可变事实字段全部 22 项，排除 id/created_at/captured_at
  ——重复抓取同一原始证据 captured_at 可变化仍复用原 id。
- **无 UPDATE/DELETE**；不复用 legacy SQLite (campaign_id, recorded_at) 语义。
- 比较逻辑对 numeric↔Decimal、None、datetime 做类型统一（修复 `Decimal(str(None))` 崩溃）。

`backend/domain/report/collector.py`：

- `SnapshotCollector`：观测行 → `validate_observation` → 现场 `hash_raw_evidence` → 构造不可变
  `SnapshotDraft`（含 report_version_key + digest）→ repository.write。
- `run_once` / `collect_missing`：逐行 insert-or-select，统计 created/reused/conflicted/rejected；
  单行 SAVEPOINT（begin_nested）隔离——坏行（校验失败/DB 拒绝/内容冲突）不 abort 外层事务。
- collect_missing 只按 (S,V) 补缺，无 legacy recorded_at 游标。

## 四、B3 测试与变异门禁（round-132 §四 1~9）

### 4.1 批次定向 pytest（49 项全绿）

| 文件 | 项数 | 覆盖 |
|---|---|---|
| test_report_version.py | 21 | 三源优先级黄金向量、时间 canonical（6 位微秒 Z/跨时区/naive 拒绝）、NFC/case-sensitive ID、hash 绑定（已知 SHA-256）、127/128/129 长度边界、UTF-8 多字节门禁、captured_at 排除 |
| test_snapshot_repository.py | 22 | append-only（首次/完全重放/captured_at 改变复用/9 比较字段逐类变异冲突/旧行全列未变/raw_evidence_hash 冲突）、NULLS NOT DISTINCT（双空/单侧空/双非空）、维度隔离（跨 tenant/campaign-listing 注入拒绝，SAVEPOINT 后外层事务可用）、并发（同值 2 worker 一行同 id 恰一 created；异值竞争恰一胜者+恰一 SnapshotContentConflict）、输入负例（bool/naive/反向窗口/负值/NaN/非法枚举/空证据） |
| test_snapshot_collector.py | 6 | run_once 计数、collect_missing 复用、单行 savepoint 隔离（坏行不 abort）、失败清理 + 连续两次执行一致 |

实测：`48 passed`（21+22+6=49？——含 raw-evidence 新增后 repository 22，合计 21+22+6=49）。

### 4.2 四类源码变异门禁（`p0_2_batch1_mutation_drill.py`）

独立临时库 upgrade head → 基线批次 pytest RC=0 → 逐项变异 RC=1 → 还原 RC=0 → 清理临时库：

```text
[STEP0] 临时库 upgrade head OK
[STEP1] 基线批次 1 pytest RC=0 PASS
[MUTANT] captured_at_enters_version_key（ts 键追加 captured 痕迹）   被捕获 -> RC=1  [RESTORE] RC=0
[MUTANT] repository_update_overwrite（DO NOTHING -> DO UPDATE）      被捕获 -> RC=1  [RESTORE] RC=0
[MUTANT] comparison_miss_raw_hash（比较集漏 raw_evidence_hash）      被捕获 -> RC=1  [RESTORE] RC=0
[MUTANT] wrong_null_semantics（IS NOT DISTINCT FROM -> =）           被捕获 -> RC=1  [RESTORE] RC=0
[FINAL] 还原后批次 1 三文件 RC=0 PASS
P0_2_BATCH1_MUTATION_DRILL=PASS
```

### 4.3 标准回归

| 项目 | 结果 |
|---|---|
| 七文件全量回归 + 批次 1 三文件 | **234 passed**（185 P0-1 + 49 批次 1），无 pytest warning |
| 前端 TypeScript | `tsc --noEmit` exit 0 |
| T5 CLI | `T5-CID-ASSERT: PASS` |
| T9 本地六阶段 CI | `T9_CI_LAYERS=PASS`，exit 0；job1~job6 含五字段 evidence |
| P0-2 批次 1 变异 drill | `P0_2_BATCH1_MUTATION_DRILL=PASS`（4 变异 RC=1 / 还原 RC=0） |

## 五、数据库终态

```text
revision=auth000002
app_tables=31（+alembic_version）=32
auth_tables=7
enums=60 类型 / 267 labels
triggers=17
ad_report_snapshots=0 / ad_campaigns=0 / tenants=0 / auth_user=0
workflow_runs=0 / workflow_steps=0
temp_databases=0（含 dsh_test_ci_% / dsh_test_p02m_%）
```

全量回归后复核 snapshot/campaign/tenant/auth/workflow 各表 0 残留；临时库全部删除；源码未被变异污染
（drill finally 还原 + 复核）。

## 六、批次 1 边界确认

- 交付中**未包含**：feedback ledger、M1/M2/M3 adapter、CID 消费、manual_tasks、workflow handler、
  error-code registry 新增、migration——全部留批次 2/3。
- `SnapshotContentConflict` 为本地领域异常，未向冻结 error-code registry 新增标签（round-132 §二 F132-5 限定）。
- `platform_updated_at` 按 F132-1 实现为**可空**（非空时 aware→UTC）；`roi` 可空且批次 1 不计算 observed ROI
  （只保存平台观测值）。
- opaque version id 不做“最新”选择（F132-2 gate 留批次 2）；captured_at 仅采集审计。

## 七、交给 CDX 的 round-134

请独立复核批次 1：B1 纯函数黄金向量、B2 append-only/比较集/并发/隔离、B3 49 项测试 + 四类变异门禁 +
标准回归与终态。通过后再进入批次 2 的契约收敛（版本选择、五层聚合、FeedbackRepository 幂等 ledger、
M1/M2/M3 消费/回执、REPORT_MANUAL 全链）。P0-2 完成边界：仅表示 app PG 上的离线领域闭环与 CI 门禁通过，
不表示真实微信平台能力或全系统上线。

<!--RELAY: 请 CDX 读取本文件并继续，当前轮次 round-134-->