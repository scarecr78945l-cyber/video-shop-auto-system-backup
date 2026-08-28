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
| （考古加） | — | — | — | **未实现**，D-1 待总控决策 |

- 环境变量：`SOURCING_DB_URL`/`SOURCING_LOG_LEVEL`/`SOURCING_CHROME_PATH`（只列名称，值不入库不落文档）。

## 三、跨模块数据契约

### C-1 类目口径（锚点）
- 本模块 `products.category` 为类目锚点；白名单 9 类（`config.DEFAULT_CATEGORY_WHITELIST`）。
- 规则：平台类目与白名单做**包含匹配**；M5 回写按「与 `products.category` 完全一致」的类目名聚合。
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

## 五、本目录文件索引
- `README.md`（本文）
- `data-requests.md`（跨模块数据需求登记，宪法第 5 节）
- `selector-log.md`（**S3a 已建立**：5 来源选择器校准记录 + 待实测项清单 + 校准动作建议 A1~A6）
- （后续：`category-registry.md` 类目映射表——S3 阶段建立）
