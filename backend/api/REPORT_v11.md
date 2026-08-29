# M6 后端 API 层 · v1.1 增强交付报告（子代理⑥）

> 日期：2026-08-29 ｜ 角色：M6 子代理⑥（后端 API 层 v1.1 增强） ｜ 父代理：M6 总工程师
> 验收命令（已实测全绿）：`python -X utf8 -m pytest tests/test_api_*.py -q --basetemp=".pytest-tmp-m6"`（backend/ 目录）
> 结果：**110 passed**（v1.0 的 75 → v1.1 110，+35：3 个 m1 测试扩展 + 32 个新增 v1.1 用例）
> 路径数：**41 → 43**（新增 `POST /api/workbench/retry-batch`、`GET /api/assets/{id}/preview`）

---

## 一、5 项实现说明（含字段/端点最终形态）

### 1. 服务端关键词过滤（D1）+ jobs limit

| 端点 | 变更 | 最终形态 |
|---|---|---|
| `GET /api/products` | 新增 `keyword` 查询参数；分页迁移 page/page_size | `keyword` 对 `title`/`sanitized_title` 做 **LIKE %kw% 大小写不敏感**匹配（`lower(col) LIKE '%kw%'`，SQLite/PostgreSQL 兼容）；与既有 category/state/compliance/min_score/max_score 任意组合；信封 `{total, page, page_size, items}`（page 默认 1 ge=1；page_size 默认 20 ge=1 le=100） |
| `GET /api/jobs` | 新增 `keyword` + `limit` | `keyword` 对可标识字段 LIKE %kw%：`product_id`（数字字符串 cast 后匹配）+ `error_message`（workflow_jobs 无 title/request_id 列，D1 按表结构定）；`limit` 默认 100 ge=1 le=500，生效页大小 = `min(page_size, limit)`（默认不改变现有分页行为）；信封不变 `{total, page, page_size, items}` |

### 2. 分页统一（总控决策：全统一 page/page_size 信封 `{total, page, page_size, items}`）

- **products 从 limit/offset 迁移**（唯一存量特例）：删除 `limit`/`offset` 参数，改 `page`/`page_size`（与 assets/listing/ads/workbench 一致）；信封改 `{total, page, page_size, items}`。
- **listing-ready 统一**：原 `limit` 参数 → `page`/`page_size`（page 默认 1；page_size 默认 20 le=100）；信封补 `page`/`page_size`（`evidence` 池截断证据保留为附加键，最小改动，未破坏既有字段）。
- **workbench-exceptions 统一**：原 `limit` 参数（默认 100）→ `page`/`page_size`（默认 20）；信封 `{total, page, page_size, items}`。
- **全层校验结果**（envelope 一致性测试 9 端点断言 + ads/report 例外登记）：

| 端点 | 信封 | 状态 |
|---|---|---|
| GET /api/jobs | `{total, page, page_size, items}` | ✅ 一致 |
| GET /api/products | `{total, page, page_size, items}` | ✅ v1.1 迁移 |
| GET /api/assets | `{total, page, page_size, items}` | ✅ 一致 |
| GET /api/assets/uploads | `{total, page, page_size, items}` | ✅ 一致 |
| GET /api/optimization/batches | `{total, page, page_size, items}` | ✅ 一致 |
| GET /api/listing/tasks | `{total, page, page_size, items}` | ✅ 一致 |
| GET /api/listing/ready | `{total, page, page_size, items}`（+evidence） | ✅ v1.1 统一 |
| GET /api/ads/campaigns | `{total, page, page_size, items}` | ✅ 一致（+product_name） |
| GET /api/workbench/exceptions | `{total, page, page_size, items}` | ✅ v1.1 统一 |
| GET /api/ads/report | `{days, total, items}` | ⚠️ **例外登记**（days 聚合，无分页语义，按决策保留） |
| GET /api/optimization/copywrites、GET /api/logs、GET /api/listing/tasks/{id}/op-logs | `{total, items}` 等 | 不在统一清单内，保持原样（未破坏） |
| GET /api/overview | 聚合视图 | 例外（决策明确排除） |

- **前端子代理⑦同步**：products 页由 limit/offset 迁移 page/page_size（决策已定稿，见 m6-frontend/decisions.md 第 25~27 行）。

### 3. 批量接管（异常中心）

