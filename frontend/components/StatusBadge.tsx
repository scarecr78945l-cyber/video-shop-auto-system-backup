/**
 * 枚举中文徽章：value 经 lib/enums.ts 映射表翻译展示（组件不硬编码中文）。
 * tone 缺省时按 value 关键词启发式着色（英文枚举值分类，非中文硬编码）。
 */
import { enumLabel } from "@/lib/enums";
import { cn } from "@/lib/cn";

export type BadgeTone = "gray" | "green" | "amber" | "red" | "blue";

const TONE_CLASS: Record<BadgeTone, string> = {
  gray: "bg-zinc-100 text-zinc-700 ring-zinc-200",
  green: "bg-emerald-50 text-emerald-700 ring-emerald-200",
  amber: "bg-amber-50 text-amber-700 ring-amber-200",
  red: "bg-red-50 text-red-700 ring-red-200",
  blue: "bg-sky-50 text-sky-700 ring-sky-200",
};

const POSITIVE = new Set(["listed", "active", "passed", "approved", "uploaded", "efficient", "excellent", "good", "pool", "candidate"]);
const NEGATIVE = new Set(["rejected", "failed", "hard_reject", "disabled", "not_eligible", "ended", "blocked", "unexpected"]);
const WARNING = new Set(["pending", "manual_review", "draft", "platform_auditing", "creating", "retry_candidate", "manual", "optimize_1", "optimize_n", "waiting_verification", "waiting_login", "risk_control"]);

export function toneForValue(value: string | null | undefined): BadgeTone {
  const v = value ?? "";
  if (POSITIVE.has(v)) return "green";
  if (NEGATIVE.has(v)) return "red";
  if (WARNING.has(v)) return "amber";
  if (v.startsWith("waiting_") || v.startsWith("pending")) return "amber";
  return "gray";
}

type Props = {
  /** 枚举映射表（lib/enums.ts 导出的 *_LABELS） */
  labels: Record<string, string>;
  value: string | null | undefined;
  tone?: BadgeTone;
  className?: string;
};

export function StatusBadge({ labels, value, tone, className }: Props) {
  return (
    <span
      className={cn(
        "inline-flex items-center rounded px-2 py-0.5 text-xs font-medium ring-1 ring-inset",
        TONE_CLASS[tone ?? toneForValue(value)],
        className,
      )}
    >
      {enumLabel(labels, value)}
    </span>
  );
}
