/**
 * 素材相关性预审（v0.6 批次3）：M2 素材相关性人工确认（REC-迁移-03 C3）。
 *
 * - 待确认视图：GET /api/assets?relevance_status=manual_review（多款式 → 人工确认目标款）；
 * - 确认操作：POST /api/assets/{id}/relevance-confirm {decision:"pass"} → passed 放行
 *   （仅 passed 可进入询价/上架链；failed 淘汰、manual_review 待确认——后端
 *   RelevanceGateService 语义，frontend 不绕过）；
 * - 二次确认弹窗说明「确认该素材为目标款，放行进入询价/上架链；多款式禁止自动创建衍生商品」；
 * - 已放行视图（可选）：relevance_status=passed 筛选查看；
 * - 展示：规格（formatDuration/resolution/formatBytes）、来源、file_path、
 *   二创义务 derivation_note、评估标签（lib 层集中格式化，组件零硬编码口径）。
 */
"use client";

import { Loader2 } from "lucide-react";
import { useMemo, useState } from "react";

import { apiGet, apiPost, type AssetSummary, type Paginated, type RelevanceConfirmResult } from "@/lib/api";
import { useAsyncData } from "@/lib/useAsyncData";
import { buildPassedAssetQuery, buildPreReviewAssetQuery, relevanceConfirmLabel } from "@/lib/review";
import { ASSET_TYPE_LABELS, EVALUATION_LABELS, RELEVANCE_STATUS_LABELS } from "@/lib/enums";
import { formatBytes, formatDateTime, formatDuration } from "@/lib/format";
import { ConfirmDialog } from "@/components/ConfirmDialog";
import { Pagination } from "@/components/Pagination";
import { StatusBadge } from "@/components/StatusBadge";
import { cn } from "@/lib/cn";

type Mode = "manual_review" | "passed";

