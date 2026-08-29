/**
 * 托管素材绑定弹窗（v0.5 批次2）：POST /api/ads/campaigns/{id}/materials
 *
 * 最小可用版：输入素材 ID 列表（逗号/空白分隔，parseMaterialIds 解析去重）→ 提交；
 * 成功展示后端 preferred_order（优选顺序：高效 > 潜力 > 探索期）与 note。
 * 失败展示后端 message（409 INVALID_STATE / 422 VALIDATION_ERROR 等）。
 */
"use client";

import { Layers, Loader2 } from "lucide-react";

import type { AdsCampaign, AdsMaterialsResult } from "@/lib/api";
import { EVALUATION_LABELS } from "@/lib/enums";

type Props = {
  open: boolean;
  campaign: AdsCampaign | null;
  input: string;
  onInputChange: (value: string) => void;
  busy: boolean;
  error: string | null;
  result: AdsMaterialsResult | null;
  onSubmit: () => void;
  onClose: () => void;
};

export function AdsMaterialsDialog({
  open,
  campaign,
  input,
  onInputChange,
  busy,
  error,
  result,
  onSubmit,
  onClose,
}: Props) {
  if (!open) return null;

  return (
    <div className="fixed inset-0 z-[60] grid place-items-center bg-black/40 p-4" onClick={busy ? undefined : onClose}>
      <div
        className="w-full max-w-md rounded-xl bg-white p-5 shadow-2xl"
        onClick={(e) => e.stopPropagation()}
        role="dialog"
        aria-modal="true"
      >
        <h3 className="flex items-center gap-2 text-base font-semibold text-zinc-900">
          <Layers size={16} className="text-teal-600" />
          托管素材绑定{campaign ? ` #${campaign.id}` : ""}
        </h3>
        <p className="mt-2 text-xs leading-5 text-zinc-500">
          输入素材 ID 列表（逗号/空白分隔），提交后后端按优选顺序
          高效(efficient) &gt; 潜力(potential) &gt; 探索期(exploring) 排序提示。
        </p>

        <label className="mt-4 block">
          <span className="text-xs text-zinc-500">素材 ID（material_ids）</span>
          <input
            value={input}
            onChange={(e) => onInputChange(e.target.value)}
            placeholder="如 1001, 1002, 1003"
            disabled={busy}
            className="mt-1 w-full rounded border border-zinc-200 bg-white px-3 py-2 text-sm text-zinc-800 outline-none transition focus:border-teal-400 disabled:opacity-60"
          />
        </label>

        {error && (
          <div className="mt-3 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-xs leading-5 text-red-700">
            {error}
          </div>
        )}

        {result && (
          <div className="mt-3 rounded-lg border border-emerald-200 bg-emerald-50 px-3 py-2 text-xs leading-5 text-emerald-800">
            <div className="font-medium">绑定成功（{result.material_ids.length} 个）</div>
            <div className="mt-1">
              优选顺序：
              <span className="ml-1 inline-flex flex-wrap gap-1">
                {result.preferred_order.map((id) => (
                  <span key={id} className="rounded bg-white px-1.5 py-0.5 font-mono text-[11px] text-emerald-700 ring-1 ring-inset ring-emerald-200">
                    {id}
                  </span>
                ))}
              </span>
            </div>
            {result.note && <div className="mt-1 text-emerald-700">{result.note}</div>}
            <div className="mt-1 text-emerald-600">操作人：{result.operator}</div>
            <span className="mt-2 inline-flex flex-wrap gap-1.5">
              {Object.entries(EVALUATION_LABELS).map(([k, v]) => (
                <span key={k} className="text-[11px] text-emerald-600">
                  {k}:{v}
                </span>
              ))}
            </span>
          </div>
        )}

        <div className="mt-5 flex justify-end gap-2">
          <button
            type="button"
            onClick={onClose}
            disabled={busy}
            className="rounded-lg border border-zinc-200 bg-white px-4 py-2 text-sm text-zinc-600 transition hover:bg-zinc-50 disabled:opacity-50"
          >
            {result ? "关闭" : "取消"}
          </button>
          {!result && (
            <button
              type="button"
              onClick={onSubmit}
              disabled={busy}
              className="inline-flex items-center gap-1.5 rounded-lg bg-teal-600 px-4 py-2 text-sm font-medium text-white transition hover:bg-teal-700 disabled:opacity-60"
            >
              {busy && <Loader2 size={14} className="animate-spin" />}
              提交绑定
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
