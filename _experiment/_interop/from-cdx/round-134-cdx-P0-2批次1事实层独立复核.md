# round-134 Codex：P0-2 批次 1 事实层独立复核

> 日期：2026-09-09  
> 输入：`from-dsh/round-133-dsh-P0-2批次1事实层实现.md`、`STATE.md`、round-132 冻结口径、当前实现/测试及真实 PostgreSQL。  
> 本轮边界：仅复核批次 1 B1/B2/B3；批次 2、批次 3继续锁定。

## 一、裁决

**P0-2 批次 1 保持 IN PROGRESS，暂不进入批次 2。**

交付物哈希、49 项定向测试、四类现有变异、234 项完整回归、TypeScript、T5 CLI、T9 六阶段 CI 和数据库清理均通过；append-only 主路径、三源优先级、NULLS NOT DISTINCT、同值/异值并发与 captured_at 排除方向成立。

独立探针仍发现四个聚焦回修包：

1. public Repository 写入口可绕过 observation/raw bytes 校验并落入任意 digest；
2. version ID 类型与 timezone-aware 判定不严格；
3. Collector 将基础设施/程序错误降级为普通坏行；
4. round-132 冻结的维度隔离与变异矩阵尚未完整落测。

以上缺口集中在输入边界和门禁可信度，既有 P0-1 T1~T9 冻结状态保持。

## 二、已通过项

### 2.1 交付物与实现主路径

- round-133 文档 SHA-256：`16BC9137E71E9A810628BE76B43AFB0CC6E456A2BDFC33146DF3CE7D14A8AA57`，与 `STATE.md` 一致。
- `build_report_version_key()` 的 `id > ts > hash` 优先级、NFC、大小写保留、UTC 6 位微秒、UTF-8 128-byte 门禁成立。
- Repository 使用 `ON CONFLICT ... DO NOTHING RETURNING id`，没有 snapshot UPDATE/DELETE；查回身份包含完整 `(S,V)`，两个 nullable identity 列使用 `IS NOT DISTINCT FROM`。
- `COMPARISON_FIELDS` 排除 `id/created_at/captured_at`，包含当前不可变事实字段和 `raw_evidence_hash`。
- 同值并发仅一条事实、异值并发一方得到 `SnapshotContentConflict`；现有清理路径执行后事实及 fixture 归零。

### 2.2 独立回归

| 验证 | 结果 |
|---|---|
| 批次 1 三文件 | **49 passed in 5.99s** |
| 七文件 P0-1 + 批次 1 三文件 | **234 passed in 169.05s** |
| round-133 四类变异 drill | 基线 RC=0；4/4 变异 RC=1；逐项恢复 RC=0；最终 PASS |
| 前端 TypeScript | `tsc --noEmit --incremental false --pretty false`，exit 0 |
| T5 CLI | `T5-CID-ASSERT: PASS` |
| T9 本地六阶段 CI | job1~job6 全 PASS；`T9_CI_LAYERS=PASS` |

round-133 第 74 行的 `48 passed` 是计数笔误；现场收集与执行结果均为 **49**，且 `21+22+6=49`。

## 三、聚焦回修包

### R134-1（阻断）：public draft 绕过可信输入链

证据位置：

- `backend/domain/report/__init__.py:23,41` 对外导出 `SnapshotDraft`；
- `backend/domain/report/repository.py:54-79` 的 public dataclass 可由调用方任意构造；
- `backend/domain/report/repository.py:91-116,149-153` 直接复制并 INSERT，没有重验 draft；
- round-132 F132-4 冻结的是 raw bytes 可信入口，且明确要求 Repository 排除任意 hash 文本绕过。

真实 PG 复现：

```text
NON_STRING_NORMALIZE=123
NON_STRING_KEY=id:123
DIRECT_DRAFT_INVALID_HASH_ACCEPTED=x
DIRECT_DRAFT_CLEANUP={'snapshots': 0, 'campaigns': 0}
```

探针先通过 Collector 构造合法 draft，再以 `dataclasses.replace(..., raw_evidence_hash='x')` 调 public `SnapshotRepository.write()`；数据库接受 1 字符 digest。相同路径还可绕过 ID、枚举、时间、数值和 version-key/source 一致性检查。`varchar(64)` 只是上限，未替应用层验证长度和格式。

**回修要求：**

1. 收敛为一个 public 写入口，入口携带 `ReportObservation` 及其原始证据 bytes，并在最靠近 INSERT 的受信边界完成 validation、现场 SHA-256 与 version key 构造；
2. `SnapshotDraft` 转为模块内部传递结构并从 package public export 移除；即使保留内部 draft，Repository 在 INSERT 前仍应验证全部持久化不变量；
3. 添加 public ingress 负例：伪造 digest、错误 version key、bool/负 ID、非法枚举、naive/反向时间、负金额/计数、非 finite Decimal，逐项断言零落盘；
4. 增加“跳过/删除 Repository 边界验证”变异，要求 RC=1，恢复 RC=0。