export function MaterialPreReview() {
  const [mode, setMode] = useState<Mode>("manual_review");
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);
  const [confirmAsset, setConfirmAsset] = useState<AssetSummary | null>(null);
  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);

  const query = useMemo(
    () =>
      mode === "manual_review"
        ? buildPreReviewAssetQuery(page, pageSize)
        : buildPassedAssetQuery(page, pageSize),
    [mode, page, pageSize],
  );
  const list = useAsyncData<Paginated<AssetSummary>>(() => apiGet(`/api/assets${query}`), [query]);

  const items = list.data?.items ?? [];

  function switchMode(next: Mode) {
    setMode(next);
    setPage(1);
  }

  function handlePageSizeChange(size: number) {
    setPageSize(size);
    setPage(1);
  }

  async function confirmPass() {
    if (!confirmAsset) return;
    setBusy(true);
    setActionError(null);
    try {
      const result = await apiPost<RelevanceConfirmResult>(
        `/api/assets/${confirmAsset.id}/relevance-confirm`,
        { decision: "pass" },
      );
      if (result?.relevance_status === "passed") {
        setConfirmAsset(null);
        list.reload();
      } else {
        setActionError(`确认后状态异常：${result?.relevance_status ?? "未知"}`);
      }
    } catch (err) {
      setActionError(err instanceof Error ? err.message : "确认失败，请稍后重试");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div>
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <div className="flex gap-1">
          {(
            [
              ["manual_review", "待确认目标款"],
              ["passed", "已放行"],
            ] as const
          ).map(([value, label]) => (
            <button
              key={value}
              type="button"
              onClick={() => switchMode(value)}
              className={cn(
                "h-10 rounded-lg border px-4 text-sm transition",
                mode === value
                  ? "border-teal-600 bg-teal-50 font-medium text-teal-700"
                  : "border-zinc-200 bg-white text-zinc-500 hover:bg-zinc-50",
              )}
            >
              {label}
            </button>
          ))}
        </div>
        <div className="text-xs text-zinc-500">
          多款式素材必须人工确认目标款后放行（REC-迁移-03 C3：禁止自动创建衍生商品）
        </div>
      </div>

      {list.error && (
        <div className="mb-4 rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-700">
          {list.error}
          <button type="button" onClick={list.reload} className="ml-3 underline">
            重试
          </button>
        </div>
      )}
      {actionError && (
        <div className="mb-4 rounded-lg border border-red-200 bg-red-50 px-4 py-2 text-xs text-red-700">{actionError}</div>
      )}

      <div className="overflow-hidden rounded-lg border border-zinc-200 bg-white">
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead className="bg-zinc-50 text-xs text-zinc-500">
              <tr>
                <th className="px-4 py-2.5 font-medium">ID</th>
                <th className="px-4 py-2.5 font-medium">类型</th>
                <th className="px-4 py-2.5 font-medium">来源</th>
                <th className="px-4 py-2.5 font-medium">规格</th>
                <th className="px-4 py-2.5 font-medium">评估标签</th>
                <th className="px-4 py-2.5 font-medium">二创义务</th>
                <th className="px-4 py-2.5 font-medium">入库时间</th>
                <th className="px-4 py-2.5 font-medium">操作</th>
              </tr>
            </thead>
            <tbody>
              {!list.loading && items.length === 0 && (
                <tr>
                  <td colSpan={8} className="px-4 py-12 text-center text-xs text-zinc-400">
                    {mode === "manual_review" ? "暂无待确认目标款的素材" : "暂无已放行素材"}
                  </td>
                </tr>
              )}
              {items.map((a) => (
                <tr key={a.id} className={cn("border-t border-zinc-100", list.loading && "opacity-60")}>
                  <td className="px-4 py-3 font-mono text-xs text-zinc-500">{a.id}</td>
                  <td className="px-4 py-3">
                    <StatusBadge
                      labels={ASSET_TYPE_LABELS}
                      value={a.asset_type}
                      tone={a.asset_type === "video" ? "blue" : "gray"}
                    />
                  </td>
                  <td className="max-w-40 px-4 py-3 text-xs text-zinc-600">
                    <div className="truncate" title={a.source_platform}>
                      {a.source_platform || "—"}
                    </div>
                    <div className="truncate text-[11px] text-zinc-400" title={a.file_path}>
                      {a.file_path || "—"}
                    </div>
                  </td>
                  <td className="px-4 py-3 text-xs text-zinc-600">
                    {a.asset_type === "video" ? `${formatDuration(a.duration ?? null)} · ` : ""}
                    {a.resolution || "—"} · {formatBytes(a.size ?? null)}
                  </td>
                  <td className="px-4 py-3">
                    <StatusBadge labels={EVALUATION_LABELS} value={a.evaluation ?? null} />
                  </td>
                  <td className="max-w-48 px-4 py-3">
                    <span
                      className="block truncate text-xs text-zinc-600"
                      title={a.derivation_note || undefined}
                    >
                      {a.derivation_note || "—"}
                    </span>
                  </td>
                  <td className="whitespace-nowrap px-4 py-3 text-xs text-zinc-500">
                    {formatDateTime(a.created_at)}
                  </td>
                  <td className="px-4 py-3">
                    {mode === "manual_review" ? (
                      <button
                        type="button"
                        onClick={() => setConfirmAsset(a)}
                        disabled={busy}
                        className="rounded-lg border border-teal-200 bg-white px-3 py-1.5 text-xs font-medium text-teal-700 transition hover:bg-teal-50 disabled:opacity-50"
                      >
                        确认目标款
                      </button>
                    ) : (
                      <StatusBadge labels={RELEVANCE_STATUS_LABELS} value={a.relevance_status} />
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <Pagination
          page={page}
          pageSize={pageSize}
          total={list.data?.total ?? 0}
          onPageChange={setPage}
          onPageSizeChange={handlePageSizeChange}
        />
      </div>

      <ConfirmDialog
        open={confirmAsset !== null}
        title="确认目标款（放行）"
        message={
          <>
            确认素材 <span className="font-mono font-medium">#{confirmAsset?.id}</span>
            （{relevanceConfirmLabel("pass")}）为目标款，放行进入询价/上架链？
            <span className="mt-1 block text-amber-700">
              多款式素材必须人工确认目标款，禁止自动创建衍生商品（REC-迁移-03 C3）。
            </span>
          </>
        }
        confirmText="确认放行"
        busy={busy}
        onConfirm={() => void confirmPass()}
        onCancel={() => setConfirmAsset(null)}
      />
      {busy && (
        <div className="pointer-events-none fixed inset-0 z-[70] grid place-items-center">
          <span className="flex items-center gap-2 rounded-lg bg-white px-4 py-2 text-xs text-zinc-600 shadow">
            <Loader2 size={14} className="animate-spin" />
            正在确认…
          </span>
        </div>
      )}
    </div>
  );
}
