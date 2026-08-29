/**
 * 二次确认弹窗（v0.5 批次2）
 *
 * 上架确认（POST /api/listing/tasks/{id}/confirm）、拒审重提（/retry）、
 * 托管暂停/恢复/结束（POST /api/ads/campaigns/{id}/pause|resume|end）共用。
 * 支持可选单行输入（如确认备注 note / 素材 ID 列表），busy 置灰 + error 展示后端 message。
 */
"use client";

import { Loader2 } from "lucide-react";
import type { ReactNode } from "react";

import { cn } from "@/lib/cn";

type Props = {
  open: boolean;
  title: string;
  message: ReactNode;
  confirmText?: string;
  cancelText?: string;
  tone?: "primary" | "danger";
  busy?: boolean;
  error?: string | null;
  inputLabel?: string;
  inputPlaceholder?: string;
  inputValue?: string;
  onInputChange?: (value: string) => void;
  onConfirm: () => void;
  onCancel: () => void;
};

export function ConfirmDialog({
  open,
  title,
  message,
  confirmText = "确认",
  cancelText = "取消",
  tone = "primary",
  busy = false,
  error = null,
  inputLabel,
  inputPlaceholder,
  inputValue,
  onInputChange,
  onConfirm,
  onCancel,
}: Props) {
  if (!open) return null;

  return (
    <div className="fixed inset-0 z-[60] grid place-items-center bg-black/40 p-4" onClick={busy ? undefined : onCancel}>
      <div
        className="w-full max-w-md rounded-xl bg-white p-5 shadow-2xl"
        onClick={(e) => e.stopPropagation()}
        role="dialog"
        aria-modal="true"
      >
        <h3 className="text-base font-semibold text-zinc-900">{title}</h3>
        <div className="mt-2 text-sm leading-6 text-zinc-600">{message}</div>

        {inputLabel !== undefined && (
          <label className="mt-4 block">
            <span className="text-xs text-zinc-500">{inputLabel}</span>
            <input
              value={inputValue ?? ""}
              onChange={(e) => onInputChange?.(e.target.value)}
              placeholder={inputPlaceholder}
              disabled={busy}
              className="mt-1 w-full rounded border border-zinc-200 bg-white px-3 py-2 text-sm text-zinc-800 outline-none transition focus:border-teal-400 disabled:opacity-60"
            />
          </label>
        )}

        {error && (
          <div className="mt-3 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-xs leading-5 text-red-700">
            {error}
          </div>
        )}

        <div className="mt-5 flex justify-end gap-2">
          <button
            type="button"
            onClick={onCancel}
            disabled={busy}
            className="rounded-lg border border-zinc-200 bg-white px-4 py-2 text-sm text-zinc-600 transition hover:bg-zinc-50 disabled:opacity-50"
          >
            {cancelText}
          </button>
          <button
            type="button"
            onClick={onConfirm}
            disabled={busy}
            className={cn(
              "inline-flex items-center gap-1.5 rounded-lg px-4 py-2 text-sm font-medium text-white transition disabled:opacity-60",
              tone === "danger"
                ? "bg-red-600 hover:bg-red-700"
                : "bg-teal-600 hover:bg-teal-700",
            )}
          >
            {busy && <Loader2 size={14} className="animate-spin" />}
            {confirmText}
          </button>
        </div>
      </div>
    </div>
  );
}
