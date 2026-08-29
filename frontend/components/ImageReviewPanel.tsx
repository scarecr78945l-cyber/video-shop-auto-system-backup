/**
 * 图片审核面板（v0.6 批次3）：M3 生图批次逐图人工审核（10 文档第五节投放素材预审 +
 * 09 状态机第 5 步图片审核；对接 /api/optimization/batches/{id} 与 assets/{id}/decision）。
 *
 * - 主图/详情图 tab + 进度条（reviewProgress）；
 * - 逐图 approve/reject：驳回必填理由（下拉预置 REJECTION_REASONS + 自定义）；
 * - 整批通过（二次确认，后端幂等 already_approved=true 视为成功）；
 * - D6：decision 触发 P0-2 规则草稿闭环（learning_rule_drafts），成功提示；
 * - 图片预览（v1.1）：待审图卡片图片区接 GET /api/assets/{id}/preview（fetch blob +
 *   objectURL，credentials include 带会话 cookie；AssetPreview 组件）；端点不可用
 *   （404/400/网络）时静默回退占位（ImageOff + 规格/质检/路径），不打断审核流程；
 *   视频类型（后端 video → 400）同样回退占位。
 */
"use client";

import { Check, CheckCheck, ImageOff, Loader2, RotateCcw, X } from "lucide-react";
import { useMemo, useState } from "react";

import type { BatchApproveResult, ImageDecisionResult, OptimizationBatchDetail, OptimizationImage } from "@/lib/api";
import {
  OPT_BATCH_STATUS_LABELS,
  OPT_IMAGE_REVIEW_STATUS_LABELS,
  OPT_IMAGE_TYPE_LABELS,
  OPT_QUALITY_LABELS,
  OPT_REVIEW_GATE_LABELS,
  OPT_REVIEW_RESULT_LABELS,
} from "@/lib/enums";
import { formatDateTime } from "@/lib/format";
import { canApproveBatch, countReviewStatus, filterAssetsByType, formatImageSpec, REJECTION_REASONS, reviewProgress } from "@/lib/review";
import { AssetPreview } from "@/components/AssetPreview";
import { ConfirmDialog } from "@/components/ConfirmDialog";
import { StatusBadge } from "@/components/StatusBadge";
import { cn } from "@/lib/cn";

const CUSTOM_REASON = "__custom__";

type Props = {
  batch: OptimizationBatchDetail | null;
  loading: boolean;
  error: string | null;
  /** 逐图判定（approve/reject）。reject 时 reason 必填。抛错由面板展示后端 message。 */
  onDecision: (image: OptimizationImage, decision: "approve" | "reject", reason: string) => Promise<ImageDecisionResult>;
  /** 整批通过（幂等：already_approved=true 视为成功）。 */
  onApproveBatch: () => Promise<BatchApproveResult>;
  onRefresh: () => void;
  onClose: () => void;
};

