/**
 * 一键全停开关（v0.4 批次1）
 *
 * POST /api/kill-switch {enabled}（S8，管理员端点）。操作人记录由后端完成
 * （audit event=kill_switch.set）；前端只做开关 + 成功/失败反馈。
 * 非管理员调用返回 403 → 展示后端 message。
 */
"use client";

import { useState } from "react";

import { ApiError, apiPost } from "@/lib/api";
import { cn } from "@/lib/cn";

type Props = {
  enabled: boolean;
  onChange?: (enabled: boolean) => void;
};

export function KillSwitch({ enabled, onChange }: Props) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function toggle() {
    if (busy) return;
    // 开启全停属危险操作，二次确认
    if (!enabled && typeof window !== "undefined" && !window.confirm("确定开启一键全停？所有自动任务将暂停执行。")) {
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await apiPost<{ ok: boolean }>("/api/kill-switch", { enabled: !enabled });
      onChange?.(!enabled);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "操作失败，请稍后重试");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div>
      <button
        type="button"
        onClick={toggle}
        disabled={busy}
        className={cn(
          "inline-flex items-center gap-2 rounded-lg px-3 py-1.5 text-sm font-medium ring-1 ring-inset transition disabled:opacity-60",
          enabled
            ? "bg-red-600 text-white ring-red-700 hover:bg-red-700"
            : "bg-white text-zinc-700 ring-zinc-300 hover:bg-zinc-50",
        )}
      >
        <span
          className={cn(
            "relative inline-flex size-2 rounded-full",
            enabled ? "bg-white" : "bg-zinc-400",
          )}
        />
        {busy ? "提交中…" : enabled ? "全停已开启" : "全停已关闭"}
      </button>
      {error && <p className="mt-1.5 text-xs text-red-600">{error}</p>}
    </div>
  );
}
