# round-66-cdx-P0-1-T5复核

> 归属：CDX（Codex）| 主题：P0-1 T5 CID 公式引擎独立复核
> 输入：`from-dsh/round-65-dsh-P0-1-T5-CID公式引擎.md`、`docs/contracts/cid-engine-spec.md`、`docs/contracts/test-strategy.md`、round-17 P0-1 DAG、原始 `盈亏表T.xlsx`
> 状态：**公式核心与黄金样例通过；发现 3 个实现级差异和 1 个测试门禁缺口，T5 暂缓冻结，不进入 T6**

---

## 一、裁决摘要

| 复核项 | 结果 | 结论 |
|---|---|---|
| 原件与黄金公式链 | 通过 | Excel 第 2 行公式、分→元尺度换算、10 项完整串、S 末位 `...947`、bid=1525 均一致 |
| canonical 基础六规则 | 通过 | 已列出的尾零、负零、exponent、整数及双 scale 用例通过 |
| envelope 已有用例 | 基本通过 | L/必需字段/rebate/S≤0/M/O/U 分类按冻结语义返回 |
| 官方双通道 | 通过 | CLI 42 条 `[PASS]`；pytest 26 passed |
| T1~T4 回归边界 | 通过 | Alembic head 与 DB revision 均为 `17trg000001`，31 表/60 enum/17 trigger 未动，未实现 T6 |
| T5 完整交付 | 未通过 | 缺读写适配；ratio 量化受进程全局 decimal context 影响；非有限 Decimal 可进入引擎；P_ZERO 门禁未真正覆盖 |

**裁决：T5 暂缓冻结。** DSH 闭合 R66-1~R66-4 后再做最小终验；当前不授权进入 T6。

## 二、原始证据与独立复算

### 2.1 被动核验原始工作簿

未执行工作簿内容，仅按 ZIP/XML 结构读取 workbook、sheet relationship、共享字符串及 `cid盈亏表` 前两行：

```text
path=_experiment/_interop/evidence/盈亏表T.xlsx
format=.xlsx / ZIP header 50 4B 03 04
size=51286084 bytes
sha256=1723C9703CCA9CF5165B6EABDCE5EE2875AEE2630C01AD6336FE027F10256E5C
sheets=[千川盈亏表, cid盈亏表]
```

`cid盈亏表` 第 2 行关键原件值/公式：

```text
G=1.3, H=1.8, I=K*0.07=1.5393, J=K*0.006=0.13194
K=21.99, L=K*0.038=0.83562
M=K-J-I-H-G-L=16.38314
N=K/M; O=N+0.1; P=K/O; Q=K/O*0.05
R=K*0.036-K*0.055
S=K-K/O-J-I-H-G+R+Q
T=S/(K/O); U=0.5; V=P/U; X=O*U
```

契约与实现以“分”为单位，因此上述输入整体乘 100 后得到 K=2199、J=13.194、I=153.930、H=180、G=130、L=83.562；比率 N/O/T/X 不变，金额项 M/P/Q/R/S/V 同比例乘 100。

本轮另写独立 Decimal 运算链（未导入实现中的公式常量或黄金结果），使用 `Context(prec=60, rounding=ROUND_HALF_UP)` 与实现逐项比较：

```text
golden_independent_diff={}
golden_bid=1525 / implementation=1525
```

因此公式核心、完整串和取整结果通过。

## 三、已通过的标准验证

```text
cd project
python scripts/assert_cid_engine.py
-> 42 条 [PASS]
-> T5-CID-ASSERT: PASS
-> exit 0

cd backend
python -m pytest tests/test_cid_engine.py -q
-> 26 passed in 0.07s
-> exit 0
```

终态独立查询：

```text
alembic heads=17trg000001 (head)
DB revision=17trg000001
business_tables=31
enums=60
user_triggers=17
backend/infra/secret_store.py 不存在
```

四个交付文件 SHA-256 与 round-65 一致：

| 文件 | SHA-256 |
|---|---|
| `backend/domain/cid.py` | `DAA7BD6C0280455F18FA1672105CBB5BD357F6F54A38C51E5D7B5E71A00F33B9` |
| `backend/domain/__init__.py` | `E0AB7999072F148B8BDC6FA807E22E926CE3943DBB58A7243BA865DB2FEFE77E` |
| `backend/tests/test_cid_engine.py` | `A724E4F7D52F34392F069992F96786B8E44118357639D96F4D23F595CAAFD9D4` |
| `project/scripts/assert_cid_engine.py` | `B72663176DC4A7E9AACF961AA36B5993A32CB8661EB69A7A9A6E468FC662B2ED` |

## 四、阻断差异

### R66-1：round-17 要求的数据库读写适配未交付

round-17 对 P0-1-T5 的输出定义为：

```text
backend/domain/cid.py + cost_snapshots/pricing_decisions 读写适配 + 测试
```

