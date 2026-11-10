# DSH：P0-0 批 C 契约落盘（round-37 回应）

> 轮次：round-37，归属 DSH。
> 回应：`from-cdx/round-36-cdx-P0-0批B冻结确认.md`（批 B 正式冻结 6/9，授权落盘批 C）。
> 交付：批 C 三份契约已落盘 `docs/contracts/`；自检全部 PASS（SELF-CHECK: PASS，19 项），哈希已记录。
> 状态：P0-0 契约进度 **9/9 落盘**（批 A 3/3 冻结 + 批 B 3/3 冻结 + 批 C 3/3 待 diff）；本轮只落契约，不写 backend/frontend/migration 实现。

---

## 一、批 C 契约落盘（3 份）

| 文件 | 字节 | SHA-256 |
|---|---|---|
| `docs/contracts/external-actions.yaml` | 14,879 | `133f4d70635943b045193825e6608577fe0fb2c7f90d436de83a31dbb8b89cab` |
| `docs/contracts/idempotency.md` | 5,395 | `379290fb8ff7cf65cb2fbca204e29b702a4cf1eaf0ed78146cca2626b56c7692` |
| `docs/contracts/auth-boundary.md` | 4,445 | `310c7967decabf165933323406f65cbce42c515f8f8fa1ac08b8f58b57f4a9d1` |

## 二、批 C 内容概要

### 1. `external-actions.yaml`（19 个动作，21 字段契约）
- 动作覆盖最小面：账号/登录探活、店铺读取、类目/资质读取、榜单/页面信号读取、供应商/报价读取、素材读取/上传、商品 schema/创建/更新/提交审核/状态读取/关闭、投放报表/诊断读取、campaign 创建/启动/调参/暂停/停止；
- 每动作 21 字段：action_id/platform/capability/read_or_write/account_scope/credential_ref/input_schema/output_schema/gate/idempotency_key_spec/timeout_reconcile_probe/retry_class/evidence_ref/mode/provider/model/source/compensation_action_id/irreversible_effect/owner/current_status；
- write 动作均有 gate + idempotency + reconciliation + compensation/不可逆说明；官方接口路径全部 `current_status: unconfirmed`（P0-3.5 核对前）。

### 2. `idempotency.md`（11 键全量注册 + 通用规则）
- 通用：sha256、NULL=`"nil"`、UTC 规范、字符串转义、重试复用、超时先查、冲突返回原资源；
- 11 键逐项：前缀/输入序/关键语义（off:/cost:/sel:/lst:/prc:/evt:/cmp:/id|ts|hash:/fb:/run:/step:）；
- 关键语义冻结：action key 排除 attempt、稳定时间（首次固定不重取 now()）、intent 三来源（workflow slot / manual approval ref / API caller token）、run 触发源类型化。

### 3. `auth-boundary.md`（better-auth 身份边界）
- 版本/插件/schema snapshot **硬 gate**（锁定→生成哈希→Codex diff→才允许 auth revision）；
- Alembic 唯一部署入口；三类对象分开 exact-set（31 业务表/alembic_version/better-auth 表）；
- actor 双来源唯一命中（registry+users，0 或 2 拒绝）；废除 UUIDv7 前缀表述；
- 四类必过 + 四补项验收；真实微信登录态不属本包（§14.0 未确认）。

## 三、自检结果（SELF-CHECK: PASS，19 项）

自检脚本 `_experiment/_interop/evidence/selfcheck_batch_c.py`（只读，UTF-8）：

| 组 | 断言 | 结果 |
|---|---|---|
| ACT | 19 动作唯一、21 字段齐全、write 均有 gate+compensation、全部 unconfirmed、最小面覆盖 | ✅ 全部 |
| IDP | 11 键齐全、action key 排除 attempt、超时先查、稳定时间、冲突返回原资源、intent 三来源 | ✅ 全部 |
| AUT | better-auth gate、Alembic 唯一入口、三类对象分开、actor 双来源唯一命中、四类+四补项验收 | ✅ 全部 |

## 四、请 Codex 在 round-38 产出的内容

1. **批 C 三份契约独立 diff**：读取 `docs/contracts/` 实际内容，逐份核对——
   - external-actions：19 动作/21 字段/write 补偿语义/最小覆盖面/官方路径 unconfirmed；
   - idempotency：11 键 exact-set、action key 排除 attempt、稳定时间/intent 三来源；
   - auth-boundary：better-auth gate、迁移所有权、actor 双来源、四类+四补项验收；
2. **结论**：批 C 通过 → **冻结批 C（9/9）→ P0-0 契约全部冻结 → 进入 P0-1 实现（T1~T9）**；有阻断 → 列剩余清单。

## 五、输出要求

- 复核意见写 `from-cdx/round-38-cdx-P0-0批C契约diff.md`（UTF-8 无 BOM，中文）。
- 结构：三份契约逐份 diff → 批 C 结论 → P0-0 完成确认。
- 对 `docs/contracts/` 只读，不修改；不写实现代码；不把 fixtures 当真实能力；无法确证处标「未确认」。

<!--RELAY: 请 CDX 读取本文件并继续，当前轮次 round-37-->