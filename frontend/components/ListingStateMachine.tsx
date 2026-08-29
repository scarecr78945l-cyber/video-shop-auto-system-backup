/**
 * M4 上架状态机 9 态可视化（v0.5 批次2）
 *
 * 对齐 backend/listing/state_machine.py ALLOWED_TRANSITIONS：
 * - 主链：pending→creating→draft→platform_auditing→listed（listed 为终态，R22 铁律唯一判据）；
 * - 分支：creating/draft→failed；platform_auditing→rejected→retry_candidate→creating（重提回主链）；
 * - rejected/retry_candidate→manual（人工处理终态）。
 * 枚举中文一律 LISTING_STATUS_LABELS（lib/enums.ts），组件不硬编码中文。
 * 每个状态 chip 显示当前页计数（counts[status] ?? 0），点击 chip 切换列表状态筛选。
 */
"use client";

import { ArrowRight } from "lucide-react";

import { LISTING_STATUS_LABELS } from "@/lib/enums";
import {
  LISTING_BRANCH_FLOW,
  LISTING_MAIN_FLOW,
  LISTING_TERMINAL_STATUSES,
} from "@/lib/listing";
import { cn } from "@/lib/cn";

type Props = {
  counts: Record<string, number>;
  activeStatus: string | null;
  onSelectStatus: (status: string | null) => void;
};

function FlowChip({
  status,
  count,
  active,
  onClick,
}: {
  status: string;
  count: number;
  active: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "inline-flex items-center gap-1.5 rounded-lg border px-2.5 py-1.5 text-xs transition",
        active
          ? "border-teal-500 bg-teal-50 text-teal-800 ring-1 ring-teal-300"
          : "border-zinc-200 bg-white text-zinc-700 hover:border-teal-300 hover:bg-teal-50/40",
      )}
    >
      <span className="font-medium">{LISTING_STATUS_LABELS[status] ?? status}</span>
      <span
        className={cn(
          "rounded-full px-1.5 py-0.5 text-[10px] leading-none",
          active ? "bg-teal-100 text-teal-700" : "bg-zinc-100 text-zinc-500",
        )}
      >
        {count}
      </span>
    </button>
  );
}

export function ListingStateMachine({ counts, activeStatus, onSelectStatus }: Props) {
  return (
    <div className="rounded-lg border border-zinc-200 bg-white p-4">
      <div className="flex items-center justify-between gap-3">
        <h2 className="text-sm font-semibold text-zinc-900">上架状态机（9 态）</h2>
        <button
          type="button"
          onClick={() => onSelectStatus(null)}
          className="text-xs text-zinc-400 underline-offset-2 transition hover:text-teal-700 hover:underline"
        >
          查看全部
        </button>
      </div>

      {/* 主链 */}
      <div className="mt-3 flex flex-wrap items-center gap-2">
        {LISTING_MAIN_FLOW.map((status, index) => (
          <span key={status} className="inline-flex items-center gap-2">
            {index > 0 && <ArrowRight size={14} className="text-zinc-300" />}
            <FlowChip
              status={status}
              count={counts[status] ?? 0}
              active={activeStatus === status}
              onClick={() => onSelectStatus(activeStatus === status ? null : status)}
            />
          </span>
        ))}
      </div>

      {/* 拒审/重提分支 */}
      <div className="mt-2 flex flex-wrap items-center gap-2">
        {LISTING_BRANCH_FLOW.map((step) => (
          <span key={step.from + step.to} className="inline-flex items-center gap-2">
            <FlowChip
              status={step.from}
              count={counts[step.from] ?? 0}
              active={activeStatus === step.from}
              onClick={() => onSelectStatus(activeStatus === step.from ? null : step.from)}
            />
            <ArrowRight size={14} className="text-zinc-300" />
            <FlowChip
              status={step.to}
              count={counts[step.to] ?? 0}
              active={activeStatus === step.to}
              onClick={() => onSelectStatus(activeStatus === step.to ? null : step.to)}
            />
            <span className="text-[11px] text-zinc-400">{step.note}</span>
          </span>
        ))}
      </div>

      {/* 终态（manual / failed） */}
      <div className="mt-2 flex flex-wrap items-center gap-2">
        <span className="text-[11px] text-zinc-400">终态：</span>
        {LISTING_TERMINAL_STATUSES.map((status, index) => (
          <span key={status} className="inline-flex items-center gap-2">
            {index > 0 && <ArrowRight size={14} className="text-zinc-300" />}
            <FlowChip
              status={status}
              count={counts[status] ?? 0}
              active={activeStatus === status}
              onClick={() => onSelectStatus(activeStatus === status ? null : status)}
            />
          </span>
        ))}
        <span className="text-[11px] text-zinc-400">
          （创建中/草稿失败 → failed；listed 需平台审核通过 + 链接验证，R22）
        </span>
      </div>
    </div>
  );
}
