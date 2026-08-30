# M1 自动选品 · 上下文库（context）

> 模块持久记忆，跨会话不丢失。本目录维护：数据字典、外部契约、跨模块数据契约、环境事实。
> **禁止写明文密钥/Token/Cookie**。基线领域模型源码：`backend/sourcing/models.py`（本文为其文档化镜像，代码变更须同步本文）。

---

## 一、数据字典

### 1. `SourceItem` — 榜单原始条目（三源通用）
| 字段 | 类型 | 单位/取值 | 说明 |
|---|---|---|---|
| `source` | str | `opportunities`/`youmi`/`doudian`（选品三源）；`alibaba`/`taobao`（补全源） | 来源标识（**M1 内部唯一锚点之一**） |
| `board` | str | 榜单名（如 `商品榜`/`机会品`/`飙升榜`） | 与 `source` 构成账本主键 |
| `platform_item_id` | str | 平台原始 ID | 与 `source`+`board` 构成 `core_key = f"{source}:{board}:{platform_item_id}"`（唯一性判定用） |
| `title` | str | — | 原始标题（未清洗） |
| `price` | float | **元** | 平台展示价；采集器负责从分/字符串转元 |
| `sales` | int | 件 | 榜单销量（口径=平台展示销量，非成交额） |
| `rank` | int | 名次 | 榜单排名，0=无 |
| `category` | str | 类目名 | **类目口径锚点**（见跨模块契约 C-1）；可为空 |
| `image_urls` | list[str] | URL | 首图/图集（去重 phash 输入） |
| `raw` | dict | — | 原始证据 JSON；入库前裁剪敏感字段（R-52） |
| `collected_at` | datetime | UTC | 采集时间 |

### 2. `ProductCandidate` — 流水线产物（持久化为 `products` 表）
| 字段 | 类型 | 说明 |
|---|---|---|
| `fingerprint` | str(64) | 属性指纹（`source_core_attributes_hash`），去重+防并发主键 |
| `image_phash` | str(64) | 图像感知哈希 |
| `title` / `sanitized_title` | str | 原始/清洗后标题（`compliance.sanitize_title`） |
| `category` | str | 合规判定后的类目（含匹配白名单） |
| `platform_price` | float 元 | 平台参考价 |
| `real_cost` | float 元 \| None | 1688 询价最低有效成本（未询价=None） |
| `suggested_price` | float 元 \| None | `pricing.py` 阶梯建议售价 |
| `profit_margin` | float \| None | 毛利率 (售价-成本)/售价 |
| `sales` / `rank_best` / `board_count` | int | 合并后销量/最优排名/多榜交叉数 |
| `source_items` | list[SourceItem] | 多源合并证据 |
| `quotes` | list[Quote] | 询价明细（`sku` 表） |
| `supplier_count` | int | 有效供应商数（供给稳定维度输入） |
| `return_rate` | float \| None | 退货率（售后风险维度输入；当前无平台数据源，默认 None→中间档 10 分） |
| `compliance` | ComplianceResult | `state` ∈ `hard_reject`/`candidate`/`manual_review` + `reasons` |
| `score` | ScoreBreakdown | 五维打分（JSON 落库 `score_breakdown`） |
| `ad_conversion` | dict | 命中类目的投放转化数据（`{roi, sales}`，快照元数据见 C-2） |
| `state` | str | `pool`/`manual_review`/`rejected`（M4 上架后由 M4 在交换层回写状态，本表只维护选品态） |

### 3. `ScoreBreakdown` / `ScoreDimension` — 打分结构与五维字段
| 字段 | 类型 | 说明 |
|---|---|---|
| `total` | float | 归一化后总分（和=100） |
| `dimensions` | dict[str, ScoreDimension] | key ∈ 五维 |
| `note` | str | 参与维度数说明（如「投放转化无数据」） |
| `ScoreDimension` | — | `key`/`label`/`raw`(原始分)/`weight`(归一化权重)/`weighted`(加权分)/`active`(是否参与)/`reasons`(逐条理由) |

