/**
 * 异常中心（v0.7）：blocked / waiting_verification / waiting_login 任务清单 + 人工接管重试。
 *
 * - 顶部统计：待接管总数 + 按 error_code 分组计数卡片（exceptionGroups，中文标签走 lib/enums）。
 * - 清单列：任务ID/商品/阶段/状态徽章/error_code 中文徽章/evidence 摘要（脱敏截断）/
 *   可重试时间（retry_after，即暂停截止语义）/更新时间/操作。
 * - 人工接管：POST /api/workbench/retry/{jobId}（二次确认，文案按任务类型区分：
 *   retryConfirmText）；成功刷新；409 INVALID_STATE / 404 message 展示在弹窗内（D8 三类状态）。
 * 展示口径：时间 formatDateTime、枚举 enumLabel/StatusBadge、摘要走 lib/workbench.ts。
 */
"use client";

import { useState } from "react";
import { AlertTriangle, RefreshCw } from "lucide-react";

import {
  ApiError,
  apiPost,
  type WorkbenchException,
  type WorkbenchRetryResult,
} from "@/lib/api";
import { errorCodeLabel, JOB_STAGE_LABELS, JOB_STATUS_LABELS } from "@/lib/enums";
import { formatDateTime } from "@/lib/format";
import { evidenceSummary, exceptionGroups, retryConfirmText } from "@/lib/workbench";
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

  const { total, groups } = exceptionGroups(items);

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

      <div className="overflow-hidden rounded-lg border border-zinc-200 bg-white">
        <div className="flex items-center justify-between gap-3 border-b border-zinc-200 px-4 py-3">
          <h2 className="flex items-center gap-2 text-sm font-semibold text-zinc-900">
            <AlertTriangle size={15} className="text-amber-600" />
            待接管任务（blocked / waiting_verification / waiting_login）
          </h2>
          <button
            type="button"
            onClick={onRefresh}
            className="inline-flex items-center gap-1.5 rounded border border-zinc-200 px-2.5 py-1.5 text-xs text-zinc-600 transition hover:bg-zinc-50"
          >
            <RefreshCw size={13} className={cn(loading && "animate-spin")} />
            刷新
          </button>
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
                {items.map((job) => (
                  <tr
                    key={job.id}
                    className={cn("border-t border-zinc-100", loading && "opacity-60")}
                  >
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
                          className="inline-flex items-center gap-1 rounded bg-teal-600 px-2.5 py-1 text-xs font-medium text-white transition hover:bg-teal-700"
                        >
                          <RefreshCw size={12} />
                          已处理，恢复执行
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* 人工接管（二次确认，文案按任务类型区分） */}
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
    </div>
  );
}
