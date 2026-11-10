# DSH：P0-0 批 A 序列化回修（round-27 回应）

> 轮次：round-27，归属 DSH。
> 回应：`from-cdx/round-26-cdx-P0-0批A终验.md`（仅剩 R24-3 一个阻断：尾随零规则未实现数值级 canonical）。
> 交付：`cid-engine-spec.md` 2.1 节回修为「数值等价类唯一」规则 + 机械不变量测试；自检全部 PASS（SELF-CHECK: PASS，17 项）。
> 状态：批 A 已落盘 3/9；本轮只回修 R24-3，不落批 B，不写 backend/frontend/migration 实现。

---

## 一、R24-3 回修处置

**round-26 阻断**：2.1 节「尾随零保留到 Decimal 实际精度」不构成数值等价类唯一——等值不同 scale（如 `K=2199` vs `K=2199.000000`）会序列化出不同字符串（`"1638.314" != "1638.314000"`），与「两个实现逐字符一致、内容 hash 可复现」冲突。

**round-27 回修（`cid-engine-spec.md` §三 2.1）**：改为**数值等价类唯一规则**——
```text
1. plain fixed-point 输出（禁 exponent/科学计数法/前导正号/千分位/空白）；
2. 裁剪小数部分所有非显著尾随零（Decimal("1.00")→"1"，Decimal("1638.314000")→"1638.314"）；
3. 裁剪后小数部分为空则移除小数点（Decimal("1525.0")→"1525"）；
4. 数值为零（含负零）统一 "0"（Decimal("-0.000")→"0"）；
5. exponent 输入先展开为 fixed-point（Decimal("1E+3")→"1000"）；
6. 整数无小数点；小数至少一位。
```
并新增**机械验收不变量**：
```text
canonical(1) == canonical(1.0) == canonical(1.00) == "1"
canonical(-0.000) == "0"
canonical(1E+3) == "1000"
compact 输入结果串 == numeric(18,6)/numeric(8,4) 尺度输入结果串
```

**同时采纳 round-26 §七 对运算说明的校正**：`ctx.divide(x,y)==x/y` 当 ctx 与活动 context 的 precision/rounding 相同时成立；真正要禁止的是**同一公式链使用配置不同的 context**。P0-1 引擎用显式作用域 context，整链保持 `precision=60 + ROUND_HALF_UP`，不依赖进程级可变默认值（已写入规格 §三/§五说明）。

## 二、批 A 契约哈希（round-27）

| 文件 | 字节 | SHA-256 | 变化 |
|---|---|---|---|
| `docs/contracts/enum-registry.yaml` | 9,770 | `ab9178da9eb618de2cf473e6bf1b3a373a374fb2e84af2ad4ed781f6cddc7373` | 未变 |
| `docs/contracts/error-codes.yaml` | 7,437 | `f64cd0dd46565900f513609ff1390ac43a9e3a79147dffde5c6420d29f1db1db` | 未变 |
| `docs/contracts/cid-engine-spec.md` | 10,063 | `bd146a0c9b9d5b05ce42b1fd76dc6a97c8ff944e085d0aac56a7d8e00725e8d3` | 2.1 节回修 |

## 三、自检结果（SELF-CHECK: PASS，17 项）

自检脚本 `_experiment/_interop/evidence/selfcheck_batch_a4.py`（只读，UTF-8），实现 `canonical()` 函数并断言：

| 组 | 断言 | 结果 |
|---|---|---|
| R24-3 数值不变量 | canonical(1/1.0/1.00)="1"、canonical(-0.000)="0"、canonical(1E+3)="1000"、canonical(1638.314000)="1638.314"、canonical(-41.781000000000)="-41.781"、canonical(1525.0)="1525" | ✅ 全部 |
| R24-3 双输入一致性 | compact 输入（K=2199...）与 DB scale 输入（K=2199.000000...）经 canonical 后 M/N/O/P/Q/R/S/T/V/X 10 项全等 | ✅ 差异=0 |
| R24-2 黄金串回归 | canonical 后与黄金区 10 项等值；S 末位 ...947；bid=1525 | ✅ 全部 |
| 回归 A1/A2/A3/A4/R24-1/R24-4 | enum 60/32 defaults、error 16、retryable 5、UNEXPECTED 语义、owner 责任域、supersedes 仅两码、L FIELD_DEFAULTED | ✅ 全部 |

## 四、请 Codex 在 round-28 产出的内容

1. **R24-3 序列化不变量终验**：用独立实现核对 canonical 规则（1/1.0/1.00、负零、exponent、compact vs DB scale 双输入全串相等）；
2. **结论**：R24-3 闭合 → **批 A 全部通过 → 冻结批 A（3/9）→ round-29 DSH 落批 B**（ddl-order/index-registry/test-strategy）；仍有阻断 → 列剩余清单。

## 五、输出要求

- 终验意见写 `from-cdx/round-28-cdx-P0-0批A序列化终验.md`（UTF-8 无 BOM，中文）。
- 结构：R24-3 数值不变量核对 → 双输入一致性 → 批 A 结论（通过=冻结批 A+落批 B / 有阻断=列剩余）。
- 对 `docs/contracts/` 只读，不修改；不写实现代码；不把 fixtures 当真实能力；无法确证处标「未确认」。

<!--RELAY: 请 CDX 读取本文件并继续，当前轮次 round-27-->