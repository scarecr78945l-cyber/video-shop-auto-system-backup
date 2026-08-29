/**
 * 商品池（M1）· v0.4 批次1 + v1.1（服务端关键词 / 分页迁移）
 *
 * 取数：GET /api/products（score 降序；category/compliance/min_score/max_score/
 *      keyword + page/page_size 分页）
 *      + GET /api/products/{id}（行点击 → 详情抽屉：五维打分/quotes/来源证据脱敏）。
 * v1.1：关键词改为**服务端过滤**（keyword 参数，title/sanitized_title LIKE），
 *      输入防抖 300ms；分页从 limit/offset 迁移为 page/page_size（总控决策），
 *      客户端过滤差异标注已移除。
 * 交互：类目/合规三态/关键词（服务端）/分页/每页条数。
 * 展示口径：金额 formatYuan（元零换算）、时间 formatDateTime（UTC→UTC+8）、
 *          枚举一律 lib/enums.ts（compliance 三态徽章）。
 */
"use client";

import { useEffect, useMemo, useState } from "react";
import { Search } from "lucide-react";

import { apiGet, type Paginated, type ProductDetail, type ProductSummary } from "@/lib/api";
import { useAsyncData } from "@/lib/useAsyncData";
import {
  buildProductQuery,
  DEFAULT_PRODUCT_FILTERS,
  distinctCategories,
  type ProductFilters,
} from "@/lib/products";
import { COMPLIANCE_LABELS } from "@/lib/enums";
import { formatDateTime } from "@/lib/format";
import { isMockMode } from "@/lib/env";
import { Pagination } from "@/components/Pagination";
import { ProductDetailPanel } from "@/components/ProductDetailPanel";
import { StatusBadge } from "@/components/StatusBadge";
import { YuanText } from "@/components/YuanText";
import { cn } from "@/lib/cn";

const COMPLIANCE_OPTIONS = Object.entries(COMPLIANCE_LABELS);
/** 关键词输入防抖（ms）：停止输入后才触发服务端过滤。 */
const KEYWORD_DEBOUNCE_MS = 300;

