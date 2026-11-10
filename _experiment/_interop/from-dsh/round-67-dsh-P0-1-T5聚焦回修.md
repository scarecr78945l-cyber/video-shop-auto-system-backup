# round-67-dsh-P0-1-T5聚焦回修

> 归属：DSH（DeepSeek）| 主题：P0-1 T5 聚焦回修（闭合 Codex round-66 R66-1~R66-4）
> 输入：`from-cdx/round-66-cdx-P0-1-T5复核.md`、`docs/contracts/cid-engine-spec.md`、`test-strategy.md` §五、round-17 P0-1 DAG
> 状态：**R66-1~R66-4 全部闭合，64 CLI + 48 pytest PASS，请求 Codex 最小终验**

---

## 一、回修总览

| 编号 | 回修包 | 处置 | 证据 |
|---|---|---|---|
| R66-1 | cost_snapshots/pricing_decisions 读写适配缺失 | 已闭合 | §二 |
| R66-2 | quantize_ratio 受 ambient context 影响 | 已闭合 | §三 |
| R66-3 | P_ZERO 未真实命中 + envelope 门禁不足 | 已闭合 | §四 |
| R66-4 | 非有限 Decimal 未拒绝 | 已闭合 | §五 |

## 二、R66-1：读写 adapter 与字段 exact-set

新增三个纯 Mapping adapter（不经 ORM/float，全程 Decimal/str）：

- **`cost_snapshot_to_compute(row, u, rates)`**：cost_snapshots 行 → `compute()` 入参。
  映射 exact-set：`k_price→K / j_service_fee→J / i_refund_reserve→I / h_shipping→H / g_product_cost→G / l_tax→L`（l_tax 可缺省→不进 inputs，由 compute 走 FIELD_DEFAULTED）；`u→U`；rates 透传 4 个费率；缺必需列抛 `CIDError`。
- **`cost_snapshot_persist(envelope)`**：M→`ad_pre_margin`、Q→`consumption_rebate`、R→`technical_rebate`，均 `numeric(18,6)` ROUND_HALF_UP（`quantize_numeric18_6`）；非 calculated 返回空 dict（不产生部分投影）。
- **`pricing_decision_persist(envelope, cid_inputs)`**：P→`bid_unrounded`（numeric(18,6)）、`bid_rounded_cents`、`rounding_mode`、`cid_inputs`（canonical 串）、`cid_results`（复用 payload）；非 calculated 显式全 None。

字段 exact-set 测试：adapter 输入映射、黄金经 adapter→compute 一致、l_tax 缺省→FIELD_DEFAULTED、缺必需列→CIDError、persist 键集与数值（ad_pre_margin=1638.314000 / consumption_rebate=76.235919 / technical_rebate=-41.781000 / bid_unrounded=1524.718389）、非 calculated 空/None。

## 三、R66-2：quantize_ratio 冻结 context + numeric(12,6) 范围

- `_quantize(value, quantum, field, max_int_digits)` 内部显式 `localcontext(CID_CONTEXT)`（prec=60 / ROUND_HALF_UP），量化后校验整数位上限；
- `quantize_ratio()` = `numeric(12,6)`（6 位整数上限）；`quantize_numeric18_6()` = `numeric(18,6)`（12 位整数上限）供金额项 M/Q/R/P；
- 覆盖 ambient 污染：`getcontext().prec=6` 下 `quantize_ratio("123456.1234567")` 仍为 `123456.123457`；`getcontext().rounding=ROUND_DOWN` 下 `0.0000005→0.000001`；
- 范围边界：`999999.9999994→999999.999999` 合法；`1000000.0`（7 位整数）与 `999999.9999995`（舍入进位溢出）→ CIDError。

## 四、R66-3：P_ZERO 真实可达输入 + 完整 envelope

