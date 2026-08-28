# M5 自动小店投放（商品托管）· v0.2 数据层交付说明

> 撰写人：M5 子代理（数据层）｜ 日期：2025 体系建立日
> 范围：本任务仅实现 v0.2 数据层（独立 SQLite 库 + 5 张 ad_* 表 + repo 层）。
> 业务执行/UI 自动化（Playwright）属后续 v0.3，本任务不涉及浏览器。

## 一、交付文件清单

| 文件 | 说明 |
|---|---|
| `backend/ads/__init__.py` | 包声明（docstring） |
| `backend/ads/config.py` | AdsConfig（pydantic-settings，env_prefix=`ADS_`），含批量/预算/止损/余额/总开关/CDP 端口等配置；**无任何凭证字段** |
| `backend/ads/models.py` | `utcnow()`（UTC 带时区）/ `ensure_aware()`，与 sourcing/models.py 一致 |
| `backend/ads/tables.py` | Base(DeclarativeBase) + 5 张 ORM 表：ad_campaigns / ad_runs / ad_report_snapshots / ad_account_states / ad_materials |
| `backend/ads/db.py` | Database 类（照抄 sourcing/db.py 模式，改 import 自 ads.config）+ `default_database()`；文件型 SQLite 自动建父目录 |
| `backend/ads/repo.py` | 函数式 repo（Session 参数）：read_app_config（只读）/ campaign CRUD / run / snapshot 幂等 upsert / account / material 幂等 upsert / sum_spend_since / count_active_campaigns |
| `backend/ads/__main__.py` | CLI（click）：`python -m ads init-db` 建表（幂等，自动建 data/db） |
| `backend/tests/test_ads_tables.py` | 表结构测试：5 表存在、各表字段齐全、默认值生效、NOT NULL、唯一约束（snapshot 幂等 / material_id）生效 |
| `backend/tests/test_ads_repo.py` | repo 层测试：campaign CRUD、run 创建/回写/多 attempt、snapshot 幂等 upsert（两次仍 1 行）、预算汇总 sum_spend_since、account 单例/节流 0~4 封顶、material 幂等 upsert、app_config 只读 |
| `backend/tests/conftest.py` | **仅末尾追加** `cfg_ads` / `db_ads` 两个 fixture（临时 SQLite，tmp_path）；未改删既有内容 |
| `_management/modules/m5-ads/REPORT_v0.2.md` | 本交付说明 |

## 二、测试结果（backend 目录执行）

### 2.1 定向测试（本任务新增，验收标准 1）
```
python -m pytest tests/test_ads_tables.py tests/test_ads_repo.py -q --basetemp=".pytest-tmp"
27 passed in 1.83s
```
全绿。覆盖：表结构（5 表/字段/默认值/唯一约束）、campaign CRUD、run、snapshot 幂等
（同 (campaign_id, recorded_at) upsert 两次仍 1 行且值更新为最新）、material 幂等 upsert
（同 material_id 两次仍 1 行）、sum_spend_since 预算汇总、account 状态/节流封顶、
app_config 只读（读后表内容不变）。

### 2.2 全量测试（验收标准 2）
```
python -m pytest tests -q --basetemp=".pytest-tmp"
256 passed, 7 failed, 1 skipped in 25.25s
```

7 个失败均为**既有环境问题**（foundation/materials 既有测试，非本任务引入，
本任务未改动任何 foundation/materials 源文件与既有测试，仅 conftest 末尾追加惰性 fixtures）：

| 失败用例 | 原因（已核实） |
|---|---|
| `test_foundation_tables.py::test_timestamp_columns_at_suffix` | 断言 workflow_jobs 应有 `retry_after` 时间戳列，实际表无此列——M0 foundation 代码与测试断言不一致（既有） |
| `test_foundation_tables.py::test_unique_constraints_present` | 断言唯一约束元组 `('product_id','stage','generation_version')`，实际返回 `('generation_version','product_id','stage')`——断言写死顺序，SQLAlchemy 返回排序不同（既有） |
| `test_foundation_queue.py::test_fail_rate_limit_sets_backoff` | `TypeError: can't subtract offset-naive and offset-aware datetimes`——SQLite 存储丢 tzinfo，foundation repo 读回 retry_after 未补 UTC（既有） |
| `test_foundation_queue.py::test_fail_unknown_code_falls_back_unexpected` | 同上 naive/aware 时间相减 TypeError（既有） |
| `test_foundation_queue.py::test_failure_isolation` | `assert 0 == 1`——领任务断言与熔断/租约时序相关（既有） |
| `test_materials_dedup.py::test_claim_and_register_conflict_raises_duplicate` | 单跑时为 ERROR：teardown 清理 `.pytest-tmp` 下临时 db 报 `PermissionError [WinError 32]`（文件占用）——P-001 描述的 Windows 临时目录坑（既有） |
| `test_materials_downloader.py::test_circuit_breaker_and_recovery` | NO_MATCH 重试/熔断探针时序断言 `assert 0 == 1`，且 teardown 同样出现 WinError 32（既有） |