export function ImageReviewPanel({ batch, loading, error, onDecision, onApproveBatch, onRefresh, onClose }: Props) {
  const [tab, setTab] = useState<"main" | "detail">("main");
  const [reasonByImage, setReasonByImage] = useState<Record<string, string>>({});
  const [customReasonByImage, setCustomReasonByImage] = useState<Record<string, string>>({});
  const [busyImageId, setBusyImageId] = useState<string | null>(null);
  const [approveOpen, setApproveOpen] = useState(false);
  const [approveBusy, setApproveBusy] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const [ruleDraftNotice, setRuleDraftNotice] = useState<string | null>(null);

  const assets = batch?.assets ?? [];
  const counts = useMemo(() => countReviewStatus(assets), [assets]);
  const progress = useMemo(() => reviewProgress(assets), [assets]);
  const tabAssets = useMemo(() => filterAssetsByType(assets, tab), [assets, tab]);
  const canBatchApprove = useMemo(() => canApproveBatch(batch), [batch]);

  function selectedReason(image: OptimizationImage): string {
    const picked = reasonByImage[image.image_id] ?? "";
    if (picked === CUSTOM_REASON) return (customReasonByImage[image.image_id] ?? "").trim();
    return picked;
  }

  async function decide(image: OptimizationImage, decision: "approve" | "reject") {
    if (busyImageId !== null) return;
    const reason = decision === "reject" ? selectedReason(image) : "";
    if (decision === "reject" && !reason) return; // 驳回必填理由（按钮已禁用，双保险）
    setBusyImageId(image.image_id);
    setActionError(null);
    setRuleDraftNotice(null);
    try {
      const result = await onDecision(image, decision, reason);
      if (result?.rule_draft_created) {
        setRuleDraftNotice("本次判定已沉淀审核规则草稿（P0-2 规则草稿闭环：learning_rule_drafts）");
      }
    } catch (err) {
      setActionError(err instanceof Error ? err.message : "审核判定失败，请稍后重试");
    } finally {
      setBusyImageId(null);
    }
  }

  async function approveBatch() {
    setApproveBusy(true);
    setActionError(null);
    try {
      await onApproveBatch();
      setApproveOpen(false);
    } catch (err) {
      setActionError(err instanceof Error ? err.message : "整批通过失败，请稍后重试");
    } finally {
      setApproveBusy(false);
    }
  }

  if (!batch && !loading) {
    return (
      <div className="grid min-h-[420px] place-items-center rounded-lg border border-zinc-200 bg-white text-sm text-zinc-400">
        请先选择一个批次
      </div>
    );
  }

  return (
    <section className="overflow-hidden rounded-lg border border-zinc-200 bg-white">
      {/* 头部：批次信息 + 进度 + 整批通过 */}
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-zinc-200 px-4 py-3">
        <div className="flex min-w-0 items-center gap-3">
          {onClose && (
            <button
              type="button"
              onClick={onClose}
              className="grid size-8 shrink-0 place-items-center rounded border border-zinc-200 text-zinc-500 transition hover:bg-zinc-50"
              aria-label="返回批次列表"
            >
              <X size={15} />
            </button>
          )}
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <h2 className="truncate font-mono text-sm font-semibold text-zinc-900">{batch?.batch_id ?? "…"}</h2>
              {batch && <StatusBadge labels={OPT_BATCH_STATUS_LABELS} value={batch.status} />}
              {batch && <StatusBadge labels={OPT_IMAGE_TYPE_LABELS} value={batch.image_type} tone="blue" />}
            </div>
            <div className="mt-1 flex flex-wrap gap-x-4 gap-y-1 text-xs text-zinc-500">
              <span>商品 #{batch?.product_id ?? "—"}</span>
              <span>目标 {batch?.target_count ?? 0} 张</span>
              <span>创建 {formatDateTime(batch?.created_at)}</span>
            </div>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <div className="text-right">
            <div className="text-xs font-medium text-zinc-700">
              已审 {progress.done} / {progress.total} 张
              {counts.rejected > 0 && <span className="ml-2 text-red-600">驳回 {counts.rejected}</span>}
            </div>
            <div className="mt-1 h-1.5 w-40 overflow-hidden rounded-full bg-zinc-100">
              <div
                className="h-full rounded-full bg-teal-500 transition-all"
                style={{ width: `${progress.percent}%` }}
              />
            </div>
          </div>
          <button
            type="button"
            onClick={() => setApproveOpen(true)}
            disabled={!canBatchApprove || approveBusy}
            className="inline-flex h-9 items-center gap-1.5 rounded-lg bg-teal-600 px-3 text-xs font-medium text-white transition hover:bg-teal-700 disabled:cursor-not-allowed disabled:opacity-50"
            title={canBatchApprove ? "批内全部图片置为已通过（幂等）" : "批次已通过或批内无图片"}
          >
            {approveBusy ? <Loader2 size={14} className="animate-spin" /> : <CheckCheck size={14} />}
            整批通过
          </button>
          <button
            type="button"
            onClick={onRefresh}
            disabled={loading}
            className="grid size-9 place-items-center rounded-lg border border-zinc-200 text-zinc-500 transition hover:bg-zinc-50 disabled:opacity-50"
            title="刷新批次"
            aria-label="刷新批次"
          >
            <RotateCcw size={14} />
          </button>
        </div>
      </div>

      {/* 主图/详情图 tab */}
      <div className="flex items-center gap-1 border-b border-zinc-200 px-4">
        {(["main", "detail"] as const).map((type) => {
          const typeAssets = filterAssetsByType(assets, type);
          const active = tab === type;
          return (
            <button
              key={type}
              type="button"
              onClick={() => setTab(type)}
              className={cn(
                "h-11 border-b-2 px-3 text-sm transition",
                active
                  ? "border-teal-600 font-medium text-teal-700"
                  : "border-transparent text-zinc-500 hover:text-zinc-700",
              )}
            >
              {OPT_IMAGE_TYPE_LABELS[type] ?? type}（{typeAssets.length}）
            </button>
          );
        })}
        <div className="ml-auto hidden text-xs text-zinc-400 md:block">
          待审 {counts.pending} · 通过 {counts.approved} · 驳回 {counts.rejected}
        </div>
      </div>

      {/* 提示区 */}
      {ruleDraftNotice && (
        <div className="border-b border-teal-100 bg-teal-50 px-4 py-2 text-xs text-teal-700">{ruleDraftNotice}</div>
      )}
      {(actionError || error) && (
        <div className="border-b border-red-200 bg-red-50 px-4 py-2 text-xs text-red-700">
          {actionError ?? error}
        </div>
      )}

      {loading ? (
        <div className="grid min-h-[360px] place-items-center text-sm text-zinc-400">
          <span className="flex items-center gap-2">
            <Loader2 size={16} className="animate-spin" />
            正在读取批次
          </span>
        </div>
      ) : (
        <div className={cn("grid gap-3 p-4", tab === "main" ? "grid-cols-1 sm:grid-cols-2 xl:grid-cols-3" : "grid-cols-1 md:grid-cols-2")}>
          {tabAssets.map((image) => (
            <ImageCard
              key={image.image_id}
              image={image}
              busy={busyImageId === image.image_id}
              busyAny={busyImageId !== null}
              reason={reasonByImage[image.image_id] ?? ""}
              customReason={customReasonByImage[image.image_id] ?? ""}
              canReject={selectedReason(image).length > 0}
              onReasonChange={(value) => {
                setReasonByImage((m) => ({ ...m, [image.image_id]: value }));
                if (value !== CUSTOM_REASON) setCustomReasonByImage((m) => ({ ...m, [image.image_id]: "" }));
              }}
              onCustomReasonChange={(value) => setCustomReasonByImage((m) => ({ ...m, [image.image_id]: value }))}
              onApprove={() => void decide(image, "approve")}
              onReject={() => void decide(image, "reject")}
            />
          ))}
          {tabAssets.length === 0 && (
            <div className="col-span-full py-16 text-center text-sm text-zinc-400">
              <ImageOff className="mx-auto mb-2 text-zinc-300" size={28} />
              当前没有可审核图片
            </div>
          )}
        </div>
      )}

      <ConfirmDialog
        open={approveOpen}
        title="整批通过"
        message={
          <>
            确认将本批 <span className="font-mono font-medium">{batch?.batch_id}</span> 全部{" "}
            <span className="font-medium text-teal-700">{counts.total} 张</span> 图片置为已通过并完成图片审核？
            已驳回图片也会一并置为通过（幂等操作，可重复提交）。
          </>
        }
        confirmText="整批通过"
        busy={approveBusy}
        onConfirm={() => void approveBatch()}
        onCancel={() => setApproveOpen(false)}
      />
    </section>
  );
}

