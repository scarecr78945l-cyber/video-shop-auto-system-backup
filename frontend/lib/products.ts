/**
 * 商品池（M1）列表纯逻辑辅助（v0.4 批次1 + v1.1 服务端关键词/分页迁移）
 *
 * v1.1 总控决策：GET /api/products 从 limit/offset 迁移为 page/page_size
 * 信封 {total, page, page_size, items}（与 assets/listing/ads/workbench 一致），
 * 并新增服务端关键词参数 `keyword`（title/sanitized_title LIKE %kw%，
 * 对齐 m1_sourcing.py list_products v1.1 契约）。
 * 客户端关键词过滤 filterProductsByKeyword 已删除（服务端承担，消除双逻辑）。
 * 筛选参数对齐 backend/api/routers/m1_sourcing.py（category/compliance/min_score/max_score/keyword）。
 * 全部为纯函数，配套单测 tests/list.test.ts。
 */

import type { ProductSummary } from "./api";

export type ProductFilters = {
  category: string; // "" = 全部
  compliance: string; // "" = 全部（hard_reject / candidate / manual_review）
  minScore: number | null; // null = 不限
  maxScore: number | null; // null = 不限
};

export const DEFAULT_PRODUCT_FILTERS: ProductFilters = {
  category: "",
  compliance: "",
  minScore: null,
  maxScore: null,
};

/**
 * 构建 GET /api/products 查询串（page/page_size 分页 + 可选服务端关键词）。
 * keyword 为空/空白时不输出参数；page 最小 1。
 */
export function buildProductQuery(
  filters: ProductFilters,
  page: number,
  pageSize: number,
  keyword = "",
): string {
  const params = new URLSearchParams();
  if (filters.category) params.set("category", filters.category);
  if (filters.compliance) params.set("compliance", filters.compliance);
  if (filters.minScore !== null && Number.isFinite(filters.minScore)) {
    params.set("min_score", String(filters.minScore));
  }
  if (filters.maxScore !== null && Number.isFinite(filters.maxScore)) {
    params.set("max_score", String(filters.maxScore));
  }
  const kw = keyword.trim();
  if (kw) params.set("keyword", kw);
  params.set("page", String(Math.max(1, page)));
  params.set("page_size", String(pageSize));
  return params.toString() ? `?${params.toString()}` : "";
}

/** 当前页类目去重（用于类目下拉；API 无独立类目枚举端点，REPORT 遗留项登记）。 */
export function distinctCategories(items: ProductSummary[]): string[] {
  const set = new Set<string>();
  for (const p of items) {
    const c = (p.category ?? "").trim();
    if (c) set.add(c);
  }
  return [...set].sort((a, b) => a.localeCompare(b, "zh-CN"));
}