**五维字段表（满分与数据来源）**
| key | label | 满分（默认） | 输入字段 | 数据来源 |
|---|---|---|---|---|
| `trend` | 热度趋势 | 35 | rank/sales/board_count | 考古加·有米云·商机中心（含抖店罗盘）榜单 |
| `profit` | 利润率 | 30 | real_cost/suggested_price/platform_price | 1688 询价（无询价按平台价 45% 估算，回填重算） |
| `after_sale` | 售后风险 | 20 | return_rate | 平台数据（当前缺源→中间档 10，标记待回填） |
| `supply` | 供给稳定 | 15 | supplier_count | 1688 供应商数 + 多榜同源数 |
| `ad_conversion` | 投放转化 | 10（可配） | ad_roi/ad_sales | **M5 托管报表回写**（无数据 → `active=False`，权重折入四维，和仍=100） |

> 权重折算实现：`scoring.py`。`ad_conversion_weight` 默认 10；有数据时基础四维 ×(100−10)/100。

### 4. 其他实体
- `Quote`：`supplier_name`/`sku_name`/`unit_cost`(元)/`min_order`/`freight`/`raw_url`(真实链接才算有效)/`quoted_at`；`effective_cost = unit_cost`。
- `BoardRunState`（账本）：`source`+`board` 唯一；`cursor`/`next_run_at`/`completed_for_date`/`empty_run_count`/`throttle_level`/`consecutive_failures`/`status`(`active`/`risk_control`/`waiting_login`/`waiting_verification`)/`last_error`。
- 错误码（复用 09 文档）：`VERIFICATION_REQUIRED`/`AUTH_REQUIRED`/`RATE_LIMIT`/`TIMEOUT`/`NO_MATCH`/`PLATFORM_REJECT`/`UNEXPECTED`。

## 二、外部契约（采集源）

> 无官方 API（R-10）。全部 Playwright + CDP，选择器/URL 配置化于 `config.py`。

| 来源 | 浏览器 | CDP 端口 | profile_dir | 契约要点 |
|---|---|---|---|---|
| 商机中心 | 共享 Chrome | 9223 | shared | 机会品列表；登录 `store.weixin.qq.com`；静态榜日扫 |
| 有米云 | 独立特制浏览器 | 9555 | youmi-portable | 商品榜动态列定位 + popover textContent；URL 带日期参数模板 |
| 抖店罗盘 | 共享 Chrome | 9223 | shared | rank-product 榜单（Aurora 表格） |
| 1688 | 共享 Chrome | 9223 | shared | 以图搜款 + 订单确认页询价，**只读不下单** |
| 淘宝 | 共享 Chrome | 9223 | shared | 同款参考素材（图片 URL 列表） |
| 考古加（kaogujia） | 待定 | 待定 | 待定 | **第四源备胎（REC-006）**：config.py 已登记 5 榜 URL（实时销量榜/视频热推荐榜/商品热销榜/商品数据大盘/往年爆款，源旧系统 kaogujia_board_catalog.py），`enabled=False` 未启用；采集器未实现，启用前置=采集器+登录态+选择器校准（D-11） |

- 环境变量：`SOURCING_DB_URL`/`SOURCING_LOG_LEVEL`/`SOURCING_CHROME_PATH`（只列名称，值不入库不落文档）。

## 三、跨模块数据契约

### C-1 类目口径（锚点）
- 本模块 `products.category` 为类目锚点；白名单 9 类（`config.DEFAULT_CATEGORY_WHITELIST`）。
- 规则：平台类目与白名单做**包含匹配**；M5 回写按「与 `products.category` 完全一致」的类目名聚合。
- **app_config 键名（REC-010/DA-008 定稿）**：运行时白名单经 app_config 键 **`category.whitelist`**（list[str]）覆盖 config 默认，读取入口 `pipeline._load_category_whitelist`（点分隔命名空间，与 M0 基准一致）；`config.category_whitelist` 为代码配置字段（环境变量 SOURCING_CATEGORY_WHITELIST 可覆盖），两者语义不同勿混淆。`scoring.weights`（打分权重 app_config 键）后续迭代接入，当前权重走 `config.scoring`。**S5 闸门放松键 `gate.relax.*`（enabled/min_samples/pass_rate/window_days/categories）同为点分隔命名空间（DA-008 纪律），键名权威见 `backend/sourcing/gate.py`，口径/用法见本文第七节**。
- 待总控确认：类目名统一表放 `_management/data-exchange/category-registry.json`（D-3 决策）。

