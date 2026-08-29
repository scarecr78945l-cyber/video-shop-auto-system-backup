# old-system-assets — 旧系统规则资产包（供新系统迁移）

> 本目录由独立分析会话从旧系统 `E:\视频号上架系统\视频号上架系统` 的代码中**逐字提取**，
> 供总控会话分派 M1/M2/M4 模块迁移使用。所有文件为 UTF-8 JSON，schema 字段注明来源代码位置。
> 迁移完成后本目录保留为"规则资产溯源"存档。
>
> **配套清单（父目录 `../`）**：
> - `../旧系统门禁迁移清单.md` —— 门禁与规则迁移（A 已套用 / B 已升级 / C 缺口 C1–C3 / D 适配 / E 不适用）
> - `../旧系统第二波融合清单.md` —— 门禁之外的资产融合（P0 直接可搬 / P1 适配融合 / P2 数据知识 / 排除）

## 文件清单

| 文件 | 内容 | 迁移去向 |
|---|---|---|
| `hard-block-policy.json` | 选品硬拦词表全集（品牌/名人IP/鞋服/包/永久排除/安全上下文/URL 阻断） | M1 `sourcing/compliance.py` + config |
| `compliance-words.json` | 旧 compliance.py 词表（BLOCKED/SEMANTIC/品牌/功效资质/类目白名单） | M1 `sourcing/compliance.py` |
| `pricing-ladder.json` | 成本→售价阶梯 | M1 `sourcing/pricing.py`（已实现，用于对照） |
| `listing-requirements.json` | 上架要求（标题/主图/详情/SKU/5 必填参数/客服补参/快照防串单） | M4 `listing_gate.py` + listing 包 |
| `scoring-model.json` | 选品打分权重与分档 | M1 `sourcing/scoring.py`（已实现，用于对照） |
| `error-codes.json` | WorkflowJob 错误码 + 退避 + 租约 | M0 权威码表 DA-008（已对齐，存档） |
| `scheduler-params.json` | 调度参数（节流/熔断/暂停/降频） | M0 `foundation/scheduler.py`（已对齐，存档） |

## 使用方式

1. 总控读取 `../旧系统门禁迁移清单.md` 确定迁移范围与验收标准。
2. 对应模块总工按文件清单将词表/参数挂载到新系统配置（优先 JSON/YAML 配置化，不硬编码）。
3. 迁移后用新系统 fixtures 测试 + 旧系统测试断言清单做回归。

## 溯源说明

提取自旧系统以下文件（2026-08 现场代码）：
- `backend/app/services/sourcing_candidates.py`（SOURCING_HARD_BLOCK_POLICY 等）
- `backend/app/services/compliance.py`
- `backend/app/services/pricing.py`
- `backend/app/services/sourcing_score.py`
- `backend/app/services/workflow_runner.py`
- `backend/app/services/sourcing_scheduler.py`
- `backend/app/services/listing_content_rules.py` / `listing_projection.py` / `listing_manager.py`
- `backend/app/scripts/fetch_1688_quotes.py`（客服补参模板）
- `backend/app/schemas.py`（图片驳回理由枚举）
