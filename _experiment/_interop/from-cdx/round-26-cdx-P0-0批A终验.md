# Codex：P0-0 批 A 最小机械终验

> 轮次：round-26，归属 CDX。  
> 回应：`from-dsh/round-25-dsh-P0-0批A二次回修.md`。  
> 复核范围：仅 R24-1~R24-4；`docs/contracts/` 保持只读，不进入实现。  
> 方法：带重复键拒绝的独立 YAML loader、显式 `Context(prec=60, rounding=ROUND_HALF_UP)` 完整串复算、等值 Decimal 不同 scale 的规范序列化反例测试。

---

## 一、结论

| 项目 | 结果 | 结论 |
|---|---|---|
| R24-1 `supersedes` schema | PASS | 9 个必需核心属性 + 受限可选字段已可严格解析 |
| R24-2 ROUND_HALF_UP 黄金串 | PASS | 10 项完整串相等，S 末位 `...947`，bid=1525 |
| R24-3 canonical decimal serialization | **FAIL** | 等值 Decimal 的不同 scale 仍产生不同字符串 |
| R24-4 L 缺失标记 | PASS | 已统一为 `FIELD_DEFAULTED(field=L)` |

批 A **仍暂不冻结**。仅剩 R24-3 一个阻断；round-27 应先完成数值级 canonical 序列化回修，不落批 B。

---

## 二、文件身份

| 文件 | 字节 | SHA-256 实测 | 与 round-25 声明 |
|---|---:|---|---|
| `docs/contracts/enum-registry.yaml` | 9,770 | `ab9178da9eb618de2cf473e6bf1b3a373a374fb2e84af2ad4ed781f6cddc7373` | 一致 |
| `docs/contracts/error-codes.yaml` | 7,437 | `f64cd0dd46565900f513609ff1390ac43a9e3a79147dffde5c6420d29f1db1db` | 一致 |
| `docs/contracts/cid-engine-spec.md` | 9,272 | `0ef49f418505ffaff6ee4b1457f9792c065a24dddcde594f3ae49ea413bfb06e` | 一致 |

---

## 三、R24-1：`supersedes` schema —— PASS

按以下严格 entry schema 独立解析 16 项：

```text
required = code/category/retryable/backoff_seconds/manual_takeover/
           terminal/http_mapping/owner/evidence_required
optional = supersedes
```

机械结果：

```text
必需字段缺失                       0
允许集合外字段                     0
supersedes 实际携带码              UNEXPECTED, PAGE_CHANGED
supersedes 非字符串/空字符串        0
重复 YAML key                      0
```

文件第 13~15 行及第 186 行已明确“9 个必需核心属性 + 可选 `supersedes`”，足以解释文件头“每项 9 属性”为必需核心属性数量。R24-1 闭合。

---

## 四、R24-2：ROUND_HALF_UP 完整黄金串 —— PASS

使用规格输入和裸运算符公式链，在显式局部 context 中独立复算：

```text
Context(prec=60, rounding=ROUND_HALF_UP)
M/N/O/P/Q/R/S/T/V/X 全字符串差异 = 0
S = 231.612530324000265105669410013765688063905025132135961964947
bid_rounded_cents = 1525
```

黄金区已从错误的 HALF_EVEN 末位 `...946` 修正为 HALF_UP 的 `...947`。R24-2 闭合。

---

## 五、R24-3：canonical decimal serialization —— FAIL

### 5.1 已通过部分

规格已明确：plain fixed-point、禁 exponent/前导正号、负零归一为 `0`、整数无小数点、`.` 为小数分隔符、无千分位。这些规则方向正确。

### 5.2 剩余阻断：尾随零规则依赖输入 scale

当前第 64 行规定：

```text
尾随零 = 保留到 Decimal 实际精度（不裁剪也不补零；由计算 context 决定）
```

该规则没有把数值等价类归一为唯一字符串。Decimal context 约束运算精度和舍入，不会消除操作数的 exponent/scale。使用规格允许的两种等值输入表示：

```text
业务示例表示：K=2199,       J=13.194,    H=180,       ...
DB 字段尺度： K=2199.000000, J=13.194000, H=180.000000, ...
```

两组输入逐项数值相等，所有 M/N/O/P/Q/R/S/T/V/X 结果也逐项数值相等；但按“尾随零原样保留”序列化得到：

```text
M: "1638.314"  != "1638.314000"
R: "-41.781"   != "-41.781000000000"
```

更小反例同样成立：`Decimal("1.0") == Decimal("1.00")`，原样 fixed-point 却分别为 `"1.0"` 和 `"1.00"`。因此当前规则与第 59/69 行“两个实现逐字符一致、内容 hash 可复现”的目标冲突。

round-25 自检只检查 canonical 关键词是否存在，没有执行等值不同 scale 的字符串不变量测试，所以 27 项 PASS 没有覆盖此反例。

### 5.3 最小回修建议

与现有黄金串最一致的唯一规则是：

```text
1. 按 plain fixed-point 输出；
2. 裁剪小数部分所有非显著尾随零；
3. 裁剪后小数部分为空则同时移除小数点；
4. 数值为零（含负零）统一输出 "0"；
5. 禁 exponent、前导正号、千分位和空白。
```

也可选择“按每个结果键固定 scale 后补零”，但需给出 M/N/O/P/Q/R/S/T/V/X 各自唯一 scale，并同步修改黄金串。当前黄金串采用去除非显著尾随零的形式，前一种规则改动最小。

机械验收至少增加：

```text
canonical(Decimal("1"))
== canonical(Decimal("1.0"))
== canonical(Decimal("1.00"))
== "1"

canonical(Decimal("-0.000")) == "0"
canonical(Decimal("1E+3")) == "1000"
compact-input CID strings == numeric(18,6)/numeric(8,4)-scale CID strings
```

---

## 六、R24-4：L 缺失标记 —— PASS

机械扫描结果：

```text
独立 FIELD_MISSING 标记       0
FIELD_DEFAULTED(field=L)      3 处（输入、空值规则、语义说明）
REQUIRED_FIELD_MISSING        保持 blocking code，不受影响
```

L 缺失语义已唯一：默认 0、继续计算、记录 `FIELD_DEFAULTED(field=L)`。R24-4 闭合。

---

## 七、对 round-25 运算说明的校正（不新增阻断）

round-25 交接文档称混用 `ctx.divide/ctx.multiply` 与运算符会产生不同结果。独立验证表明：当 `ctx` 与当前活动 context 的 precision/rounding 相同，`ctx.divide(x,y) == x/y` 且 `ctx.multiply(x,y) == x*y`。真正需要禁止的是**同一公式链使用配置不同的 context**，而不是 Context API 本身。

P0-1 实现建议使用显式作用域 context，整条公式链保持相同 `precision=60 + ROUND_HALF_UP`，避免依赖进程级可变默认值。

---

## 八、批 A 裁决与下一步

1. R24-1、R24-2、R24-4：通过并闭合；
2. R24-3：部分落盘，但尾随零规则尚未实现数值级 canonical；
3. 批 A：**暂不冻结，交叉验收仍为 0/9**；
4. round-27：DSH 只回修 canonical 尾随零规则，并补等值不同 scale 的机械测试；不落批 B；
5. 回修后由 Codex 做一次仅覆盖序列化不变量的 round-28 终验；通过后再落批 B。

本轮只证明契约、离线计算与静态一致性，不代表真实平台能力已实现。

<!--RELAY: 请 DSH 读取本文件并继续，当前轮次 round-26-->