### C-2 M5 → M1：投放转化回写（输入契约草案）
- 载体：`_management/data-exchange/m5-ad-conversion.json`（M5 总工产出，双方在文件头签字）。
- **口径对齐（重要）**：M5 context 约定「金额统一「分」int、时间 UTC+8」——本契约对齐该口径：`sales_amount` 单位为**分**（int）；时间戳 ISO-8601 带时区（建议 +08:00 与 M5 一致，或 UTC 但必须显式标注）；`roi` 为比值无量纲。**禁止出现金额单位混用（元/分）。**
- 结构：
```json
{
  "schema_version": 1,
  "period": {"start": "2026-08-01", "end": "2026-08-31"},
  "generated_at": "2026-09-01T00:00:00+08:00",
  "data": {
    "收纳整理": {"roi": 3.2, "sales_amount": 12800000, "sample_count": 34},
    "宠物用品": {"roi": 2.4, "sales_amount": 8600000, "sample_count": 21}
  }
}
```
- 字段口径：`roi`=期间托管成交额/花费（>0）；`sales_amount`=成交额（**分**，int）；`sample_count`=计入商品数（<5 建议视为弱样本）；`generated_at` 用于**数据新鲜度判定**（>7 天视为无数据，R-14）。
- 导入端：M1 `ad_backfill.py`（幂等：以 `period+generated_at` 为唯一键，重复导入覆盖）→ `m1_ad_conversion_cache`。
- 无文件/无数据时：打分维度自动不生效（已实现），**不报错**。
- 待总控确认：`sales_amount` 口径最终以 M5 总工签发的契约为准（BLOCKER-003）。

### C-3 M1 → M4：商品池出池（输出契约草案）
- 载体：`_management/data-exchange/m1-pool-<YYYYMMDD>.json`（每日快照）或总控裁定的只读视图。
- 结构草案：
```json
{
  "schema_version": 1,
  "generated_at": "2026-09-01T00:00:00Z",
  "items": [
    {"product_id": 101, "fingerprint": "…", "title": "…", "sanitized_title": "…",
     "category": "收纳整理", "platform_price": 29.9, "real_cost": 8.5,
     "suggested_price": 19.9, "score": 82.3, "score_breakdown": {…},
     "image_urls": ["…"], "source_evidence": [{"source": "youmi", "board": "商品榜", "item_id": "…"}],
     "quotes": [{"supplier_name": "…", "unit_cost": 8.5, "sku_name": "…"}],
     "taobao_reference_urls": ["…"]}
  ]
}
```
- M4 消费字段：`product_id`/`sanitized_title`/`category`/`suggested_price`/`image_urls`/`quotes`（逐 SKU 定价）/`score`（排序参考）。口径变更由双方总工共同签字后生效。

### C-4 M1 → M2：淘宝参考素材（输出）
- 载体：`products` 证据表 `taobao_reference_urls`（或 C-3 快照内字段）；M2 按 `product_id` 取用，仅限可二创来源（10 文档第三节素材版权）。

## 四、环境事实
| 项 | 值（不含密钥） |
|---|---|
| 模块库 | `backend/data/db/m1-sourcing.db`（SQLite 开发；生产 PostgreSQL） |
| 默认库 | `sqlite:///data/db/m1-sourcing.db`（backend 相对路径，S1a 已切换 REC-007） |
| fixtures 目录 | `backend/fixtures/`（6 个 JSON：三源+询价+淘宝+ad_snapshots） |
| 共享浏览器 CDP | 9223（商机中心/抖店罗盘/1688/淘宝） |
| 有米云浏览器 CDP | 9555 |
| 浏览器资料目录 | `backend/data/chrome-profiles/`（不入 git） |
| pytest | `python -m pytest tests -q --basetemp=".pytest-tmp-m1"`（**P-001 + P-011/宪法第 12 节**：独立 basetemp，避免并行代理共享清理抖动；全量回归由总控统一执行） |
| 测试基线 | sourcing 域 91 passed（S3a 复核：既有 85 + test_page_changed 6 新增，独立 basetemp `.pytest-tmp-m1` 全绿）；全量含 M0 foundation 4~5 个既有失败（跨模块已知，勿修） |
| 依赖 | Python 3.12、Playwright、pydantic v2、SQLAlchemy、pydantic-settings |

