/**
 * 素材库（M2）列表纯逻辑辅助（v0.4 批次1）
 *
 * GET /api/assets 使用 page/page_size 分页，筛选参数对齐
 * backend/api/routers/m2_materials.py（asset_type/source_platform/relevance_status/
 * upload_status/evaluation）。全部为纯函数，配套单测 tests/list.test.ts。
 */

import type { AssetSummary } from "./api";

export type AssetFilters = {
  assetType: string; // "" = 全部（video / image）
  sourcePlatform: string; // "" = 全部
  relevanceStatus: string; // "" = 全部（pending / passed / failed / manual_review）
  uploadStatus: string; // "" = 全部（local / uploading / uploaded / failed / disabled）
  evaluation: string; // "" = 全部（exploring / efficient / potential）
};

export const DEFAULT_ASSET_FILTERS: AssetFilters = {
  assetType: "",
  sourcePlatform: "",
  relevanceStatus: "",
  uploadStatus: "",
  evaluation: "",
};

/** 构建 GET /api/assets 查询串（page/page_size 分页）。 */
export function buildAssetQuery(filters: AssetFilters, page: number, pageSize: number): string {
  const params = new URLSearchParams();
  if (filters.assetType) params.set("asset_type", filters.assetType);
  if (filters.sourcePlatform) params.set("source_platform", filters.sourcePlatform);
  if (filters.relevanceStatus) params.set("relevance_status", filters.relevanceStatus);
  if (filters.uploadStatus) params.set("upload_status", filters.uploadStatus);
  if (filters.evaluation) params.set("evaluation", filters.evaluation);
  params.set("page", String(Math.max(1, page)));
  params.set("page_size", String(pageSize));
  return `?${params.toString()}`;
}

/** 当前页来源平台去重（用于平台下拉；API 无独立平台枚举端点，REPORT 遗留项登记）。 */
export function distinctSourcePlatforms(items: AssetSummary[]): string[] {
  const set = new Set<string>();
  for (const a of items) {
    const p = (a.source_platform ?? "").trim();
    if (p) set.add(p);
  }
  return [...set].sort((a, b) => a.localeCompare(b, "zh-CN"));
}
