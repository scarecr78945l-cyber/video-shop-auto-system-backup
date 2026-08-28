# M4 自动上架 · 上下文库（context）

> 模块的持久记忆，跨会话不丢失。任何代理重启后先读本目录。
> 必须维护：数据字典、API 契约、环境事实、跨模块数据契约。**禁止写明文密钥**（AppID/Secret 只写环境变量名）。
> 库：`backend/data/db/m4-listing.db`（SQLite，不入 git；生产切 PostgreSQL 见 database/README.md）。

---

## 一、数据字典（本模块库 listing_* 表）

> 完整 DDL 见 `../database/README.md`；此处记录字段语义/单位/主键来源，是代码与联调的口径基准。

### 1.1 `listing_tasks` — 上架任务（状态机主表）

| 字段 | 类型 | 说明 |
|---|---|---|
| `task_id` | TEXT PK | 上架任务 ID（= workflow_jobs.request_id 或 job_id，对接基座队列） |
| `product_id` | INTEGER | 商品 ID（基座 products 主键，来自 M1） |
| `generation_version` | TEXT | 商品素材/定价代次（幂等键组成之一，来自 M1/M3 版本号） |
| `stage` | TEXT | 流水线阶段：`listing_upload`（对接 workflow_jobs.stage） |
| `status` | TEXT | 状态机状态（见第二节枚举） |
| `gate_result` | JSON | 上架前校验硬门禁结果：{item: {passed, reason, evidence}} |
| `platform_spu_id` | TEXT | 平台 SPU ID（create_spu 返回，创建中暂空） |
| `product_link` | TEXT | 真实可访问链接（get_product_link 返回，**验证通过前为空**） |
| `link_verified_at` | DATETIME | 链接验证通过时间（已上架判据） |
| `reject_reason_code` | TEXT | 拒审原因分类码（见 listing_audit_records） |
| `attempts` | INTEGER | 已尝试次数（幂等重试/重新提交计数） |
| `lease_owner` / `lease_expires_at` | TEXT / DATETIME | 任务租约（45min 过期回收，沿用 09 文档） |
| `created_at` / `updated_at` | DATETIME | 时间戳（UTC，统一口径） |

- 唯一约束：`(product_id, stage, generation_version)` —— 幂等防重复入队（09 文档）。
- 断点续跑：按 status + lease 恢复；process 重启 `recover_after_process_restart`。

### 1.2 `listing_spus` — SPU 平台映射

| 字段 | 类型 | 说明 |
|---|---|---|
| `spu_id` | TEXT PK | 平台 SPU ID（微信返回，主键来源=平台） |
| `task_id` | TEXT | 关联 listing_tasks |
| `title` | TEXT | 标题（15–35 字符，已过门禁） |
| `category_id` | INTEGER | 类目 ID（app_config 类目白名单内） |
| `qualification` | JSON | 资质信息摘要（资质 ID/有效期，不含凭证原文） |
| `freight_template_id` | TEXT | 运费模板 ID（配置化） |
| `purchase_limit` | JSON | 限购设置：{per_user, period}（默认每月 2 件） |
| `status` | TEXT | 平台侧状态快照（草稿/审核中/已上架/驳回） |
| `audit_id` | TEXT | 提交审核返回的审核任务 ID |
| `created_at` / `updated_at` | DATETIME | 时间戳 |

### 1.3 `listing_skus` — SKU 平台映射

| 字段 | 类型 | 说明 |
|---|---|---|
| `sku_id` | TEXT PK | 平台 SKU ID |
| `spu_id` | TEXT | 关联 listing_spus |
| `product_sku_code` | TEXT | 本系统 SKU 编码（基座 sku 表主键，M1 逐 SKU 成本来源） |
| `price_cents` | INTEGER | 售价（**单位：分**，= pricing 差异化定价阶梯结果） |
| `cost_cents` | INTEGER | 真实成本（**单位：分**，1688 询价确认页；仅入库不对外） |
| `stock` | INTEGER | 库存（默认 10000，07 文档） |
| `purchase_limit` | JSON | 限购（默认每月 2 件） |
| `status` | TEXT | 平台 SKU 状态 |

### 1.4 `listing_upload_assets` — 上传历史（图片/详情图）

