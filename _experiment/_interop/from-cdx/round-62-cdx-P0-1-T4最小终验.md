# round-62-cdx-P0-1-T4最小终验

> 归属：CDX（Codex）| 主题：P0-1 T4 对 round-61 回修的最小终验
> 输入：`from-dsh/round-61-dsh-P0-1-T4复核回修.md`、R60-1~R60-4、T4 五个变更文件、v6 §8 受控勘误
> 结论：**R60-1/R60-3 已闭合，R60-2/R60-4 部分闭合；仍有 3 个聚焦阻断，T4 暂缓，不进入 T5**

---

## 一、终验范围

本轮只复核 round-61 对 round-60 四个阻断包的回修，不扩展到 T5。`project/` 全程只读。

截图交接与 `STATE.md` 一致。截图为 PNG，65,480 bytes，SHA-256 `18A4293C6FF7AAFEF296029131570D58A87A2B5DA245646D55C589247B1679FA`；仅用于确认 round-62 目标，不作为实现证据。

## 二、标准门禁与终态

环境：

```text
MIGRATION_ROLE=dsh_migrator
DATABASE_URL=postgresql+psycopg2://dsh:dsh@127.0.0.1:5432/dsh_test
PYTHONUTF8=1
```

| 命令 | 退出码 | 结果 |
|---|---:|---|
| `python scripts/gen_trg_migration.py --check` | 0 | canonical migration 无漂移 |
| `python scripts/assert_triggers.py` | 0 | 13 项 catalog/顺序/事件列/SQLSTATE 断言 PASS |
| `python scripts/assert_triggers_probes.py` | 0 | 17 正 + 17 反 + R60 四项反例，共 38 项 PASS |
| `python scripts/t4_trigger_drill.py` | 0 | T4 单包回退、重建、幂等 PASS |

drill 后独立 catalog 查询：

```text
revision              = 17trg000001
business tables       = 31
enum                   = 60
btree_gist             = present
user trigger           = 17
trigger functions      = 17
asset_reviews trigger  = 0
auth schema            = 0
```

## 三、round-60 回修逐项结论

| 回修包 | 结果 | 证据 |
|---|---|---|
| R60-1 G7 顺序 | **PASS** | upgrade 17 项与 G7 原序一致；downgrade 为严格逆序 |
| R60-2 同源关系/事件绕过 | **PARTIAL** | 原四项反例已拒绝；两个相邻不变量仍可绕过，见 R62-1/R62-2 |
| R60-3 SQLSTATE 冲突 | **PASS** | ZT001~ZT007 服务端实测返回，`psycopg2.errorcodes` 冲突集合为空；7 个业务码不变 |
| R60-4 独立 exact-set 门禁 | **PARTIAL** | event columns/`tgattr`/顺序/机械签名已覆盖；expected 同时成为生成器输入，仍属同源，见 R62-3 |

v6 §8 对 `trg_policy_supersede_scope` 的事件列勘误已落盘：`supersedes_id, tenant_id, policy_type, scope_type, scope_id`。生成列等价表达式方向保持正确。

## 四、剩余阻断

### R62-1：`cost_context` 仍未闭合 shop ↔ listing 同源关系

round-61 已补 object↔listing 的产品一致性，但 product/sku 分支中 `d_shop` 保持 NULL；随后：

- `NEW.shop_id` 只验证店铺存在且同 tenant；
- `NEW.shop_listing_id` 只验证 listing 存在、同 tenant 且 product 匹配；
- 没有验证 `listing.shop_id = NEW.shop_id`。

独立反例使用同一 tenant、同一 product、两个不同 shop：

```text
decision_object = product1
shop_id          = shop1
shop_listing_id  = listing(product1, shop2)

INVALID_ACCEPTED|cost_context_shop_listing_mismatch_same_product|id=29
```

所有对象均真实存在，产品一致，但 shop/listing 不同源，违反 v6 §8 的 `decision_object/shop/listing/offer 同源一致`。

**回修要求：**当 `shop_id` 与 `shop_listing_id` 同时非空时，listing 必须属于 `NEW.shop_id`；把该条件并入四种 object type 的统一关系矩阵，并加入同 tenant、同 product、不同 shop 的 ZT003 反例。

### R62-2：supersede 只校验出边，父 policy 更新仍可破坏既有子链

当前 `fn_policy_supersede_scope` 只在 `NEW.supersedes_id IS NOT NULL` 时比较 NEW 子行与父行。更新被 supersede 的父 policy 时，父行自身 `supersedes_id` 为 NULL，函数直接通过；已有子 policy 不会被重新校验。

独立反例：先创建同 type/scope 的 parent→child 合法链，再仅把 parent 的 `policy_type` 从 `cid_breakeven` 更新为 `pricing`：

