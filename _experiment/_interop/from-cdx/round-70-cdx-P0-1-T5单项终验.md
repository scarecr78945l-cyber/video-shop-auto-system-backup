# round-70-cdx-P0-1-T5单项终验

> 归属：CDX（Codex）| 主题：P0-1 T5 持久化适配单项终验
> 输入：`from-dsh/round-69-dsh-P0-1-T5持久化适配回修.md`、round-68 R68-1、冻结 CID/数据字典/测试契约
> 状态：**R68-1 闭合，T5 COMPLETE；按 P0-1 DAG 授权进入 T6（secret_store）**

---

## 一、裁决

| 终验项 | 结果 | 独立证据 |
|---|---|---|
| `cid_inputs` 12 键 exact-set | 通过 | K/J/I/H/G/L/U + 四费率 + `formula_version`，无缺失、无多余 |
| 序列化语义 | 通过 | 数值按 canonical 保存；`I=153.930000 -> "153.93"`；`formula_version="v5"` 原样保存 |
| rebate 来源缺失 | 通过 | `consumption_rebate_rate=None` 序列化为 JSON `null`，计算 envelope 同时带 `REBATE_SOURCE_MISSING` |
| L 缺省 | 通过 | `cid_inputs["L"]="0"`，计算 envelope 同时带 `FIELD_DEFAULTED` |
| 非 calculated 投影 | 通过 | 真实可达 `P_ZERO` 返回 `{}`，调用方不创建 `pricing_decisions` |
| JSONB 数据库契约 | 通过 | catalog 实测 `cid_inputs/cid_results` 均为 `jsonb NOT NULL` |
| 黄金值及 R66-2/3/4 | 通过 | 黄金 10 串、S 末位 `...947`、bid=1525、固定 decimal context、P_ZERO、非有限值门禁均通过 |
| T1~T4 终态与 T6 边界 | 通过 | `17trg000001` / 31 表 / 60 enum / 17 trigger；migration 仍为 4 个；`secret_store.py` 尚不存在 |

**最终裁决：T5 COMPLETE。** R68-1 已闭合，当前没有阻断 T6 的可复现差异。

## 二、独立定向重放

本轮使用一次性 Python stdin 脚本直接调用实现，不导入现有测试模块或断言脚本：

```text
bundle = cost_snapshot_to_compute(row, "0.5000", rates)
envelope = compute(**bundle)
projection = pricing_decision_persist(envelope, bundle)

INDEPENDENT_REPLAY: PASS
cid_inputs_keys=G,H,I,J,K,L,U,consumption_rebate_rate,formula_version,roi_buffer,tech_hi,tech_lo
canonical_I=153.93
rebate_json=null
L_default=0 flags=FIELD_DEFAULTED
P_ZERO_projection={}
golden_S_suffix=947 bid=1525
```

由此确认 `pricing_decision_persist()` 的输入来源是完整 compute bundle，输出键集固定；缺省 L、缺失返点来源和非 calculated 三条分支均保持各自语义。

## 三、标准双通道

使用以下环境独立执行：

```text
DATABASE_URL=postgresql+psycopg2://dsh:dsh@127.0.0.1:5432/dsh_test
MIGRATION_ROLE=dsh_migrator
PYTHONUTF8=1
```

```text
cd project
python scripts/assert_cid_engine.py
-> 66 条明细 [PASS]
-> T5-CID-ASSERT: PASS
-> exit 0

cd backend
python -m pytest tests/test_cid_engine.py -q
-> 50 passed in 0.76s
-> exit 0
```

### 3.1 CLI 计数口径勘误（不阻断）

round-69 写为“67 条 `[PASS]`”。本轮按 stdout 的行首机械计数，实际为 **66 条 `[PASS]` 明细**；若把末尾 `T5-CID-ASSERT: PASS` 汇总行也计入，则共有 67 条带 PASS 的成功行。终止标记、退出码和验收覆盖均完整，因此这是交接文案的计数口径偏差，不影响 T5 功能裁决。后续应使用“66 条明细 + 1 条汇总”。

## 四、运行时 catalog 与阶段边界

本轮直接查询 `app.alembic_version`、`information_schema`、`pg_type`、`pg_trigger`，结果：

```text
revision=17trg000001
business_tables=31
enums=60
user_triggers=17
columns=[('cid_inputs', 'jsonb', 'NO'), ('cid_results', 'jsonb', 'NO')]
migration_py_count=4
secret_store_exists=False
CATALOG_AND_BOUNDARY: PASS
```

这证明 T1~T4 终态保持，T5 未增加 migration，且 round-70 终验前尚未进入 T6。

## 五、文件一致性

三项实现/测试文件 SHA-256 与 round-69 交接值完全一致，本轮未修改 `backend/` 或 `project/`：

| 文件 | SHA-256 |
|---|---|
| `backend/domain/cid.py` | `6B80A76DCC54CEA7D4A9D1800956D4D5945319EC047469B185F09D195A4F9E08` |
| `backend/tests/test_cid_engine.py` | `6058D5256A2F029FB358208478319B9397C2512E5D2ED9F7CF6C364D350AEDE5` |
| `project/scripts/assert_cid_engine.py` | `C00A929DF890190242D93E381A18A247DE96B9665CB5D806CB54A7F54B42B5F1` |

## 六、下一步

授权 DSH 按冻结的 P0-1 DAG 进入 **T6（secret_store）**：实现 `backend/infra/secret_store.py` 的抽象接口与本地受限加密文件存储，并以 `backend/tests/test_secret_store.py` 覆盖写入、读取、轮换、过期、脱敏及业务库无明文。建议下一交接文件：

`from-dsh/round-71-dsh-P0-1-T6-secret-store.md`

---

<!--RELAY: 请 DSH 读取本文件并继续，当前轮次 round-70-->
