/**
 * 异常中心（v0.7 + v1.1 批量接管）：blocked / waiting_verification / waiting_login
 * 任务清单 + 人工接管重试（单条 / 批量）。
 *
 * - 顶部统计：待接管总数 + 按 error_code 分组计数卡片（exceptionGroups，中文标签走 lib/enums）。
 * - 清单列：任务ID/商品/阶段/状态徽章/error_code 中文徽章/evidence 摘要（脱敏截断）/
 *   可重试时间（retry_after，即暂停截止语义）/更新时间/操作。
 * - 单条接管：POST /api/workbench/retry/{jobId}（二次确认，文案按任务类型区分：
 *   retryConfirmText）；成功刷新；409 INVALID_STATE / 404 message 展示在弹窗内（D8 三类状态）。
 * - v1.1 批量接管：行复选框 + 全选/取消 + 「批量接管（N）」→ 二次确认 → 调
 *   POST /api/workbench/retry-batch（body {job_ids}，逐 job 复用单端点语义，单 job 失败
 *   不影响其余）→ 结果横幅「成功 X / 失败 Y」+ 失败明细展开（error.message）→ 刷新列表。
 * 展示口径：时间 formatDateTime、枚举 enumLabel/StatusBadge、摘要/汇总走 lib/workbench.ts。
 */
"use client";

import { useState } from "react";
import { AlertTriangle, CheckCircle2, ChevronDown, ChevronUp, RefreshCw, XCircle } from "lucide-react";

import {
  ApiError,
  apiPost,
  type WorkbenchException,
  type WorkbenchRetryBatchResult,
  type WorkbenchRetryResult,
} from "@/lib/api";
import { errorCodeLabel, JOB_STAGE_LABELS, JOB_STATUS_LABELS } from "@/lib/enums";
import { formatDateTime } from "@/lib/format";
import {
  buildBatchRetryBody,
  evidenceSummary,
  exceptionGroups,
  retryConfirmText,
  sumBatchRetryResults,
} from "@/lib/workbench";
import { cn } from "@/lib/cn";
import { ConfirmDialog } from "@/components/ConfirmDialog";
import { StatusBadge } from "@/components/StatusBadge";

type Props = {
  items: WorkbenchException[];
  loading: boolean;
  error: string | null;
  onRefresh: () => void;
};