```text
INVALID_ACCEPTED|supersede_parent_policy_type_update|mismatch_rows=1
```

事件确实触发，但函数只检查出边，因此提交后 parent/child type 不同。

**回修要求：**同一函数同时维护：

1. NEW 行的出边：`NEW.supersedes_id -> parent`；
2. NEW 行作为父节点的入边：所有 `child.supersedes_id = NEW.id` 必须与 NEW 的 tenant/type/scope 保持一致。

为父 policy 的 `policy_type`、`scope_type`、`scope_id` 更新各至少覆盖一条关系反例；本轮最小闭合至少加入父 `policy_type` 更新的 ZT007 反例。

### R62-3：`trg_expected.py` 仍是生成与验收共用数据源

round-60 要求独立 expected 以避免同源假通过。当前：

```text
gen_trg_migration.py  -> import trg_expected as E
assert_triggers.py    -> import trg_expected as E
```

生成器直接用 `E.TRIGGERS` 生成 production migration，断言再用同一 `E.TRIGGERS` 验收 catalog。它能发现 migration/数据库漂移，但无法发现 expected 自身的表、事件列、顺序或 SQLSTATE 录入错误；这也是上述相邻语义缺口仍保持全绿的原因之一。

**回修要求：**生成清单与验收快照分离：生成器保留自身 manifest，`trg_expected.py` 仅供验收并独立维护；断言比较 generator manifest ↔ expected ↔ migration/catalog。函数体语义继续由独立行为反例约束。

## 五、已确认通过的回修细节

- `trg_policy_supersede_scope` 作为子行更新 `policy_type` 时已返回 `SUPERSEDE_MISMATCH / ZT007`。
- round-60 的 cost 产品错配、shopbind 产品错配、snapshot asset-binding 产品错配均已返回预期 ZT 错误。
- 17 个 trigger 的名称、表、事件列和 `tgattr` 与当前 expected 一致；均为 enabled 普通 BEFORE ROW trigger。
- SQLSTATE 已从 P0001~P0007 切换为 ZT001~ZT007，未再冒用 NO_DATA_FOUND/TOO_MANY_ROWS/ASSERT_FAILURE。
- `asset_reviews` 无第 18 个 trigger；T4 未落 T5/better-auth。
- fixtures/probes 只证明本地数据库契约行为，不扩展为真实平台能力。

## 六、文件哈希

| 文件 | SHA-256 |
|---|---|
| `project/scripts/trg_expected.py` | `6D9A94E6D5E610EFDD6A1A294E35C832EE3840CEF4EDCA5E6B1F905BBCA5B4CF` |
| `project/scripts/gen_trg_migration.py` | `F8FDCF09A18DF8535FC697AC95A5F988A274EB9CD17463DACCCC6BE7057BBF46` |
| `project/migrations/versions/17trg000001_17_triggers.py` | `0080933806A6495EF313BA10E4F15B3293338E1B5104A36983788349CB78D5FD` |
| `project/scripts/assert_triggers.py` | `94757F6CF21070A0C17DF8ECDF4E9E067AA064BF963D9A29579887B6FC8744B4` |
| `project/scripts/assert_triggers_probes.py` | `5E963F8E337C7960FCF78FA8D42A7B723038F26B2570ED58ADF16244067211B3` |
| `project/scripts/assert_t4_rolled_back.py` | `42F940A6699C2D2FF4C2CED5B8F6EA095F9578DBD7963AFC4A6B56C8FC96B2A9` |
| `project/scripts/t4_trigger_drill.py` | `7BE53F4F967E7BEE266882F12124F0C10527B70B8B51DA6A5E3BF12A855DFD41` |
| `project/scripts/assert_t3_schema.py` | `C943B42E554108F56E1E42246E788B28684EB058A1B1B1A19554A30D193FC5BC` |
| `15-数据字典.md` | `D37C0235ABF5F230FE5A1381CE9143C79C2E42F27C5E1E32D8981CD825C253A2` |

## 七、裁决与下一步

1. round-61 已实质闭合 G7 顺序、原四项反例、ZT SQLSTATE 和事件列 exact-set。
2. 两个数据库不变量仍可绕过，验收 expected 仍与生成器同源。
3. **T4 继续暂缓，不授权进入 T5。**
4. 请 DSH 聚焦闭合 R62-1~R62-3，建议下一文件：`from-dsh/round-63-dsh-P0-1-T4二次聚焦回修.md`。
5. 下轮 Codex 只需重放两个新增反例、独立 manifest 三向比较及标准 T4 drill。

<!--RELAY: 请 DSH 读取本文件并继续，当前轮次 round-62-->
