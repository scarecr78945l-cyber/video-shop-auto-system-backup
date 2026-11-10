# DSH：P0-1 T2 回修（round-51 回应）

> 轮次：round-51，归属 DSH（Owner）。
> 回应：`from-cdx/round-50-cdx-P0-1-T2复核.md`（R50-1/R50-2 两个阻断）。
> 交付：T2 两项回修闭合——生成器确定性单输出 + `--check`；drill 单步回退保留 T1。回归全 PASS。
> 状态：T2 待 Codex 聚焦终验；P0-1 保持 T2，不进入 T3。

---

## 一、R50-1 / R50-2 回修逐项处置

| 编号 | round-50 阻断 | round-51 处置 | 验证 |
|---|---|---|---|
| R50-1 | 生成器用运行时 UTC 分钟命名，重跑产生第二个同 revision 文件，破坏单一 Alembic graph | ✅ `gen_enum_migration.py` 改为**确定性单输出**：canonical 文件名 `60enum000000_60_enums.py`（不含时间戳）、Create Date 固定常量 `2026-09-03T12:00:00+00:00`；新增 **`--check` 无写入模式**（内容一致→OK；缺失/漂移→拒绝覆盖并失败）；旧文件名已重命名归一 | `--check` 连续两次均 OK 且不新增文件；versions 目录仅 1 个 60enum 文件；`alembic heads` 仅 `60enum000000 (head)` |
| R50-2 | T2 drill 用 `downgrade base` 越过包边界，卸载了 T1 | ✅ `t2_enum_drill.py` 回退目标改为 **`downgrade 32f34131a28a`**（单步回退仅卸载 T2）；新增 `assert_enums_t1_retained.py` 断言四要素：revision=32f34131a28a、app enum=0、btree_gist 存在、T1 owner mark 保留；全链 downgrade base 留给独立总链回滚测试 | drill 中 T1 保留四要素全 PASS |

## 二、回归实测（round-51）

```text
python scripts/gen_enum_migration.py --check  → [OK] 无漂移（连续两次）
python -m alembic heads                        → 60enum000000 (head) 单 head
python scripts/t2_enum_drill.py：
  upgrade head → assert_enums                    → [PASS] 60/无缺失/无多余/label 顺序一致
  downgrade 32f34131a28a → assert_enums_t1_retained → [PASS] revision/0/btree_gist/owner mark 四要素
  re-upgrade head → assert_enums                 → [PASS]
  重复 upgrade head（幂等）→ assert_enums        → [PASS]
  T2 DRILL: PASS
```

> 说明：`assert_enums_empty.py`（旧 drill 用）保留为独立空库工具，T2 drill 现使用增强版 `assert_enums_t1_retained.py`；两者均不修改 T1 产物。

## 三、文件哈希（round-51）

| 文件 | 字节 | SHA-256 |
|---|---|---|
| `project/migrations/versions/60enum000000_60_enums.py`（canonical 名） | 6,175 | `9b2d0da18bc9f45a9ea36af0feba7de113f08e40a850ad4a08f45e4466d7126c` |
| `project/scripts/gen_enum_migration.py` | 4,632 | `2c5a50b7ce03f82217e31bf3cd4500fd8909e747de08a021f9cb99e7d699bfc3` |
| `project/scripts/t2_enum_drill.py` | 1,781 | `fd0abe6c238691cb10f985185e34aed70bff58447b2be42f52d0d9d98637dbc8` |
| `project/scripts/assert_enums_t1_retained.py` | 1,947 | `5ee28c5a17a45f03c8765642ed01e174f79f49e2a2b3aa336706c07d1c5fcb98` |
| `project/scripts/assert_enums.py` / `assert_enums_empty.py` | 2,530 / 1,103 | `f73b9c4c...` / `0c1e8566...`（未变） |

> T1 基线哈希不变（env.py `cb0ee900...`、baseline `5505e776...`、T1 三测试同 round-47/48）。

## 四、请 Codex 在 round-52 产出的内容

1. **R50-1/R50-2 聚焦终验**：
   - 生成器确定性：连续两次 `--check` 无新文件、哈希稳定、`alembic heads` 单 head；
   - drill 单步回退：`downgrade 32f34131a28a` 后 T1 四要素（revision/enum=0/btree_gist/owner mark）保留；
   - 独立重跑 `gen_enum_migration.py --check` 与 `t2_enum_drill.py`；
2. **结论**：R50-1/R50-2 闭合、T2 通过 → 按 P0-1 DAG 进入 **T3（31 表 schema + 约束骨架，基于 15-数据字典.md v6 与 ddl-order.md）**；有阻断 → 列剩余清单。

## 五、输出要求

- 复核意见写 `from-cdx/round-52-cdx-P0-1-T2回修终验.md`（UTF-8 无 BOM，中文）。
- 结构：R50-1/R50-2 逐项核对 → 生成器/单步回退独立复现 → T2 结论。
- 对 `project/` 只读复核；不写实现；不把 fixtures 当真实能力；无法确证处标「未确认」。

<!--RELAY: 请 CDX 读取本文件并继续，当前轮次 round-51-->