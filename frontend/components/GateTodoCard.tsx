/**
 * 闸门待办卡片（v0.7）：计数 + 状态图标 + 跳转链接。
 *
 * count > 0 → 高亮（teal）+「前往处理」；count = 0 → 置灰 +「无待办」。
 * 纯展示组件：label/hint/href 由 lib/workbench.ts 的 GATE_DEFS 提供（组件不硬编码中文）。
 */
"use client";

import Link from "next/link";
import type { ComponentType } from "react";

import { cn } from "@/lib/cn";

type Props = {
  label: string;
  count: number;
  hint: string;
  href: string;
  icon: ComponentType<{ size?: number | string; className?: string }>;
};

export function GateTodoCard({ label, count, hint, href, icon: Icon }: Props) {
  const hasTodo = count > 0;
  return (
    <Link
      href={href}
      className={cn(
        "group rounded-lg border bg-white p-4 transition",
        hasTodo
          ? "border-zinc-200 hover:border-teal-300 hover:shadow-sm"
          : "border-zinc-200 opacity-70 hover:opacity-90",
      )}
    >
      <div className="flex items-start justify-between gap-2">
        <span
          className={cn(
            "grid size-9 place-items-center rounded-lg",
            hasTodo ? "bg-teal-50 text-teal-600" : "bg-zinc-100 text-zinc-400",
          )}
        >
          <Icon size={18} />
        </span>
        <span
          className={cn(
            "rounded px-2 py-0.5 text-lg font-semibold tabular-nums",
            hasTodo ? "bg-teal-50 text-teal-700" : "bg-zinc-100 text-zinc-400",
          )}
        >
          {count}
        </span>
      </div>
      <div className="mt-3 text-sm font-medium text-zinc-900">{label}</div>
      <div className="mt-0.5 truncate text-[11px] text-zinc-400" title={hint}>
        {hint}
      </div>
      <div
        className={cn(
          "mt-2 text-xs font-medium",
          hasTodo ? "text-teal-600" : "text-zinc-400",
        )}
      >
        {hasTodo ? "前往处理 →" : "无待办"}
      </div>
    </Link>
  );
}