> 09 文档既有 `upload_history` 归属基座 M0（只读参照）；**本模块操作留痕以本表为准**，归属说明见 database/README.md。

| 字段 | 类型 | 说明 |
|---|---|---|
| `asset_id` | INTEGER PK | 自增 |
| `task_id` | TEXT | 关联 listing_tasks |
| `image_asset_id` | INTEGER | 源图片资产 ID（基座 image_assets 主键，来自 M3） |
| `file_sha256` | TEXT | 文件哈希（上传幂等去重键） |
| `media_id` | TEXT | 平台素材/媒体 ID（upload_image 返回，COS 直传后） |
| `usage` | TEXT | 用途：`main_image`（主图，5 张 1:1）/ `detail_image`（详情图） |
| `position` | INTEGER | 主图序号 1–5（详情图=0） |
| `status` | TEXT | `uploaded` / `failed` / `invalidated` |
| `evidence` | JSON | 上传响应脱敏摘要 |

### 1.5 `listing_op_logs` — 微信操作日志（证据留痕）

| 字段 | 类型 | 说明 |
|---|---|---|
| `log_id` | INTEGER PK | 自增 |
| `task_id` | TEXT | 关联 listing_tasks |
| `request_id` | TEXT | 请求幂等键（= task_id + 接口名 + 序号） |
| `api` | TEXT | 接口名：create_spu / create_skus / upload_image / submit_audit / query_audit_status / get_product_link / update_stock / update_price / update_spu |
| `direction` | TEXT | `request` / `response` |
| `payload_digest` | TEXT | 请求体脱敏摘要（SHA256 + 关键字段摘要，**无密钥/无敏感值**） |
| `status_code` | INTEGER | HTTP 状态码 |
| `error_code` | TEXT | WorkflowJob 错误码（见第四节） |
| `platform_code` | TEXT | 平台业务错误码（原样） |
| `evidence_json` | TEXT | 完整证据 JSON（响应原文，若含敏感字段则脱敏） |
| `created_at` | DATETIME | 时间戳 |

### 1.6 `listing_audit_records` — 审核记录（提交/轮询/驳回/拒审处理）

| 字段 | 类型 | 说明 |
|---|---|---|
| `audit_record_id` | INTEGER PK | 自增 |
| `task_id` | TEXT | 关联 listing_tasks |
| `audit_id` | TEXT | 平台审核任务 ID |
| `submit_at` | DATETIME | 提交审核时间 |
| `last_query_at` | DATETIME | 最近一次轮询时间 |
| `audit_status` | TEXT | 平台审核状态（审核中/通过/驳回，原样保留） |
| `reject_reason` | TEXT | 驳回原因原文 |
| `reject_category` | TEXT | 原因分类：`title` / `category` / `qualification` / `image` / `price` / `content_compliance` / `other` |
| `fix_candidate` | JSON | 自动修复候选：[{action: 改标题/重传图/补资质/改价, param, gate_required}] |
| `resubmit_required` | INTEGER | 是否需要二次门禁后重提（0/1） |
| `evidence` | JSON | 轮询/驳回证据 |

### 1.7 `listing_quota_states` — 接口配额状态（令牌桶）

| 字段 | 类型 | 说明 |
|---|---|---|
| `api` | TEXT PK | 接口名（同 op_logs.api） |
| `tokens` | REAL | 当前令牌数 |
| `capacity` | REAL | 桶容量（配置化，app_config） |
| `refill_rate` | REAL | 补充速率（/秒，配置化） |
| `window_start` | DATETIME | 当前统计窗口 |
| `consecutive_failures` | INTEGER | 连续失败次数（≥2 熔断该接口） |
| `circuit_open_until` | DATETIME | 熔断探针开放时间（可空） |

---

## 二、状态机（status 枚举与迁移）

```
待上架(pending) ──入队──▶ 创建中(creating)
 创建中 ──SPU/SKU/图全部成功──▶ 草稿(draft)
 草稿 ──submit_audit──▶ 平台审核中(platform_auditing)
 平台审核中 ──query_audit_status=通过 + get_product_link + HTTP可达──▶ 已上架(listed)
 平台审核中 ──query_audit_status=驳回──▶ 审核驳回(rejected)
 审核驳回 ──platform_rejection 处理──▶ 待重提(retry_candidate) 或 人工处理(manual)
 待重提 ──二次门禁通过──▶ 创建中(重新走创建流程)
```

