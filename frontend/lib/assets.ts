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

// ================================================================ v1.1 素材选择器（托管素材绑定）

/** 素材选择器筛选（评估标签 + 相关性门；其余维度选择器不暴露）。 */
export type AssetSelectorFilters = {
  evaluation: string; // "" = 全部（exploring / efficient / potential）
  relevanceStatus: string; // "" = 全部（pending / passed / failed / manual_review）
};

export const DEFAULT_ASSET_SELECTOR_FILTERS: AssetSelectorFilters = {
  evaluation: "",
  relevanceStatus: "",
};

/**
 * 构建素材选择器列表查询（复用 GET /api/assets 的 evaluation/relevance_status 过滤 +
 * page/page_size 分页；对齐 m2_materials.py list_assets v1.1 契约）。
 */
export function buildAssetSelectorQuery(
  filters: AssetSelectorFilters,
  page: number,
  pageSize: number,
): string {
  return buildAssetQuery(
    {
      assetType: "",
      sourcePlatform: "",
      relevanceStatus: filters.relevanceStatus,
      uploadStatus: "",
      evaluation: filters.evaluation,
    },
    page,
    pageSize,
  );
}

/**
 * 素材 → 后端 materials 端点接受的标识：优先 platform_material_id
 * （M5 AdMaterial.material_id 同域标识），缺失回落 String(asset.id)。
 * POST /api/ads/campaigns/{id}/materials body {material_ids} 按此字段提交。
 */
export function assetToMaterialId(asset: AssetSummary): string {
  const pid = asset.platform_material_id?.trim();
  return pid || String(asset.id);
}