function ImageCard({
  image,
  busy,
  busyAny,
  reason,
  customReason,
  canReject,
  onReasonChange,
  onCustomReasonChange,
  onApprove,
  onReject,
}: {
  image: OptimizationImage;
  busy: boolean;
  busyAny: boolean;
  reason: string;
  customReason: string;
  canReject: boolean;
  onReasonChange: (value: string) => void;
  onCustomReasonChange: (value: string) => void;
  onApprove: () => void;
  onReject: () => void;
}) {
  const status = image.review_status;
  const isDecided = status === "approved" || status === "rejected";
  return (
    <article className={cn("overflow-hidden rounded-lg border border-zinc-200 bg-zinc-50", busy && "opacity-60")}>
      {/* 预览（v1.1）：接 GET /api/assets/{id}/preview 真实图片流；端点不可用时回退占位 */}
      <div
        className={cn(
          "relative flex items-center justify-center bg-white",
          image.image_type === "main" ? "aspect-square" : "aspect-[4/5]",
        )}
      >
        <AssetPreview
          assetId={image.image_id}
          enabled
          aspectClass=""
          className="absolute inset-0"
          alt={`${OPT_IMAGE_TYPE_LABELS[image.image_type] ?? image.image_type} ${image.variant_no} 预览`}
          placeholder={
            <div className="grid place-items-center text-zinc-300">
              <ImageOff size={36} />
            </div>
          }
        />
        <span className="absolute left-2 top-2 z-10 rounded bg-black/70 px-2 py-0.5 text-xs text-white">
          {OPT_IMAGE_TYPE_LABELS[image.image_type] ?? image.image_type} {image.variant_no}
        </span>
        {isDecided && (
          <span
            className={cn(
              "absolute right-2 top-2 z-10 grid size-7 place-items-center rounded-full text-white",
              status === "approved" ? "bg-emerald-600" : "bg-red-600",
            )}
          >
            {status === "approved" ? <Check size={15} /> : <X size={15} />}
          </span>
        )}
      </div>

      <div className="border-t border-zinc-200 p-2.5">
        {/* 元信息 */}
        <div className="mb-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-zinc-500">
          <span>{formatImageSpec(image)}</span>
          <StatusBadge labels={OPT_QUALITY_LABELS} value={String(image.quality_ok)} tone={image.quality_ok ? "green" : "red"} />
          <StatusBadge labels={OPT_IMAGE_REVIEW_STATUS_LABELS} value={status} />
        </div>
        <div className="mb-2 truncate text-[11px] text-zinc-400" title={image.file_path}>
          {image.file_path || "—"}
        </div>

        {status === "rejected" && image.reject_reason && (
          <div className="mb-2 rounded bg-red-50 px-2 py-1 text-xs text-red-600">原因：{image.reject_reason}</div>
        )}

        {status !== "approved" && (
          <>
            <label className="mb-1.5 block">
              <span className="text-[11px] text-zinc-400">驳回理由（必填）</span>
              <select
                value={reason}
                onChange={(e) => onReasonChange(e.target.value)}
                disabled={busyAny}
                className="mt-0.5 h-8 w-full rounded border border-zinc-200 bg-white px-2 text-xs text-zinc-700 outline-none focus:border-teal-500 disabled:opacity-50"
              >
                <option value="">请选择理由</option>
                {REJECTION_REASONS.map((r) => (
                  <option key={r} value={r}>
                    {r}
                  </option>
                ))}
                <option value={CUSTOM_REASON}>自定义…</option>
              </select>
            </label>
            {reason === CUSTOM_REASON && (
              <input
                value={customReason}
                onChange={(e) => onCustomReasonChange(e.target.value)}
                disabled={busyAny}
                placeholder="输入自定义驳回理由"
                className="mb-1.5 h-8 w-full rounded border border-zinc-200 bg-white px-2 text-xs text-zinc-700 outline-none focus:border-teal-500 disabled:opacity-50"
              />
            )}
            <div className="grid grid-cols-2 gap-2">
              <button
                type="button"
                onClick={onApprove}
                disabled={busyAny || status === "approved"}
                className="inline-flex h-8 items-center justify-center gap-1 rounded border border-emerald-200 bg-white text-xs font-medium text-emerald-700 transition hover:bg-emerald-50 disabled:opacity-50"
              >
                {busy ? <Loader2 size={13} className="animate-spin" /> : <Check size={13} />}
                {status === "approved" ? "已通过" : "通过"}
              </button>
              <button
                type="button"
                onClick={onReject}
                disabled={busyAny || !canReject || status === "rejected"}
                className="inline-flex h-8 items-center justify-center gap-1 rounded border border-red-200 bg-white text-xs font-medium text-red-700 transition hover:bg-red-50 disabled:opacity-50"
              >
                {busy ? <Loader2 size={13} className="animate-spin" /> : <X size={13} />}
                {status === "rejected" ? "已驳回" : "驳回"}
              </button>
            </div>
          </>
        )}

        {/* 审核流水（audit：rule/evaluate/manual） */}
        {image.audit.length > 0 && (
          <div className="mt-2 border-t border-zinc-100 pt-2">
            <div className="mb-1 text-[11px] text-zinc-400">审核流水（{image.audit.length}）</div>
            <ul className="space-y-1">
              {image.audit.map((record) => (
                <li key={record.review_id} className="flex flex-wrap items-center gap-x-2 gap-y-0.5 text-[11px] text-zinc-500">
                  <StatusBadge labels={OPT_REVIEW_GATE_LABELS} value={record.gate_type} />
                  <StatusBadge labels={OPT_REVIEW_RESULT_LABELS} value={record.result} />
                  <span className="text-zinc-400">{record.reviewer || "—"}</span>
                  <span className="text-zinc-300">{formatDateTime(record.created_at)}</span>
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>
    </article>
  );
}
