/**
 * 选品复核面板（v0.7，闸门工作台内联）：
 *
 * 取数：GET /api/products?state=manual_review（limit/offset 分页，buildReviewProductsQuery）
 * 操作：POST /api/sourcing/gate-confirm {product_id} → pool（二次确认；
 *       已在池中 → 409 INVALID_STATE / 不存在 → 404，后端 message 展示在弹窗内）；
 *       行点击 → GET /api/products/{id} → ProductDetailPanel 详情抽屉。
 * 展示口径：金额 formatYuan（元零换算）、时间 formatDateTime、枚举/合规摘要走 lib 层。
 */
"use client";

import { useMemo, useState } from "react";
import { Eye, ShieldCheck } from "lucide-react";

import {
  ApiError,
  apiGet,
  apiPost,
  type GateConfirmResult,
  type Paginated,
  type ProductDetail,
  type ProductSummary,
} from "@/lib/api";
import { useAsyncData } from "@/lib/useAsyncData";
import { buildReviewProductsQuery, complianceReasonsSummary } from "@/lib/workbench";
import { COMPLIANCE_LABELS } from "@/lib/enums";
import { formatDateTime } from "@/lib/format";
import { cn } from "@/lib/cn";
import { ConfirmDialog } from "@/components/ConfirmDialog";
import { Pagination } from "@/components/Pagination";
import { ProductDetailPanel } from "@/components/ProductDetailPanel";
import { StatusBadge } from "@/components/StatusBadge";
import { YuanText } from "@/components/YuanText";

type Props = {
  /** 确认入池成功后回调（父级刷新闸门聚合计数）。 */
  onConfirmed?: () => void;
};

