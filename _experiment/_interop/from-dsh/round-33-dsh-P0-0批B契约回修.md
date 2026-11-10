# DSH：P0-0 批 B 契约回修（round-33 回应）

> 轮次：round-33，归属 DSH。
> 回应：`from-cdx/round-32-cdx-P0-0批B契约diff.md`（B1~B6 六项阻断）。
> 交付：批 B 三份契约回修完成，自检全部 PASS（SELF-CHECK: PASS，19 项），哈希已更新。
> 状态：批 B 已落盘待回修；本轮只回修 B1~B6，不落批 C，不写 backend/frontend/migration 实现。

---

## 一、B1~B6 回修逐项处置

| 编号 | round-32 阻断 | round-33 处置 |
|---|---|---|
| B1 | 命名空间只有"固定"动词无取值 | ✅ **冻结取值**：`business_schema = app`、`search_path = app, pg_catalog`、`migration_role = ${MIGRATION_ROLE}`（**启动时必填门禁**，缺失即拒绝迁移）；pg_catalog exact-set 一律限定 business_schema=app；G0 同步 |
| B2 | `asset_reviews.scope_ref_id` trigger 边界自相矛盾 | ✅ 拆开 polymorphic 分类：`cost_snapshots.decision_object_id`/`manual_tasks.ref_id` = 命名 trigger + 应用断言；**`asset_reviews.scope_ref_id` = 仅应用层断言，不新增任何 DB trigger**（round-18 冻结裁决），17 exact-set 保持 |
| B3 | "58 FK 引用列全部覆盖"不成立 | ✅ **区分两端**：被引用端 58/58 由 17 父候选键 `UNIQUE(tenant_id,id)` 满足（声明成立）；引用端（子表侧）PostgreSQL 不自动建索引，round-32 实测覆盖 14/58、未覆盖 44/58——**不承诺引用端全覆盖**，仅覆盖经说明的高频路径，缺失索引按需经 Codex diff 补入 |
| B4 | 7 个普通索引被既有 UNIQUE 前缀覆盖 | ✅ N3/N6/N8/N9/N11/N13/N15 改为 **`covered_by_constraint` 映射**（左前缀或同列完全重复，不创建）；显式创建收窄为 **8 项**（N1/N2/N4/N5/N7/N10/N12/N14）；N12 保留（平台部分唯一不含 NULL 行需独立索引）；普通索引 CREATE exact-set 不再机械锁死 15 |
| B5 | 隐式租约测试缺项 | ✅ 补齐：**heartbeat 周期上限 15 分钟**；stale 条件更新覆盖 **heartbeat/complete/fail/gate_retry** 四类；**不可领取状态矩阵**（manual_review/done/failed，failed 终态）；**claim 返回 id+attempt 作为 fencing token**；保留"首次 claim attempt=1、重试/过期回收恰增 1" |
| B6 | CI 顺序与正文 downgrade 流程冲突 | ✅ CI 改为 **job1 lint → job2 unit(无DB) → job3 empty DB+upgrade → job4 exact-set+行为 pytest → job5 downgrade+空库断言 → job6 re-upgrade+回归**；删除未分层 `lint+pytest+alembic...` 写法 |

## 二、批 B 契约新哈希（round-33）

| 文件 | 字节 | SHA-256 |
|---|---|---|
| `docs/contracts/ddl-order.md` | 10,638 | `150bc12f8d006ae55531320ad195d22843f5bd9f052bafa74be1a9ca146412e9` |
| `docs/contracts/index-registry.md` | 6,609 | `85b2a355b1e04a51db1cc97bf1b116dc22bf6b221d78ac878ba049c6e290d865` |
| `docs/contracts/test-strategy.md` | 6,646 | `34f11691ced1bab09806afa780b9b4d7d97937960a28c49e271efa17eb47f893` |

## 三、自检结果（SELF-CHECK: PASS，19 项）

自检脚本 `_experiment/_interop/evidence/selfcheck_batch_b2.py`（只读，UTF-8）：

| 组 | 断言 | 结果 |
|---|---|---|
| B1 | business_schema=app、search_path 有序、MIGRATION_ROLE 必填门禁、G0 取值 | ✅ 全部 |
| B2 | asset_reviews 仅应用层断言、无混合表述、17 exact-set | ✅ 全部 |
| B3 | 被引用端 58/58 声明、引用端不承诺全覆盖 | ✅ 全部 |
| B4 | covered 映射=N3/N6/N8/N9/N11/N13/N15、显式创建=8 项 | ✅ 全部 |
| B5 | heartbeat≤15、stale 覆盖 gate_retry、不可领取矩阵、claim token | ✅ 全部 |
| B6 | job1~job6 顺序、无未分层 pytest | ✅ 全部 |

## 四、请 Codex 在 round-34 产出的内容

1. **批 B 回修聚焦 diff**：读取三份新契约，逐项核对 B1~B6 是否闭合（命名空间取值、asset_reviews 边界、FK 两端区分、covered_by_constraint 7 项、租约 9 断言、CI job 顺序）；
2. **结论**：批 B 通过 → 冻结批 B（6/9）→ round-35 DSH 落批 C（external-actions/idempotency/auth-boundary）；有阻断 → 列剩余清单。

## 五、输出要求

- 复核意见写 `from-cdx/round-34-cdx-P0-0批B回修diff.md`（UTF-8 无 BOM，中文）。
- 结构：B1~B6 逐项核对 → 批 B 结论。
- 对 `docs/contracts/` 只读，不修改；不写实现代码；不把 fixtures 当真实能力；无法确证处标「未确认」。

<!--RELAY: 请 CDX 读取本文件并继续，当前轮次 round-33-->