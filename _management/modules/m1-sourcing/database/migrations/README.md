# M1 自动选品 · 数据库迁移脚本

> 迁移脚本目录：开发库 SQLite 幂等 DDL（IF NOT EXISTS + 唯一约束），可重入。
> ORM 定义源：`backend/sourcing/tables.py`（DDL 以其为准，本目录 SQL 为文档化镜像）。

## 版本清单

| 脚本 | 版本 | 说明 | 状态 |
|---|---|---|---|
| `v0.1_m1_ad_tables.sql` | v0.1 | 新增 `m1_ad_conversion_cache` + `m1_ad_conversion_ingests`（投放转化缓存 + 回写导入审计） | 已落地 |

## 执行方式

### 方式一：ORM 建表（开发/测试推荐）

代码中直接调用 `Database(config).create_all()`（`backend/sourcing/db.py`）：
SQLAlchemy 按 `backend/sourcing/tables.py` 元数据建表，`checkfirst` 幂等（重复调用不报错），
测试基座（`backend/tests/conftest.py` 的 `db` fixture）即走此路径，两表随建。

```python
from sourcing.config import load_config
from sourcing.db import Database

db = Database(load_config())
db.create_all()
```

### 方式二：SQLite CLI / Python 执行（人工核对、离线库、增量补表）

```bash
# 在 backend 目录下（相对 DSN 基准）
sqlite3 data/db/m1-sourcing.db < _management/modules/m1-sourcing/database/migrations/v0.1_m1_ad_tables.sql
```

或 Python：

```python
import sqlite3
from pathlib import Path

sql = Path("_management/modules/m1-sourcing/database/migrations/v0.1_m1_ad_tables.sql").read_text(encoding="utf-8")
con = sqlite3.connect("data/db/m1-sourcing.db")
con.executescript(sql)
con.commit()
con.close()
```

脚本幂等可重入：`IF NOT EXISTS` + 唯一约束，重复执行不报错、不产生重复数据
（唯一键测试见 `backend/tests/test_m1_ad_tables.py`）。

### 方式三：生产 PostgreSQL 迁移起点

`backend/sourcing/tables.py` 使用 SQLAlchemy 通用类型，生产切 DSN 即可；如需手写 DDL，按本目录 SQL 做类型映射：

| SQLite | PostgreSQL |
|---|---|
| `VARCHAR(n)` | `VARCHAR(n)` |
| `DATETIME` | `TIMESTAMPTZ`（`generated_at`/`ingested_at` 显式带时区） |
| `INTEGER PRIMARY KEY AUTOINCREMENT` | `BIGSERIAL PRIMARY KEY` |
| `TEXT` | `TEXT` |
| `REAL` | `DOUBLE PRECISION` |

唯一约束（`UNIQUE (category, period_start, period_end)` /
`UNIQUE (source_file, period_start, period_end, generated_at)`）与索引语句原样保留。

## 口径备忘（写入前必读）

- `sales_amount` 单位「分」（int），与 M5 契约一致，**禁止元/分混用**（C-2）。
- `generated_at` 为 M5 生成时间，新鲜度判定基准：超过 `scoring.ad_data_max_age_days`（默认 7 天）视为无数据（R-14）。
- `sample_count < 5` 视为弱样本，打分时维度不生效。
- 完整字段口径见 `_management/modules/m1-sourcing/database/README.md` 第二节 与
  `_management/modules/m1-sourcing/context/README.md` C-2。