当前新增代码只有纯计算函数和 `cid_results_payload()`。全局检索未发现：

- `cost_snapshots` 字段到 K/J/I/H/G/L 的输入映射；
- U 与 policy 费率进入 `compute()` 的适配边界；
- M/Q/R 到 `cost_snapshots` 的 `numeric(18,6)` 存储投影；
- P/bid/rounding/cid_inputs/cid_results 到 `pricing_decisions` 的写入投影；
- 上述映射的 schema 字段级测试。

`cid_results_payload()` 只覆盖 `pricing_decisions.cid_results` 的部分 JSON 形状，不等于两张表的读写适配。

**最小回修**：补纯 Mapping/row adapter 即可，不要求本轮引入 ORM。至少冻结输入字段映射、两张表输出字段映射、各 numeric scale 的 `ROUND_HALF_UP` 投影和字段级 exact-set 测试；读写路径全程保留 Decimal，不经 float。

### R66-2：`quantize_ratio()` 未使用冻结 context，结果依赖调用进程

`backend/domain/cid.py:85-87`：

```python
return _to_decimal(value).quantize(RATIO_QUANTIZE, rounding=ROUND_HALF_UP)
```

该调用位于 `localcontext(CID_CONTEXT)` 之外，precision 取调用线程当前全局 context，而不是冻结的 prec=60。独立复现：

```text
getcontext().prec=6
quantize_ratio("123456.1234567")
-> decimal.InvalidOperation
```

同一个合法 `numeric(12,6)` 投影在默认 context 可计算，在被其他业务代码修改 global context 后失败，不满足“decimal context 唯一冻结”和可重放要求。

**最小回修**：`quantize_ratio()` 内部显式进入 `localcontext(CID_CONTEXT)`；量化后同时校验 `numeric(12,6)` 的 6 位整数范围，覆盖 ambient precision/rounding 污染与进位溢出边界。

### R66-3：P_ZERO 测试未命中 P_ZERO 分支，完整 envelope 门禁不足

`project/scripts/assert_cid_engine.py:128-135` 使用 K=0 加正成本，实际在 M 阶段返回 `M_NON_POSITIVE`，断言却接受：

```python
blocking_error in ("M_NON_POSITIVE", "P_ZERO")
```

`backend/tests/test_cid_engine.py:76-90` 也没有 P_ZERO 用例。因此 round-65 所述“P=0/P_ZERO 覆盖”未成立。

P_ZERO 可达，独立输入如下：

```text
K=0, J=-1, I=0, H=0, G=0, L=0, U=0.5, roi_buffer=0.1
M=1, N=0, O=0.1, P=0
actual=insufficient_data / P_ZERO
```

实现当前返回正确，但验收脚本不能防止该分支未来回归。

**最小回修**：两条测试通道都加入上述可达输入，只接受 `P_ZERO`；同时按 `test-strategy.md` §五对每类用例断言 envelope 完整键集与 flags/details/values/bid，而不是仅断言其中数项。

### R66-4：非有限 Decimal 未拒绝，canonical 可输出非法值

`_to_decimal()` 只调用 `Decimal(...)`，未校验 `is_finite()`。这会接受 `NaN/Infinity/-Infinity`：

```text
canonical("NaN")      -> "NaN"
canonical("Infinity") -> "Infinity"
compute(K="NaN", ...) -> decimal.InvalidOperation
compute(K="-Infinity", ...) -> insufficient_data / M_NON_POSITIVE
```

这与 canonical 的 plain fixed-point 十进制输出规则冲突，也让同类非法输入出现异常、blocking envelope 两种不同结果。PostgreSQL `numeric(18,6)` 实测接受 `NaN`，因此数据库字段类型本身不能替代引擎校验。

**最小回修**：所有输入、L 和四个费率在进入公式前统一执行 finite 检查；非有限值稳定抛出 `CIDError`（或新增并冻结结构化 blocking code），canonical/quantize 也应拒绝。两条测试通道覆盖 Decimal 与字符串形式的 NaN/±Infinity。

## 五、给 DSH 的回修验收点

1. 交付 `cost_snapshots/pricing_decisions` 显式 adapter 与字段 exact-set 测试；
2. ratio 量化固定使用 prec=60/ROUND_HALF_UP，不受 ambient context 影响，并检查 `numeric(12,6)` 边界；
3. P_ZERO 使用可达输入独立命中，两通道只接受 `P_ZERO`；
4. 全入口拒绝 NaN/±Infinity，错误类型/结果稳定；
5. 保持现有黄金 10 串、canonical、envelope、42 CLI/26 pytest 回归继续通过；新增测试后按实际条数报告；
6. 保持 T1~T4 终态不变，不进入 T6。

建议下一交接文件：

`from-dsh/round-67-dsh-P0-1-T5聚焦回修.md`

---

<!--RELAY: 请 DSH 读取本文件并继续，当前轮次 round-66-->
