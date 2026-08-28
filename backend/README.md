# 自动选品模块（sourcing）

视频号微信小店全自动系统 — **自动选品**链路的可运行实现。

对应方案文档 `../04-自动选品模块设计.md`：三源采集 → 去重 → 合规三态 → 数据补全 → 打分（五维）→ TopN 入池，与上架/托管投放形成闭环。

## 目录结构

```
backend/
├── sourcing/                  # 选品模块包
│   ├── config.py              # 配置（环境变量 SOURCING_*，全部偏好可配置化）
│   ├── models.py              # 领域模型（SourceItem / ProductCandidate / ScoreBreakdown …）
│   ├── tables.py              # ORM 表（对齐 09 文档表清单）
│   ├── db.py                  # SQLAlchemy 引擎（SQLite 开发 / PostgreSQL 生产）
│   ├── repo.py                # 数据访问（账本/商品/指纹/配置）
│   ├── compliance.py          # 合规三态 + 标题清洗 + 类目白名单
│   ├── dedup.py               # image_phash + source_core_attributes_hash + 来源合并
│   ├── scoring.py             # 五维打分（权重折算 + 逐条可解释 reasons）
│   ├── pricing.py             # 定价阶梯（成本→售价）
│   ├── pipeline.py            # 流水线编排（采集→去重→合规→补全→打分→入池）
│   ├── scheduler.py           # 调度器（账本/节流/熔断/降频/断点续跑）
│   ├── cli.py                 # 命令行
│   └── collectors/            # 采集器（商机中心/有米云/抖店罗盘/1688/淘宝 + fixtures 离线）
├── fixtures/                  # 离线样本数据（零登录态跑通全链路）
├── tests/                     # 测试套件（41 用例）
└── requirements.txt
```

## 快速开始

```bash
cd backend
pip install -r requirements.txt

# 1) 建表（默认 sqlite:///data/db/m1-sourcing.db，生产设 SOURCING_DB_URL=postgresql+psycopg2://…）
#    开发库文件在 backend/data/db/m1-sourcing.db，不入 git（*.db 已在 .gitignore 排除）
python -m sourcing init-db

# 2) 跑一次完整流水线（离线 fixtures 模式，零登录态零网络）
python -m sourcing run-pipeline --mode fixtures --top-n 20

# 3) 查看商品池（按得分排序）
python -m sourcing pool --limit 20

# 4) 查看单个商品完整打分理由
python -m sourcing score --product-id 1

# 5) 人工复核闸门：manual_review → pool
python -m sourcing gate-confirm --product-id 7

# 6) 调度器：单轮 / 常驻（独立进程）
python -m sourcing scheduler --once
python -m sourcing scheduler --loop --interval 60
```

运行测试：

```bash
cd backend
# 注意：必须带 --basetemp=".pytest-tmp"（踩坑日志 P-001：本机默认临时目录 WinError 5 无权限）
python -m pytest tests -q --basetemp=".pytest-tmp"
```

## 五维打分模型

| 维度 | 满分 | 说明 |
|---|---|---|
| 热度趋势 | 35 | 榜单排名 + 销量 + 多榜交叉确认加分 |
| 利润率 | 30 | (建议售价 − 真实成本) / 建议售价，成本取 1688 逐 SKU 询价最低有效方案 |
| 售后风险 | 20 | 退货率 ≤3%→20，≤8%→16，≤15%→8，更高→0 |
| 供给稳定 | 15 | 1688 供应商数分档 |
| 投放转化 | 10 | 类目历史托管 ROI 回写；**无数据时不生效，权重从其他四维折算（和仍为 100）** |

> 权重折算细节见 `scoring.py`：基础四维满分和 = 100；投放转化 10 分从其他四维按 (100−10)/100 折算，
> 对应里程碑 M2「数据结构先行，无数据时权重=0 不生效」。每个维度打分理由写入 `reasons`，逐条可解释。

## 合规三态