### 环境探测快照（S3a 实测，体系建立日）
| 项 | 值（不含密钥） |
|---|---|
| Python 实测 | 3.13.14（`python --version`，2026 环境；requirements 声明 3.12 兼容） |
| Playwright | 已安装，**1.61.0**（`python -m playwright --version`，≥1.44 满足） |
| Chrome 可执行文件 | `SOURCING_CHROME_PATH` 未设置；PATH 中无 `chrome/chromium/msedge`；标准路径存在：`C:/Program Files/Google/Chrome/Application/chrome.exe`（`cli._find_chrome` 首选命中）、`C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe` 兜底 |
| CDP 端口可达性 | **9223 ✓（共享浏览器）/ 9555 ✓（有米云）/ 9222 ✓（历史口径，config 未用）**，`socket.create_connection(timeout=2)` 实测 |
| launch-browsers 输出 | 幂等跳过：`浏览器已存在（跳过启动）：视频号商机中心 → CDP :9223`、`有米云 → CDP :9555`（未启动任何新浏览器） |
| probe-browsers 输出 | 5 来源全部 `CDP ✓`：共享 9223 打开页面含 `store.weixin.qq.com/shop/home`（商机中心）、`compass.jinritemai.com/shop` 与 `/shop/chance/rank-product`（抖店罗盘）；有米云 9555 打开 `console.youshu.youcloud.com/goods/sale?site_id=10502&...`（与 config url_template 一致） |
| 浏览器可用性 | **浏览器已启动且持有登录态页面（商机中心/抖店罗盘/有米云）**；1688/淘宝共享同一 9223 浏览器（采集时新开标签页）。真实采集仍待登录态确认后由总控批准（S3 第二阶段） |
| 选择器校准 | 详见 `selector-log.md`（v1.0，S3a）：5 来源 config.selectors 均为空 → 生效选择器=代码 DEFAULT_SELECTORS；待实测项清单已登记 |

### S3c 真实采集联调实测（2026-08-29，总控批准，临时库验证）
| 项 | 结论（不含密钥） |
|---|---|
| 三源真实采集 | **全部成功入库（临时库 `backend/.pytest-tmp-m1/s3c.db`）**：商机中心 机会品 **1 条**（当前类目筛选下仅 1 条）、有米云 商品榜 **50 条**、抖店罗盘 商品榜 **50 条**；均状态 active、throttle 0、连续失败 0，**无 AUTH_REQUIRED / 验证码 / 风控事件** |
| 登录态有效性 | **三源登录态均有效**（商机中心/抖店罗盘共享 9223、有米云独立 9555；无 login_gate/verify_gate 触发）——S3a 预留的「真实采集待登录态确认」已确认通过 |
| 字段口径 | price=**元**（youmi 0.01~69.9、doudian 15~1580）、sales=**件**（youmi 10万~162万、doudian 1000~10万）、rank 正确；**category 三源恒空**（真实页面无类目列，与 fixtures 差异，R-25 确认）；商机中心 price/sales 恒 0（A5 确认） |
| 选择器/解析 | 有米云**动态列定位命中**（A4）；抖店罗盘**「价格带 ¥XX」解析 50/50 命中**、动态列定位命中；商机中心 row/columns/图片提取命中（imgs=2）；有米云 **imgs=0**（图片提取需收敛，见 selector-log A6 注） |
| 环境异常（已解决） | 共享 9223 曾因**僵尸页面**（商机中心 home / 罗盘核心数据页）导致 playwright connect_over_cdp 挂起（HTTP /json 正常但 ws 无响应）；经 CDP `/json/close` 关闭多余页面后恢复——**已登记 pitfall-log P-016** |
| 脱敏 | 临时库 raw_json 裁剪干净，日志无明文 cookie/token/session/password/secret/authorization（脱敏验证 PASS） |
| 安全边界 | 未点击验证码/滑块、未重试风控源、未下单、未读取 cookie/localStorage/凭据；临时库 s3c.db 保留在 `.pytest-tmp-m1/`（不入 git，供验收） |
| 选择器实测明细 | 详见 `selector-log.md` 各来源「实测结果（S3c）」小节；A2（动态日期）✅、A4（动态列定位）✅、A5（恒空确认）✅、A3（飙升榜 URL）仍待回填、A6（alibaba/taobao）待后续 |

