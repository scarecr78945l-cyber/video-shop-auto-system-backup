/**
 * 轻量柱状图（v0.5 批次2）：纯 div 实现，不引入重型图表库。
 *
 * - SimpleBarChart：单序列垂直柱（如每日曝光）。
 * - GroupedBarChart：多序列分组柱（如每日 花费/成交/补贴）。
 * 缩放基准由调用方经 lib/ads.ts barMax 计算传入（纯函数，已单测）。
 */
"use client";

import type { ReactNode } from "react";

export type BarDatum = {
  label: string;
  value: number;
  title?: string;
};

type SimpleProps = {
  data: BarDatum[];
  max: number;
  height?: number;
  valueFormat?: (value: number) => string;
  colorClass?: string;
  emptyText?: ReactNode;
};

export function SimpleBarChart({
  data,
  max,
  height = 120,
  valueFormat = (v) => String(v),
  colorClass = "bg-teal-500",
  emptyText = "暂无数据",
}: SimpleProps) {
  if (!data.length) {
    return <div className="grid h-20 place-items-center text-xs text-zinc-400">{emptyText}</div>;
  }
  return (
    <div className="flex items-end gap-1" style={{ height }}>
      {data.map((d) => {
        const ratio = Math.min(1, Math.max(0, d.value) / max);
        return (
          <div key={d.label} className="group flex min-w-0 flex-1 flex-col items-center justify-end gap-1" title={d.title ?? `${d.label}: ${valueFormat(d.value)}`}>
            <span className="text-[10px] leading-none text-zinc-400 opacity-0 transition group-hover:opacity-100">
              {valueFormat(d.value)}
            </span>
            <div className={`w-full rounded-t ${colorClass} transition-opacity group-hover:opacity-80`} style={{ height: `${Math.max(ratio * 100, ratio > 0 ? 3 : 1)}%` }} />
            <span className="truncate text-[10px] leading-none text-zinc-500" title={d.label}>
              {d.label}
            </span>
          </div>
        );
      })}
    </div>
  );
}

export type GroupedBarDatum = {
  label: string;
  series: Array<{ key: string; value: number; colorClass: string; name: string }>;
};

type GroupedProps = {
  data: GroupedBarDatum[];
  max: number;
  height?: number;
  valueFormat?: (value: number) => string;
  emptyText?: ReactNode;
};

export function GroupedBarChart({
  data,
  max,
  height = 120,
  valueFormat = (v) => String(v),
  emptyText = "暂无数据",
}: GroupedProps) {
  if (!data.length) {
    return <div className="grid h-20 place-items-center text-xs text-zinc-400">{emptyText}</div>;
  }
  return (
    <div className="flex items-end gap-2" style={{ height }}>
      {data.map((d) => (
        <div key={d.label} className="flex min-w-0 flex-1 flex-col items-center justify-end gap-1">
          <div className="flex w-full items-end justify-center gap-0.5">
            {d.series.map((s) => {
              const ratio = Math.min(1, Math.max(0, s.value) / max);
              return (
                <div
                  key={s.key}
                  className={`min-w-1 flex-1 rounded-t ${s.colorClass} transition-opacity hover:opacity-80`}
                  style={{ height: `${Math.max(ratio * 100, ratio > 0 ? 3 : 1)}%` }}
                  title={`${d.label} · ${s.name}: ${valueFormat(s.value)}`}
                />
              );
            })}
          </div>
          <span className="truncate text-[10px] leading-none text-zinc-500" title={d.label}>
            {d.label}
          </span>
        </div>
      ))}
    </div>
  );
}
