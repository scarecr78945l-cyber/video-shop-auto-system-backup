/**
 * 商品详情面板（v0.4 批次1）：GET /api/products/{id} 抽屉内容。
 *
 * - 概览：标题/类目/compliance 三态 + products.state + 得分 note
 * - 五维打分可解释列表（raw / weight / weighted / reasons，维度顺序 SCORE_DIM_ORDER）
 * - 询价明细 quotes（金额经 YuanText 元展示）
 * - 来源证据 source_evidence（脱敏字段直展）
 */
"use client";

import { Loader2, X } from "lucide-react";

import type { ProductDetail } from "@/lib/api";
import { COMPLIANCE_LABELS, PRODUCT_STATE_LABELS, SCORE_DIM_LABELS, SCORE_DIM_ORDER } from "@/lib/enums";
import { formatDateTime, formatPercent } from "@/lib/format";
import { StatusBadge } from "@/components/StatusBadge";
import { YuanText } from "@/components/YuanText";
import { cn } from "@/lib/cn";

type Props = {
  detail: ProductDetail | null;
  loading: boolean;
  error: string | null;
  onClose: () => void;
};

export function ProductDetailPanel({ detail, loading, error, onClose }: Props) {
  return (
    <div className="fixed inset-0 z-50 bg-black/30" onClick={onClose}>
      <div
        className="absolute inset-y-0 right-0 flex w-full max-w-2xl flex-col bg-white shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex h-14 shrink-0 items-center justify-between border-b border-zinc-200 px-5">
          <div className="text-sm font-semibold text-zinc-900">
            商品详情{detail ? ` #${detail.id}` : ""}
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
          {!error && detail && <DetailContent detail={detail} />}
        </div>
      </div>
    </div>
  );
}

