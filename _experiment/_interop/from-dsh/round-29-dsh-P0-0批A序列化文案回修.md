# DSH：P0-0 批 A 序列化文案回修（round-29 回应）

> 轮次：round-29，归属 DSH。
> 回应：`from-cdx/round-28-cdx-P0-0批A序列化终验.md`（唯一剩余：第 159 行旧文案「尾随零保留」与裁剪规则冲突）。
> 交付：`cid-engine-spec.md` 第 159 行一行回修；全文旧措辞命中 0；既有 17 项自检保持 PASS。
> 状态：批 A 已落盘 3/9；本轮只做一行文本回修，不落批 B，不写 backend/frontend/migration 实现。

---

## 一、round-28 阻断处置

**round-28 结论**：canonical 数值不变量（9 例全过）、compact/DB scale 双输入十项完整串（差异=0）、ROUND_HALF_UP 黄金十项与 bid=1525（全部通过）；唯一剩余是文档自身验收断言残留旧措辞。

**round-29 一行回修**：
- `docs/contracts/cid-engine-spec.md` 第 159 行：
  - 旧：`canonical serialization 用例：尾随零保留、exponent 禁止、负零→"0"、整数无小数点、分隔符/千分位规则；`
  - 新：`canonical serialization 用例：裁剪非显著尾随零、exponent 禁止、负零→"0"、整数无小数点、分隔符/千分位规则；`
- 与第 64 行（`裁剪小数部分所有非显著尾随零`）和 §三 2.1 机械不变量（`1.00→"1"`、`1638.314000→"1638.314"`）语义统一。

## 二、回修验收

| 验收项 | 结果 |
|---|---|
| 全文 `尾随零保留` 命中数 | ✅ 0 |
| `裁剪小数部分所有非显著尾随零` 与验收断言语义一致 | ✅ 一致 |
| 既有 17 项自检（`selfcheck_batch_a4.py`） | ✅ SELF-CHECK: PASS |

## 三、批 A 契约哈希（round-29）

| 文件 | 字节 | SHA-256 | 变化 |
|---|---|---|---|
| `docs/contracts/enum-registry.yaml` | 9,770 | `ab9178da9eb618de2cf473e6bf1b3a373a374fb2e84af2ad4ed781f6cddc7373` | 未变 |
| `docs/contracts/error-codes.yaml` | 7,437 | `f64cd0dd46565900f513609ff1390ac43a9e3a79147dffde5c6420d29f1db1db` | 未变 |
| `docs/contracts/cid-engine-spec.md` | 10,072 | `6dd50e8fb1ca9d0f045e2bc130b5666ec3fe825bc2f4b7822ccb7be70916ac18` | 第 159 行文案 |

## 四、请 Codex 在 round-30 产出的内容

1. **单项文本终验**：核对 `cid-engine-spec.md` 第 159 行已改为「裁剪非显著尾随零」、全文旧措辞命中 0、与第 64 行/机械不变量语义一致；
2. **结论**：通过 → **冻结批 A（3/9）→ round-31 DSH 落批 B**（ddl-order/index-registry/test-strategy）；有阻断 → 列剩余清单。

## 五、输出要求

- 终验意见写 `from-cdx/round-30-cdx-P0-0批A冻结确认.md`（UTF-8 无 BOM，中文）。
- 结构：第 159 行核对 → 全文旧措辞扫描 → 批 A 冻结确认 → 批 B 落盘授权。
- 对 `docs/contracts/` 只读，不修改；不写实现代码；不把 fixtures 当真实能力；无法确证处标「未确认」。

<!--RELAY: 请 CDX 读取本文件并继续，当前轮次 round-29-->