export function ExceptionCenter({ items, loading, error, onRefresh }: Props) {
  const [target, setTarget] = useState<WorkbenchException | null>(null);
  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  // v1.1 批量接管：选中 job id 集合 / 确认弹窗 / 结果横幅
  const [selectedIds, setSelectedIds] = useState<ReadonlyArray<number>>([]);
  const [batchConfirmOpen, setBatchConfirmOpen] = useState(false);
  const [batchSummary, setBatchSummary] = useState<ReturnType<typeof sumBatchRetryResults> | null>(null);
  const [showFailures, setShowFailures] = useState(false);

  const { total, groups } = exceptionGroups(items);

  // 有效选中：仅保留仍在本页清单中的 id（翻页/刷新后自动剔除失效项）
  const visibleIds = items.map((j) => j.id);
  const selected = selectedIds.filter((id) => visibleIds.includes(id));
  const allVisibleSelected = items.length > 0 && selected.length === items.length;

  function toggleSelect(id: number) {
    setSelectedIds((prev) =>
      prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id],
    );
  }

  function toggleSelectAll() {
    if (allVisibleSelected) {
      setSelectedIds([]);
    } else {
      setSelectedIds([...new Set([...selected, ...visibleIds])]);
    }
  }

  function clearSelection() {
    setSelectedIds([]);
    setBatchSummary(null);
    setShowFailures(false);
  }

  async function handleRetry() {
    if (!target || busy) return;
    setBusy(true);
    setActionError(null);
    try {
      await apiPost<WorkbenchRetryResult>(`/api/workbench/retry/${target.id}`);
      setTarget(null);
      onRefresh();
    } catch (err) {
      setActionError(err instanceof ApiError ? err.message : "操作失败，请稍后重试");
    } finally {
      setBusy(false);
    }
  }

  async function handleBatchRetry() {
    if (selected.length === 0 || busy) return;
    setBusy(true);
    setActionError(null);
    setBatchSummary(null);
    try {
      const result = await apiPost<WorkbenchRetryBatchResult>(
        "/api/workbench/retry-batch",
        buildBatchRetryBody(selected),
      );
      setBatchSummary(sumBatchRetryResults(result.results));
      setBatchConfirmOpen(false);
      clearSelection();
      onRefresh();
    } catch (err) {
      // 保留弹窗打开，后端 message（422/409 等）展示在弹窗内（与单条接管同模式）
      setActionError(err instanceof ApiError ? err.message : "批量接管失败，请稍后重试");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-4">
      {/* 顶部统计：待接管总数 + 按 error_code 分组计数 */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
        <div className="rounded-lg border border-zinc-200 bg-white p-4">
          <div className="text-[11px] text-zinc-400">待接管总数</div>
          <div className="mt-1 text-2xl font-semibold tabular-nums text-zinc-900">{total}</div>
        </div>
        {groups.map((g) => (
          <div
            key={g.errorCode ?? g.label}
            className="rounded-lg border border-zinc-200 bg-white p-4"
          >
            <div className="truncate text-[11px] text-zinc-400" title={g.label}>
              {g.label}
            </div>
            <div
              className={cn(
                "mt-1 text-2xl font-semibold tabular-nums",
                g.errorCode === "VERIFICATION_REQUIRED" || g.errorCode === "AUTH_REQUIRED"
                  ? "text-amber-600"
                  : "text-red-600",
              )}
            >
              {g.count}
            </div>
          </div>
        ))}
      </div>

      {error && (
        <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-xs text-red-700">
          {error}
          <button type="button" onClick={onRefresh} className="ml-2 underline">
            重试
          </button>
        </div>
      )}

      {/* v1.1 批量接管结果横幅：成功 X / 失败 Y（失败展开明细） */}
      {batchSummary && (
        <div
          className={cn(
            "rounded-lg border px-4 py-3 text-xs",
            batchSummary.failed === 0
              ? "border-emerald-200 bg-emerald-50 text-emerald-800"
              : "border-amber-200 bg-amber-50 text-amber-800",
          )}
        >
          <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
            <span className="flex items-center gap-1.5 font-medium">
              <CheckCircle2 size={14} className="text-emerald-600" />
              批量接管完成：成功 {batchSummary.ok} / 失败 {batchSummary.failed}
            </span>
            {batchSummary.failed > 0 && (
              <button
                type="button"
                onClick={() => setShowFailures((v) => !v)}
                className="inline-flex items-center gap-1 text-amber-700 underline"
              >
                {showFailures ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
                失败明细（{batchSummary.failed}）
              </button>
            )}
            <button
              type="button"
              onClick={() => setBatchSummary(null)}
              className="ml-auto text-zinc-400 hover:text-zinc-600"
              aria-label="关闭结果横幅"
            >
              ×
            </button>
          </div>
          {showFailures && batchSummary.failedItems.length > 0 && (
            <ul className="mt-2 space-y-1 border-t border-amber-100 pt-2">
              {batchSummary.failedItems.map((f) => (
                <li key={f.job_id} className="flex items-start gap-2">
                  <XCircle size={13} className="mt-0.5 shrink-0 text-red-500" />
                  <span className="font-mono">#{f.job_id}</span>
                  <span className="text-amber-800">{f.message}</span>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}

      <div className="overflow-hidden rounded-lg border border-zinc-200 bg-white">
        <div className="flex items-center justify-between gap-3 border-b border-zinc-200 px-4 py-3">
          <h2 className="flex items-center gap-2 text-sm font-semibold text-zinc-900">
            <AlertTriangle size={15} className="text-amber-600" />
            待接管任务（blocked / waiting_verification / waiting_login）
          </h2>
          <div className="flex items-center gap-2">
            {selected.length > 0 && (
              <button
                type="button"
                onClick={() => {
                  setActionError(null);
                  setBatchConfirmOpen(true);
                }}
                disabled={busy}
                className="inline-flex items-center gap-1.5 rounded bg-teal-600 px-2.5 py-1.5 text-xs font-medium text-white transition hover:bg-teal-700 disabled:opacity-50"
              >
                <RefreshCw size={13} />
                批量接管（{selected.length}）
              </button>
            )}
            <button
              type="button"
              onClick={onRefresh}
              className="inline-flex items-center gap-1.5 rounded border border-zinc-200 px-2.5 py-1.5 text-xs text-zinc-600 transition hover:bg-zinc-50"
            >
              <RefreshCw size={13} className={cn(loading && "animate-spin")} />
              刷新
            </button>
          </div>
        </div>

        {!error && items.length === 0 && (
          <div className="grid min-h-40 place-items-center py-10 text-sm text-zinc-500">
            暂无异常任务，队列运行正常
          </div>
        )}

        {items.length > 0 && (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead className="bg-zinc-50 text-xs text-zinc-500">
                <tr>
                  <th className="w-10 px-4 py-2.5">
                    <input
                      type="checkbox"
                      checked={allVisibleSelected}
                      onChange={toggleSelectAll}
                      disabled={busy || items.length === 0}
                      title={allVisibleSelected ? "取消全选" : "全选本页"}
                      aria-label="全选本页"
                      className="size-3.5 accent-teal-600"
                    />
                  </th>
                  <th className="px-4 py-2.5 font-medium">任务 ID</th>
                  <th className="px-4 py-2.5 font-medium">商品</th>
                  <th className="px-4 py-2.5 font-medium">阶段</th>
                  <th className="px-4 py-2.5 font-medium">状态</th>
                  <th className="px-4 py-2.5 font-medium">错误码</th>
                  <th className="px-4 py-2.5 font-medium">evidence 摘要</th>
                  <th className="px-4 py-2.5 font-medium">可重试时间</th>
                  <th className="px-4 py-2.5 font-medium">更新时间</th>
                  <th className="px-4 py-2.5 text-right font-medium">操作</th>
                </tr>
              </thead>
              <tbody>
                {items.map((job) => {
                  const checked = selected.includes(job.id);
                  return (
                    <tr
                      key={job.id}
                      className={cn(
                        "border-t border-zinc-100",
                        loading && "opacity-60",
                        checked && "bg-teal-50/50",
                      )}
                    >
                      <td className="px-4 py-3">
                        <input
                          type="checkbox"
                          checked={checked}
                          onChange={() => toggleSelect(job.id)}
                          disabled={busy}
                          aria-label={`选择任务 #${job.id}`}
                          className="size-3.5 accent-teal-600"
                        />
                      </td>
                      <td className="px-4 py-3 font-mono text-xs text-zinc-700">#{job.id}</td>
                      <td className="px-4 py-3 text-xs text-zinc-600">#{job.product_id}</td>
                      <td className="px-4 py-3">
                        <StatusBadge labels={JOB_STAGE_LABELS} value={job.stage} />
                      </td>
                      <td className="px-4 py-3">
                        <StatusBadge labels={JOB_STATUS_LABELS} value={job.status} />
                      </td>
                      <td className="px-4 py-3">
                        <span
                          className={cn(
                            "inline-flex rounded px-2 py-0.5 text-xs font-medium ring-1 ring-inset",
                            job.error_code
                              ? "bg-red-50 text-red-700 ring-red-200"
                              : "bg-zinc-100 text-zinc-500 ring-zinc-200",
                          )}
                          title={job.error_message || undefined}
                        >
                          {job.error_code ? errorCodeLabel(job.error_code) : "—"}
                        </span>
                      </td>
                      <td className="max-w-[240px] px-4 py-3">
                        <span
                          className="block truncate font-mono text-[11px] text-zinc-500"
                          title={evidenceSummary(job.evidence)}
                        >
                          {evidenceSummary(job.evidence)}
                        </span>
                      </td>
                      <td className="whitespace-nowrap px-4 py-3 text-xs text-zinc-500">
                        {formatDateTime(job.retry_after)}
                      </td>
                      <td className="whitespace-nowrap px-4 py-3 text-xs text-zinc-500">
                        {formatDateTime(job.updated_at)}
                      </td>
                      <td className="px-4 py-3">
                        <div className="flex justify-end">
                          <button
                            type="button"
                            onClick={() => {
                              setActionError(null);
                              setTarget(job);
                            }}
                            disabled={busy}
                            className="inline-flex items-center gap-1 rounded bg-teal-600 px-2.5 py-1 text-xs font-medium text-white transition hover:bg-teal-700 disabled:opacity-50"
                          >
                            <RefreshCw size={12} />
                            已处理，恢复执行
                          </button>
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
        {items.length > 0 && (
          <div className="border-t border-zinc-100 px-4 py-2 text-[11px] text-zinc-400">
            已选 {selected.length} 项 · 勾选后可使用「批量接管」一次恢复多个任务（逐 job 独立失败不影响其余）
          </div>
        )}
      </div>

      {/* 单条人工接管（二次确认，文案按任务类型区分） */}
      <ConfirmDialog
        open={target !== null}
        title="人工接管 · 恢复执行"
        message={
          target ? (
            <span>
              任务 <strong className="font-mono text-zinc-900">#{target.id}</strong>（商品 #
              {target.product_id} · {JOB_STAGE_LABELS[target.stage] ?? target.stage} ·{" "}
              {errorCodeLabel(target.error_code)}）：{retryConfirmText(target.status, target.error_code)}
              。确认后任务回到待执行队列，从断点续跑。
            </span>
          ) : null
        }
        confirmText="确认，恢复执行"
        busy={busy}
        error={actionError}
        onConfirm={handleRetry}
        onCancel={() => {
          if (!busy) setTarget(null);
        }}
      />

      {/* v1.1 批量接管（二次确认，文案语义同单条三类） */}
      <ConfirmDialog
        open={batchConfirmOpen}
        title="批量接管 · 恢复执行"
        message={
          <>
            确认对选中的{" "}
            <strong className="font-medium text-zinc-900">{selected.length} 个</strong>{" "}
            异常任务执行批量接管？各任务按对应类型语义恢复执行——验证码类「确认验证码已通过，
            恢复执行」/ 登录类「确认已重新登录，从断点续跑」/ 阻塞类「确认问题已解决，重试」。
            <span className="mt-1 block text-xs text-zinc-400">
              逐任务独立处理：单个任务失败不影响其余；成功后回到待执行队列从断点续跑。
            </span>
          </>
        }
        confirmText="确认批量接管"
        busy={busy}
        error={actionError}
        onConfirm={handleBatchRetry}
        onCancel={() => {
          if (!busy) setBatchConfirmOpen(false);
        }}
      />
    </div>
  );
}