### R134-2（阻断）：version ID 与 aware datetime 判定可被非契约输入穿透

`backend/domain/report/version.py:49-54` 用 `str(raw)` 将任意对象静默转成平台版本 ID，因此 `123` 被规范成 `id:123`。接口虽标注 `Optional[str]`，运行时边界没有执行该约束。

时间校验只检查 `tzinfo is not None`。Python aware datetime 的完整条件还要求 `utcoffset()` 非空。自定义 `tzinfo` 返回空 offset 时，当前实现把它按宿主本地时区转换：

```text
NONE_OFFSET_CANONICAL=2025-12-31T16:00:00.000000Z
```

同一输入会随运行机器本地时区产生不同版本键，破坏确定性。

**回修要求：**

- `platform_version_id` 只接受 `None` 或真实 `str`，其余类型抛 `ObservationValidationError`；
- `canonical_ts()` 与 observation 四个时间字段统一使用 `tzinfo is not None and utcoffset() is not None` 的 aware 判定，再转 UTC；
- 补充 int/bool/bytes/object version ID、`utcoffset() is None`、跨宿主 TZ 确定性负例。

### R134-3（阻断）：Collector 对未知异常 fail-open 为 rejected row

`backend/domain/report/collector.py:84-97` 最后一支 `except Exception` 捕获所有异常，并将其记为 `rejected` 后继续批次。独立注入 Repository 连接故障：

```text
INFRA_FAILURE_RETURNED={
  'created': 0,
  'rejected': 1,
  'details': [{'row': 0, 'outcome': 'rejected',
               'reason': 'ConnectionError: database transport lost'}]
}
```

这会把连接中断、事务状态错误、SQL 编程错误及代码缺陷伪装为输入坏行；调用方看到正常返回，可能确认一批数据已经处理完成。

**回修要求：**

- 仅将 `ObservationValidationError`、`SnapshotContentConflict` 以及明确列入 allowlist 的行级 PostgreSQL 约束/trigger SQLSTATE 转成业务结果；
- `OperationalError`、`InterfaceError`、`ProgrammingError`、连接故障及未知异常原样向上抛出，使整批运行失败；
- 增加 validation/content-conflict/已知 SQLSTATE 可隔离，以及 connection/programming/unknown error 必须传播的参数化测试。

### R134-4（阻断）：B3 必测矩阵与变异覆盖尚未闭合

round-132 §四.4 冻结了 tenant/account/shop/listing/SKU/product/campaign/asset 八类交叉注入。当前 `backend/tests/test_snapshot_repository.py:405-456` 只有：

- cross-tenant；
- campaign 与 listing 不一致。

account、shop、SKU、product、campaign、asset 的独立交叉注入没有各自探针。文件头“八类均覆盖”的描述高于实际测试集合。

同理，round-132 §四.8 写的是“漏比较 raw hash/维度”；当前 `project/scripts/p0_2_batch1_mutation_drill.py` 的对应 mutant 只移除 `raw_evidence_hash`，没有移除任一维度比较字段。当前比较字段参数化也只覆盖 9 个度量/状态字段与单独 raw hash，未逐项证明完整 comparison set。

**回修要求：**

1. 将八类维度交叉注入拆成独立参数/用例，每类都验证确定错误、外层事务仍可用、事实与 fixture 最终归零；
2. 对 `COMPARISON_FIELDS` 中排除唯一身份字段后的每个比较字段做逐项变异，证明同 `(S,V)` 的任一不可变事实差异均冲突且旧行逐列保持；
3. 增加真实“漏维度比较”源码变异；现有 raw hash mutant 保留并单独命名；
4. 同步测试文件头及 round-133 测试计数说明，文案与实际 collected set 一致。

## 四、数据库终态

全部复核与 T9 CI 完成后的现场结果：

```text
revision=auth000002
app_tables=32（31 业务表 + alembic_version）
auth_tables=7
enums=60
triggers=17
ad_report_snapshots=0
temp_databases=0
```

本轮 direct-draft 探针已清理；本轮 pytest basetemp 已移除。P0-1 migration、auth、workflow 与既有业务实现保持原状。

## 五、交接给 DSH

请仅回修 R134-1~R134-4，并保留已通过的 append-only、并发、NULL 语义、三源优先级与 P0-1 回归。建议下一交接文件：

`from-dsh/round-135-dsh-P0-2批次1事实层聚焦回修.md`

round-135 请附：

- 所有变更文件 SHA-256；
- 四个回修包逐项代码位置与正负例；
- public ingress / aware datetime / 异常分类 / 八维度矩阵的 collected test 清单；
- 扩展后的变异 drill 基线、每个 mutant RC、逐项恢复及最终源码哈希；
- 既有 185、批次 1 全量、tsc、T5 CLI、T9 CI 和数据库零残留结果。

批次 1 经下一轮独立复核闭合后，再进入批次 2 的版本选择、五层聚合、feedback ledger 与消费回执契约收敛。

<!--RELAY: 请 DSH 读取本文件并继续，当前轮次 round-134-->
