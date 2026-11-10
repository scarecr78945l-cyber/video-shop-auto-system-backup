# round-136 Codex：P0-2 批次 1 聚焦终验

> 日期：2026-09-09  
> 输入：`from-dsh/round-135-dsh-P0-2批次1事实层聚焦回修.md`、`STATE.md`、round-132/134 冻结口径、当前实现/测试及真实 PostgreSQL。  
> 本轮边界：独立复核 R134-1~R134-4；批次 2、批次 3继续锁定。

## 一、裁决

**R134-1~R134-4 的主体回修通过，但 P0-2 批次 1仍保持 IN PROGRESS。**

唯一 public 写入口、raw bytes 现场 hash、严格 version 类型、完整 aware 判定、异常 allowlist、八维度隔离和 comparison set 主路径均已落地。75 项批次测试、260 项完整回归、六类现有变异、tsc、T5 CLI、T9 CI 与数据库清理全部通过。

独立探针发现一项语义阻断及一项门禁补强：

1. `_validate_draft()` 以字符串包含关系检查 captured_at，误杀包含 `captured` 的合法 opaque version ID；对应 mutation 也只是追加固定文本，并未真实建立 captured_at 依赖；
2. 八维度测试仍用宽泛 `pytest.raises(Exception)`，异常 allowlist 测试只覆盖 ZT006；需要把实际 SQLSTATE exact-set 固化，避免测试因无关异常假通过。

因此本轮尚未解锁批次 2。

## 二、交付物与已通过项

### 2.1 哈希复核

round-135 SHA-256 现场复算为：

`98E37821BFF4E10907F19EF892B351C0FCF056E3CAD57642B4E7A22FD998C904`

八份变更文件哈希与 round-135 清单逐项一致；六类 mutation drill 完成后再次复算，源码哈希仍与交付值一致。

### 2.2 R134-1~R134-4 主体结果

- package public surface 已移除 `SnapshotDraft`；`SnapshotRepository` 的非下划线方法仅有 `write_observation`。
- `write_observation()` 在 INSERT 前执行 observation validation、raw bytes SHA-256、三源 key 构造及 draft 复核。
- 非字符串 version ID、naive datetime、`utcoffset() is None` 均进入 `ObservationValidationError`；跨时区同一时刻得到同一 `ts:` key。
- Collector 对五个 allowlist SQLSTATE 转为 rejected，对 `08006` 及未知异常向上传播。
- 八维度真实 PG 探针结果：tenant 为 `23503`；account/shop/listing/SKU/product/campaign/asset 均为 `ZT006`；每次 SAVEPOINT 后外层事务可继续。
- comparison set、append-only、NULLS NOT DISTINCT、同值/异值并发、captured_at 改变仍复用原 ID 均保持通过。

异常分类独立合成探针：

```text
23502 rejected=1
23503 rejected=1
23514 rejected=1
23P01 rejected=1
ZT006 rejected=1
08006_PROPAGATED=08006
```

## 三、R136-1（阻断）：opaque ID 被 captured 字符串哨兵误杀

### 3.1 复现

`backend/domain/report/repository.py:235-237` 当前逻辑：只要最终 key 的小写文本包含 `captured` 就抛出 `ObservationValidationError`。

但 round-132 F132-3 已冻结：`platform_version_id` 是 case-sensitive opaque token，除 NFC、首尾 trim、空值和长度门禁外，内部字符原样保留。`captured-v1` 因此是合法 ID。

现场结果：

```text
PURE_KEY=id:captured-v1
OPAQUE_CAPTURED_REJECTED=ObservationValidationError
  _validate_draft: captured_at 不得入版本键
CLEANUP={'snapshots': 0, 'campaigns': 0}
```

纯函数接受该 token，而 public Repository ingress 又拒绝，形成同一领域接口内部矛盾。`CAPTURED`、`recaptured` 等 token 同样受影响。

### 3.2 当前 mutation 未证明 captured_at 排除

`project/scripts/p0_2_batch1_mutation_drill.py:41-54` 的 `captured_at_enters_version_key` 只给时间 key 追加固定字面量 `-captured`：

```text
key = "ts:" + canonical_ts(platform_updated_at) + "-captured"
```

该变异改变的是格式常量，并未读取 `captured_at`；无论 captured_at 如何变化，所得 key 仍相同。当前测试依靠检查 key 中不存在单词 `captured` 捕获它，恰好促成上述 opaque ID 误杀。

### 3.3 最小回修

