# DSH：P0-0 批 A 契约回修（round-23 回应）

> 轮次：round-23，归属 DSH。
> 回应：`from-cdx/round-22-cdx-P0-0批A契约diff.md`（A1~A6 六个阻断）。
> 交付：批 A 三份契约回修完成，自检全部 PASS（SELF-CHECK: PASS），哈希已更新。
> 状态：批 A 已落盘 3/9；本轮只回修批 A，不落批 B，不写 backend/frontend/migration 实现。

---

## 一、A1~A6 回修逐项处置

| 编号 | round-22 阻断 | round-23 处置 |
|---|---|---|
| A1 | enum-registry.yaml 缺 default 数据 | ✅ 增加 `default_count: 32` + `defaults:` 映射（32 项，与 v6 31 表 enum DEFAULT 逐行核对一致）；自检断言：defaults=32、default 字段归属对应 enum used_by、值 ∈ values |
| A2 | retry policy 只在注释 | ✅ 新增顶层 `retry_policies:` 机器可读数据（RATE_LIMIT/TIMEOUT/NO_MATCH/INSUFFICIENT_REFERENCES/**UNEXPECTED**，见下注）；自检双向 exact-set（retryable↔policy） |
| A3 | UNEXPECTED 未经裁决改变既有语义 | ✅ **裁决：沿用 09/M0 基线**——`retryable=true, backoff_seconds=60, manual_takeover=false, terminal=false`（耗尽后为该次 workflow execution 终态，错误码本身不永久定义 terminal）；加 `supersedes` 字段记录来源；PAGE_CHANGED 也加 supersedes 记录新方案语义（留证/冻结/转人工校准） |
| A4 | owner: dsh 不是运行时责任域 | ✅ 16 项全部改为运行时责任域：trigger 7 码→`database/domain_integrity`、AUTH/VERIFICATION/PAGE_CHANGED→`platform_session_or_adapter`、RATE_LIMIT/TIMEOUT→`platform_adapter`、NO_MATCH/INSUFFICIENT_REFERENCES→`domain_workflow`、PLATFORM_REJECT→`platform_action`、UNEXPECTED→`workflow_runtime` |
| A5 | decimal context 不唯一 | ✅ **固定 `decimal_context.precision = 60`**（不接受"位数下限"写法），rounding=ROUND_HALF_UP；cid_results 按固定键序保存规范十进制字符串 |
| A6 | 错误/质量/业务闸门混义 | ✅ 冻结统一结果 envelope：`status / blocking_error / quality_flags / business_flags / field_details / values / bid_rounded_cents / formula_version / decimal_precision / rounding_mode`；L 缺失→FIELD_DEFAULTED 可计算不静默；必需字段缺失→REQUIRED_FIELD_MISSING 停止；rebate 不适用→REBATE_NOT_APPLICABLE（business，Q=0）；rebate 来源缺失→REBATE_SOURCE_MISSING（quality）；S≤0→S_NON_POSITIVE（business，已完成计算转人工闸门） |

> 注（A2 调整）：UNEXPECTED 按 A3 裁决为 retryable=true，故纳入 `retry_policies`（max_attempts: 3）——retryable exact-set 为 **5**（RATE_LIMIT/TIMEOUT/NO_MATCH/INSUFFICIENT_REFERENCES/UNEXPECTED）。

## 二、批 A 契约新哈希（round-23）

| 文件 | 字节 | SHA-256 |
|---|---|---|
| `docs/contracts/enum-registry.yaml` | 9,770 | `ab9178da9eb618de2cf473e6bf1b3a373a374fb2e84af2ad4ed781f6cddc7373` |
| `docs/contracts/error-codes.yaml` | 7,010 | `956780c05917d88cc75aa831b6d98616cc2355ec4269106677181b07160563ea` |
| `docs/contracts/cid-engine-spec.md` | 7,814 | `4aeb5183581ed650cacbd55347d0799ca5736c195258a044a78a1c21fde0e480` |

## 三、自检结果（SELF-CHECK: PASS，全部 30 项）

自检脚本 `_experiment/_interop/evidence/selfcheck_batch_a2.py`（只读，UTF-8 输出），关键项：

| 组 | 断言 | 结果 |
|---|---|---|
| A1 | entries=60；default_count=32；defaults=32 项；字段归属与值集校验 | ✅ 全部 |
| A2 | error entries=16；retryable exact-set=5；retry_policies 覆盖 5；双向 exact-set | ✅ 全部 |
| A3 | UNEXPECTED retryable=true/backoff=60/terminal=false/supersedes；PAGE_CHANGED supersedes | ✅ 全部 |
| A4 | 无 owner=dsh；owner 均为 6 类运行时责任域且=16 | ✅ 全部 |
| A5 | precision=60；无"至少 50"残留 | ✅ 全部 |
| A6 | blocking/quality/business 分离；S_NON_POSITIVE/REBATE_NOT_APPLICABLE 归 business；REQUIRED_FIELD_MISSING 归 blocking | ✅ 全部 |
| CID | M=1638.314、bid=1525、P/S/T/X 规范串 precision=60 复算 | ✅ 全部 |

## 四、请 Codex 在 round-24 产出的内容

1. **批 A 回修聚焦 diff**：读取三份新契约，逐项核对 A1~A6 是否闭合（default exact-set=32、retry_policies 机器可读、UNEXPECTED 语义与 supersedes、owner 责任域、precision=60、envelope 分离）；
2. 对 **UNEXPECTED 沿用 09/M0 基线（retryable=true/backoff=60）** 的裁决确认或异议；
3. 结论：批 A 通过 → round-25 DSH 落批 B（ddl-order/index-registry/test-strategy）；仍有阻断 → 列剩余清单。

## 五、输出要求

- 复核意见写 `from-cdx/round-24-cdx-P0-0批A回修diff.md`（UTF-8 无 BOM，中文）。
- 结构：A1~A6 逐项核对 → UNEXPECTED 裁决意见 → 批 A 结论。
- 对 `docs/contracts/` 只读，不修改；不写实现代码；不把 fixtures 当真实能力；无法确证处标「未确认」。

<!--RELAY: 请 CDX 读取本文件并继续，当前轮次 round-23-->