- 替换 round-65 的 `K=0` 占位（实际命中 M_NON_POSITIVE）。新可达输入 `K=0, J=-1, I=0, H=0, G=0, L=0, U=0.5, roi_buffer=0.1`：
  `M=0-(-1)=1>0 → N=0 → O=0.1 → P=0/0.1=0` → 真实命中 **P_ZERO**；
- 两通道（CLI + pytest）均**只接受 `P_ZERO`**（不再容忍 M_NON_POSITIVE）；
- 新增完整 envelope 键集断言：`{status, blocking_error, quality_flags, business_flags, field_details, values, bid_rounded_cents, formula_version, decimal_precision, rounding_mode}`，并断言 values/bid 为 None。

## 五、R66-4：全入口拒绝 NaN/±Infinity

- `_to_decimal()` 增加 `is_finite()` 校验：Decimal 与字符串形式的 `NaN / Infinity / -Infinity` 统一抛 `CIDError`（不再出现"异常 vs blocking envelope"两种不同结果）；
- `canonical()` / `quantize_ratio()` / `quantize_numeric18_6()` 复用 `_to_decimal`，同样拒绝；
- 覆盖：必需字段、L、4 个费率（tech_lo=Infinity 等）各自 Decimal/str 形式；float 输入拒绝仍为 CIDError。

## 六、验证证据（全部实测，退出码 0）

```text
cd project && python scripts/assert_cid_engine.py
  -> 64 条 [PASS]（黄金 10 串 + canonical 不变量 + envelope 用例 + R66 新用例），T5-CID-ASSERT: PASS
cd backend && python -m pytest tests/test_cid_engine.py -q
  -> 48 passed
```

回归保持：
```text
黄金 10 项完整串等值（含 S 末位 ...947）、bid=1525           PASS
canonical 六规则 + compact vs DB scale 全串相等            PASS
envelope：L/必需/rebate 两态/S≤0/M/O/U/.5 分边界          PASS
T1~T4 终态：revision=17trg000001、31 表、17 trigger 未动    PASS
未新增 migration、未进入 T6
```

计数口径：round-65 为 42 CLI / 26 pytest；round-67 实测 **64 CLI / 48 pytest**（新增 R66-1 8 项、R66-2 4 项、R66-3 2 项、R66-4 8 项）。

## 七、交付物与哈希

| 文件 | SHA-256 | 变更 |
|---|---|---|
| `backend/domain/cid.py` | `498AA86B025AC7EE3B5DFDC6274659D961CF7BC9C1DF5ABF31B53E540EA0A699` | 新增 adapter×3 + _quantize 冻结/范围 + is_finite |
| `backend/tests/test_cid_engine.py` | `4072BF432C36BF5CA42B693CC47752850AB0BCF988661201EA3BF261132ADD1D` | R66 用例 + P_ZERO 可达 + 非有限拒绝 |
| `project/scripts/assert_cid_engine.py` | `7C08583A08330A07772BF95D4438F1C20300F96E4F80AD3513DF89454374127E` | 同步 R66 用例 + 完整 envelope 键集 |

（`backend/domain/__init__.py` 未变；T1~T4 文件哈希不变。）

## 八、给 Codex 的最小终验点

1. 重放 R66-3 可达输入，只接受 P_ZERO，完整 envelope 键集；
2. 复核 R66-2 ambient context 污染（prec=6 / ROUND_DOWN）与 numeric(12,6) 范围边界；
3. 复核 R66-4 全入口 NaN/±Infinity 拒绝（Decimal 与 str、L 与费率）；
4. 复核 R66-1 三 adapter 的字段 exact-set 与 numeric scale 投影；
5. 双通道独立执行（64 CLI / 48 pytest），确认黄金 10 串与 T1~T4 终态保持；
6. 确认未进入 T6。

闭合后请标记 **T5 COMPLETE**，按 P0-1 DAG 授权进入 **T6（secret_store）**。

---

<!--RELAY: 请 CDX 读取本文件并继续，当前轮次 round-67-->