- **新增 `POST /api/workbench/retry-batch`**：body `{job_ids: [int]}`（pydantic `min_length=1` / `max_length=100`；空数组 → **422 VALIDATION_ERROR**，超 100 个 → **422 VALIDATION_ERROR**）。
- 逐 job 复用单端点 retry 语义（共享 `_retry_job_result` 帮助函数，单端点 `retry/{job_id}` 同源重构，语义零漂移）：仅 blocked/waiting_verification/waiting_login 可重试；非异常状态 → 该项 `INVALID_STATE`；不存在 → `NO_MATCH`。
- 返回 `{ok, total, success_count, results: [{job_id, ok, status?, error?}]}`，`error` 为 `{code, message}`（ok/total/success_count 为附加键，只增不改）。
- **单 job 失败不影响其他**（每个 job 独立 session 提交，不整体 500，整体恒 200）；**幂等**：批量中已恢复的 job → `ok:false + code:INVALID_STATE`，整体仍 200。
- 每个成功 job 走既有 `workbench.retry` 审计留痕（`services.audit`，脱敏）。

### 4. 图片预览媒体端点（v0.6 遗留）

- **新增 `GET /api/assets/{id}/preview`**：
  - 读 M2 `asset_items`；**asset_type=image 才可预览**，video（或其它类型）→ **400** + code `INVALID_STATE` + 说明消息。
  - `file_path` 为 M2 素材存储键 → **路径白名单校验**：复用 `materials.storage.LocalStorage._resolve`（对齐 M2 语义：拒绝绝对路径/盘符/`..` 越界，解析后必须位于存储根内）；越界/不存在/不可读 → **404 NO_MATCH**。
  - 文件存在 → **FileResponse 图片流**，Content-Type 按扩展名：`.png→image/png`、`.jpg/.jpeg→image/jpeg`、`.webp→image/webp`（未知扩展回退 mimetypes 探测）。
  - **免 JSON 信封（媒体流），鉴权仍生效**（auth_guard 中间件覆盖，测试断言未登录 401）。
  - **脱敏**：FileResponse 不传 filename/绝对路径，响应体不含真实路径（测试断言）。
  - **存储根解析**：M2 配置 `services.materials_db.config.storage_dir`（即 `MATERIALS_STORAGE_DIR` 环境变量经 pydantic-settings 映射）；读不到配置 → **503** + code `UNEXPECTED` + 明确消息（测试用临时目录 env 注入 + storage_dir 置空触发 503）。

### 5. 托管看板商品名 join（v0.5 遗留）

- `GET /api/ads/campaigns` 每项新增 **`product_name`**（只增不改）：跨库 join M1 `products.title`——M5 库 `ad_campaigns.product_id` → M1 库 `products.id`，经 services 六库容器**分别查询**（批量 `IN` 取回后映射，不跨库 SQL、不改任何模块 repo）；`title` 为空时回退 `sanitized_title`；**M1 库不可用或商品不存在 → null**（try/except 兜底不阻塞看板）。
- 详情端点 `GET /api/ads/campaigns/{id}` 未变更（任务书仅要求列表；如需详情 join 属后续增量）。

---

## 二、测试结果

- 验收命令（backend/ 目录）：`python -X utf8 -m pytest tests/test_api_*.py -q --basetemp=".pytest-tmp-m6"` → **110 passed**（P-001/P-011 独立 basetemp、P-017 -X utf8）。
- 新增 `backend/tests/test_api_v11.py`（32 用例）+ 就地扩展 `test_api_m1_sourcing.py`（+3：分页信封迁移断言、分页参数、keyword 大小写不敏感）。
- 覆盖矩阵（v1.1 项）：
  - products keyword 命中/未命中/组合过滤（category/state/score 区间）+ page/page_size 信封 + 迁移后无 limit/offset 键 + 非法分页 422 + 大小写不敏感；
  - jobs keyword（product_id 数字字符串 / error_message / 组合 status）+ limit（1 条截断 / 500 不截断 / 0 / 501 → 422）；
  - retry-batch 混合成功/409/404（整体 200、success_count、单失败不影响其他、审计留痕）、blocked 可重试、空数组 422、超 100 422、幂等（二次批量 INVALID_STATE）、未登录 401；
  - preview image 200 流 + Content-Type image/jpeg + 内容一致 + 无绝对路径泄漏、video 400、素材不存在 404、文件缺失 404、路径穿越防护（`../`、绝对路径、盘符三种键均 404）、无存储配置 503、未登录 401；
  - campaigns product_name（有商品 → title / 无商品 → null / M1 库不可用 → 全 null）+ 既有字段不改变；
  - 信封一致性抽查（9 端点 `{total,page,page_size,items}`）+ ads/report 例外 `{days,total,items}`。
