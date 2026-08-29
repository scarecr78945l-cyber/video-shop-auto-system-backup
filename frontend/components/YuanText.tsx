/**
 * 金额展示组件：统一走 formatYuan（元 → `¥12.90`）。
 * 铁律：本组件与 lib/format.ts 均不做事分→元换算（API 层已完成，DA-001）。
 */
import { formatYuan } from "@/lib/format";

type Props = {
  value: number | null | undefined;
  className?: string;
  /** 空值占位（默认 `—`，D2/D3 可空字段口径） */
  emptyText?: string;
};

export function YuanText({ value, className, emptyText }: Props) {
  const text =
    value === null || value === undefined || Number.isNaN(value)
      ? emptyText ?? "—"
      : formatYuan(value);
  return <span className={className}>{text}</span>;
}