### P-016 防复发：僵尸标签页清理（v1.1-③，zombie_clean）
- **背景**：CDP 9223 共享浏览器长期挂机积累僵尸标签页（渲染进程无响应，如商机中心 home `store.weixin.qq.com/shop/home`、罗盘核心数据页 `compass.jinritemai.com/shop`），playwright `connect_over_cdp` 初始化逐个 target Page.enable/Network.enable 时被卡死（HTTP /json 正常但 ws 无响应）——pitfall-log P-016。
- **能力**：`backend/sourcing/zombie_clean.py::clean_zombie_targets(port, keep_url_fragments=None)`——CDP HTTP `GET /json/list` 拉取 target 列表（短超时 4s），`GET /json/close/<id>` 关闭**非采集目标**的 http(s) 页面；幂等、容错（任何失败返回统计 dict 不抛异常）；全程不触碰登录态/凭据（cookie 在 profile，非页面内）。
- **保留规则**：
  - 9223 共享浏览器默认保留：`opprotunity`（商机中心机会品）、`rank-product`（罗盘商品榜）；
  - 9555 有米云默认保留：`console.youshu.youcloud.com`；
  - `--keep <片段>` 追加额外保留片段；browser_ui/devtools 等非页面 target 与 chrome:// about:blank devtools:// 等非 http(s) 页面一律跳过不报错；`/json/close` 对 browser_ui 返回 404 → 计数跳过不阻塞；
  - **防御**：找不到任何可保留的采集目标页（保留集为空）→ `safe_aborted=True`，不关闭任何页面；绝不触碰凭据/登录态。
- **用法**：
  ```bash
  python -m sourcing zombie-clean --port 9223            # 共享浏览器（默认）
  python -m sourcing zombie-clean --port 9555            # 有米云
  python -m sourcing zombie-clean --port 9223 --keep console.youshu.youcloud.com  # 追加保留
  python -m sourcing probe-browsers                      # 已内置 P-016 前置清理（探测前自动执行）
  ```
- **返回统计**：`{ok, port, targets_seen, pages_seen, kept, closed, close_failed, skipped, safe_aborted, closed_ids, errors, error}`。
- **测试**：`backend/tests/test_zombie_clean.py`（纯 mock CDP HTTP 层，**绝不真实连接 9223/9555**；覆盖列表解析/保留规则/404 与 browser_ui 跳过/幂等/防御性中止/失败容错）。

### S4 日有效候选度量（口径+用法，2026-09-01 实施）
- **目的**：对齐 04 文档验收标准「日有效候选 ≥200」的联调度量；实现于 `backend/sourcing/report.py::SourcingReport.daily_effective_candidates(days=N)`（只读查询）。
- **口径（实现内明确，测试锁定）**：
  - 「有效候选」= `products.state ∈ (pool, manual_review)`，按 `created_at` 的 **UTC 日期（YYYY-MM-DD）** 分组计数；`rejected` 及未知状态**不计**。
  - 每日采集事件数 = `source_collection_events.created_at` 按 UTC 日计数；每日运行 = `source_runs.started_at` 按 UTC 日计数（`ok_runs` 为 `ok=True` 数）。
  - 达标判定：`effective_candidates >= DAILY_EFFECTIVE_TARGET(200)` → `target_met=True`；`gap = max(0, 200 - effective_candidates)`（达标日 `gap=0`）。
  - 窗口：最近 N 天滚动窗口（切点 `>= now - N 天`，与 `weekly()` 一致）；**首/末日可为不完整日**（UTC 日粒度对齐，非自然日对齐）。
  - **空数据 → `daily=[]`，不抛异常**。
