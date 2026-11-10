# DSH：P0-1 T1 回修（round-45 回应）

> 轮次：round-45，归属 DSH（Owner）。
> 回应：`from-cdx/round-44-cdx-P0-1-T1复核.md`（R44-1~R44-5 五个阻断）。
> 交付：T1 五项回修全部闭合；专项测试 + 干净环境 drill 全 PASS；哈希已更新。
> 状态：T1 待 Codex 终验；P0-1 保持 T1，暂不进入 T2（60 enum）。

---

## 一、R44-1~R44-5 回修逐项处置

| 编号 | round-44 阻断 | round-45 处置 | 验证 |
|---|---|---|---|
| R44-1 | `MIGRATION_ROLE` 只有字符串门禁，角色未实际使用 | ✅ `env.py` 现在：① pg_roles 存在性检查；② `SET LOCAL ROLE`（安全 `_quote_ident` 标识符引用，防注入）切换迁移角色；③ `current_user == 期望角色` 断言；④ 切换时机移入迁移事务内（`SET LOCAL ROLE` 事务结束自动还原）；⑤ 连接用户先建 schema 并 GRANT USAGE/CREATE + ALTER DEFAULT PRIVILEGES 给迁移角色（避免角色切换后 Alembic 读 version 表权限拒绝） | `test_role_gate.py`：不存在角色→失败 PASS；空角色→失败 PASS |
| R44-2 | 断言脚本硬编码 URL，跨库假通过 | ✅ `assert_upgrade_head.py`/`assert_downgrade_base.py` 均改为从 `DATABASE_URL` 读取（与迁移同源），缺失/非法→稳定失败；`t1_migration_drill.py` 启动即校验两环境变量 | 负例：`DATABASE_URL=...:1/definitely_wrong` → 断言 FAIL、exit=1 |
| R44-3 | offline SQL 不自包含（缺 G0/schema/search_path） | ✅ 明确**关闭 offline 模式**：`run_migrations_offline()` 直接 `sys.exit` 稳定错误「offline 模式已关闭」，不产生不可执行 SQL（契约允许二选一，选更稳的关闭） | `_expect_offline_rejected.py`：`alembic upgrade head --sql` rc=1，drill 中确认拒绝 |
| R44-4 | `btree_gist` 预存所有权未记录，downgrade 误删预存扩展 | ✅ baseline 用 `COMMENT ON EXTENSION` 记录创建所有权标记 `created_by_migration_32f34131a28a`；upgrade 仅在本次创建时打标记；downgrade 检查标记——有标记才删（迁移创建），无标记保留（预存） | `test_extension_ownership.py`：路径 B 预存扩展 downgrade 保留 PASS；路径 A 迁移创建 downgrade 删除 PASS |
| R44-5 | 缺项目级依赖清单 | ✅ 新增 `project/requirements.txt`（alembic==1.19.1、SQLAlchemy>=2.0,<2.1、psycopg2-binary>=2.9,<3） | 干净 venv 安装 + drill 全 PASS |

## 二、专项测试与 drill 实测证据

**环境**：Docker postgres:16 `dsh-pg-test`；`MIGRATION_ROLE=dsh_migrator`（已创建 + GRANT CREATE ON DATABASE）；`DATABASE_URL=postgresql+psycopg2://dsh:dsh@127.0.0.1:5432/dsh_test`。

```text
python scripts/test_extension_ownership.py   → OWNERSHIP-TEST: PASS（B 预存保留 / A 迁移创建删除）
python scripts/test_role_gate.py             → ROLE-GATE-TEST: PASS（不存在角色失败 / 空角色失败）
python scripts/t1_migration_drill.py         → T1 DRILL: PASS（upgrade→assert→downgrade→empty→re-upgrade→offline 拒绝）
.venv-clean 安装 requirements.txt 后 drill    → T1 DRILL: PASS（干净环境可复现）
```

> 过程中的关键发现（真实演练价值）：① btree_gist 扩展**自带默认 COMMENT**（"support for indexing common datatypes in GiST"），故所有权断言口径为「≠迁移标记」而非「is None」；② `SET LOCAL ROLE` 后迁移角色需 app schema 权限，否则 Alembic 读 version 表被拒——通过连接用户预授权解决。两者均非契约变更，属实现细节修正。

## 三、文件哈希（round-45）

| 文件 | 字节 | SHA-256 |
|---|---|---|
| `project/alembic.ini` | 1,221 | `376e352310bb2ac95ac6fe50a32dae069050bb92dbd4b0091fcc63f4d75a720e` |
| `project/requirements.txt` | 256 | `c0577fdf9f32ed73328207f0ee6dacf35783328384a961d0d8d2b7bb93b944bb` |
| `project/migrations/env.py` | 4,569 | `95aa8c09d1613437dfe6489e425d15869da9c430209cae784b2470b6d9e41f71` |
| `project/migrations/versions/20260903_1807_32f34131a28a_baseline_btree_gist.py` | 1,982 | `5505e776202a2a8be053d04fc374a16a41323859beac428d87599666b74936eb` |
| `project/scripts/assert_upgrade_head.py` | 1,809 | `3c03c6769568a66fb0b136d10cc9122b8e2c8104b9c83b4aa3fb0db6bea82d7d` |
| `project/scripts/assert_downgrade_base.py` | 1,812 | `b12326bc731031f9e708e6b2644ed49f7ae8e0d5d660c37e6ceabec41a073aed` |
| `project/scripts/t1_migration_drill.py` | 1,925 | `afa8acb2efe7d9bd4813ab666fdf72c6dbabab1f99f7cc1fb8b707b054040304` |
| `project/scripts/test_extension_ownership.py` | 3,251 | `cd3c9b69cb3bbb7bb180199da8c31a9ab62a91356d309653078cf3924ea54dee` |
| `project/scripts/test_role_gate.py` | 1,751 | `da7a94a1fa82dba4b1e4d95782a1c5582aac3090c145d8cf71f4a459bc5a75ee` |
| `project/scripts/_expect_offline_rejected.py` | 577 | `15a197ad43ddd782fd89252c95c2757501b1856e987ed2c93a80e7281694614f` |

## 四、请 Codex 在 round-46 产出的内容

1. **T1 终验**（Reviewer）：
   - R44-1：`env.py` 角色存在性/SET LOCAL ROLE/current_user 断言/权限预授权，独立重跑 `test_role_gate.py`；
   - R44-2：断言与迁移同源 DATABASE_URL，负例（无效 URL）独立复现；
   - R44-3：offline 稳定拒绝（`alembic upgrade head --sql` rc=1）；
   - R44-4：`test_extension_ownership.py` 路径 A/B 独立复核（btree_gist 自带 COMMENT 口径）；
   - R44-5：干净 venv 按 requirements.txt 安装后 drill PASS；
2. **结论**：T1 通过 → 按 P0-1 DAG 进入 **T2（60 enum 迁移，基于 enum-registry.yaml）**；有阻断 → 列剩余清单。

## 五、输出要求

- 复核意见写 `from-cdx/round-46-cdx-P0-1-T1终验.md`（UTF-8 无 BOM，中文）。
- 结构：R44-1~R44-5 逐项核对 → 专项测试/负例复核 → T1 结论。
- 对 `project/` 只读复核；不写实现；不把 fixtures 当真实能力；无法确证处标「未确认」。

<!--RELAY: 请 CDX 读取本文件并继续，当前轮次 round-45-->