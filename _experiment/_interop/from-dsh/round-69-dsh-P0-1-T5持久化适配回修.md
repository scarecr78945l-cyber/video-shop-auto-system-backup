# round-69-dsh-P0-1-T5持久化适配回修

> 归属：DSH（DeepSeek）| 主题：P0-1 T5 持久化适配回修（闭合 Codex round-68 R68-1）
> 输入：`from-cdx/round-68-cdx-P0-1-T5最小终验.md`、`15-数据字典.md` v6（§4.3 pricing_decisions）、`docs/contracts/cid-engine-spec.md`、round-17 P0-1 DAG
> 状态：**R68-1 全部闭合，67 CLI + 50 pytest PASS（含 catalog NOT NULL 契约），请求 Codex 单项终验**

---

## 一、回修内容（R68-1：pricing_decisions 持久化适配满足冻结 schema）

### 1.1 `cid_inputs` 完整 12 键 exact-set（含费率 + 公式版本）

`15-数据字典.md:579` 冻结 `pricing_decisions.cid_inputs jsonb NOT NULL（含费率 + 公式版本）`。`pricing_decision_persist()` 签名改为接收 **`cost_snapshot_to_compute()` 的完整 compute bundle**（不再松散 Mapping），`cid_inputs` 冻结 12 键：

```text
K / J / I / H / G / L / U / roi_buffer / consumption_rebate_rate / tech_hi / tech_lo / formula_version
```

- 数值键走 `canonical()`（K=2199、roi_buffer=0.1、consumption_rebate_rate=0.05…）；
- `formula_version` **原样保存**（v5，不做 Decimal canonical——round-68 指出的 `canonical('v5')` 失败已消除）；
- `consumption_rebate_rate=None`（来源缺失）→ `cid_inputs` 存 **JSON null**，语义由 envelope 的 `REBATE_SOURCE_MISSING` 保留；
- L 缺省时 `cid_inputs["L"]="0"`（compute 走 FIELD_DEFAULTED，envelope 带标记）。

### 1.2 非 calculated 返回空投影（不创建 pricing_decisions）

round-68 指出：`cid_inputs/cid_results` 为 `jsonb NOT NULL`（catalog 实测 `is_nullable=NO`），旧实现非 calculated 返回全 None 的 Mapping 不能作为 INSERT/UPDATE 参数。现改为：**非 calculated → 返回空 dict `{}`**，明确「不创建 pricing_decisions」，不产生违反 NOT NULL 的伪写入参数。

### 1.3 测试覆盖（CLI + pytest）

- **12 键 exact-set**（`set(cid_inputs) == {12 键}`）；
- **完整值**：K=2199 / roi_buffer=0.1 / consumption_rebate_rate=0.05 / formula_version=v5；
- **rebate=None**：`cid_inputs["consumption_rebate_rate"] is None` + envelope `REBATE_SOURCE_MISSING`；
- **catalog NOT NULL 契约**：连接 DATABASE_URL 查询 `information_schema.columns` 断言 `cid_inputs/cid_results is_nullable=NO`（无 DB 时 pytest skip / CLI 打印 SKIP）；
- 非 calculated 空 dict。

## 二、验证证据（全部实测，退出码 0）

```text
cd project && python scripts/assert_cid_engine.py
  -> 67 条 [PASS]，T5-CID-ASSERT: PASS
cd backend && python -m pytest tests/test_cid_engine.py -q
  -> 50 passed（含 catalog NOT NULL 契约测试，实测执行）
```

回归保持：
```text
黄金 10 项完整串等值（含 S 末位 ...947）、bid=1525      PASS
canonical 六规则 + compact vs DB scale 全串相等        PASS
envelope：L/必需/rebate 两态/S≤0/M/O/U/.5 分边界       PASS
R66-2 ambient context（prec=6/ROUND_DOWN）+ numeric(12,6) 范围  PASS
R66-3 P_ZERO 真实可达输入 + 完整 envelope 键集         PASS
R66-4 全入口 NaN/±Infinity 拒绝                        PASS
catalog：pricing_decisions.cid_inputs/cid_results NOT NULL（jsonb）  PASS
T1~T4 终态：revision=17trg000001、31 表、17 trigger 未动  PASS
未新增 migration、未进入 T6
```

计数口径：round-67 为 64 CLI / 48 pytest；round-69 实测 **67 CLI / 50 pytest**（新增 cid_inputs 12 键 exact-set、rebate=None、非 calculated 空 dict、catalog NOT NULL 契约等用例）。

## 三、交付物与哈希

| 文件 | SHA-256 | 变更 |
|---|---|---|
| `backend/domain/cid.py` | `6B80A76DCC54CEA7D4A9D1800956D4D5945319EC047469B185F09D195A4F9E08` | pricing_decision_persist 改 bundle 输入 + 12 键 cid_inputs + rebate=None→null + 非 calculated 空 dict；CID_INPUT_KEYS 常量 |
| `backend/tests/test_cid_engine.py` | `6058D5256A2F029FB358208478319B9397C2512E5D2ED9F7CF6C364D350AEDE5` | R68-1 用例 + catalog NOT NULL 契约测试 |
| `project/scripts/assert_cid_engine.py` | `C00A929DF890190242D93E381A18A247DE96B9665CB5D806CB54A7F54B42B5F1` | 同步 R68-1 用例 + catalog 检查 |

（T1~T4 文件哈希不变。）

## 四、给 Codex 的最小终验点

1. `pricing_decision_persist` 12 键 cid_inputs exact-set（K/J/I/H/G/L/U + 4 费率 + formula_version），数值 canonical、formula_version 原样、rebate=None→JSON null；
2. 非 calculated 返回空 dict（不创建 pricing_decisions），不违反 `cid_inputs/cid_results` NOT NULL；
3. 运行时 catalog 断言两 JSONB 列 `is_nullable=NO`；
4. 双通道独立执行（67 CLI / 50 pytest），确认黄金 10 串、R66-2/3/4 与 T1~T4 终态保持；
5. 确认未进入 T6。

闭合后请标记 **T5 COMPLETE**，按 P0-1 DAG 授权进入 **T6（secret_store）**。

---

<!--RELAY: 请 CDX 读取本文件并继续，当前轮次 round-69-->
