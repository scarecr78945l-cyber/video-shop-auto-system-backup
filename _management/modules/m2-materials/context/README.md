# M2 自动收集素材 · 上下文库（context）

> 模块持久记忆，跨会话不丢失。任何代理（含子代理）开工前先读本目录。
> 本文件是**数据字典 + 外部契约 + 跨模块数据契约 + 环境事实**的唯一口径源。
> 铁律：禁止写明文密钥/Cookie/Token（只写环境变量名）。

---

## 一、数据字典

### 1.1 核心实体：Asset（素材库统一实体，对应 09 文档新增表 `assets`）

> 本模块实现为表 `asset_items`（宪法第 4 节前缀规则优先，见 decisions.md）。字段与 05 文档第四节完全对齐。

| 字段 | 类型（SQLite） | 必填 | 说明 | 取值/口径 |
|---|---|---|---|---|
| `id` | INTEGER PK AUTOINCREMENT | 是 | 素材主键 | 自增 |
| `asset_type` | TEXT | 是 | 素材类型 | `video` / `image` |
| `source_platform` | TEXT | 是 | 来源平台 | `video号` / `抖音` / `快手` / `小红书` / `淘宝` / `1688` / `考古加` / `有米云`（视频号统一写作"视频号"） |
| `source_url` | TEXT | 是 | 原始来源 URL | 非空，追溯与版权标记依据 |
| `source_author` | TEXT | 否 | 达人/作者标识 | 达人昵称或 id；尽量填 |
| `md5` | TEXT | 是 | 文件 MD5 | 32 位小写 hex；入库前必算 |
| `phash` | TEXT | 是 | 感知哈希 | 图片=整图 phash；视频=关键帧 phash（首/中/尾采样，存 JSON 数组或主帧值，见 1.2） |
| `file_path` | TEXT | 是 | 存储键/本地路径 | 当前=本地路径（`MATERIALS_STORAGE_DIR` 下相对键）；M4 迁 MinIO 后=MinIO 键（R-M2-22） |
| `duration` | INTEGER | 视频必填 | 时长（秒） | 单位：秒；硬规格 5~300 |
| `resolution` | TEXT | 视频必填 | 分辨率 | `宽x高`，如 `720x1280`；硬规格 ≥720×1280 |
| `size` | INTEGER | 是 | 文件大小（字节） | 单位：字节；硬规格 ≤500M（= 524288000 字节） |
| `tags_json` | TEXT | 否 | 标签 JSON | 类目/场景/达人标签数组，如 `["美妆","洁面","达人A"]` |
| `heat_score` | REAL | 否 | 来源热度 | 播放/点赞/销量折算参考值（来源不同量纲，入库时归一化 0~100） |
| `evaluation` | TEXT | 否 | 评估标签 | 枚举码：`exploring`（探索期）/ `efficient`（高效）/ `potential`（潜力）；由 M5 回写，M2 入库时为 NULL |
| `upload_status` | TEXT | 是 | 上传小店素材库状态 | `local`（默认）/ `uploading` / `uploaded` / `failed` / `disabled`（拒审下架） |
| `platform_material_id` | TEXT | 否 | 小店素材库 ID | M3 上传后回填；投放绑定用；唯一约束防重复上传 |
| `compliance_status` | TEXT | 是 | 内容预审状态 | `pending` / `passed` / `rejected`；入库前必须非 pending |
| `derivation_note` | TEXT | 否 | 二创义务标记 | 如 `去水印/混剪/换文案`；搬运素材必填 |
| `created_at` / `updated_at` | TEXT | 是 | 时间戳 | ISO8601 UTC（跨模块统一） |

### 1.2 双去重规则（唯一权威口径）

| 类型 | 指纹 | 判定 | 备注 |
|---|---|---|---|
| 视频 | ① 文件 MD5 ② 关键帧感知哈希（phash） | ① 精确判重：MD5 相同→重复（无论来源）；② 近似判重：采样首/中/尾 3 帧 phash，任意帧汉明距离 ≤ 阈值 → 疑似重复 | 转码/加轻微水印不改变语义 → 依赖 phash；阈值配置化，fixtures 离线校准后定默认值 |
| 图片 | 整图 phash | 汉明距离 ≤ 阈值 → 重复 | 复用 backend `sourcing/dedup.py` 的 `image_phash` 口径，保持跨模块一致 |

