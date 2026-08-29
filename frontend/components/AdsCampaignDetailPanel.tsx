/**
 * 托管计划详情面板（v0.5 批次2）：GET /api/ads/campaigns/{id} 抽屉内容。
 *
 * - 设置：target_type（D5 中文翻译）/ target_roi / material_ids / ad_mode / batch_id /
 *   status 徽章 / 创建·更新时间；
 * - 报表快照序列：recorded_at 升序表格（时间/曝光/花费/成交/补贴/诊断/状态）。
 * 金额一律元（YuanText，DA-001 零换算）；枚举翻译走 lib/enums.ts（M5 三表）。
 */
"use client";

import { Loader2, X } from "lucide-react";

import type { AdsCampaignDetail } from "@/lib/api";
import {
  M5_DIAGNOSIS_LABELS,
  M5_STATUS_LABELS,
  M5_TARGET_TYPE_LABELS,
  enumLabel,
} from "@/lib/enums";
import { formatDateTime } from "@/lib/format";
import { formatTargetBid } from "@/lib/ads";
import { StatusBadge } from "@/components/StatusBadge";
import { YuanText } from "@/components/YuanText";

type Props = {
  detail: AdsCampaignDetail | null;
  loading: boolean;
  error: string | null;
  onClose: () => void;
};

export function AdsCampaignDetailPanel({ detail, loading, error, onClose }: Props) {
  return (
    <div className="fixed inset-0 z-50 bg-black/30" onClick={onClose}>
      <div
        className="absolute inset-y-0 right-0 flex w-full max-w-2xl flex-col bg-white shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex h-14 shrink-0 items-center justify-between border-b border-zinc-200 px-5">
          <div className="text-sm font-semibold text-zinc-900">
            托管计划详情{detail ? ` #${detail.id}` : ""}
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
              {/* 设置 */}
              <section className="rounded-lg border border-zinc-200 p-4">
                <div className="flex flex-wrap items-center gap-2">
                  <StatusBadge labels={M5_STATUS_LABELS} value={detail.status} />
                  <StatusBadge labels={M5_DIAGNOSIS_LABELS} value={detail.diagnosis} />
                  <span className="rounded bg-zinc-100 px-2 py-0.5 text-xs text-zinc-600">
                    商品 #{detail.product_id}
                  </span>
                  <span className="rounded bg-zinc-100 px-2 py-0.5 text-xs text-zinc-600">
                    模式 {detail.ad_mode || "—"}
                  </span>
                </div>
                <dl className="mt-3 grid grid-cols-2 gap-x-6 gap-y-1.5 text-xs sm:grid-cols-3">
                  <div className="flex justify-between gap-2"><dt className="text-zinc-400">目标出价</dt><dd className="text-zinc-800">{formatTargetBid(detail.target_type, detail.target_roi)}</dd></div>
                  <div className="flex justify-between gap-2"><dt className="text-zinc-400">目标类型</dt><dd className="text-zinc-800">{enumLabel(M5_TARGET_TYPE_LABELS, detail.target_type)}</dd></div>
                  <div className="flex justify-between gap-2"><dt className="text-zinc-400">批次</dt><dd className="text-zinc-800">{detail.batch_id ?? "—"}</dd></div>
                  <div className="flex justify-between gap-2"><dt className="text-zinc-400">创建时间</dt><dd className="text-zinc-800">{formatDateTime(detail.created_at, true)}</dd></div>
                  <div className="flex justify-between gap-2"><dt className="text-zinc-400">更新时间</dt><dd className="text-zinc-800">{formatDateTime(detail.updated_at, true)}</dd></div>
                </dl>
                <div className="mt-2 text-xs">
                  <span className="text-zinc-400">绑定素材（{detail.material_ids?.length ?? 0}）：</span>
                  {detail.material_ids?.length ? (
                    <span className="ml-1 inline-flex flex-wrap gap-1">
                      {detail.material_ids.map((id) => (
                        <span key={id} className="rounded bg-zinc-100 px-1.5 py-0.5 font-mono text-[11px] text-zinc-600">
                          {id}
                        </span>
                      ))}
                    </span>
                  ) : (
                    <span className="ml-1 text-zinc-400">—</span>
                  )}
                </div>
              </section>

              {/* 报表快照 */}
              <section className="rounded-lg border border-zinc-200 p-4">
                <h4 className="mb-3 text-sm font-semibold text-zinc-900">
                  报表快照序列（{detail.snapshot_count ?? 0}，recorded_at 升序）
                </h4>
                {detail.snapshots?.length ? (
                  <div className="overflow-x-auto">
                    <table className="w-full text-left text-xs">
                      <thead className="text-zinc-400">
                        <tr>
                          <th className="px-2 py-1.5 font-medium">时间</th>
                          <th className="px-2 py-1.5 font-medium">曝光</th>
                          <th className="px-2 py-1.5 font-medium">花费</th>
                          <th className="px-2 py-1.5 font-medium">成交</th>
                          <th className="px-2 py-1.5 font-medium">补贴</th>
                          <th className="px-2 py-1.5 font-medium">诊断</th>
                          <th className="px-2 py-1.5 font-medium">状态</th>
                        </tr>
                      </thead>
                      <tbody className="text-zinc-700">
                        {detail.snapshots.map((s) => (
                          <tr key={s.id} className="border-t border-zinc-100">
                            <td className="whitespace-nowrap px-2 py-2">{formatDateTime(s.recorded_at, true)}</td>
                            <td className="px-2 py-2">{s.impressions.toLocaleString("zh-CN")}</td>
                            <td className="px-2 py-2"><YuanText value={s.spend_yuan} /></td>
                            <td className="px-2 py-2"><YuanText value={s.gmv_yuan} /></td>
                            <td className="px-2 py-2"><YuanText value={s.subsidy_yuan} /></td>
                            <td className="px-2 py-2"><StatusBadge labels={M5_DIAGNOSIS_LABELS} value={s.diagnosis} /></td>
                            <td className="px-2 py-2"><StatusBadge labels={M5_STATUS_LABELS} value={s.status} /></td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                ) : (
                  <p className="text-xs text-zinc-400">暂无报表快照</p>
                )}
              </section>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