- **输出结构**：
```json
{"period_days": 7, "generated_at": "2026-09-01T00:00:00Z",
 "daily": [{"date": "2026-08-31", "collected_events": 101, "runs": 3,
            "ok_runs": 3, "effective_candidates": 205,
            "target_met": true, "gap": 0}]}
```
- **用法**：
  - Python：`SourcingReport(db).daily_effective_candidates(days=7)`（时间 UTC）。
  - CLI：`python -m sourcing report-daily --days 7 [--json-out PATH]`（backend 目录下）。
  - 测试：`backend/tests/test_report_daily.py`（跨日分组 / state 过滤 / 达标边界与 gap / 空数据 / CLI 冒烟）。

## 五、本目录文件索引
- `README.md`（本文）
- `data-requests.md`（跨模块数据需求登记，宪法第 5 节）
- `selector-log.md`（**S3a 建立**：5 来源选择器校准记录 + 待实测项清单 + 校准动作建议 A1~A6；**S3c 已追加三源真实采集实测小节与 A2/A4/A5 验证结论**）
- （后续：`category-registry.md` 类目映射表——S3 阶段建立）

## 六、P2 数据知识吸收（2026-08-29，P2-6/P2-7）

### P2-6 旧系统榜单目录知识档案（config.py 已登记，全部 disabled）
- **考古加（第四源备胎，REC-006/D-11）**：5 榜（`kaogujia.boards`，`enabled=False`）——
  实时销量榜 `https://www.kaogujia.com/liveTopList/douyinProductList/realSales`
  ｜ 视频热推荐榜 `.../videoRecommendList` ｜ 商品热销榜 `.../hotSales`
  ｜ 商品数据大盘 `https://www.kaogujia.com/productMarket` ｜ 往年爆款 `https://www.kaogujia.com/historyBestseller`；
  源：旧系统 `kaogujia_board_catalog.py`（page_size=50，旧节奏 interval=120min）；配套 `playwright_kaogujia.py` 32KB 分页逻辑（未移植，启用时按需吸收）。
- **抖店罗盘旧榜单目录**（doudian.boards 扩展 4 榜，`enabled=False` + url_template 留空）——
  商品卡榜/短视频榜/同行低退榜（static）/实时爆品挖掘榜（realtime）；
  旧系统为「3 类目（运动户外/个护家清/智能家居）× 3 时间窗（近1天/近7天/近30天）× 3 静态榜 + 1 实时榜」共 30 组合，URL 同为 rank-product 页内 tab 切换（`playwright_douyin_compass.py` 实证 COMPASS_URL 单一）；
  启用前置：罗盘页 tab 实测 + 类目/时间窗参数化 + 选择器校准（R-23）。

### P2-7 旧系统契约字段对照（models.py 已加对照注释，决策 D-10）
- `SourcedProduct` ↔ `SourceItem`：image_url→image_urls、name→title、sales_rank→rank、source_url→(source+board+platform_item_id)+raw["source_product_url"]、price_range(str 区间)→price(float 元)。
- `AlibabaMatch` ↔ `Quote`（匹配 vs 询价语义）：url→raw_url、purchase_price→unit_cost、missing_fields→missing_attrs（REC-迁移-02）、sku_summary→sku_name（近似）；旧系统独有未建模：score/material/dropshipping_supported/product_attrs/customer_service_questions/targets（归 M4 C2）/image_offer_candidates。
- `UploadResult` 属 M4 上架边界，M1 不建模。
- 结论：**以新系统命名为准**，不实际改名（108 测试 + 库 schema 稳定），差异仅登记防漂移。

## 七、S5 人工闸门按达标自动放松（v1.1+，gate.relax）

> 背景：R-54 人工闸门失效风险（全自动误放行高合规风险品）——高风险类目强制 `manual_review`；
> 10 文档第五节「选品复核」闸门可放松条件 = **该类目通过率连续达标（如 95% × 50 品）**。
> 本迭代将其落地为**配置化放松策略**（读 app_config 不写；默认不放松，行为零变化）。

