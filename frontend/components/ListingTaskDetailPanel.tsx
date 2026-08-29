/**
 * 上架任务详情面板（v0.5 批次2）：GET /api/listing/tasks/{id} 抽屉内容。
 *
 * - 概览：9 态徽章 / 标题(D3 可空) / product_id / attempts / gate_result /
 *   platform_spu_id / product_link / 拒审原因码 / 租约 / 时间；
 * - 状态机轨迹：从操作日志 direction=transition 的 evidence{from,to} 提取
 *   （extractListingTrajectory，lib/listing.ts）；
 * - SPU 映射 / 拒审记录（audit_records：reject_category/reject_reason/fix_candidate）；
 * - 操作日志（GET /api/listing/tasks/{id}/op-logs，direction 徽章 + api + 错误码）。
 * 人工操作按钮（确认上架/拒审重提）由父页触发二次确认弹窗。
 */
"use client";

import { AlertTriangle, ExternalLink, Loader2, X } from "lucide-react";

import type { ListingOpLog, ListingOpLogsResponse, ListingTaskDetail } from "@/lib/api";
import { LISTING_OP_LOG_DIRECTION_LABELS, LISTING_STATUS_LABELS, errorCodeLabel } from "@/lib/enums";
import { formatDateTime } from "@/lib/format";
import { canConfirmTask, canRetryTask, extractListingTrajectory } from "@/lib/listing";
import { StatusBadge } from "@/components/StatusBadge";
import { cn } from "@/lib/cn";

type Props = {
  detail: ListingTaskDetail | null;
  logs: ListingOpLogsResponse | null;
  loading: boolean;
  error: string | null;
  onClose: () => void;
  onConfirm: (task: ListingTaskDetail) => void;
  onRetry: (task: ListingTaskDetail) => void;
};

/** 任意值 → 可展示文本（dict/list → 紧凑 JSON；其他原样）。 */
function displayValue(value: unknown): string {
  if (value === null || value === undefined) return "—";
  if (typeof value === "object") {
    try {
      return JSON.stringify(value);
    } catch {
      return String(value);
    }
  }
  return String(value);
}