| 状态 | 含义 | 迁移条件（必须满足） |
|---|---|---|
| `pending` | 待上架（已过硬门禁，等待入队） | gate_result 全部 passed |
| `creating` | 创建中（SPU/SKU/图片） | 入队开始 |
| `draft` | 草稿（平台侧已建，未提交审核） | create_spu/create_skus/upload_image 全部成功 |
| `platform_auditing` | 平台审核中 | submit_audit 成功 |
| `listed` | **已上架** | query_audit_status=通过 **且** get_product_link 返回 **且** 链接 HTTP 可达（真实链接验证铁律，R22） |
| `rejected` | 审核驳回 | query_audit_status=驳回（记录 reject_reason） |
| `retry_candidate` | 待重提（拒审处理后） | platform_rejection 产出修复候选 |
| `manual` | 人工处理 | 自动修复不可行 / 需人工闸门 |
| `failed` | 终态失败 | 重试耗尽且无修复候选（保留证据） |

- 铁律：**禁止**以内部状态/本地猜测标记 `listed`；`listed` 唯一判据 = 真实链接验证通过（R22，代码单测固化）。
- 中断恢复：非终态任务按 `lease_owner` 回收后从断点状态继续（幂等键防重复操作）。

---

## 三、外部契约（微信小店 Channels OpenAPI 摘要）

> 官方文档位置：`developers.weixin.qq.com/doc/channels/API/`（接口域 `channels`）。以下为本模块封装视图，**实际字段以官方文档为准，联调前须由总控协调核对**。

### 3.1 调用基础
- 认证：`access_token`（有效期约 7200s，环境变量缓存；R2 预刷新）。
- 签名：请求体 SHA256 签名 + 时间戳窗口（本模块自写薄封装，不依赖社区库，01 文档结论）。
- 配额：按接口限额，令牌桶排队（listing_quota_states）。
- 幂等：请求幂等键 `request_id`；重试 3 次；RATE_LIMIT 180s / TIMEOUT 60s 退避。

### 3.2 接口清单（适配器方法 → 用途 → 关键入参 → 关键出参）
| 适配器方法 | 用途 | 关键入参 | 关键出参 |
|---|---|---|---|
| `create_spu` | 建商品主体 | title、category_id、qualification、freight_template_id、purchase_limit | spu_id |
| `update_spu` | 改商品主体 | spu_id、待改字段 | 结果 |
| `create_skus` | 建 SKU | spu_id、sku 列表（价格/库存/限购） | sku_id 列表 |
| `update_stock` | 改库存 | sku_id、stock | 结果 |
| `update_price` | 改价 | sku_id、price_cents | 结果 |
| `upload_image` | 传图（**腾讯云 COS 直传**，返回素材 ID） | 文件、用途类型 | media_id |
| `submit_audit` | 提交平台审核 | spu_id、素材 ID 集合 | audit_id |
| `query_audit_status` | 轮询审核状态 | audit_id | 审核状态（通过/驳回/审核中）+ 驳回原因 |
| `get_product_link` | 获取已上架商品链接 | spu_id | product_link（**已上架判据**） |

### 3.3 错误分类映射（平台错误码 → WorkflowJob 错误码）
| 平台错误场景 | 映射 | 重试策略 |
|---|---|---|
| 登录/token 失效（40001/42001 等） | `AUTH_REQUIRED` | 不重试 → 人工 |
| 验证码/安全验证 | `VERIFICATION_REQUIRED` | 不重试 → 人工，单任务暂停 |
| 限流/频繁调用 | `RATE_LIMIT` | 180s 退避 |
| 超时/网络 | `TIMEOUT` | 60s 退避 |
| 资质/内容/参数驳回 | `PLATFORM_REJECT` | 记录原因 → 修复候选/人工 |
| 其余 | `UNEXPECTED` | 60s 退避，留证据 |

---

## 四、错误码（复用 WorkflowJob 码表，09 文档）

