# M5 自动小店投放（商品托管）· v0.4 监控回读 — 交付说明

> 角色：监控回读子代理 ｜ 日期：2025 体系建立日 ｜ 状态：**待总工验收**
> 任务：v0.4 监控层第一部分「监控回读」——定时回读投放管理列表 → 结构化快照幂等入库
> `ad_report_snapshots`，支持断点补快照。纯数据驱动（fixtures/mock），无真实浏览器/登录态。

---

## 一、文件清单

| 文件 | 动作 | 说明 |
|---|---|---|
| `backend/ads/report.py` | **新建** | 监控回读核心模块：归一化纯函数 ×3 + 快照行解析 + SnapshotCollector + next_run_hint |
| `backend/tests/test_ads_report.py` | **新建** | 24 个用例（数据驱动 + tmp_path 临时库，fixtures 全部文件内自建） |
| `_management/modules/m5-ads/REPORT_v0.4_report.md` | **新建** | 本交付说明 |

**未改动**：`repo.py / tables.py / config.py / settings.py / executor.py / ui_config.py /
interfaces.py / models.py / db.py / __main__.py / __init__.py`、既有测试、`conftest.py`（0 处改动，
测试 fixtures 文件内自建，优先方案，避免 conftest 并发冲突）。并行子代理的 `stop_loss.py` 未触碰。

---

## 二、接口说明（backend/ads/report.py）

### 1. `normalize_diagnosis(raw: str | None) -> str`
中文诊断 → 英文枚举（strip 后匹配）：
- `优秀`→`excellent`、`良好`→`good`；
- 正则 `(\d+)\s*项待优化`：N==1→`optimize_1`、N≥2→`optimize_n`（"1项待优化"/"2项待优化"/"12项待优化"）；
- 空/未知（含英文输入、`0项待优化`）→`unknown`；空白容忍（"  优秀  "、数字与「项」间空格）。

### 2. `normalize_status(raw: str | None) -> str`
- `投放中`→`active`；`暂停投放`/`已暂停`/`暂停`/`暂停（投放）`→`paused`（凡以「暂停」开头）；
- `不可投放`→`not_eligible`、`待托管`→`pending`、`已结束`→`ended`；空/未知→`unknown`。

### 3. `parse_amount_fen(raw: str | float | int | None, default: int = 0) -> int`
金额统一「分」（DA-001），**str 按元→分，数值按分直取**（口径已在 docstring 写明）：
- str："12.34"→1234（×100 四舍五入）、"1,234.56"→123456（千分位）、"1234"→123400（字符串一律按元！）；
- int/float：输入即「分」直接取整（1234→1234、12.9→12，不乘 100）；
- None/非法（空串/非数字/多余小数点/bool）→ default（默认 0）。

### 4. `parse_snapshot_row(raw: dict) -> dict`
一行原始投放列表 dict → 规范化 dict（字段超集，保留 `raw_json` 原始行副本）：
`campaign_id:int`、`recorded_at:datetime(UTC aware)`、`impressions:int`、
`spend/gmv/platform_subsidy:int(分)`、`diagnosis/status:str(英文枚举)`、`raw_json:dict`。
- campaign_id 缺失/非法、recorded_at 非法 → 抛 `ValueError`（上层收集器记 errors 失败隔离）；
- recorded_at 缺省 → 当前 UTC；带偏移字符串转 UTC（"2025-01-01T08:00:00+08:00"→UTC 00:00）；
- 其余字段缺失/非法 → 默认值（impressions=0、金额=0、诊断/状态=unknown）。

### 5. `CollectResult`（dataclass）
`collected`（解析成功进入入库流程行数 = upserted + skipped）/ `upserted` / `skipped` /
`errors`（`[{row: 行号1起, reason: 原因, raw: 脱敏原始行}]`）。

### 6. `SnapshotCollector(session, db=None)`
- `run_once(rows) -> CollectResult`：逐行 parse → `repo.upsert_snapshot`（幂等：同
  (campaign_id, recorded_at) 只更新不新增）；**每行独立 savepoint（begin_nested）**，
  解析/入库失败记 errors 继续下一行（失败隔离，不整批崩）；
- `collect_missing(campaign_ids, since=None, rows=None) -> CollectResult`：断点补快照——
  只处理 campaign_id ∈ campaign_ids 且 recorded_at ≥ since 的行；已存在→skipped、缺失→补齐；
  批内同周期重复行仅首次 upsert；**rows=None（无数据源）返回空结果不报错**（本层纯数据驱动，
  调度器集成时由真实读取适配器传入页面行，接口不变）；
- `next_run_hint(interval_s=None, last_run_at=None) -> datetime`（类静态方法 + 模块级函数）：
  下次回读建议时间（UTC 带时区）；interval_s 缺省 → `config.report_interval_s`（只读默认，
  不修改配置）；last_run_at 缺省以当前 UTC 为基准。**本层不做真实定时器**（调度归后续集成/总控）。
- `commit()`：显式提交会话（调度器集成用；fixtures 阶段提交由调用方负责，与 repo 层一致）。

### 7. 与 repo / config 对接
- 复用 `repo.upsert_snapshot`（幂等 upsert，唯一约束 uq_snapshot_campaign_time）、
  `repo.list_snapshots(campaign_id)`（collect_missing 预取已存在时间集，SQLite 读回 naive 用
  `models.ensure_aware` 补 UTC 统一比较）；
