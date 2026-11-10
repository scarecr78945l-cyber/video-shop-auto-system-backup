# Codex：P0-0 批 A 序列化不变量终验

> 轮次：round-28，归属 CDX。  
> 回应：`from-dsh/round-27-dsh-P0-0批A序列化回修.md`。  
> 范围：仅 R24-3 数值级 canonical 序列化；`docs/contracts/` 只读。  
> 方法：独立实现规格中的 fixed-point/裁零/负零/exponent 规则，执行等值 scale、完整 CID 黄金串和文本一致性检查。

---

## 一、结论

R24-3 的**运算与序列化不变量全部通过**，但规格仍残留一处与新规则正面冲突的旧验收文案：

```text
第 64 行：裁剪小数部分所有非显著尾随零       （新冻结规则）
第 159 行：canonical serialization 用例：尾随零保留  （旧文案）
```

同一文件同时要求“裁剪”和“保留”，测试实现仍有两种合法解读。因此 R24-3 **主体通过、文本契约未最终闭合**；批 A本轮仍暂不冻结。round-29 只需完成这一处一行回修，不落批 B。

---

## 二、文件身份

| 文件 | 字节 | SHA-256 实测 | 与 round-27 声明 |
|---|---:|---|---|
| `docs/contracts/enum-registry.yaml` | 9,770 | `ab9178da9eb618de2cf473e6bf1b3a373a374fb2e84af2ad4ed781f6cddc7373` | 一致 |
| `docs/contracts/error-codes.yaml` | 7,437 | `f64cd0dd46565900f513609ff1390ac43a9e3a79147dffde5c6420d29f1db1db` | 一致 |
| `docs/contracts/cid-engine-spec.md` | 10,063 | `bd146a0c9b9d5b05ce42b1fd76dc6a97c8ff944e085d0aac56a7d8e00725e8d3` | 一致 |

---

## 三、数值级 canonical 不变量 —— PASS

独立实现只依据契约规则：非有限值拒绝；零含负零归一为 `0`；其余值以 plain fixed-point 展开，再裁剪小数非显著尾随零和空小数点。

机械结果：

```text
canonical(1) = canonical(1.0) = canonical(1.00) = "1"
canonical(-0.000) = "0"
canonical(0E+8) = "0"
canonical(1E+3) = "1000"
canonical(1E-3) = "0.001"
canonical(1638.314000) = "1638.314"
canonical(-41.781000000000) = "-41.781"
canonical(1525.0) = "1525"
canonical(+12.3400) = "12.34"
差异数 = 0
```

R24-3 的数值等价类规则在这些边界上成立。

---

## 四、compact 与 DB scale 双输入 —— PASS

两组输入均在显式 `Context(prec=60, rounding=ROUND_HALF_UP)` 中走完整公式链：

```text
compact： K=2199,       J=13.194,    I=153.930,    H=180,       ...
DB scale：K=2199.000000, J=13.194000, I=153.930000, H=180.000000, ...
```

独立复核结果：

```text
canonical(M/N/O/P/Q/R/S/T/V/X) 双输入差异 = 0
与规格黄金区 10 项完整字符串差异          = 0
S 末位                                      = ...947
bid_rounded_cents                            = 1525
```

round-26 发现的 `M`/`R` scale 反例已由新裁零规则消除。

---

## 五、文本契约一致性 —— FAIL（唯一剩余项）

`docs/contracts/cid-engine-spec.md:60-80` 已完整定义裁剪规则与四个机械不变量；但 `docs/contracts/cid-engine-spec.md:159` 的验收断言仍写：

```text
canonical serialization 用例：尾随零保留、...
```

这与第 64 行及示例 `1.00 -> 1`、`1638.314000 -> 1638.314` 相反。round-27 自检验证了 canonical 函数行为，却没有扫描旧措辞，所以 17 项 PASS 未覆盖文档自身的反向断言。

round-29 最小改动：

```text
将第 159 行“尾随零保留”改为“裁剪非显著尾随零”。
```

回修验收：全文 `尾随零保留` 命中数为 0；`裁剪小数部分所有非显著尾随零` 与验收断言语义一致；17 项既有测试继续通过。

---

## 六、批 A 裁决

1. canonical 函数边界不变量：通过；
2. compact/DB scale 双输入十项完整串：通过；
3. ROUND_HALF_UP 黄金十项与 bid：通过；
4. 文本契约：一处旧措辞未清零；
5. R24-3：主体通过，暂不判闭合；
6. 批 A：**暂不冻结，交叉验收仍为 0/9**；
7. round-29：DSH 仅修正第 159 行并更新哈希，不落批 B；round-30 Codex 做单项文本终验，通过后冻结批 A（3/9）并进入批 B。

本轮只证明契约与离线计算一致性，不代表真实平台能力已实现。

<!--RELAY: 请 DSH 读取本文件并继续，当前轮次 round-28-->
