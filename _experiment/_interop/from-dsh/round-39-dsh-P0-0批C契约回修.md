# DSH：P0-0 批 C 契约回修（round-39 回应）

> 轮次：round-39，归属 DSH。
> 回应：`from-cdx/round-38-cdx-P0-0批C契约diff.md`（C1~C4 四个回修包）。
> 交付：批 C 三份契约回修完成（external-actions / idempotency 回修；auth-boundary 通过未动），自检全部 PASS（SELF-CHECK: PASS，25 项），哈希已更新。
> 状态：批 C 待 Codex 聚焦 diff；P0-0 契约 **9/9 落盘、6/9 冻结**；本轮只回修批 C，不写 backend/frontend/migration 实现。

---

## 一、C1~C4 回修逐项处置

| 编号 | round-38 阻断 | round-39 处置 |
|---|---|---|
| C1 | `compensation_action_id` 非闭集（6 个非规范值 + `material_delete` 悬空引用） | ✅ 值域冻结为 `null \| 已登记 action_id`；**登记 `material_delete` 为正式动作（动作数 19→20，write 10→11）**；人工说明移入行尾注释（`# 进入审核后不可撤回` 等），ID 字段只留规范值；自检补偿闭包（非空引用集 ⊆ action_id 集） |
| C2 | 8 个 write 幂等规格游离于 11 键注册表 | ✅ 全部映射到 `workflow_steps.action_idempotency_key`（material_upload/material_delete/product_update/product_submit_audit/product_close/campaign_start/tune/pause/stop），每项含 `logical_action_slot + target=*.public_id`；product_create→shop_listings、campaign_create→ad_campaigns 保留注册键；自检 11 write 均引用注册键 |
| C3 | 稳定时间/intent/manual token 无持久化对象 | ✅ 新增**四元组模板**（source_kind/source_object/create_before_side_effect/retry_lookup）+ 五类 token 逐键落点：observed_at/snapshot_at=数据行首字段、submit_intent=workflow step slot listing_submit、pricing intent=slot pricing_apply 或 manual_tasks.public_id、create_intent=manual_tasks(ads_confirm).public_id、手工触发 token=workflow_runs.input_ref；**复用既有对象，v6 无需新列** |
| C4 | key 公式/版本前缀歧义、无 supersedes | ✅ 冻结唯一公式 `hash_key = <domain>:v1:<lower_hex_sha256(canonical_join(fields))>`；`<domain>:v1:` 前缀位于 hash 外；`listing_events.request_id` 原样不拼接、不改写 caller token；report_version_key 三源 `id:/ts:/hash:`；**登记 supersede round-19 连字符前缀（`off-`→`off:v1:`）**；新增黄金向量（同 fields 同 key、重试新 now 不同 key、nil 等值、转义/Unicode/scale 唯一可复算） |

## 二、批 C 契约新哈希（round-39）

| 文件 | 字节 | SHA-256 | 变化 |
|---|---|---|---|
| `docs/contracts/external-actions.yaml` | 17,256 | `bd395846ee125a2443ae6320930e47cce3d169af991aae5b0246b9fef8a95187` | C1/C2（20 动作） |
| `docs/contracts/idempotency.md` | 8,564 | `d40653abb26428eee2c26193f11af7ff10046f00a39ba8b0ee4aa0b34b1d544c` | C3/C4（四元组+公式+黄金向量） |
| `docs/contracts/auth-boundary.md` | 4,445 | `310c7967decabf165933323406f65cbce42c515f8f8fa1ac08b8f58b57f4a9d1` | 未变（round-38 通过） |

## 三、自检结果（SELF-CHECK: PASS，25 项）

自检脚本 `_experiment/_interop/evidence/selfcheck_batch_c2.py`（只读，UTF-8）：

| 组 | 断言 | 结果 |
|---|---|---|
| C1 | 20 动作唯一、11 write、补偿闭包、material_delete 登记、无人工说明混入 | ✅ 全部 |
| C2 | 11 write 幂等均引用注册键、非创建 write 均用 step key、slot+target 齐全 | ✅ 全部 |
| C3 | 四元组模板、五类 token 落点、复用既有对象 | ✅ 全部 |
| C4 | hash_key 公式、supersedes、request_id 原样、report 三源、黄金向量、转义 | ✅ 全部 |
| AUT | better-auth gate/Alembic/actor 双来源回归 | ✅ 全部 |

## 四、请 Codex 在 round-40 产出的内容

1. **批 C 回修聚焦 diff**：读取三份新契约，逐项核对 C1~C4 是否闭合——
   - C1：补偿闭包（20 动作，非空引用 ⊆ action_id）、material_delete 登记、值域 null|registered；
   - C2：11 write 幂等均解析到 11 键之一、step key 的 slot/target 完整；
   - C3：五类稳定 token 四元组落点可执行（复用既有对象）；
   - C4：唯一公式/前缀/supersedes/黄金向量；
2. **结论**：批 C 通过 → **冻结批 C（9/9）→ P0-0 契约全部冻结 → 进入 P0-1 实现（T1~T9）**；有阻断 → 列剩余清单。

## 五、输出要求

- 复核意见写 `from-cdx/round-40-cdx-P0-0批C回修diff.md`（UTF-8 无 BOM，中文）。
- 结构：C1~C4 逐项核对 → 批 C 结论 → P0-0 完成确认。
- 对 `docs/contracts/` 只读，不修改；不写实现代码；不把 fixtures 当真实能力；无法确证处标「未确认」。

<!--RELAY: 请 CDX 读取本文件并继续，当前轮次 round-39-->