- **入库门禁**：`asset_dedup_fingerprints` 表对 (fingerprint_type, fingerprint_value) 唯一约束；并发认领机制对齐 `product_fingerprint_claims`（先认领后入库，防并发重复）。
- **重复处理**：命中重复 → 不入库，累加 `asset_items` 已有记录的来源计数（`dup_hits`，若需）或记 `asset_dedup_fingerprints.hits`；不静默丢弃，写日志留证据。
- **指纹值存储格式（子代理 E 定稿，见 decisions.md）**：md5=32 位小写 hex；image_phash=16 位小写 hex；video_phash=**JSON 数组字符串**（`["帧0hex","帧1hex","帧2hex"]`，数组下标=首/中/尾帧序号即帧标识），与 `asset_items.phash` 的 combined 值共用；检查器读取兼容 `{index}:{hex}` 与纯 hex。近似判重 = 任一候选帧与任一所存帧汉明距离 ≤ 阈值（默认 8，`config.dedup.phash_hamming_threshold` 配置化）。

### 1.3 素材硬规格（写死，投放/投稿共用；05 文档第三节）

| 项 | 要求 |
|---|---|
| 分辨率 | ≥720×1280 |
| 比例 | 9:16（竖屏） |
| 格式 | MOV / MP4 |
| 大小 | ≤500M（524288000 字节） |
| 时长 | 5 ~ 300 秒 |

- ffmpeg 输出参数锁定（示例）：`ffmpeg -i in.mp4 -vf scale=720:1280:force_original_aspect_ratio=decrease,pad=720:1280:(ow-iw)/2:(oh-ih)/2 -t 300 -c:v libx264 -crf 23 -c:a aac output.mp4`（实际按素材源微调，参数集中配置 `config.normalize`；比例校验容差 ±0.01 = `normalize.ratio_tolerance`，与 `normalizer.validate_specs` 模块常量同值，见 decisions.md 子代理 C 决策行）。
- 校验时机：入库（原始素材预检）与标准化后（成品复检）双校验；M5 绑定前再校验（P-007 防复发）。

### 1.4 评估标签取值（M5 回写，枚举唯一）

| 枚举码 | 中文 | 含义 |
|---|---|---|
| `exploring` | 探索期 | 素材刚投放/数据不足，处于测试阶段 |
| `efficient` | 高效 | 素材投放表现好（如 ROI/转化达标），优先复用 |
| `potential` | 潜力 | 有潜力但尚未达高效标准，可继续优化 |

- 写入口：`asset_evaluations` 审计表（每次回写留 evidence JSON 与来源批次）；`asset_items.evaluation` 只存当前值。
- M2 不主动写 evaluation；仅 M5 回写。拒审/源文件损坏 → `upload_status=disabled` + 记录拒审原因（非 evaluation）。

### 1.5 其他表（见 database/README.md DDL）

- `asset_download_jobs`：下载任务账本（状态/重试/节流/租约/证据）
- `asset_sources`：采集源与达人账本（游标/next_run_at/节流级/熔断）
- `asset_dedup_fingerprints`：去重指纹注册表
- `asset_evaluations`：评估标签回流审计
- `asset_compliance_checks`：内容预审记录（命中词/结果/证据）
- `asset_uploads`：上传小店素材库记录

---

## 二、外部契约

### 2.1 TikTokDownloader（抖音/快手/小红书）

- 定位：外部 CLI 进程，仅用于**抖音/快手/小红书**；**不用于视频号**（R-M2-05，视频号自研）。
- 调用方式：子进程调用 + 超时 + 输出 JSON 解析；版本锁定（requirements 固定版本，升级需回归测试）。
- 能力：批量关键词搜索下载 / 达人主页下载；输出目录与命名规范由本模块控制。
- 失败分类：进程超时→`TIMEOUT`；输出无结果→`NO_MATCH`；频控/风控→`RATE_LIMIT`；签名失效→`PLATFORM_REJECT` 记录证据。

### 2.2 视频号采集器（自研，签名+直链）

- 分层：页面层（Playwright 共享浏览器 CDP 拿作者/视频信息）→ 直链解析层（`signer.py` 接口化，签名算法独立可替换）。
- 输出：视频直链 URL + 元数据（作者/标题/播放热度）。
- 失败分类：登录失效→`AUTH_REQUIRED`（人工接管）；签名失效→`PLATFORM_REJECT`（改 signer 后重试）；无结果→`NO_MATCH`。

