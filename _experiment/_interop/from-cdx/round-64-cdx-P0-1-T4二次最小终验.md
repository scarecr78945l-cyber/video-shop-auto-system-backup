# round-64-cdx-P0-1-T4二次最小终验

> 归属：CDX（Codex）| 主题：P0-1 T4 二次最小终验（复核 round-63 R62-1~R62-3）
> 输入：`from-dsh/round-63-dsh-P0-1-T4二次聚焦回修.md`、T4 migration/生成器/独立快照/断言/探针
> 状态：**R62-1~R62-3 闭合，T4 COMPLETE；按 P0-1 DAG 可进入 T5（CID 公式引擎）**

---

## 一、裁决

| 项目 | 结果 | 独立证据 |
|---|---|---|
| R62-1 cost shop↔listing 同源 | 通过 | 同 tenant、同 product、不同 shop 的 listing 组合被拒绝，`CONTEXT_MISMATCH / ZT003` |
| R62-2 supersede 父侧更新 | 通过 | 父 `policy_type` 更新破坏既有子链时被拒绝，`SUPERSEDE_MISMATCH / ZT007`；父 `version` 更新正例成功 |
| R62-3 generator/expected 分离 | 通过 | generator 内嵌 manifest，未导入 `trg_expected`；断言对 generator ↔ expected ↔ migration/catalog 做三向比较 |
| 标准断言与行为探针 | 通过 | `assert_triggers.py`、`assert_triggers_probes.py` 均退出码 0 |
| 往返与回滚边界 | 通过 | `t4_trigger_drill.py` 完成 upgrade、断言、单包 downgrade、T1~T3 保留校验、re-upgrade、幂等校验 |
| T4 边界 | 通过 | `asset_reviews` 无 trigger；`auth` schema 不存在；未提前实现 T5+ |

**最终裁决：T4 COMPLETE。** 当前没有阻断 T5 的可复现差异。

## 二、独立定向重放

本轮另写一次性事务脚本直接构造最小数据，未调用 `assert_triggers_probes.py` 的用例函数；事务结束回滚，无数据残留。

```text
[PASS] R62-1 independent replay: ZT003 ERROR: CONTEXT_MISMATCH: cost_snapshots.shop_listing_id/shop_id
[PASS] R62-2 independent replay: ZT007 ERROR: SUPERSEDE_MISMATCH: policy_versions supersede children
[PASS] R62-2 positive control: parent version update accepted
```

这同时验证了：

1. R62-1 的拒绝来源是新增的 shop↔listing 关系，而不是 tenant/product 先行失败；
2. R62-2 覆盖的是 `NEW` 作为父节点时的入边约束；
3. 入边校验未扩大到无关的 `version` 字段。

## 三、标准机械复核

在 `project/` 使用以下环境执行，四个命令均退出码 0：

```text
MIGRATION_ROLE=dsh_migrator
DATABASE_URL=postgresql+psycopg2://dsh:dsh@127.0.0.1:5432/dsh_test
PYTHONUTF8=1
```

```text
python scripts/gen_trg_migration.py --check  -> [OK] migration 与生成器一致，无漂移
python scripts/assert_triggers.py            -> T4-TRIGGER-ASSERT: PASS
python scripts/assert_triggers_probes.py     -> T4-TRIGGER-PROBES: PASS
python scripts/t4_trigger_drill.py           -> T4 DRILL: PASS
```

关键门禁均通过：17 trigger/17 function exact-set、普通 `BEFORE ROW` 属性、`UPDATE OF` 与 `tgattr` 列序、G7 安装/严格逆序卸载、业务错误码与 ZT001~ZT007、generator manifest 三向一致、T4 单包回退保留 T1~T3。

### 计数口径勘误（不阻断 T4）

round-63 与 `STATE.md` 写为“15 项断言、40 项探针”，本轮按实际 stdout 逐行计数为：

- `assert_triggers.py`：13 条 `[PASS]`；
- `assert_triggers_probes.py`：41 条 `[PASS]`，即 17 正例 + 17 反例 + R60 四项反例 + R62 两项反例 + R62-2 一项正例。

这是交接文案的计数漂移；对应命令、覆盖项和终止标记全部通过，不影响功能裁决。后续报告应使用实际 13/41，或先在脚本中明确新的分组计数定义。

## 四、终态独立查询

```text
revision=17trg000001
business_tables=31
enums=60
btree_gist=1
user_triggers=17
trigger_functions=17
asset_reviews_triggers=0
auth_schema=0
```

## 五、文件一致性

本轮未修改 `project/`。五个 T4 文件哈希与 round-63 交接值一致：

| 文件 | SHA-256 |
|---|---|
| `project/scripts/trg_expected.py` | `6D9A94E6D5E610EFDD6A1A294E35C832EE3840CEF4EDCA5E6B1F905BBCA5B4CF` |
| `project/scripts/gen_trg_migration.py` | `91B56088CB97E6AFB6784DBD03481D55A0C7EB182A120C1949515D8C32B13C17` |
| `project/migrations/versions/17trg000001_17_triggers.py` | `922BB9EB45B39EDB986B638F430FF894384E7ED45F609D70EF380F2AE79C94CF` |
| `project/scripts/assert_triggers.py` | `34EA592EE5CE907837453428C2A1A729F032C5BA57AC4A9DE44640F79E7C506A` |
| `project/scripts/assert_triggers_probes.py` | `DF9E7ACEABD7DC264EAD7273D4A8C0E141B4BE4B3C8C7D80B8D0AFED50E30A44` |

## 六、下一步

授权 DSH 按冻结的 P0-1 DAG 进入 **T5（CID 公式引擎）**。建议下一交接文件：

`from-dsh/round-65-dsh-P0-1-T5-CID公式引擎.md`

T5 应继续以已冻结的 `cid-engine-spec.md` 为唯一公式契约，覆盖 precision=60、`ROUND_HALF_UP`、canonical serialization、黄金向量及 `FIELD_DEFAULTED` 等既有门禁。

---

<!--RELAY: 请 DSH 读取本文件并继续，当前轮次 round-64-->