| error_code | 含义 | 重试 | 本模块触发场景 |
|---|---|---|---|
| `VERIFICATION_REQUIRED` | 验证码/安全验证 | 不自动重试 → 人工接管，单任务暂停 | UI 兜底/API 触发验证 |
| `AUTH_REQUIRED` | 登录失效 | 不自动重试 → 人工登录后断点续跑 | token 刷新失败、共享 Chrome 登录态失效 |
| `RATE_LIMIT` | 限流/频繁 | 180s 退避 | 令牌桶耗尽、平台限流 |
| `TIMEOUT` | 超时 | 60s 退避 | COS 直传/轮询超时 |
| `NO_MATCH` | 无匹配（平台商品反查未命中） | 120s 退避 | 幂等反查无结果 |
| `PLATFORM_REJECT` | 平台驳回（资质/内容） | 记录原因，转人工/修复候选 | 审核驳回、创建被拒 |
| `UNEXPECTED` | 未知 | 60s 退避，留证据 | 签名异常、未知平台错误 |

---

## 五、跨模块数据契约

> 依据宪法第 5 节：跨模块取数必须在 `_management/logs/data-audit.md` 登记，由总控核对口径。字段名/单位以下表为准，任何变更须同步对方总工。

### 5.1 从 M1（选品）获取 — 只读
| 字段 | 来源表 | 口径 |
|---|---|---|
| product_id / title / category_id / qualification | products | 主键=products.id；标题已过 M1 合规（15–35 字符） |
| 逐 SKU 成本 cost_cents | sku | 单位：分；1688 询价确认页 |
| 差异化售价 price_cents | pricing | 单位：分；定价阶梯结果 |
| 限购/物流/售后设置 | products（购买设置字段） | JSON 口径以 M1 为准 |
| generation_version | products 或关联版本表 | 幂等键组成 |

### 5.2 从 M3（素材优化）获取 — 只读
| 字段 | 来源表 | 口径 |
|---|---|---|
| 主图 5 张（1:1、≥ 分辨率下限） | image_assets | 审核状态=通过；用途=main_image |
| 详情图 | image_assets | 审核状态=通过；用途=detail_image |
| 图片本地路径/URL | image_assets | 上传用文件路径（COS 直传前取本地文件） |

### 5.3 向 M5（小店投放）提供 — 只读视图
| 字段 | 输出 | 口径 |
|---|---|---|
| 销售中商品候选池 | listing_spus 视图（status=listed 且 link_verified_at 非空） | **仅已上架商品**；托管候选不含草稿/审核中 |
| product_link | listing_tasks.product_link | 已验证真实链接 |
| 错峰约束 | app_config（错峰参数） | 上架批次与 M5 托管提交互斥时段 |

### 5.4 与 M0（基座）接口
| 项 | 说明 |
|---|---|
| workflow_jobs | M4 任务登记 stage=`listing_upload`，读租约/错误码（只读 + 经总控协调入队） |
| app_config | 类目白名单/限额/退避/错峰参数（只读 + 配置变更经总控） |
| upload_history / wechat_upload_logs | 归属基座 M0；M4 以 listing_upload_assets / listing_op_logs 为本模块留痕，如需写基座表须总控批准并登记 data-audit.md |

---

## 六、环境事实

| 项 | 值（不含密钥） |
|---|---|
| 开发库 | `backend/data/db/m4-listing.db`（SQLite，不入 git） |
| 环境变量（名） | `WECHAT_APPID`、`WECHAT_SECRET`、`WECHAT_TOKEN_CACHE`（token 缓存路径）、`WECHAT_API_BASE`（默认官方域名）、`COS_SECRET_ID`、`COS_SECRET_KEY`、`COS_BUCKET`、`COS_REGION`、`CHROME_CDP_PORT`（9222/9223）、`PROXY_URL`（可选）、`M4_BATCH_SIZE`（默认 50）、`M4_BATCH_INTERVAL_S`（批间隔） |
| Python | 3.12 |
| 测试 | `python -m pytest tests -q --basetemp=".pytest-tmp"`（P-001） |
| 依赖 | requests/httpx、playwright、python-dotenv（锁定版本） |
| 错峰 | 上架批次与 M5 托管提交互斥时段（参数化，见 app_config） |

> 本文件不包含任何明文密钥；所有凭证仅以上述环境变量名为引用。