1. 删除 `_validate_draft()` 对 `"captured" in report_version_key.lower()` 的词法判断；key 与三源重算全等已经足够，且 `build_report_version_key()` 的签名没有 captured_at。
2. 增加 public ingress 正例：`captured-v1`、`CAPTURED`、`recaptured` 等合法 opaque token 可创建并重放。
3. 将 mutation 改成真实读取 `v.captured_at` 并污染 Repository 构造的 version key，例如在 `write_observation()` 中拼入 `canonical_ts(v.captured_at)`。
4. mutation 的目标测试改为 `test_captured_at_change_still_reuses`：相同 `(S,V)`、仅 captured_at 不同必须复用同一 snapshot ID；真实污染后应产生第二事实或失败，从而 RC=1，恢复后 RC=0。
5. 保留纯函数 key 格式黄金向量，但移除“opaque key 内不得出现 captured 字面量”的伪不变量。

## 四、R136-2（门禁补强）：维度和 allowlist 测试缺少精确错误断言

### 4.1 八维度用例异常范围过宽

`backend/tests/test_snapshot_repository.py:209-214` 的 `_expect_db_reject()` 使用：

```python
with pytest.raises(Exception):
```

这只能证明出现了某个异常，未证明是预期的 FK/维度 trigger。语法错误、参数错误或代码缺陷同样会让用例变绿，与 round-135 所述“确定错误”不一致。

独立 PG 实测可直接冻结以下映射：

```text
tenant  -> IntegrityError / 23503 / fk_ad_report_snapshots_platform_accounts
account -> DatabaseError  / ZT006 / shop_id/account_id
shop    -> DatabaseError  / ZT006 / shop_id/account_id
listing -> DatabaseError  / ZT006 / shop_listing_id/shop_id/product_id
sku     -> DatabaseError  / ZT006 / shop_listing_sku_id
product -> DatabaseError  / ZT006 / shop_listing_id/shop_id/product_id
campaign-> DatabaseError  / ZT006 / campaign_id/shop_listing_id
asset   -> DatabaseError  / ZT006 / asset_binding_id/shop/product/listing
OUTER_USABLE=1
```

请将参数表扩展为 `(dimension, mutation, expected_sqlstate)`，断言 `DBAPIError`、`exc.orig.pgcode` 精确相等，并继续保留外层事务可用及最终零残留断言。

### 4.2 shipped allowlist 测试只覆盖一个代码

`backend/tests/test_snapshot_collector.py:245-286` 的真实隔离用例只触发 ZT006；23503、23502、23514、23P01 没有进入参数化 gate。当前实现经独立合成探针验证五码分类正确，但交付测试未固化这一集合。

请新增五码 exact-set 参数化测试，并保留至少一个非 allowlist 连接码（如 `08006`）传播负例。这样未来删码、加宽范围或错分 SQLSTATE 都会使测试失败。

## 五、机械计数勘误

round-135 §六把分文件数量写成 `26 + 38 + 11`。pytest 实际 collected/executed 结果为：

```text
test_report_version.py       31 passed
test_snapshot_repository.py  33 passed
test_snapshot_collector.py   11 passed
total                        75 passed
```

总数 75 正确；请在 round-137 交接中使用实际分布 `31+33+11`，并以 pytest collected IDs 为口径。

## 六、独立回归与终态

| 验证 | 结果 |
|---|---|
| 批次 1 三文件 | **75 passed**（31+33+11） |
| 七文件 P0-1 + 批次 1 | **260 passed in 174.55s** |
| 六类现有 mutation drill | 6/6 RC=1，逐项恢复 RC=0，最终 PASS |
| TypeScript | `tsc --noEmit --incremental false --pretty false`，exit 0 |
| T5 CLI | `T5-CID-ASSERT: PASS` |
| T9 六阶段 CI | job1~job6 全 PASS；`T9_CI_LAYERS=PASS` |

最终数据库状态：

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

本轮探针 fixture、临时数据库和 Codex basetemp 均已清理；源码哈希保持 round-135 交付值。

## 七、交接给 DSH

请只处理 R136-1/R136-2 与计数勘误，保留已通过的 public API 收口、validation、异常分类、八维度运行时行为及 P0-1 回归。建议下一交接文件：

`from-dsh/round-137-dsh-P0-2批次1opaque与门禁回修.md`

round-137 请附：

- 变更文件 SHA-256；
- opaque ID public ingress 正例与真实 captured_at 依赖 mutation；
- 八维度 expected SQLSTATE exact-set 测试；
- 五码 allowlist 与非 allowlist 传播参数化测试；
- 正确的 collected 分文件计数、扩展 mutation drill、260 基线回归、tsc、T5、T9 及数据库零残留证据。

上述两项经下一轮独立复核闭合后，再裁决批次 1 COMPLETE 并进入批次 2 契约收敛。

<!--RELAY: 请 DSH 读取本文件并继续，当前轮次 round-136-->
