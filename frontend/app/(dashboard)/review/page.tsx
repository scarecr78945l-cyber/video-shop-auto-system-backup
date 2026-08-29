/**
 * 审核工作台（v0.6 批次3）：M3 生图批次图片审核 + M2 素材相关性预审。
 *
 * Tab「图片审核」：GET /api/optimization/batches（status 筛选 + 分页）→ 批次详情
 *   GET /api/optimization/batches/{id} → ImageReviewPanel 逐图 approve/reject
 *   （POST /api/optimization/assets/{id}/decision，D6 规则草稿闭环）+ 整批通过
 *   （POST /api/optimization/batches/{id}/approve，幂等 already_approved）。
 * Tab「素材相关性预审」：MaterialPreReview（GET /api/assets?relevance_status=manual_review
 *   → POST /api/assets/{id}/relevance-confirm）。
 * 展示口径：时间 formatDateTime、枚举 enumLabel/StatusBadge、金额（本页无金额）。
 */
"use client";

import { useEffect, useState } from "react";

import {
  apiGet,
  apiPost,
  type BatchApproveResult,
  type ImageDecisionResult,
  type OptimizationBatchDetail,
  type OptimizationBatchSummary,
  type OptimizationImage,
  type Paginated,
} from "@/lib/api";
import { useAsyncData } from "@/lib/useAsyncData";
import { buildBatchQuery } from "@/lib/review";
import { OPT_BATCH_STATUS_LABELS, OPT_IMAGE_TYPE_LABELS } from "@/lib/enums";
import { formatDateTime } from "@/lib/format";
import { ImageReviewPanel } from "@/components/ImageReviewPanel";
import { MaterialPreReview } from "@/components/MaterialPreReview";
import { Pagination } from "@/components/Pagination";
import { StatusBadge } from "@/components/StatusBadge";
import { cn } from "@/lib/cn";

const BATCH_STATUS_OPTIONS = Object.entries(OPT_BATCH_STATUS_LABELS);