- `config.py` **零改动**（无需新增字段；report_interval_s 既有字段只读作默认间隔）；
- 入库参数与 `AdReportSnapshot` 字段一一对应（金额分、时间 UTC、枚举英文）。

---

## 三、测试结果

命令（P-001 + P-011：独立 basetemp `.pytest-tmp-m5`，未共用 `.pytest-tmp`）：

```
python -m pytest tests/test_ads_report.py -q --basetemp=".pytest-tmp-m5"
→ 24 passed in 0.84s（无 warning，含 -W error 导入检查）

python -m pytest tests/test_ads_report.py tests/test_ads_repo.py tests/test_ads_tables.py -q --basetemp=".pytest-tmp-m5"
→ 51 passed（不破坏既有）

python -m pytest tests/test_ads_report.py tests/test_ads_repo.py tests/test_ads_tables.py tests/test_ads_settings.py tests/test_ads_executor.py -q --basetemp=".pytest-tmp-m5"
→ 101 passed（全量 ads 套件回归）

python -c "from ads.report import SnapshotCollector, parse_snapshot_row, normalize_diagnosis, parse_amount_fen"
→ import ok
```

用例覆盖（24 个）：
- 诊断归一化 3：全枚举 / 未知·空·0项 / 空白容忍（正则 N项）；
- 状态归一化 3：全枚举（含暂停变体）/ 未知·空 / 空白容忍；
- 金额解析 4：元字符串×100 / 千分位 / 数值按分直取 / 非法默认（含自定义 default、bool）；
- 快照行解析 4：全字段映射（金额转分·枚举化·时区转 UTC·raw_json）/ 缺失字段默认 /
  recorded_at 变体（偏移·naive·Z·datetime·缺省 UTC）/ 非法输入抛 ValueError；
- run_once 4：正常入库（查库验证字段值）/ **幂等（同 (campaign_id, recorded_at) 两次 run
  仍 1 行且值更新）** / 解析失败隔离（errors 含行号+原因+脱敏 raw，其余成功）/
  入库异常隔离（monkeypatch 模拟 DB 失败，savepoint 回滚仅本行，其余成功）/ 空列表；
- collect_missing 4：已存在跳过（skipped）+ 缺失补齐 / since 过滤 / campaign 过滤 + 无数据源空结果 / 批内去重；
- next_run_hint 1：UTC aware、基于 last_run_at 精确偏移、config 默认间隔。

---

## 四、宪法与纪律自查

| 纪律 | 自查 |
|---|---|
| 一模块一库 | ✅ 测试只用 tmp_path 临时库（report-test.db），不读写其他模块库；app_config 只读未触碰 |
| 禁新增表 | ✅ 只使用既有 ad_report_snapshots（经 repo.upsert_snapshot），无 CREATE TABLE |
| 禁 git / 禁安装 | ✅ 未运行任何 git 命令，未安装任何软件 |
| 禁明文凭证 | ✅ 本任务不涉及凭证；errors 记录带 `_redact_raw` 轻量脱敏（截断 + 长串掩码） |
| 口径 | ✅ 金额=分 int（str 元→分、数值按分直取）；时间=UTC 带时区；枚举英文（诊断 5 值 / 状态 6 值） |
| 禁改既有 | ✅ 未改动任何既有文件（含 conftest.py 0 改动）；config.py 未追加字段 |
| UTF-8 无 BOM | ✅ write 工具 UTF-8，无 BOM，未用 PowerShell 写中文 |

---

## 五、偏差与说明

1. **`collect_missing` 增加可选 `rows` 关键字参数**（任务书签名 `(campaign_ids, since)` 保持兼容）：
   本层纯数据驱动，断点补快照的「重跑数据」需由调用方提供（fixtures 阶段=测试传入；真实阶段=
   读取适配器把页面行转同结构 dict 传入）；rows=None 时返回空结果，不报错。已在 docstring 注明。
2. **每行独立 savepoint（begin_nested）**：超出任务书最低要求，用于保证入库层异常（如 FK 冲突）
   也能单行隔离不整批崩（有专门用例覆盖）。
3. **`next_run_hint` 增加可选 `last_run_at`**：无此参数时以当前 UTC 为基准，满足任务书单参签名。
4. `0项待优化` 无对应枚举 → `unknown`（正则 N==1→optimize_1、N≥2→optimize_n，其余 unknown）。
5. 调度器（真实定时器）不在本任务范围，只提供幂等入口 + 建议时间，等待后续集成/总控编排。

---

## 六、给总工的验收提示

- 验收命令见「三、测试结果」（三组命令应全绿）；
- 幂等验收点：`test_run_once_idempotent_same_period`（同周期两次 run 仍 1 行且值更新）；
- 与并行子代理（止损引擎）边界：本模块 `normalize_diagnosis` 为独立实现，`stop_loss.py` 未触碰，
  联调时两处枚举口径一致（excellent/good/optimize_1/optimize_n/unknown）；
- 后续集成：真实读取适配器 → 页面行 dict → `SnapshotCollector(session, db).run_once(rows)` /
  `collect_missing(campaign_ids, since, rows)`，接口不变。