- `hard_reject`：品牌侵权词 / 禁售词 / 功效资质缺失 → 直接拒
- `candidate`：进商品池
- `manual_review`：疑似功效词 / 类目不在白名单 → 人工闸门确认后入池

类目白名单为**配置项**（`config.category_whitelist`，默认 9 类），后台可经 `app_config` 表增删。

## 调度器机制（对齐 09 文档第三节）

- 账本：每（平台,榜单）游标 / `next_run_at` / `completed_for_date` / 空转计数 / 节流级
- 节流：失败 → throttle 0~4 级，退避 `throttle_base_seconds × 2^level`（默认 30s 起）
- 熔断：连续失败 ≥2 → `risk_control` 暂停整平台，探针板恢复
- 实时榜降频：连续空转 24 次 → 小时轮询降日轮询；静态榜扫完当天跳过
- 断点续跑：`resume_on_startup()` 进程重启后自愈（生产接入 systemd）

## 采集源

| 来源 | 实现 | 浏览器 | 说明 |
|---|---|---|---|
| 视频号商机中心 | `collectors/opportunities.py` | **共享浏览器（CDP 9223）** | 机会品（✅ 已实测打通，按类目筛选） |
| 有米云 | `collectors/youmi.py` | **独立特制浏览器（CDP 9555）** | 商品销售榜（✅ 已实测打通，动态列定位+textContent） |
| 抖店电商罗盘 | `collectors/doudian.py` | **共享浏览器（CDP 9223）** | 商品榜单 rank-product（✅ 已实测打通，Aurora 表格） |
| 1688 | `collectors/alibaba.py` | 共享浏览器（CDP 9223） | 以图搜款 + 订单确认页逐 SKU 询价（不下单） |
| 淘宝 | `collectors/taobao.py` | 共享浏览器（CDP 9223） | 同款参考素材收集 |

### 接入真实数据

```bash
# 1) 启动缺失的浏览器（已有浏览器自动跳过；有米云 9555 独立特制浏览器已就绪）
python -m sourcing launch-browsers

# 2) 确认各浏览器登录情况（显示每个端口浏览器打开的页面）
python -m sourcing probe-browsers

# 3) 在共享浏览器（9223）登录：视频号商机中心 / 抖店电商罗盘 / 1688 / 淘宝

# 4) 跑真实采集（未登录的来源自动隔离，不阻塞全链路）
python -m sourcing run-pipeline --mode auto
python -m sourcing collect --source youmi --board 商品榜 --mode auto
```

选择器/URL 全部配置化（`config.<来源>.boards[].url_template` + `config.<来源>.selectors`）。
有米云按表头**动态定位列**（商品/价格/销量），标题渲染在隐藏 popover 里，已用 textContent 兼容。
页面改版只改配置、留证据（`page_changed` 检测），不崩代码；开发/测试走 `fixtures` 离线模式。

### 选择器校准工具

```bash
# 连接来源浏览器打开页面，输出类名统计 + 可见文本，用于校准 row/title/price 选择器
python -m sourcing inspect-page --source youmi --url "https://console.youshu.youcloud.com/goods/sale"
```

## 配置（环境变量前缀 `SOURCING_`）

| 变量 | 默认 | 说明 |
|---|---|---|
| `SOURCING_DB_URL` | `sqlite:///data/db/m1-sourcing.db` | 开发默认 SQLite（`backend/data/db/m1-sourcing.db`，不入 git）；生产切 PostgreSQL |
| `SOURCING_CHROME_PATH` | 空 | 系统/便携 Chrome 路径（`launch-browsers` 用） |
| `SOURCING_LOG_LEVEL` | `INFO` | 日志级别 |

各来源浏览器端口/登录态在 `config.py` 里按来源配置（`<来源>.cdp_port` / `<来源>.profile_dir`）：
- 视频号商机中心 / 1688 / 淘宝 → 共享 Chrome（9222）
- 有米云 → 独立浏览器（9230，`profile_dir="youmi"`）
- 抖店电商罗盘 → 独立浏览器（9231，`profile_dir="doudian"`）