### 7.1 app_config 键名表（点分隔命名空间，REC-010/DA-008 纪律，与 `category.whitelist` 同约定）
| 键 | 类型 | 默认 | 口径 |
|---|---|---|---|
| `gate.relax.enabled` | bool | `false` | 总开关；`false`=不放松（默认行为零变化，既有测试不回归） |
| `gate.relax.min_samples` | int | `50` | 最小样本数（窗口内 通过+拒绝 合计 ≥ 该值才可放行） |
| `gate.relax.pass_rate` | float | `0.95` | 通过率阈值（通过/(通过+拒绝) ≥ 该值才可放行，取值 (0,1]） |
| `gate.relax.window_days` | int | `30` | 统计窗口（天）：按 `products.created_at >= now - window_days` 计样本 |
| `gate.relax.categories` | list[str] | `[]` | 类目子集；空=全部类目参与，非空=仅这些类目可放松 |

> 键名权威实现：`backend/sourcing/gate.py`（`KEY_ENABLED` 等常量 + `load_gate_relax_config`）；
> 键缺失/类型非法/越界/异常 → 逐键回落默认（绝不抛异常，对齐 `_load_category_whitelist` 纪律）。

### 7.2 复核统计口径（10 文档第五节「通过率」落地）
- 窗口内该类目 `products`：**通过数 = `state='pool'`、拒绝数 = `state='rejected'`**（在途 `manual_review` 与 `hard_reject` 不计）；
- 样本数 = 通过 + 拒绝；通过率 = 通过 / 样本数（无样本 → 0）；
- **放行条件（全部满足）**：`enabled 且 样本数 ≥ min_samples 且 通过率 ≥ pass_rate 且 类目命中 categories 子集`；
- **保守边界**：空类目（未归类）一律不放松（无法按类目统计，R-54 兜底）。

### 7.3 实现与接线
- `backend/sourcing/gate.py`（新增）：
  - `should_relax_category(db, category, config) -> (bool, reasons)`——S5 核心判定（reasons 逐条可解释，对齐打分可解释纪律）；
  - `decide_relax(stats, category, config, subset=None)`——纯判定（无 IO）；
  - `compute_category_stats(db, category, config)` / `_stats_in_session`——复核统计；
  - `load_gate_relax_config(session)`——app_config 只读解析（含类型校验回落）；
  - `relax_manual_review(db, config=None, dry_run=True, categories=None, limit=None) -> RelaxReport`——存量 `manual_review` 商品判定/放行（dry-run 默认只报告）；
- `backend/sourcing/pipeline.py`：构造时读 `gate.relax.*`（`self.gate_relax`）；`run()`/`run_from_items()` 在人工复核前调用 `_relax_manual_review`——达标 manual_review 候选 `state → pool`（放行理由追加 `compliance.reasons` 落库审计），计数 `PipelineResult.gate_relaxed`；补全/打分/TopN 以 `state=='pool'` 为准（默认 enabled=false 时与 `is_candidate` 等价，零变化）；
- `backend/sourcing/cli.py`：`gate-relax`（缺省 dry-run 只报告）`/ --apply`（实际放行）`/ --category`（子集覆盖）`/ --limit`；
- `backend/sourcing/models.py`：`PipelineResult.gate_relaxed: int = 0`。

### 7.4 用法
```bash
# 1) 总控在 app_config 写入（本模块只读）：
#    gate.relax.enabled=true, min_samples=50, pass_rate=0.95, window_days=30, categories=[]
python -m sourcing gate-relax                        # dry-run：只报告不放行
python -m sourcing gate-relax --apply                # 实际放行达标类目 manual_review 商品
python -m sourcing gate-relax --category 家居日用     # 仅该子集
python -m sourcing run-pipeline --mode fixtures      # 新一批 manual_review 候选达标自动入池
```
- 测试：`backend/tests/test_gate_relax.py`（16 用例：未启用/样本不足/通过率不足/达标放行/dry-run/类目过滤/app_config 注入/类型回落/窗口过滤/空类目保守/pipeline 接线/CLI）。
- 回归：sourcing 域 17 文件 130 基线 + 16 新增 = 146 passed（`.pytest-tmp-m1`，2026-09-01 实测）。
