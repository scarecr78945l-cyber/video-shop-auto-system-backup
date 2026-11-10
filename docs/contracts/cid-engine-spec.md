# cid-engine-spec.md — P0-0 批 A 契约：CID 公式引擎规格

> 来源：`_experiment/_interop/evidence/盈亏表T.xlsx` 的 `cid盈亏表`（SHA-256 `1723C9703CCA9CF5165B6EABDCE5EE2875AEE2630C01AD6336FE027F10256E5C`，仅采用 `cid盈亏表`，不采用 `千川盈亏表`）。
> 冻结：round-16（v6 §7）+ round-19（精度/取整裁决）+ round-18 §4（Codex 高精度独立复算，差异=0）。
> 验收：用第 2 行输入复算，结果与原件一致；错误分类结构化；量化不回流。

---

## 一、输入与单位

| 字母 | 业务名 | 单位/类型 | 说明 |
|---|---|---|---|
| K | 客单价 | numeric(18,6) 分 | 输入，保留小数分 |
| J | 微信小店技术服务费 | numeric(18,6) 分 | 输入 |
| I | 退货预留 | numeric(18,6) 分 | 输入 |
| H | 运费 | numeric(18,6) 分 | 输入 |
| G | 产品成本 | numeric(18,6) 分 | 输入 |
| L | 电商税 | numeric(18,6) 分 | 输入；缺失按 0 处理但标记 `FIELD_DEFAULTED(field=L)`（可计算不静默） |
| U | 回传数 feedback_coefficient | numeric(8,4) | 输入（样本 0.4/0.5）；非订单数 |

**费率参数（版本化，policy_versions cid_breakeven v5）**：
- `roi_buffer` 默认 +0.1（样本含 0.1/0.2/0.3/0.45，店铺/商品策略覆盖）；
- `consumption_rebate_rate` 默认 0.05（样本含 0.05 与 0；**空白区分「无返点（费率=0）」与「来源缺失」**）；
- `tech_hi` / `tech_lo` 默认 0.036 / 0.055（版本化保存两个构成费率，不合并）。

---

## 二、公式（原件一致）

```
M = K − J − I − H − G − L
N = K / M
O = N + roi_buffer
P = K / O
Q = P × consumption_rebate_rate
R = K × tech_hi − K × tech_lo        # 可为负
S = K − P − J − I − H − G + R + Q    # 原件不减 L
T = S / P
V = P / U
X = O × U
bid_rounded_cents = ROUND_HALF_UP(P) # 平台提交价（分）
```

> W（溢价）、Y（消耗）不在核心链，标扩展/未确认，不纳入计算。

---

## 三、精度与取整规则（冻结）

1. **输入持久化**：K/J/I/H/G/L 以 `numeric(18,6)` 分保存（保留 Excel 小数分，如 J=13.194、I=153.930、L=83.562），**入库不得按分四舍五入**；
2. **decimal context 唯一冻结（round-23 A5 裁决）**：
   ```text
   decimal_context.precision = 60
   decimal_context.rounding  = ROUND_HALF_UP
   输入      = 十进制字符串 / DB Decimal（不经 binary float）
   中间值    = 同一 context 一次计算；后续项不得读取已量化的中间投影
   cid_results = 按固定键序保存规范十进制字符串
   ```
   > 精度固定为唯一的 `precision=60`（不接受"位数下限"式写法），保证两个合规实现输出逐字符一致，审计 diff / 内容 hash / 重放可复现。
