/**
 * 审核工作台（M3 图片审核 + M2 素材相关性预审）纯逻辑辅助（v0.6 批次3）
 *
 * GET /api/optimization/batches 使用 status + page/page_size 分页（对齐
 * backend/api/routers/m3_optimization.py）；素材预审复用 GET /api/assets 的
 * relevance_status 过滤（backend/api/routers/m2_materials.py）。
 * 全部为纯函数，配套单测 tests/review.test.ts。
 */

import type { AssetSummary, OptimizationBatchDetail, OptimizationImage } from "./api";
import { buildAssetQuery } from "./assets";

// ---------------------------------------------------------------- 驳回理由预置

/**
 * 图片驳回理由预置（旧系统 ImageReviewPanel 5 项语义 + 新增清晰度项，
 * 对齐 10 文档第五节「投放素材预审」；仍支持自定义输入）。
 */
export const REJECTION_REASONS: ReadonlyArray<string> = [
  "产品不一致",
  "卖点不清晰",
  "文字错误",
  "场景不合适",
  "颜色不对",
  "构图/清晰度不合格",
];

// ---------------------------------------------------------------- 批次列表查询

/** 构建 GET /api/optimization/batches 查询串（status 过滤 + page/page_size 分页）。 */
export function buildBatchQuery(status: string, page: number, pageSize: number): string {
  const params = new URLSearchParams();
  if (status) params.set("status", status);
  params.set("page", String(Math.max(1, page)));
  params.set("page_size", String(pageSize));
  return `?${params.toString()}`;
}

// ---------------------------------------------------------------- 批内统计/进度

export type ReviewStatusCounts = {
  total: number;
  approved: number;
  rejected: number;
  pending: number;
};

/** 按 review_status 统计批内图片（pending / approved / rejected；未知值归入 pending）。 */
export function countReviewStatus(assets: OptimizationImage[]): ReviewStatusCounts {
  let approved = 0;
  let rejected = 0;
  let pending = 0;
  for (const a of assets) {
    if (a.review_status === "approved") approved += 1;
    else if (a.review_status === "rejected") rejected += 1;
    else pending += 1;
  }
  return { total: assets.length, approved, rejected, pending };
}

/** 审核进度：已审（approved/rejected）/总数 → percent 0..100（空批返回 0）。 */
export function reviewProgress(
  assets: OptimizationImage[],
): { done: number; total: number; percent: number } {
  const total = assets.length;
  if (total === 0) return { done: 0, total: 0, percent: 0 };
  const done = assets.filter(
    (a) => a.review_status === "approved" || a.review_status === "rejected",
  ).length;
  return { done, total, percent: Math.round((done / total) * 100) };
}

/**
 * 整批通过可用性：批次存在、未处于 approved（后端幂等：already 态返回
 * already_approved=true，前端直接视为成功）、且批内有图。
 */
export function canApproveBatch(batch: OptimizationBatchDetail | null): boolean {
  if (!batch) return false;
  if (batch.status === "approved") return false;
  return batch.assets.length > 0;
}

/** 按 image_type（main/detail）过滤批内图片（tab 切换用）。 */
export function filterAssetsByType(
  assets: OptimizationImage[],
  imageType: string,
): OptimizationImage[] {
  return assets.filter((a) => a.image_type === imageType);
}

/** 单图规格摘要（宽×高；无尺寸 → `—`）。 */
export function formatImageSpec(image: OptimizationImage): string {
  if (image.width > 0 && image.height > 0) return `${image.width}×${image.height}`;
  return "—";
}

// ---------------------------------------------------------------- 素材相关性预审

/** 待确认素材列表查询（GET /api/assets?relevance_status=manual_review）。 */
export function buildPreReviewAssetQuery(page: number, pageSize: number): string {
  return buildAssetQuery(
    {
      assetType: "",
      sourcePlatform: "",
      relevanceStatus: "manual_review",
      uploadStatus: "",
      evaluation: "",
    },
    page,
    pageSize,
  );
}

/** 已放行素材列表查询（relevance_status=passed，可选查看）。 */
export function buildPassedAssetQuery(page: number, pageSize: number): string {
  return buildAssetQuery(
    {
      assetType: "",
      sourcePlatform: "",
      relevanceStatus: "passed",
      uploadStatus: "",
      evaluation: "",
    },
    page,
    pageSize,
  );
}

/** 是否待人工确认目标款（relevance_status=manual_review）。 */
export function isManualReviewAsset(asset: AssetSummary): boolean {
  return asset.relevance_status === "manual_review";
}

/** relevance-confirm 决策中文（POST /api/assets/{id}/relevance-confirm body.decision）。 */
export const RELEVANCE_CONFIRM_DECISION_LABELS: Record<string, string> = {
  pass: "确认目标款（放行）",
  reject: "不相关（淘汰）",
  manual_review: "继续人工复核",
};

/** decision → 中文（未知原样透传，便于排障）。 */
export function relevanceConfirmLabel(decision: string): string {
  return RELEVANCE_CONFIRM_DECISION_LABELS[decision] ?? decision;
}
