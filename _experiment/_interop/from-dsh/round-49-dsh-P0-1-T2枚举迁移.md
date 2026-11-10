# DSH：P0-1 T2 枚举迁移（round-49 回应）

> 轮次：round-49，归属 DSH（Owner）。
> 回应：`from-cdx/round-48-cdx-P0-1-T1门禁终验.md`（T1 COMPLETE，授权进入 T2）。
> 用户指令：round-49（T2）。
> 交付：60 enum migration（由 `enum-registry.yaml` 生成）；upgrade 顺序创建 / downgrade 逆序；往返+幂等 drill PASS。
> 状态：T2 待 Codex 复核；P0-1 保持 T2，不提前进入 T3（表结构）。

---

## 一、T2 交付物

### 1. 新增文件（`project/`）

```text
project/
  migrations/versions/20260903_1200_60enum000000_60_enums.py   # T2: 60 enum（down_revision=32f34131a28a）
  scripts/gen_enum_migration.py        # 生成器：从 enum-registry.yaml 生成 migration
  scripts/assert_enums.py              # upgrade 后：app schema 60 enum exact-set（名称+label 顺序）
  scripts/assert_enums_empty.py        # downgrade 后：app schema enum=0
  scripts/t2_enum_drill.py             # 往返+幂等 drill
```

### 2. 契约落地点

| 契约（round-48 §五） | 落地 |
|---|---|
| 以 `docs/contracts/enum-registry.yaml` 为唯一输入 | `gen_enum_migration.py` 解析 registry entries（名称/值集/顺序），生成 `_ENUMS` 内嵌列表 |
| enum 位于 `app` schema | env.py search_path=app,pg_catalog；`CREATE TYPE` 无 schema 前缀即落 app |
| catalog 按 schema+类型名+label 顺序 exact-set 验收 | `assert_enums.py`：pg_catalog 查 `nspname='app' AND typtype='e'`，与 registry 名称集、label 集、label 顺序逐一比对 |
| 保持 60，不生成 `enum_error_code` | registry count=60；migration 无 error_code 类型 |
| upgrade 按注册顺序 / downgrade 严格逆序 | `_ENUMS` 顺序创建；`reversed(_ENUMS)` 逆序删除 |

## 二、实测证据（命令 + 结果）

**环境**：Docker postgres:16 `dsh-pg-test`；`MIGRATION_ROLE=dsh_migrator`；`DATABASE_URL=postgresql+psycopg2://dsh:dsh@127.0.0.1:5432/dsh_test`。

```text
python scripts/gen_enum_migration.py  → [OK] generated 20260903_1200_60enum000000_60_enums.py (60 enums)
python scripts/t2_enum_drill.py：
  upgrade head（T2）                  → Running upgrade 32f34131a28a -> 60enum000000
  assert_enums.py                     → [PASS] registry=60 / app enum=60 / 无缺失 / 无多余 / label 顺序一致
  downgrade base（T2 逆序）            → Running downgrade 60enum000000 -> 32f34131a28a
  assert_enums_empty.py               → [PASS] app enum=0
  re-upgrade head                     → 60 enum 恢复
  assert_enums.py                     → [PASS]（回归一致）
  重复 upgrade head（幂等）            → 无新增
  assert_enums.py                     → [PASS]
  T2 DRILL: PASS
```

## 三、文件哈希（round-49）

| 文件 | 字节 | SHA-256 |
|---|---|---|
| `project/migrations/versions/20260903_1200_60enum000000_60_enums.py` | 6,180 | `8013ba6c436c67f8c6ca178dab8ca447e4d98801fb64fef04d1e106cb2d6b04f` |
| `project/scripts/gen_enum_migration.py` | 3,509 | `d9eca5da8d3c65011b5136339d4120246521432eabf29d5ec651994762054676` |
| `project/scripts/assert_enums.py` | 2,530 | `f73b9c4ced2fbcccda360f7a94c74e4fbaea5ee1c60f17e0f912c1ba64417bc9` |
| `project/scripts/assert_enums_empty.py` | 1,103 | `0c1e85666806b439fe63435e6317b173e438aeebb4470914aedf5359f41a6b21` |
| `project/scripts/t2_enum_drill.py` | 1,599 | `26e294504fd17375c79eb7dae7795437fdc28f6726f95bbb6146fdca6a9a0e43` |

> T1 基线文件哈希不变（env.py `cb0ee900...`、baseline `5505e776...`、T1 三测试哈希同 round-47）。

## 四、请 Codex 在 round-50 产出的内容

1. **T2 复核**（Reviewer）：
   - `gen_enum_migration.py` 解析 registry 与 `_ENUMS` 一致性（60 项、名称/值集/顺序）；
   - `20260903_1200_60enum000000_60_enums.py` upgrade/downgrade 方向与逆序正确性；
   - `assert_enums.py` pg_catalog exact-set（schema+类型名+label 顺序）独立复核；
   - 独立重跑 `t2_enum_drill.py`；
2. **结论**：T2 通过 → 按 P0-1 DAG 进入 **T3（31 表 schema + 约束骨架，基于 15-数据字典.md v6 与 ddl-order.md）**；有阻断 → 列剩余清单。

## 五、输出要求

- 复核意见写 `from-cdx/round-50-cdx-P0-1-T2复核.md`（UTF-8 无 BOM，中文）。
- 结构：生成器/迁移/断言核对 → drill 复核 → T2 结论。
- 对 `project/` 只读复核；不写实现；不把 fixtures 当真实能力；无法确证处标「未确认」。

<!--RELAY: 请 CDX 读取本文件并继续，当前轮次 round-49-->