2.1 **canonical decimal serialization（round-25 R24-3 冻结 + round-27 R24-3 数值级回修）**：
   ```text
   规则（数值等价类唯一——Decimal context 只管 precision/rounding，不负责统一 scale）：
   1. 按 plain fixed-point 输出（禁 exponent / 科学计数法 / 前导正号 / 千分位 / 空白）；
   2. 裁剪小数部分所有非显著尾随零（Decimal("1.00") → "1"，Decimal("1638.314000") → "1638.314"）；
   3. 裁剪后小数部分为空则同时移除小数点（Decimal("1525.0") → "1525"）；
   4. 数值为零（含负零）统一输出 "0"（Decimal("-0.000") → "0"）；
   5. exponent 输入先展开为 fixed-point（Decimal("1E+3") → "1000"）；
   6. 整数无小数点；小数至少一位小数位。
   示例 = "1638.314"（M）、"-41.781"（R）、"0.721116770045302670916564223952184990178927848995980013599345"（X）
   ```
   > 两个合规实现必须对同一**数值**输入输出逐字符相同的规范字符串——无论输入 scale 是 compact（K=2199）还是 DB 字段尺度（K=2199.000000），结果串必须一致；比较使用完整字符串等值（非前缀匹配）。
   >
   > **机械验收不变量（round-27 新增，P0-1 引擎必须通过）**：
   ```text
   canonical(Decimal("1")) == canonical(Decimal("1.0")) == canonical(Decimal("1.00")) == "1"
   canonical(Decimal("-0.000")) == "0"
   canonical(Decimal("1E+3")) == "1000"
   compact 输入（K=2199, J=13.194, ...）结果串
     == numeric(18,6)/numeric(8,4) 尺度输入（K=2199.000000, J=13.194000, ...）结果串
   ```
3. **持久化**：`pricing_decisions.cid_results` 保存 M/N/O/P/Q/R/S/T/V/X **未取整规范十进制字符串** + 公式版本 + decimal_precision=60 + rounding_mode；`bid_rounded_cents bigint` 为平台提交价实体列；`cost_snapshots` 保存输入与中间 M/Q/R（numeric(18,6)）；
4. **比率**：N/O/T/X 持久化量化 `numeric(12,6)`（仅存储投影，不回流参与计算）；
5. **取整**：`bid_rounded_cents` 明确 `ROUND_HALF_UP` 到整数分（避免语言默认 bankers rounding）；持久化量化统一 `ROUND_HALF_UP`，与 PostgreSQL numeric cast 行为做边界样例（.5 分）；
6. **除零防护**：`M=0`、`O=0`、`U<=0`、`P=0` → 不进入出价计算，返回 `blocking_error`（见 §四）；
7. **负毛利**：`M<=0` → blocking；`S<=0` → 已完成计算但带 `S_NON_POSITIVE` 业务标记（见 §四），由调用方决定人工闸门/退出上架，不是计算失败；
8. **空值**：`L` 缺失 → 默认 0 但 `FIELD_DEFAULTED(field=L)`；`Q/R` 的「无返点（费率=0）」与「来源缺失」分开（`REBATE_NOT_APPLICABLE` vs `REBATE_SOURCE_MISSING`）。

---

## 四、结果 envelope（round-23 A6 裁决：blocking / quality / business 分离）

引擎统一返回结构化 envelope，不再把数据质量标记与业务闸门混为"引擎错误"：

```text
status: calculated | insufficient_data | rejected
blocking_error: M_NON_POSITIVE | O_ZERO | U_NON_POSITIVE | P_ZERO | REQUIRED_FIELD_MISSING | null
quality_flags: [FIELD_DEFAULTED, REBATE_SOURCE_MISSING, ...]
business_flags: [REBATE_NOT_APPLICABLE, S_NON_POSITIVE, ...]
field_details: [{field, source_state, default_applied}]
values: M/N/O/P/Q/R/S/T/V/X（仅 calculated 时按规则给出）
bid_rounded_cents: integer | null
formula_version / decimal_precision / rounding_mode
```

**状态语义**：
| 状态 | 触发 |
|---|---|
| `calculated` | 计算完成（可含 quality/business 标记） |
| `insufficient_data` | 必需输入缺失或除零（blocking_error 非空） |
| `rejected` | 调用方按 business_flags 拒绝（如 S_NON_POSITIVE 转人工/退出上架） |