- 未跑 M0~M5 全量（总控执行）；已抽查 `test_ads_repo.py` + `test_foundation_security.py` → **23 passed** 零回归（与 v1.0 基线一致）。

---

## 三、与契约（decisions.md v1.1 契约定稿）的差异登记

| # | 契约表述 | 实际实现 | 说明 |
|---|---|---|---|
| V1 | jobs `keyword`（product_id 字符串匹配，如表有任务标识字段一并匹配） | product_id（cast 字符串）+ **error_message** 一并匹配；无 title/request_id 列 | workflow_jobs 表结构定（D1 延续）；error_message 为任务级可读标识 |
| V2 | jobs `limit`（默认 100 ≤500） | 实现为「单次返回条数硬上限」：生效页大小 = `min(page_size, limit)`；默认 100 不影响既有 page_size=20 行为 | 与 page/page_size 信封并存的最小改动语义；已在前端契约文档注明 |
| V3 | retry-batch 返回 `{results:[{job_id, ok, status?, error?}]}` | 附加顶层键 `ok`/`total`/`success_count`（只增不改） | 便于前端汇总展示 |
| V4 | preview 返回 503「明确错误」 | 503 + code `UNEXPECTED` + 消息「素材存储目录未配置（MATERIALS_STORAGE_DIR 或 M2 storage_dir）」 | 错误格式复用统一信封 |
| V5 | campaigns product_name join M1 products.title | title 为空时回退 sanitized_title（防御）；详情端点未加 | 任务书仅要求列表 |

---

## 四、遗留项 / 待会签确认项

| # | 项 | 需谁决策/动作 |
|---|---|---|
| V-L1 | **workbench-exceptions 的 limit 参数被 page/page_size 取代**：前端异常中心 v1.0 若传 `limit` 需迁移（子代理⑦按契约开发，无需兼容） | M6 总工知悉 |
| V-L2 | **listing-ready 保留 `evidence` 附加键**（池截断证据）：信封 4 键一致，extra 键供前端可选消费 | 无动作（文档已登记） |
| V-L3 | **ads/campaigns/{id} 详情未加 product_name**：如前端看板详情需要，属 v1.2 增量 | 待总工排期 |
| V-L4 | **copywrites/logs/op-logs 信封未统一**（不在总控统一清单内）：`{total, items}` 或 `{task_id,total,items}`，保持原样 | 若总控后续要求统一再排期 |
| V-L5 | preview 存储根**复用 M2 storage_dir**（默认 `data/materials` 相对 backend/ 运行目录）：生产需保证 `MATERIALS_STORAGE_DIR` 与 M2 实际落盘目录一致 | 总控/部署方配置 |
| V-L6 | v1.0 遗留 L1~L9 未处理（本批范围外；L1/L6 m0 鉴权、L2 requirements 等仍待总控） | 总控 |

---

## 五、纪律核验

- ✅ 未运行任何 git 命令（宪法第 7 节）
- ✅ 未修改 M0~M5 任何源码（sourcing/materials/ads/listing/foundation/optimization 一律只读；join/白名单校验仅 import 复用模块类/函数）
- ✅ 只改 `backend/api/` 与 `backend/tests/test_api_*.py`（schemas.py / routers/m1_sourcing.py / system.py / m2_materials.py / m5_ads.py / workbench.py / m4_listing.py / test_api_m1_sourcing.py / 新增 test_api_v11.py）
- ✅ 无明文密钥/token/cookie 值（测试密码运行时随机生成；审计证据走既有脱敏）
- ✅ 全部文件 write/edit 工具 UTF-8 无 BOM（宪法第 11 节）
- ✅ pytest 独立 basetemp `.pytest-tmp-m6`（P-001/P-011）+ `-X utf8`（P-017）；未跑全量回归（仅抽查 23 passed 零回归）
- ✅ 小步落盘（P-014）：按 1→5 顺序逐项落盘，每完成一项跑对应测试（m1/system 20 passed → v1.1+workbench/m2/m5/m4 67 passed → 全量 110 passed）
- ✅ 既有端点字段只增不改（分页信封迁移为总控决策契约变更，已同步前端子代理⑦）
