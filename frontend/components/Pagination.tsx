/**
 * 分页条（v0.4 批次1）：共 N 条 · 第 p/N 页 + 上一页/下一页 + 每页条数（可选）。
 * 商品池（limit/offset）与素材库（page/page_size）共用。
 */
"use client";

import { cn } from "@/lib/cn";

type Props = {
  page: number;
  pageSize: number;
  total: number;
  onPageChange: (page: number) => void;
  onPageSizeChange?: (size: number) => void;
  pageSizeOptions?: number[];
};

export function Pagination({
  page,
  pageSize,
  total,
  onPageChange,
  onPageSizeChange,
  pageSizeOptions = [20, 50, 100],
}: Props) {
  const totalPages = Math.max(1, Math.ceil(total / pageSize));
  const canPrev = page > 1;
  const canNext = page < totalPages;

  function go(target: number) {
    const clamped = Math.min(Math.max(1, target), totalPages);
    if (clamped !== page) onPageChange(clamped);
  }

  return (
    <div className="flex flex-wrap items-center justify-between gap-3 border-t border-zinc-100 px-4 py-3">
      <div className="text-xs text-zinc-500">
        共 {total} 条 · 第 {page} / {totalPages} 页
      </div>
      <div className="flex items-center gap-2">
        {onPageSizeChange && (
          <label className="flex items-center gap-1.5 text-xs text-zinc-500">
            每页
            <select
              value={pageSize}
              onChange={(e) => onPageSizeChange(Number(e.target.value))}
              className="rounded border border-zinc-200 bg-white px-1.5 py-1 text-xs text-zinc-700 outline-none"
            >
              {pageSizeOptions.map((size) => (
                <option key={size} value={size}>
                  {size}
                </option>
              ))}
            </select>
            条
          </label>
        )}
        <button
          type="button"
          onClick={() => go(page - 1)}
          disabled={!canPrev}
          className={cn(
            "rounded border border-zinc-200 bg-white px-2.5 py-1 text-xs transition",
            canPrev ? "hover:bg-zinc-50" : "cursor-not-allowed opacity-40",
          )}
        >
          上一页
        </button>
        <button
          type="button"
          onClick={() => go(page + 1)}
          disabled={!canNext}
          className={cn(
            "rounded border border-zinc-200 bg-white px-2.5 py-1 text-xs transition",
            canNext ? "hover:bg-zinc-50" : "cursor-not-allowed opacity-40",
          )}
        >
          下一页
        </button>
      </div>
    </div>
  );
}