export function ListingTaskDetailPanel({
  detail,
  logs,
  loading,
  error,
  onClose,
  onConfirm,
  onRetry,
}: Props) {
  const trajectory = logs ? extractListingTrajectory(logs.items) : [];
  const canConfirm = !!detail && canConfirmTask(detail.status);
  const canRetry = !!detail && canRetryTask(detail.status);

  return (
    <div className="fixed inset-0 z-50 bg-black/30" onClick={onClose}>
      <div
        className="absolute inset-y-0 right-0 flex w-full max-w-2xl flex-col bg-white shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex h-14 shrink-0 items-center justify-between border-b border-zinc-200 px-5">
          <div className="text-sm font-semibold text-zinc-900">
            上架任务详情{detail ? ` · ${detail.task_id}` : ""}
          </div>
          <button
            type="button"
            onClick={onClose}
            className="grid size-8 place-items-center rounded text-zinc-400 transition hover:bg-zinc-100 hover:text-zinc-700"
            aria-label="关闭"
          >
            <X size={18} />
          </button>
        </div>

        <div className="flex-1 overflow-y-auto p-5">
          {error && (
            <div className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-700">{error}</div>
          )}
          {loading && !detail && (
            <div className="grid h-48 place-items-center text-sm text-zinc-400">
              <span className="flex items-center gap-2">
                <Loader2 size={16} className="animate-spin" />
                加载中…
              </span>
            </div>
          )}
          {!error && detail && (
            <div className="space-y-5">
              {/* 概览 */}
              <section className="rounded-lg border border-zinc-200 p-4">
                <div className="flex flex-wrap items-center gap-2">
                  <StatusBadge labels={LISTING_STATUS_LABELS} value={detail.status} />
                  <span className="rounded bg-zinc-100 px-2 py-0.5 text-xs text-zinc-600">
                    商品 #{detail.product_id}
                  </span>
                  <span className="rounded bg-zinc-100 px-2 py-0.5 text-xs text-zinc-600">
                    尝试 {detail.attempts ?? 0} 次
                  </span>
                  {detail.error_code && (
                    <span className="inline-flex items-center gap-1 rounded bg-red-50 px-2 py-0.5 text-xs text-red-700 ring-1 ring-inset ring-red-200">
                      <AlertTriangle size={12} />
                      {errorCodeLabel(detail.error_code)}
                    </span>
                  )}
                  {detail.reject_reason_code && (
                    <span className="rounded bg-amber-50 px-2 py-0.5 text-xs text-amber-700 ring-1 ring-inset ring-amber-200">
                      拒审码 {detail.reject_reason_code}
                    </span>
                  )}
                </div>
                {detail.title && (
                  <p className="mt-2 text-sm font-medium leading-6 text-zinc-800">{detail.title}</p>
                )}
                <dl className="mt-3 grid grid-cols-2 gap-x-6 gap-y-1.5 text-xs sm:grid-cols-3">
                  <div className="flex justify-between gap-2"><dt className="text-zinc-400">创建时间</dt><dd className="text-zinc-800">{formatDateTime(detail.created_at, true)}</dd></div>
                  <div className="flex justify-between gap-2"><dt className="text-zinc-400">更新时间</dt><dd className="text-zinc-800">{formatDateTime(detail.updated_at, true)}</dd></div>
                  <div className="flex justify-between gap-2"><dt className="text-zinc-400">生成版本</dt><dd className="text-zinc-800">{detail.generation_version ?? "—"}</dd></div>
                  <div className="flex justify-between gap-2"><dt className="text-zinc-400">平台 SPU</dt><dd className="truncate text-zinc-800" title={detail.platform_spu_id ?? undefined}>{detail.platform_spu_id ?? "—"}</dd></div>
                  <div className="flex justify-between gap-2"><dt className="text-zinc-400">链接验证时间</dt><dd className="text-zinc-800">{formatDateTime(detail.link_verified_at, true)}</dd></div>
                  <div className="flex justify-between gap-2"><dt className="text-zinc-400">租约归属</dt><dd className="text-zinc-800">{detail.lease_owner ?? "—"}</dd></div>
                </dl>
                {detail.product_link && (
                  <p className="mt-2 flex items-center gap-1.5 text-xs">
                    <ExternalLink size={12} className="text-zinc-400" />
                    <a
                      href={detail.product_link}
                      target="_blank"
                      rel="noreferrer"
                      className="truncate text-teal-700 underline-offset-2 hover:underline"
                    >
                      {detail.product_link}
                    </a>
                  </p>
                )}
              </section>

              {/* 状态机轨迹 */}
              <section className="rounded-lg border border-zinc-200 p-4">
                <h4 className="mb-3 text-sm font-semibold text-zinc-900">
                  状态机轨迹{trajectory.length > 0 ? `（${trajectory.length} 步）` : ""}
                </h4>
                {trajectory.length > 0 ? (
                  <ol className="space-y-1.5">
                    {trajectory.map((step, index) => (
                      <li key={index} className="flex flex-wrap items-center gap-2 text-xs">
                        <StatusBadge labels={LISTING_STATUS_LABELS} value={step.from} />
                        <span className="text-zinc-400">→</span>
                        <StatusBadge labels={LISTING_STATUS_LABELS} value={step.to} />
                        <span className="text-zinc-400">{formatDateTime(step.at, true)}</span>
                      </li>
                    ))}
                  </ol>
                ) : (
                  <p className="text-xs text-zinc-400">暂无状态迁移记录</p>
                )}
                {detail.gate_result !== undefined && detail.gate_result !== null && (
                  <div className="mt-3">
                    <div className="text-xs text-zinc-400">gate_result（已脱敏）</div>
                    <pre className="mt-1 max-h-40 overflow-auto rounded bg-zinc-50 p-2 text-[11px] leading-5 text-zinc-600">
                      {displayValue(detail.gate_result)}
                    </pre>
                  </div>
                )}
              </section>

              {/* SPU 映射 */}
              {detail.spu && (
                <section className="rounded-lg border border-zinc-200 p-4">
                  <h4 className="mb-3 text-sm font-semibold text-zinc-900">SPU 映射</h4>
                  <dl className="grid grid-cols-2 gap-x-6 gap-y-1.5 text-xs sm:grid-cols-3">
                    <div className="flex justify-between gap-2"><dt className="text-zinc-400">SPU ID</dt><dd className="truncate text-zinc-800" title={detail.spu.spu_id}>{detail.spu.spu_id}</dd></div>
                    <div className="flex justify-between gap-2"><dt className="text-zinc-400">类目 ID</dt><dd className="text-zinc-800">{detail.spu.category_id ?? "—"}</dd></div>
                    <div className="flex justify-between gap-2"><dt className="text-zinc-400">状态</dt><dd className="text-zinc-800">{detail.spu.status || "—"}</dd></div>
                    <div className="col-span-2 flex justify-between gap-2"><dt className="text-zinc-400">标题</dt><dd className="text-zinc-800">{detail.spu.title || "—"}</dd></div>
                    <div className="flex justify-between gap-2"><dt className="text-zinc-400">审核单 ID</dt><dd className="truncate text-zinc-800" title={detail.spu.audit_id ?? undefined}>{detail.spu.audit_id ?? "—"}</dd></div>
                  </dl>
                </section>
              )}

              {/* 拒审记录 */}
              <section className="rounded-lg border border-zinc-200 p-4">
                <h4 className="mb-3 text-sm font-semibold text-zinc-900">
                  拒审记录（{detail.audit_records?.length ?? 0}）
                </h4>
                {detail.audit_records?.length ? (
                  <div className="space-y-2">
                    {detail.audit_records.map((a) => (
                      <div key={a.audit_record_id} className="rounded border border-zinc-100 bg-zinc-50/60 p-3 text-xs leading-5">
                        <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-zinc-700">
                          <span className="font-medium text-zinc-900">{a.reject_category || "（无拒审类目）"}</span>
                          <span className="rounded bg-zinc-100 px-1.5 py-0.5 text-[11px] text-zinc-500">
                            审核单 {a.audit_id ?? "—"}
                          </span>
                          <span className="rounded bg-zinc-100 px-1.5 py-0.5 text-[11px] text-zinc-500">
                            平台状态 {a.audit_status || "—"}
                          </span>
                          <span className="text-zinc-400">{formatDateTime(a.submit_at, true)}</span>
                          {a.resubmit_required && (
                            <span className="rounded bg-amber-50 px-1.5 py-0.5 text-[11px] text-amber-700 ring-1 ring-inset ring-amber-200">需重新提交</span>
                          )}
                        </div>
                        {a.reject_reason && <p className="mt-1 text-zinc-600">驳回原因：{a.reject_reason}</p>}
                        {a.fix_candidate !== null && a.fix_candidate !== undefined && (
                          <p className="mt-0.5 text-zinc-500">修复建议：{displayValue(a.fix_candidate)}</p>
                        )}
                      </div>
                    ))}
                  </div>
                ) : (
                  <p className="text-xs text-zinc-400">暂无拒审记录</p>
                )}
              </section>

              {/* 操作日志 */}
              <section className="rounded-lg border border-zinc-200 p-4">
                <h4 className="mb-3 text-sm font-semibold text-zinc-900">
                  微信操作日志（{logs?.items?.length ?? 0}，evidence 已脱敏）
                </h4>
                {logs && logs.items.length > 0 ? (
                  <div className="overflow-x-auto">
                    <table className="w-full text-left text-xs">
                      <thead className="text-zinc-400">
                        <tr>
                          <th className="px-2 py-1.5 font-medium">方向</th>
                          <th className="px-2 py-1.5 font-medium">接口</th>
                          <th className="px-2 py-1.5 font-medium">HTTP</th>
                          <th className="px-2 py-1.5 font-medium">错误码</th>
                          <th className="px-2 py-1.5 font-medium">时间</th>
                        </tr>
                      </thead>
                      <tbody className="text-zinc-700">
                        {logs.items.map((log: ListingOpLog) => (
                          <tr key={log.log_id} className="border-t border-zinc-100">
                            <td className="px-2 py-2">
                              <StatusBadge
                                labels={LISTING_OP_LOG_DIRECTION_LABELS}
                                value={log.direction}
                                tone={log.direction === "transition" ? "blue" : "gray"}
                              />
                            </td>
                            <td className="max-w-[180px] truncate px-2 py-2" title={log.api}>{log.api || "—"}</td>
                            <td className="px-2 py-2">{log.status_code ?? "—"}</td>
                            <td className="px-2 py-2">
                              {log.error_code ? (
                                <span className={cn("rounded px-1.5 py-0.5 text-[11px]", "bg-red-50 text-red-700")}>
                                  {errorCodeLabel(log.error_code)}
                                </span>
                              ) : (
                                "—"
                              )}
                            </td>
                            <td className="whitespace-nowrap px-2 py-2">{formatDateTime(log.created_at, true)}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                ) : (
                  <p className="text-xs text-zinc-400">暂无操作日志</p>
                )}
              </section>

              {/* 人工操作 */}
              {(canConfirm || canRetry) && (
                <section className="flex flex-wrap gap-2 border-t border-zinc-100 pt-4">
                  {canConfirm && (
                    <button
                      type="button"
                      onClick={() => onConfirm(detail)}
                      className="inline-flex items-center gap-1.5 rounded-lg bg-teal-600 px-4 py-2 text-sm font-medium text-white transition hover:bg-teal-700"
                    >
                      确认上架（入队创建）
                    </button>
                  )}
                  {canRetry && (
                    <button
                      type="button"
                      onClick={() => onRetry(detail)}
                      className="inline-flex items-center gap-1.5 rounded-lg border border-amber-300 bg-amber-50 px-4 py-2 text-sm font-medium text-amber-800 transition hover:bg-amber-100"
                    >
                      拒审修复后重提
                    </button>
                  )}
                </section>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