export default function ProductsPage() {
  const [filters, setFilters] = useState<ProductFilters>(DEFAULT_PRODUCT_FILTERS);
  const [keyword, setKeyword] = useState(""); // 输入框即时值
  const [debouncedKeyword, setDebouncedKeyword] = useState(""); // 防抖后实际生效值
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);
  const [selectedId, setSelectedId] = useState<number | null>(null);

  // 闸门工作台跳转 `?state=manual_review`：挂载时读取 query 参数做初始合规筛选（仅客户端运行时）
  useEffect(() => {
    const state = new URLSearchParams(window.location.search).get("state");
    if (state) {
      setFilters((f) => ({ ...f, compliance: state }));
    }
  }, []);

  // 关键词防抖：停止输入 300ms 后生效并重置页码（服务端过滤）
  useEffect(() => {
    const timer = window.setTimeout(() => {
      setDebouncedKeyword(keyword.trim());
      setPage(1);
    }, KEYWORD_DEBOUNCE_MS);
    return () => window.clearTimeout(timer);
  }, [keyword]);

  const query = useMemo(
    () => buildProductQuery(filters, page, pageSize, debouncedKeyword),
    [filters, page, pageSize, debouncedKeyword],
  );
  const list = useAsyncData<Paginated<ProductSummary>>(() => apiGet(`/api/products${query}`), [query]);
  const detail = useAsyncData<ProductDetail | null>(
    () => (selectedId === null ? Promise.resolve(null) : apiGet(`/api/products/${selectedId}`)),
    [selectedId],
  );

  const items = list.data?.items ?? [];
  const categories = useMemo(() => distinctCategories(items), [items]);

  function setFilter<K extends keyof ProductFilters>(key: K, value: ProductFilters[K]) {
    setFilters((f) => ({ ...f, [key]: value }));
    setPage(1);
  }

  function handlePageSizeChange(size: number) {
    setPageSize(size);
    setPage(1);
  }

  return (
    <div>
      <div className="mb-6">
        <h1 className="text-xl font-semibold text-zinc-900">商品池</h1>
        <p className="mt-1 text-sm text-zinc-500">
          M1 选品商品池：按 score 降序 · 合规三态 · 类目/合规/关键词筛选（GET /api/products）
        </p>
      </div>

      {isMockMode() && (
        <div className="mb-4 rounded-lg border border-amber-200 bg-amber-50 px-4 py-2 text-xs text-amber-700">
          NEXT_PUBLIC_USE_MOCK=1：演示模式保留位（当前版本未注入 mock 数据，直连真实 API）
        </div>
      )}

      {/* 筛选栏 */}
      <div className="mb-4 rounded-lg border border-zinc-200 bg-white p-4">
        <div className="flex flex-wrap items-center gap-3">
          <label className="flex items-center gap-2 text-xs text-zinc-500">
            类目
            <select
              value={filters.category}
              onChange={(e) => setFilter("category", e.target.value)}
              className="rounded border border-zinc-200 bg-white px-2 py-1.5 text-xs text-zinc-700 outline-none"
            >
              <option value="">全部</option>
              {categories.map((c) => (
                <option key={c} value={c}>
                  {c}
                </option>
              ))}
            </select>
          </label>
          <label className="flex items-center gap-2 text-xs text-zinc-500">
            合规
            <select
              value={filters.compliance}
              onChange={(e) => setFilter("compliance", e.target.value)}
              className="rounded border border-zinc-200 bg-white px-2 py-1.5 text-xs text-zinc-700 outline-none"
            >
              <option value="">全部</option>
              {COMPLIANCE_OPTIONS.map(([value, label]) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </select>
          </label>
          <label className="flex items-center gap-2 text-xs text-zinc-500">
            得分 ≥
            <input
              type="number"
              min={0}
              max={100}
              value={filters.minScore ?? ""}
              onChange={(e) =>
                setFilter("minScore", e.target.value === "" ? null : Number(e.target.value))
              }
              className="w-20 rounded border border-zinc-200 bg-white px-2 py-1.5 text-xs text-zinc-700 outline-none"
              placeholder="不限"
            />
          </label>
          <label className="flex items-center gap-2 text-xs text-zinc-500">
            得分 ≤
            <input
              type="number"
              min={0}
              max={100}
              value={filters.maxScore ?? ""}
              onChange={(e) =>
                setFilter("maxScore", e.target.value === "" ? null : Number(e.target.value))
              }
              className="w-20 rounded border border-zinc-200 bg-white px-2 py-1.5 text-xs text-zinc-700 outline-none"
              placeholder="不限"
            />
          </label>
          <label className="flex min-w-[220px] flex-1 items-center gap-2 rounded border border-zinc-200 bg-zinc-50 px-3">
            <Search size={14} className="shrink-0 text-zinc-400" />
            <input
              value={keyword}
              onChange={(e) => setKeyword(e.target.value)}
              placeholder="关键词（服务端过滤，标题包含）"
              className="min-w-0 flex-1 bg-transparent py-1.5 text-xs outline-none"
            />
          </label>
        </div>
        <div className="mt-2 text-[11px] text-zinc-400">
          关键词经 300ms 防抖后作为 keyword 参数提交服务端（标题/清洗后标题 LIKE 匹配）。
        </div>
      </div>

      {list.error && (
        <div className="mb-4 rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-700">
          {list.error}
          <button type="button" onClick={list.reload} className="ml-3 underline">
            重试
          </button>
        </div>
      )}

      {/* 列表 */}
      <div className="overflow-hidden rounded-lg border border-zinc-200 bg-white">
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead className="bg-zinc-50 text-xs text-zinc-500">
              <tr>
                <th className="px-4 py-2.5 font-medium">标题</th>
                <th className="px-4 py-2.5 font-medium">类目</th>
                <th className="px-4 py-2.5 font-medium">平台价</th>
                <th className="px-4 py-2.5 font-medium">建议价</th>
                <th className="px-4 py-2.5 font-medium">得分</th>
                <th className="px-4 py-2.5 font-medium">合规</th>
                <th className="px-4 py-2.5 font-medium">销量 / 排名</th>
                <th className="px-4 py-2.5 font-medium">入库时间</th>
              </tr>
            </thead>
            <tbody>
              {!list.loading && items.length === 0 && (
                <tr>
                  <td colSpan={8} className="px-4 py-12 text-center text-xs text-zinc-400">
                    {debouncedKeyword ? "无匹配关键词的商品" : "暂无商品"}
                  </td>
                </tr>
              )}
              {items.map((p) => {
                const complianceState =
                  typeof p.compliance?.state === "string" ? p.compliance.state : p.state;
                return (
                  <tr
                    key={p.id}
                    onClick={() => setSelectedId(p.id)}
                    className={cn(
                      "cursor-pointer border-t border-zinc-100 transition hover:bg-teal-50/40",
                      list.loading && "opacity-60",
                    )}
                  >
                    <td className="max-w-[280px] truncate px-4 py-3 font-medium text-zinc-800" title={p.title}>
                      {p.title || "（无标题）"}
                    </td>
                    <td className="px-4 py-3 text-xs text-zinc-600">{p.category || "—"}</td>
                    <td className="px-4 py-3 text-xs text-zinc-700">
                      <YuanText value={p.platform_price} />
                    </td>
                    <td className="px-4 py-3 text-xs text-zinc-700">
                      <YuanText value={p.suggested_price} />
                    </td>
                    <td className="px-4 py-3">
                      <span
                        className={cn(
                          "inline-flex rounded px-2 py-0.5 text-xs font-semibold",
                          p.score >= 70
                            ? "bg-emerald-50 text-emerald-700"
                            : p.score >= 50
                              ? "bg-amber-50 text-amber-700"
                              : "bg-zinc-100 text-zinc-600",
                        )}
                      >
                        {p.score.toFixed(1)}
                      </span>
                    </td>
                    <td className="px-4 py-3">
                      <StatusBadge labels={COMPLIANCE_LABELS} value={complianceState} />
                    </td>
                    <td className="px-4 py-3 text-xs text-zinc-600">
                      {p.sales ?? 0} / 第 {p.rank_best ?? 0} 名
                    </td>
                    <td className="whitespace-nowrap px-4 py-3 text-xs text-zinc-500">
                      {formatDateTime(p.created_at)}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
        <Pagination
          page={page}
          pageSize={pageSize}
          total={list.data?.total ?? 0}
          onPageChange={setPage}
          onPageSizeChange={handlePageSizeChange}
        />
      </div>

      {/* 详情抽屉 */}
      {selectedId !== null && (
        <ProductDetailPanel
          detail={detail.data}
          loading={detail.loading}
          error={detail.error}
          onClose={() => setSelectedId(null)}
        />
      )}
    </div>
  );
}