function DetailContent({ detail }: { detail: ProductDetail }) {
  const complianceState =
    typeof detail.compliance?.state === "string" ? detail.compliance.state : detail.state;
  const reasons = Array.isArray(detail.compliance?.reasons) ? (detail.compliance.reasons as string[]) : [];
  const breakdown = detail.score_breakdown ?? { total: 0, dimensions: {} };

  return (
    <div className="space-y-5">
      {/* 概览 */}
      <section className="rounded-lg border border-zinc-200 p-4">
        <h3 className="text-base font-semibold leading-6 text-zinc-900">{detail.title || "（无标题）"}</h3>
        <div className="mt-2 flex flex-wrap items-center gap-2">
          <StatusBadge labels={COMPLIANCE_LABELS} value={complianceState} />
          <StatusBadge labels={PRODUCT_STATE_LABELS} value={detail.state} />
          <span className="rounded bg-zinc-100 px-2 py-0.5 text-xs text-zinc-600">
            {detail.category || "—"} · 得分 {breakdown.total.toFixed(1)}
          </span>
          {typeof breakdown.note === "string" && breakdown.note && (
            <span className="text-xs text-zinc-400">{breakdown.note}</span>
          )}
        </div>
        {reasons.length > 0 && (
          <ul className="mt-2 space-y-0.5">
            {reasons.map((r, i) => (
              <li key={i} className="text-xs text-zinc-500">
                · {r}
              </li>
            ))}
          </ul>
        )}
        <dl className="mt-3 grid grid-cols-2 gap-x-6 gap-y-1.5 text-xs sm:grid-cols-3">
          <div className="flex justify-between gap-2"><dt className="text-zinc-400">平台价</dt><dd className="text-zinc-800"><YuanText value={detail.platform_price} /></dd></div>
          <div className="flex justify-between gap-2"><dt className="text-zinc-400">实际成本</dt><dd className="text-zinc-800"><YuanText value={detail.real_cost} /></dd></div>
          <div className="flex justify-between gap-2"><dt className="text-zinc-400">建议售价</dt><dd className="text-zinc-800"><YuanText value={detail.suggested_price} /></dd></div>
          <div className="flex justify-between gap-2"><dt className="text-zinc-400">毛利率</dt><dd className="text-zinc-800">{formatPercent(detail.profit_margin)}</dd></div>
          <div className="flex justify-between gap-2"><dt className="text-zinc-400">销量</dt><dd className="text-zinc-800">{detail.sales ?? 0}</dd></div>
          <div className="flex justify-between gap-2"><dt className="text-zinc-400">最佳排名</dt><dd className="text-zinc-800">{detail.rank_best ?? 0}</dd></div>
          <div className="flex justify-between gap-2"><dt className="text-zinc-400">上榜榜单</dt><dd className="text-zinc-800">{detail.board_count ?? 0}</dd></div>
          <div className="flex justify-between gap-2"><dt className="text-zinc-400">供应商数</dt><dd className="text-zinc-800">{detail.supplier_count ?? 0}</dd></div>
          <div className="flex justify-between gap-2"><dt className="text-zinc-400">入库时间</dt><dd className="text-zinc-800">{formatDateTime(detail.created_at, true)}</dd></div>
        </dl>
      </section>

      {/* 五维打分 */}
      <section className="rounded-lg border border-zinc-200 p-4">
        <h4 className="mb-3 text-sm font-semibold text-zinc-900">五维打分（总分 {breakdown.total.toFixed(1)}）</h4>
        <div className="grid gap-2 sm:grid-cols-2">
          {SCORE_DIM_ORDER.map((key) => {
            const dim = breakdown.dimensions?.[key];
            if (!dim) return null;
            return (
              <div
                key={key}
                className={cn(
                  "rounded border p-3",
                  dim.active ? "border-zinc-200" : "border-zinc-100 bg-zinc-50 opacity-70",
                )}
              >
                <div className="flex items-baseline justify-between gap-2">
                  <span className="text-sm font-medium text-zinc-800">
                    {dim.label || SCORE_DIM_LABELS[key] || key}
                  </span>
                  <span className="text-sm font-semibold text-zinc-900">
                    {dim.weighted.toFixed(1)}
                    <span className="ml-1 text-xs font-normal text-zinc-400">
                      / 权重 {dim.weight.toFixed(4)}
                    </span>
                  </span>
                </div>
                <div className="mt-0.5 text-xs text-zinc-400">
                  raw {dim.raw.toFixed(1)}
                  {dim.active ? "" : " · 无数据，未参与"}
                </div>
                {dim.reasons.length > 0 && (
                  <ul className="mt-1.5 space-y-0.5">
                    {dim.reasons.map((r, i) => (
                      <li key={i} className="text-xs leading-5 text-zinc-600">
                        · {r}
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            );
          })}
        </div>
      </section>

      {/* 询价明细 */}
      <section className="rounded-lg border border-zinc-200 p-4">
        <h4 className="mb-3 text-sm font-semibold text-zinc-900">
          询价明细（{detail.quotes?.length ?? 0}）
        </h4>
        {detail.quotes?.length ? (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead className="text-zinc-400">
                <tr>
                  <th className="px-2 py-1.5 font-medium">供应商</th>
                  <th className="px-2 py-1.5 font-medium">SKU</th>
                  <th className="px-2 py-1.5 font-medium">单价</th>
                  <th className="px-2 py-1.5 font-medium">起订量</th>
                  <th className="px-2 py-1.5 font-medium">运费</th>
                  <th className="px-2 py-1.5 font-medium">询价时间</th>
                </tr>
              </thead>
              <tbody className="text-zinc-700">
                {detail.quotes.map((q) => (
                  <tr key={q.id} className="border-t border-zinc-100">
                    <td className="px-2 py-2">{q.supplier_name || "—"}</td>
                    <td className="max-w-[200px] truncate px-2 py-2" title={q.sku_name}>
                      {q.sku_name || "—"}
                    </td>
                    <td className="px-2 py-2"><YuanText value={q.unit_cost} /></td>
                    <td className="px-2 py-2">{q.min_order}</td>
                    <td className="px-2 py-2"><YuanText value={q.freight} /></td>
                    <td className="whitespace-nowrap px-2 py-2">{formatDateTime(q.quoted_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <p className="text-xs text-zinc-400">暂无询价记录</p>
        )}
      </section>

      {/* 来源证据 */}
      <section className="rounded-lg border border-zinc-200 p-4">
        <h4 className="mb-3 text-sm font-semibold text-zinc-900">
          来源证据（{detail.source_evidence?.length ?? 0}，已脱敏）
        </h4>
        {detail.source_evidence?.length ? (
          <ul className="space-y-2">
            {detail.source_evidence.map((e) => (
              <li key={e.id} className="rounded border border-zinc-100 bg-zinc-50/60 p-3 text-xs leading-5">
                <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-zinc-700">
                  <span className="font-medium text-zinc-900">{e.source || "—"}</span>
                  <span className="text-zinc-400">{e.board || "—"}</span>
                  <span>价格 <YuanText value={e.price} /></span>
                  <span>销量 {e.sales}</span>
                  <span>排名 {e.rank}</span>
                  <span className="text-zinc-400">{formatDateTime(e.collected_at)}</span>
                </div>
                <div className="mt-1 truncate text-zinc-500" title={e.title}>
                  {e.title || "（无标题）"}
                </div>
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-xs text-zinc-400">暂无来源证据</p>
        )}
      </section>
    </div>
  );
}