### 2.3 淘宝/1688 商品视频与同款图

- 复用半成品：`fetch_taobao_references.py`（淘宝同款图）/ `fetch_1688_images.py`（1688 图/视频）。
- 浏览器：共享 Chrome（CDP 9222，登录态在共享 profile）。
- 选择器/URL 全配置化；`page_changed` 检测留证据。

### 2.4 考古加/有米云榜单图（IMAGE_CACHE）

- 采集候选时顺带缓存；缓存键=榜单 id+商品 id；仅缓存图片，不爬榜单以外的页面。

---

## 三、跨模块数据契约

> 口径以本文件为准。所有交接走宪法第 5 节：data-requests 登记 → data-audit 审计 → `_management/data-exchange/<交换名>.json` 签字。

### 3.1 向 M3 素材优化提供（原始素材）

| 字段 | 口径 |
|---|---|
| `asset_id` | 素材主键 |
| `asset_type` / `source_platform` / `source_url` | 同数据字典 |
| `file_path` | 原始素材存储键（M3 拉取二创原料） |
| `tags_json` / `heat_score` | 二创选题参考 |
| `derivation_note` | 二创义务提示 |

### 3.2 向 M4 上架提供（图片素材）

| 字段 | 口径 |
|---|---|
| `asset_type=image` 的素材 | 同款图/榜单图，作为上架主图/详情参考（正式主图由 M3 生图链路产出） |
| `compliance_status` | 必须 `passed` 才能对外提供 |

### 3.3 与 M5 投放联动（双向）

| 方向 | 字段 | 口径 |
|---|---|---|
| M2→M5 | 素材查询/绑定：`asset_id`、`file_path`、`platform_material_id`、`upload_status=uploaded`、规格字段 | 仅 `uploaded` 且规格合格素材可绑定 |
| M5→M2 | 评估标签回写：`asset_id` + `evaluation`（exploring/efficient/potential）+ 证据 | 写 `asset_evaluations` 审计 + 更新 `asset_items.evaluation` |
| M5→M2 | 拒审/源文件损坏标记 | `upload_status=disabled` + 拒审原因记录 |

### 3.4 与 M0 基座

- 读取：`workflow_jobs`（任务入队/状态）、`app_config`（节流/阈值/白名单配置）、`logs`。
- 写入：任务与日志经总控协调；本模块不直接写基座表。

---

## 四、环境事实

| 项 | 值/约定 |
|---|---|
| 模块库 | `backend/data/db/m2-materials.db`（SQLite 开发；生产 PostgreSQL，迁移脚本在 `database/`） |
| 表前缀 | `asset_*`（本模块全部表） |
| 环境变量 | `MATERIALS_DB_URL`（默认 sqlite:///m2-materials.db）、`MATERIALS_STORAGE_DIR`（素材存储根目录）、`MATERIALS_CHROME_PATH`、`MATERIALS_LOG_LEVEL`、`MATERIALS_FFMPEG_PATH`、`MATERIALS_DOWNLOAD_CONCURRENCY`（前缀 `MATERIALS_`，值不入库不写文档） |
| 共享 Chrome | CDP 9222（共享 profile；视频号/淘宝/1688）；独立浏览器见 sourcing（youmi 9230 / doudian 9231），本模块尽量复用共享，不重复开页（P-002） |
| 下载中台 API 端口 | 默认 **8788**（`--port` 可覆盖）；**8787 已被工作区 captcha-vision-gateway 占用**，禁止使用（P-008） |
| ffmpeg | 版本待确认（11 文档前置条件）；启动探测，缺失即报错不静默 |
| Python | 3.12；Node 20+（前端素材库页） |
| 测试 | pytest 必须带 `--basetemp=".pytest-tmp"`（P-001） |
| 文件编码 | **所有文本文件一律 UTF-8 无 BOM**：用 write/edit 工具写；禁止 PowerShell `Add-Content`/`Set-Content`/`>` 写中文（PS 5.1 默认 ANSI/GBK 污染）；必须用 PowerShell 写时用 `[System.IO.File]::WriteAllText($path, $content, (New-Object System.Text.UTF8Encoding($false)))`（宪法第 11 节） |
| fixtures | 离线样本目录（对齐 sourcing/fixtures 模式），零登录态零网络可跑通全链路 |
