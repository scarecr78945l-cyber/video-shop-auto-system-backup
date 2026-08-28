# M4 自动上架 · 微信小店 Channels OpenAPI 外部契约（核对稿）

> 依据 REC-003 建立：核对微信小店官方 OpenAPI 契约，写进 context/外部契约并标注来源。
> **核对状态说明（重要）**：本稿基于项目既有权威文档整理（来源：`01-开源项目盘点与借鉴.md`、`07-自动上架模块设计.md`、本模块 `context/README.md` 外部契约节），**尚未经官方文档 web 核对**——web_search 工具当前额度不足（Insufficient Balance，P1 子代理两次中断均由此导致），官方文档核对待额度恢复后由总工/总控侧执行并更新本文件。所有未确认项一律标注 **【待核对】**，禁止臆造字段。
> 官方文档位置：`developers.weixin.qq.com/doc/channels/API/`（微信小店板块，接口域 `channels`）。

---

## 一、调用基础

| 项 | 内容 | 来源 | 状态 |
|---|---|---|---|
| 认证 | `access_token`（有效期约 7200s），需缓存 + 提前 5min 预刷新（R2） | context/README 3.1、risks R2 | 已知，**具体获取接口（api.weixin.qq.com/cgi-bin/token 或 channels 专用路径）待核对** |
| 签名 | 请求体 **SHA256 签名 + 时间戳窗口**；本模块自写薄封装（不依赖社区库，决策 D2） | 07 第四节、01 文档 | 已知；**签名参数名/拼接规则/窗口秒数待核对** |
| 配额 | 按接口限额；令牌桶排队（listing_quota_states）；RATE_LIMIT 180s / TIMEOUT 60s 退避 | 07 第四节、09 错误码表 | **各接口 QPS/日配额具体数值待核对** |
| 幂等 | 请求幂等键 `request_id`（= task_id+接口名+序号）；重试 3 次；`(product_id,stage,generation_version)` 唯一约束 | decisions D6、09 | 已知 |
| 金额 | 一律整数「分」（决策 D7） | decisions D7 | 已知 |
| 模式 | `WECHAT_MODE=mock`（默认，REC-004）/ `live`（显式开启且密钥齐备）；**不提交真实商品（铁律）** | REC-004 | 已知 |

## 二、接口清单（适配器方法 → 用途 → 关键入参 → 关键出参）

> 每个接口：本模块适配器方法、用途、关键入参、关键出参；**接口实际路径/字段名待核对**（以官方文档为准）。

| 适配器方法 | 用途 | 关键入参 | 关键出参 | 状态 |
|---|---|---|---|---|
| `create_spu` | 建商品主体 | title（15–35 字符）、category_id、qualification、freight_template_id、purchase_limit | spu_id | **接口路径/字段名待核对** |
| `update_spu` | 改商品主体 | spu_id、待改字段 | 结果 | **待核对** |
| `create_skus` | 建 SKU | spu_id、sku 列表（price_cents/stock/purchase_limit） | sku_id 列表 | **待核对** |
| `update_stock` | 改库存 | sku_id、stock（默认 10000） | 结果 | **待核对** |
| `update_price` | 改价 | sku_id、price_cents | 结果 | **待核对** |
| `upload_image` | 传图（**腾讯云 COS 直传**，返回素材 ID） | 文件、用途类型（main_image/detail_image） | media_id | **直传协议（预签名 URL 或自传）待核对** |
| `submit_audit` | 提交平台审核 | spu_id、素材 ID 集合 | audit_id | **待核对** |
| `query_audit_status` | 轮询审核状态 | audit_id | 审核状态（审核中/通过/驳回）+ 驳回原因 | **待核对（轮询间隔/上限建议 60s 起）** |
| `get_product_link` | 获取已上架商品链接 | spu_id | product_link（**已上架唯一判据**，R22） | **待核对** |

## 三、错误码映射（平台错误 → WorkflowJob 码表）

| 平台错误场景 | 映射 | 重试 | 来源 |
|---|---|---|---|
| 登录/token 失效（40001/42001 等） | `AUTH_REQUIRED` | 不重试 → 人工 | context 3.3（**平台错误码具体编号待核对**） |
| 验证码/安全验证 | `VERIFICATION_REQUIRED` | 不重试 → 人工 | 同上 |
| 限流/频繁调用 | `RATE_LIMIT` | 180s 退避 | 同上 |
| 超时/网络 | `TIMEOUT` | 60s 退避 | 同上 |
| 资质/内容/参数驳回 | `PLATFORM_REJECT` | 记录原因 → 修复候选/人工 | 同上 |
| 其余 | `UNEXPECTED` | 60s 退避，留证据 | 同上 |

## 四、待核对清单（官方文档核对后逐项销项）

| # | 待核对项 | 影响 | 核对方式 |
|---|---|---|---|
| T1 | access_token 获取接口路径与参数（grant_type/appid/secret） | P1 `_get_token` 实现 | web_search/官方文档 |
| T2 | SHA256 签名参数名、拼接顺序、时间戳窗口秒数 | P1 `_sign` 实现 | 官方文档 |
| T3 | 9 个接口的实际请求路径与方法（GET/POST） | P1 `_call` 路由 | 官方文档 |
| T4 | 各接口入参/出参字段名与类型（含分页/嵌套结构） | P1 方法签名 | 官方文档 |
| T5 | 各接口配额（QPS/日上限） | 令牌桶参数 | 官方文档 |
| T6 | upload_image 的 COS 直传协议（预签名 URL？） | P1 `upload_image` | 官方文档 |
| T7 | 平台业务错误码编号表 | 错误分类映射 | 官方文档 |

> 核对完成一项即在对应行标记「已核对」并补充来源 URL；**P1 骨架开发不等待核对**（按上表已知项实现，待核对项用常量占位 + 注释「待核对」）。