**错误/标记分类**：
| 类别 | 码 | 语义 |
|---|---|---|
| blocking | `M_NON_POSITIVE` | M ≤ 0（负毛利硬拒绝） |
| blocking | `O_ZERO` | O = 0 |
| blocking | `U_NON_POSITIVE` | U ≤ 0 |
| blocking | `P_ZERO` | P = 0 |
| blocking | `REQUIRED_FIELD_MISSING` | 必需 K/J/I/H/G/U 缺失，停止 |
| quality | `FIELD_DEFAULTED` | L 等缺失已用默认 0，可计算但不可静默 |
| quality | `REBATE_SOURCE_MISSING` | 返点来源缺失（费率/证据未知） |
| business | `REBATE_NOT_APPLICABLE` | 返点费率=0，正常业务状态，Q=0 继续计算 |
| business | `S_NON_POSITIVE` | 预估利润 ≤ 0，已完成计算，转业务闸门（人工/退出上架） |

> L 缺失 → 默认 0 + `FIELD_DEFAULTED(field=L)`，可计算但不可静默；必需字段缺失 → `REQUIRED_FIELD_MISSING` 停止；rebate 不适用 → Q=0 + `REBATE_NOT_APPLICABLE` 不是失败；rebate 来源缺失 → flag 显式，是否阻断由 policy 决定；S≤0 → 计算完成 + `S_NON_POSITIVE`，进入业务闸门。

---

## 五、黄金样例（Excel 第 2 行，验收基准）

**输入（按 v6 小数分）**：
```
K=2199, J=13.194, I=153.930, H=180, G=130, L=83.562, U=0.5
roi_buffer=0.1, consumption_rebate_rate=0.05, tech_hi=0.036, tech_lo=0.055
```

**高精度一次计算（显式 `Context(prec=60, rounding=ROUND_HALF_UP)`，与原件一致）**：
```
M = 1638.314
N = 1.34223354009060534183312844790436998035785569799196002719869
O = 1.44223354009060534183312844790436998035785569799196002719869
P = 1524.71838913263129988876904209077295993273155249248846108953
Q = 76.2359194566315649944384521045386479966365776246244230544765
R = -41.781
S = 231.612530324000265105669410013765688063905025132135961964947
T = 0.151905120299465930780868549195949287016521859444202856705946
V = 3049.43677826526259977753808418154591986546310498497692217906
X = 0.721116770045302670916564223952184990178927848995980013599345
bid_rounded_cents = 1525     # ROUND_HALF_UP(P)
```

> 注：S 末位为 `...947` 是显式 `ROUND_HALF_UP` 下的机械结果；`ROUND_HALF_EVEN` 会得到 `...946`。规格以 ROUND_HALF_UP 为准。

**验收断言**：
1. `M=1638.314`、`bid_rounded_cents=1525` 与原件一致；
2. `S` 明确不减 L（S=231.612530...，若减 L 则不同）；
3. N/O/T/X 量化 `numeric(12,6)` 后不回流参与后续计算；
4. 黄金结果在显式 `Context(prec=60, rounding=ROUND_HALF_UP)` 下**完整字符串等值**（非前缀匹配），两个合规实现输出相同规范字符串（含 S 末位 `...947`）；
5. canonical serialization 用例：裁剪非显著尾随零、exponent 禁止、负零→"0"、整数无小数点、分隔符/千分位规则；
6. 测试至少含：原件第 2 行、M=0、M<0、O=0、U=0/U<0、P=0、L 缺失（→FIELD_DEFAULTED）、必需字段缺失（→REQUIRED_FIELD_MISSING）、返点不适用（→REBATE_NOT_APPLICABLE）、返点来源缺失（→REBATE_SOURCE_MISSING）、S≤0（→S_NON_POSITIVE）、.5 分边界；每个用例断言完整 envelope（status/blocking_error/quality_flags/business_flags/values/bid）。

---

## 六、与 v6 §7 / round-18 §4 一致性

- 公式与 `15-数据字典.md` v6 §7 完全一致；
- 第 2 行高精度数值与 round-18 §4.2（Codex 独立复算）差异=0；
- round-24 修正：S 黄金值在显式 `ROUND_HALF_UP` 下末位 `...947`（round-18 文档未指定 rounding，round-25 起以本规格 ROUND_HALF_UP + canonical serialization 为唯一实现契约）；
- 本规格是 P0-1-T5（CID 公式引擎实现）的唯一输入契约。
