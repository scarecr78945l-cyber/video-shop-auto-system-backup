/**
 * 商品池（M1）列表纯逻辑辅助（v0.4 批次1）
 *
 * GET /api/products 使用 limit/offset 分页（非 page/page_size），
 * 筛选参数对齐 backend/api/routers/m1_sourcing.py（category/compliance/min_score/max_score）。
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
 * 客户端关键词过滤：标题 / 清洗后标题包含（大小写不敏感）。
 * API 无关键词参数（REPORT 遗留项登记），本函数作用于已取回的分页条目。
 */
export function filterProductsByKeyword(items: ProductSummary[], keyword: string): ProductSummary[] {
  const kw = keyword.trim().toLowerCase();
  if (!kw) return items;
  return items.filter((p) => {
    const title = (p.title ?? "").toLowerCase();
    const sanitized = (p.sanitized_title ?? "").toLowerCase();
    return title.includes(kw) || sanitized.includes(kw);
  });
}

/** 构建 GET /api/products 查询串（limit/offset 分页）。 */
export function buildProductQuery(filters: ProductFilters, page: number, pageSize: number): string {
  const params = new URLSearchParams();
  if (filters.category) params.set("category", filters.category);
  if (filters.compliance) params.set("compliance", filters.compliance);
  if (filters.minScore !== null && Number.isFinite(filters.minScore)) {
    params.set("min_score", String(filters.minScore));
  }
  if (filters.maxScore !== null && Number.isFinite(filters.maxScore)) {
    params.set("max_score", String(filters.maxScore));
  }
  params.set("limit", String(pageSize));
  params.set("offset", String(Math.max(0, (page - 1) * pageSize)));
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