export default function ReviewPage() {
  const [tab, setTab] = useState<"image" | "material">("image");
  const [batchStatus, setBatchStatus] = useState("");
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);
  const [selectedBatchId, setSelectedBatchId] = useState<string | null>(null);

  // 闸门工作台跳转 `?tab=image|material`：挂载时读取 query 参数做初始 tab（仅客户端运行时）
  useEffect(() => {
    const tabParam = new URLSearchParams(window.location.search).get("tab");
    if (tabParam === "material") setTab("material");
  }, []);

  const query = `${buildBatchQuery(batchStatus, page, pageSize)}`;
  const batches = useAsyncData<Paginated<OptimizationBatchSummary>>(
    () => apiGet(`/api/optimization/batches${query}`),
    [query],
  );
  const detail = useAsyncData<OptimizationBatchDetail | null>(
    () =>
      selectedBatchId === null
        ? Promise.resolve(null)
        : apiGet(`/api/optimization/batches/${selectedBatchId}`),
    [selectedBatchId],
  );

  const batchItems = batches.data?.items ?? [];

  function selectBatch(batchId: string) {
    setSelectedBatchId((current) => (current === batchId ? null : batchId));
  }

  function handleStatusChange(value: string) {
    setBatchStatus(value);
    setPage(1);
  }

  async function handleDecision(
    image: OptimizationImage,
    decision: "approve" | "reject",
    reason: string,
  ): Promise<ImageDecisionResult> {
    const result = await apiPost<ImageDecisionResult>(
      `/api/optimization/assets/${image.image_id}/decision`,
      { decision, reason: reason || undefined },
    );
    detail.reload();
    return result;
  }

  async function handleApproveBatch(): Promise<BatchApproveResult> {
    const result = await apiPost<BatchApproveResult>(
      `/api/optimization/batches/${selectedBatchId}/approve`,
    );
    detail.reload();
    batches.reload();
    return result;
  }

  return (
    <div>
      <div className="mb-6">
        <h1 className="text-xl font-semibold text-zinc-900">审核工作台</h1>
        <p className="mt-1 text-sm text-zinc-500">
          人工闸门：图片审核（M3 生图批次）+ 素材相关性预审（M2 多款式目标款确认）
        </p>
      </div>

      {/* Tab */}
      <div className="mb-4 flex gap-1">
        {(
          [
            ["image", "图片审核"],
            ["material", "素材相关性预审"],
          ] as const
        ).map(([value, label]) => (
          <button
            key={value}
            type="button"
            onClick={() => setTab(value)}
            className={cn(
              "h-10 rounded-lg border px-4 text-sm transition",
              tab === value
                ? "border-teal-600 bg-teal-50 font-medium text-teal-700"
                : "border-zinc-200 bg-white text-zinc-500 hover:bg-zinc-50",
            )}
          >
            {label}
          </button>
        ))}
      </div>

      {tab === "material" ? (
        <MaterialPreReview />
      ) : (
        <div className="grid gap-4 xl:grid-cols-[minmax(320px,380px)_1fr]">
          {/* 批次列表 */}
          <div className="overflow-hidden rounded-lg border border-zinc-200 bg-white">
            <div className="flex items-center justify-between gap-3 border-b border-zinc-200 px-4 py-3">
              <h2 className="text-sm font-semibold text-zinc-900">生图批次</h2>
              <select
                value={batchStatus}
                onChange={(e) => handleStatusChange(e.target.value)}
                className="rounded border border-zinc-200 bg-white px-2 py-1.5 text-xs text-zinc-700 outline-none"
                aria-label="批次状态筛选"
              >
                <option value="">全部状态</option>
                {BATCH_STATUS_OPTIONS.map(([value, label]) => (
                  <option key={value} value={value}>
                    {label}
                  </option>
                ))}
              </select>
            </div>

            {batches.error && (
              <div className="border-b border-red-200 bg-red-50 px-4 py-3 text-xs text-red-700">
                {batches.error}
                <button type="button" onClick={batches.reload} className="ml-2 underline">
                  重试
                </button>
              </div>
            )}

            <div className="max-h-[560px] overflow-y-auto">
              {!batches.loading && batchItems.length === 0 && (
                <div className="px-4 py-14 text-center text-xs text-zinc-400">暂无生图批次</div>
              )}
              {batchItems.map((b) => {
                const active = b.batch_id === selectedBatchId;
                return (
                  <button
                    key={b.batch_id}
                    type="button"
                    onClick={() => selectBatch(b.batch_id)}
                    className={cn(
                      "block w-full border-b border-zinc-100 px-4 py-3 text-left transition",
                      active ? "bg-teal-50/70" : "hover:bg-zinc-50",
                      batches.loading && "opacity-60",
                    )}
                  >
                    <div className="flex items-center justify-between gap-2">
                      <span className="truncate font-mono text-xs font-medium text-zinc-800">{b.batch_id}</span>
                      <StatusBadge labels={OPT_BATCH_STATUS_LABELS} value={b.status} />
                    </div>
                    <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-0.5 text-[11px] text-zinc-500">
                      <span>商品 #{b.product_id}</span>
                      <StatusBadge labels={OPT_IMAGE_TYPE_LABELS} value={b.image_type} tone="blue" />
                      <span>{b.image_count} 张</span>
                      <span className="text-zinc-400">{formatDateTime(b.created_at)}</span>
                    </div>
                  </button>
                );
              })}
            </div>
            <Pagination
              page={page}
              pageSize={pageSize}
              total={batches.data?.total ?? 0}
              onPageChange={setPage}
              onPageSizeChange={(size) => {
                setPageSize(size);
                setPage(1);
              }}
            />
          </div>

          {/* 审核面板 */}
          <ImageReviewPanel
            key={detail.data?.batch_id ?? selectedBatchId ?? "none"}
            batch={detail.data}
            loading={detail.loading}
            error={detail.error}
            onDecision={handleDecision}
            onApproveBatch={handleApproveBatch}
            onRefresh={detail.reload}
            onClose={() => setSelectedBatchId(null)}
          />
        </div>
      )}
    </div>
  );
}