export function SourcingReviewPanel({ onConfirmed }: Props) {
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);
  const [confirming, setConfirming] = useState<ProductSummary | null>(null);
  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const [detailId, setDetailId] = useState<number | null>(null);

  const query = useMemo(() => buildReviewProductsQuery(page, pageSize), [page, pageSize]);
  const list = useAsyncData<Paginated<ProductSummary>>(
    () => apiGet(`/api/products${query}`),
    [query],
  );
  const detail = useAsyncData<ProductDetail | null>(
    () => (detailId === null ? Promise.resolve(null) : apiGet(`/api/products/${detailId}`)),
    [detailId],
  );

  const items = list.data?.items ?? [];

  function handlePageSizeChange(size: number) {
    setPageSize(size);
    setPage(1);
  }

  async function confirmProduct() {
    if (!confirming || busy) return;
    setBusy(true);
    setActionError(null);
    try {
      await apiPost<GateConfirmResult>("/api/sourcing/gate-confirm", {
        product_id: confirming.id,
      });
      setConfirming(null);
      list.reload();
      onConfirmed?.();
    } catch (err) {
      setActionError(err instanceof ApiError ? err.message : "操作失败，请稍后重试");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="overflow-hidden rounded-lg border border-zinc-200 bg-white">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-zinc-200 px-4 py-3">
        <div>
          <h2 className="flex items-center gap-2 text-sm font-semibold text-zinc-900">
            <ShieldCheck size={15} className="text-teal-600" />
            选品复核（manual_review 待复核商品）
          </h2>
          <p className="mt-0.5 text-[11px] text-zinc-400">
            人工确认入池 → POST /api/sourcing/gate-confirm；确认后商品进入商品池
          </p>
        </div>
        {list.loading && <span className="text-xs text-zinc-400">加载中…</span>}
      </div>

      {list.error && (
        <div className="border-b border-red-200 bg-red-50 px-4 py-3 text-xs text-red-700">
          {list.error}
          <button type="button" onClick={list.reload} className="ml-2 underline">
            重试
          </button>
        </div>
      )}

      <div className="overflow-x-auto">
        <table className="w-full text-left text-sm">
          <thead className="bg-zinc-50 text-xs text-zinc-500">
            <tr>
              <th className="px-4 py-2.5 font-medium">标题</th>
              <th className="px-4 py-2.5 font-medium">类目</th>
              <th className="px-4 py-2.5 font-medium">得分</th>
              <th className="px-4 py-2.5 font-medium">平台价</th>
              <th className="px-4 py-2.5 font-medium">合规摘要</th>
              <th className="px-4 py-2.5 font-medium">入库时间</th>
              <th className="px-4 py-2.5 text-right font-medium">操作</th>
            </tr>
          </thead>
          <tbody>
            {!list.loading && items.length === 0 && (
              <tr>
                <td colSpan={7} className="px-4 py-12 text-center text-xs text-zinc-400">
                  暂无待复核商品（manual_review 为空）
                </td>
              </tr>
            )}
            {items.map((p) => (
              <tr
                key={p.id}
                onClick={() => setDetailId(p.id)}
                className={cn(
                  "cursor-pointer border-t border-zinc-100 transition hover:bg-teal-50/40",
                  list.loading && "opacity-60",
                )}
              >
                <td className="max-w-[240px] truncate px-4 py-3 font-medium text-zinc-800" title={p.title}>
                  {p.title || "（无标题）"}
                </td>
                <td className="px-4 py-3 text-xs text-zinc-600">{p.category || "—"}</td>
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
                <td className="px-4 py-3 text-xs text-zinc-700">
                  <YuanText value={p.platform_price} />
                </td>
                <td className="max-w-[220px] px-4 py-3">
                  <div className="flex items-center gap-1.5">
                    <StatusBadge labels={COMPLIANCE_LABELS} value={p.compliance?.state} tone="amber" />
                    <span
                      className="truncate text-[11px] text-zinc-500"
                      title={complianceReasonsSummary(p.compliance?.reasons)}
                    >
                      {complianceReasonsSummary(p.compliance?.reasons)}
                    </span>
                  </div>
                </td>
                <td className="whitespace-nowrap px-4 py-3 text-xs text-zinc-500">
                  {formatDateTime(p.created_at)}
                </td>
                <td className="px-4 py-3">
                  <div className="flex justify-end gap-2">
                    <button
                      type="button"
                      onClick={(e) => {
                        e.stopPropagation();
                        setDetailId(p.id);
                      }}
                      className="inline-flex items-center gap-1 rounded border border-zinc-200 px-2 py-1 text-xs text-zinc-600 transition hover:bg-zinc-50"
                    >
                      <Eye size={12} />
                      详情
                    </button>
                    <button
                      type="button"
                      onClick={(e) => {
                        e.stopPropagation();
                        setActionError(null);
                        setConfirming(p);
                      }}
                      className="inline-flex items-center gap-1 rounded bg-teal-600 px-2.5 py-1 text-xs font-medium text-white transition hover:bg-teal-700"
                    >
                      <ShieldCheck size={12} />
                      确认入池
                    </button>
                  </div>
                </td>
              </tr>
            ))}
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

      {/* 确认入池（二次确认） */}
      <ConfirmDialog
        open={confirming !== null}
        title="选品复核 · 确认入池"
        message={
          confirming ? (
            <span>
              确认将「<strong className="text-zinc-900">{confirming.title || `#${confirming.id}`}</strong>
              」放入商品池？入池后进入后续素材/上架/托管链路，需确保合规复核已通过。
            </span>
          ) : null
        }
        confirmText="确认入池"
        busy={busy}
        error={actionError}
        onConfirm={confirmProduct}
        onCancel={() => {
          if (!busy) setConfirming(null);
        }}
      />

      {/* 详情抽屉（复用商品池详情） */}
      {detailId !== null && (
        <ProductDetailPanel
          detail={detail.data}
          loading={detail.loading}
          error={detail.error}
          onClose={() => setDetailId(null)}
        />
      )}
    </div>
  );
}
