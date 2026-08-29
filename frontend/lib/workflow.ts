/**
 * 前端状态机映射（重写版，对齐 09 文档四节 7 阶段条）
 *
 * 旧实现（旧系统 lib/workflow.ts）按**中文状态文本 includes 匹配**，新系统
 * 状态机为英文枚举（M4 9 态 / M5 枚举 / M1 compliance 等），故整体重写：
 * 输入 = 新 API 字段（products.state / compliance.state / quotes 非空 /
 * asset.relevance_status / asset.upload_status / 生图与图片审核 / listing_tasks.status /
 * ads.campaigns.status），输出 = 09 阶段 1..7：
 *
 *   1 已选品 → 2 淘宝素材 → 3 询价(1688) → 4 生图 → 5 图片审核
 *   → 6 待上架/已上架 → 7 托管投放
 *
 * 规则：取「最远」已到达阶段（单调推进）；M4 9 态全部落阶段 6；
 * M5 任一状态落阶段 7。
 */

import { WORKFLOW_STAGES } from "./enums";

/** M4 上架状态机 9 态（M4 context 第二节） */
export const LISTING_STATUSES = new Set([
  "pending",
  "creating",
  "draft",
  "platform_auditing",
  "listed",
  "rejected",
  "retry_candidate",
  "manual",
  "failed",
]);

/** M5 托管状态（D5：英文枚举原值） */
export const M5_CAMPAIGN_STATUSES = new Set([
  "pending",
  "active",
  "paused",
  "not_eligible",
  "ended",
]);

/** 图片审核状态（M3 review gate 口径，供阶段推导） */
export const IMAGE_AUDIT_STATUSES = new Set(["pending_audit", "approved", "rejected"]);

/** 阶段条数据（与 enums.WORKFLOW_STAGES 同源；供 WorkflowSteps 组件使用） */
export { WORKFLOW_STAGES };

export type WorkflowInput = {
  /** M1 products.state：pool / manual_review / rejected */
  productState?: string | null;
  /** M1 compliance.state：hard_reject / candidate / manual_review */
  complianceState?: string | null;
  /** M1 商品详情 quotes 非空（询价完成） */
  hasQuotes?: boolean;
  /** M2 relevance_status：pending / passed / failed / manual_review */
  relevanceStatus?: string | null;
  /** M2 upload_status：local / uploading / uploaded / failed / disabled */
  uploadStatus?: string | null;
  /** M3 已产出生成图（批次存在且 assets 非空） */
  hasGeneratedImages?: boolean;
  /** M3 图片审核状态：pending_audit / approved / rejected / null（未进入审核） */
  imageAuditStatus?: string | null;
  /** M4 listing_tasks.status（9 态） */
  listingStatus?: string | null;
  /** M5 ads.campaigns.status：pending / active / paused / not_eligible / ended */
  campaignStatus?: string | null;
};

/** 是否已淘汰（不再处于推进管道） */
export function isEliminated(input: WorkflowInput): boolean {
  if (input.complianceState === "hard_reject") return true;
  if (input.productState === "rejected") return true;
  if (input.relevanceStatus === "failed") return true;
  if (input.uploadStatus === "disabled") return true;
  return false;
}

/**
 * 推导 09 阶段（1..7）。取最远已到达阶段；淘汰品返回 1（阶段条上不推进）。
 */
export function deriveWorkflowStage(input: WorkflowInput): number {
  // 7 托管投放
  if (input.campaignStatus && M5_CAMPAIGN_STATUSES.has(input.campaignStatus)) return 7;
  // 6 待上架/已上架：M4 9 态全部落 6；图片审核通过（已可上架）同样落 6
  if (input.listingStatus && LISTING_STATUSES.has(input.listingStatus)) return 6;
  if (input.imageAuditStatus === "approved") return 6;
  // 5 图片审核（待审 / 拒审待修复）
  if (input.imageAuditStatus === "pending_audit" || input.imageAuditStatus === "rejected") return 5;
  // 4 生图（已产出生成图，尚未进入审核）
  if (input.hasGeneratedImages === true) return 4;
  // 3 询价（1688 已核价）
  if (input.hasQuotes === true) return 3;
  // 2 淘宝素材（相关性放行或已上传）
  if (input.relevanceStatus === "passed" || input.uploadStatus === "uploaded") return 2;
  // 1 已选品（含待人工复核、淘汰）
  return 1;
}

/** 是否可发起询价（阶段 2 完成且未到 3 之后） */
export function canStartQuote(input: WorkflowInput): boolean {
  if (isEliminated(input)) return false;
  if (input.hasQuotes === true) return false;
  if (input.listingStatus) return false;
  if (input.campaignStatus) return false;
  return true;
}

/** 是否可发起生图（询价完成、未生图、未进入上架/托管） */
export function canStartGeneration(input: WorkflowInput): boolean {
  if (isEliminated(input)) return false;
  if (input.hasQuotes !== true) return false;
  if (input.hasGeneratedImages === true) return false;
  if (input.listingStatus) return false;
  if (input.campaignStatus) return false;
  return true;
}