以上失败与本任务交付物无任何依赖关系（ads 测试单独运行全绿；失败用例不请求
cfg_ads/db_ads fixtures）。按任务书要求**未删除/改写任何既有测试**。

## 三、验收标准对照

| # | 标准 | 结果 |
|---|---|---|
| 1 | 定向 pytest 全绿（带 `--basetemp=".pytest-tmp"`） | ✅ 27 passed |
| 2 | 全量无回归（既有失败记录在案） | ✅ 256 passed / 7 既有环境失败（见上表，未改既有测试） |
| 3 | `python -m ads init-db` 建 m5-ads.db 且 5 表齐全 | ✅ 已运行：`backend/data/db/m5-ads.db`（53248 B），5 张 ad_* 表齐全（保留，不入 git） |
| 4 | repo 全函数有测试覆盖；snapshot/material upsert 幂等验证 | ✅ 见 2.1 |
| 5 | 无明文密钥；无 git 操作；未触碰其他模块库 | ✅ 见下 |

## 四、与任务书规格的偏差说明

1. **无功能偏差**：字段/表名/枚举/默认值严格按任务书执行。枚举存储英文
   （status=pending/active/paused/not_eligible/ended；target_type=roi/net_roi/goods；
   diagnosis=excellent/good/optimize_1/optimize_n；evaluation=exploring/efficient/
   potential 与 M2 完全一致；upload_status=uploading/uploaded/reviewing/approved/
   rejected/corrupt；run.status=running/success/failed/blocked；error_code 复用 09 码表
   含 page_changed；account.status=active/risk_control/waiting_login/
   waiting_verification/paused），中文仅注释/展示映射。
2. **account.status 默认值**：任务书与 DDL 规划 v0.1 的 context 数据字典（normal）
   存在口径差异，按任务书枚举口径取默认 `active`（任务书为权威）。
3. **read_app_config 实现**：app_config 表定义属 M0/sourcing（不跨模块 import 表结构），
   用原生 SQL 只读查询；本模块库中该表不存在时（正常情况）返回 default 不抛错；
   测试在临时库内建最小 app_config 表验证只读行为与读后内容不变。
4. **索引**：按任务书字段规格实现；额外按 DDL 规划 v0.1 为 ad_materials.evaluation
   建索引（查询过滤用），未新增其他表/字段。
5. **未落地项（属后续 v0.3）**：Playwright 执行、止损规则引擎执行、调度器、CLI 除
   init-db 外的命令（如 report/campaigns 列表）——均不在本任务范围。

## 五、纪律核对

- ✅ 禁 git：全程未执行任何 git 命令。
- ✅ 一模块一库：只操作 `backend/data/db/m5-ads.db` 与测试 tmp_path 临时库；
  未触碰 m1-sourcing.db / m2-materials.db 等文件及其表；app_config 仅只读。
- ✅ 无明文密钥：config.py 只含路径/数值，无任何凭证字段；代码/文档无密钥。
- ✅ 金额一律分（int）、时间 UTC 带时区（DateTime(timezone=True)+utcnow）、
  时间戳字段名 `_at`。
- ✅ 中文文件（本说明/代码 docstring）用 write 工具 UTF-8 无 BOM 写入。
- ✅ 测试均带 `--basetemp=".pytest-tmp"`（P-001）。

## 六、环境备注

- Python 3.13（本机），SQLAlchemy 2.x / pydantic-settings / click 可用。
- 控制台输出中文乱码仅为 GBK 显示问题，不影响功能与文件编码。
- 全量测试中 materials 个别用例 teardown 出现 WinError 32（Windows 下 SQLite
  临时文件占用），与 P-001 坑同源，属既有环境问题。
