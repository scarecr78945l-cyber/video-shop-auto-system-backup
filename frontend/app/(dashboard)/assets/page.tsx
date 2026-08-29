/**
 * 素材库（M2）· v0.4 批次1 + v0.6 批次3（相关性预审入口）
 *
 * 取数：GET /api/assets（asset_type/source_platform/relevance_status/upload_status/
 *      evaluation + page/page_size 分页）
 *      + GET /api/assets/{id}（行点击 → 详情抽屉：完整规格/双去重指纹/二创义务）
 *      + GET /api/assets/uploads?asset_id=（详情内上传记录，可选）。
 * 交互：五维筛选 / 分页 / 每页条数 / 详情抽屉。
 * v0.6 批次3：详情抽屉对 relevance_status=manual_review 素材提供「确认目标款」
 *      （POST /api/assets/{id}/relevance-confirm {decision:"pass"} → passed 放行，
 *      二次确认，REC-迁移-03 C3：多款式必须人工确认目标款，禁止自动创建衍生商品）。
 * 展示口径：金额 formatYuan、时间 formatDateTime（UTC→UTC+8）、规格 formatDuration/
 *          formatBytes、枚举一律 lib/enums.ts 徽章（本页无硬编码中文）。
 */
"use client";

import { useMemo, useState } from "react";

import {
  apiGet,
  apiPost,
  type AssetSummary,
  type AssetUploadRecord,
  type Paginated,
  type RelevanceConfirmResult,
} from "@/lib/api";
import { useAsyncData } from "@/lib/useAsyncData";
import {
  buildAssetQuery,
  DEFAULT_ASSET_FILTERS,
  distinctSourcePlatforms,
  type AssetFilters,
} from "@/lib/assets";
import {
  ASSET_TYPE_LABELS,
  EVALUATION_LABELS,
  RELEVANCE_STATUS_LABELS,
  UPLOAD_STATUS_LABELS,
} from "@/lib/enums";
import { formatBytes, formatDateTime, formatDuration } from "@/lib/format";
import { isMockMode } from "@/lib/env";
import { AssetDetailPanel } from "@/components/AssetDetailPanel";
import { ConfirmDialog } from "@/components/ConfirmDialog";
import { Pagination } from "@/components/Pagination";
import { StatusBadge } from "@/components/StatusBadge";
import { cn } from "@/lib/cn";

const ASSET_TYPE_OPTIONS = Object.entries(ASSET_TYPE_LABELS);
const RELEVANCE_OPTIONS = Object.entries(RELEVANCE_STATUS_LABELS);
const UPLOAD_OPTIONS = Object.entries(UPLOAD_STATUS_LABELS);
const EVALUATION_OPTIONS = Object.entries(EVALUATION_LABELS);

export default function AssetsPage() {
  const [filters, setFilters] = useState<AssetFilters>(DEFAULT_ASSET_FILTERS);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [confirmAsset, setConfirmAsset] = useState<AssetSummary | null>(null);
  const [confirming, setConfirming] = useState(false);
  const [confirmError, setConfirmError] = useState<string | null>(null);

  const query = useMemo(() => buildAssetQuery(filters, page, pageSize), [filters, page, pageSize]);
  const list = useAsyncData<Paginated<AssetSummary>>(() => apiGet(`/api/assets${query}`), [query]);
  const detail = useAsyncData<AssetSummary | null>(
    () => (selectedId === null ? Promise.resolve(null) : apiGet(`/api/assets/${selectedId}`)),
    [selectedId],
  );
  const uploads = useAsyncData<Paginated<AssetUploadRecord> | null>(
    () =>
      selectedId === null
        ? Promise.resolve(null)
        : apiGet(`/api/assets/uploads?asset_id=${selectedId}&page_size=20`),
    [selectedId],
  );

  const items = list.data?.items ?? [];
  const platforms = useMemo(() => distinctSourcePlatforms(items), [items]);

  function setFilter<K extends keyof AssetFilters>(key: K, value: AssetFilters[K]) {
    setFilters((f) => ({ ...f, [key]: value }));
    setPage(1);
  }

  function handlePageSizeChange(size: number) {
    setPageSize(size);
    setPage(1);
  }

  async function handleConfirmPass() {
    if (!confirmAsset) return;
    setConfirming(true);
    setConfirmError(null);
    try {
      const result = await apiPost<RelevanceConfirmResult>(
        `/api/assets/${confirmAsset.id}/relevance-confirm`,
        { decision: "pass" },
      );
      if (result?.relevance_status === "passed") {
        setConfirmAsset(null);
        detail.reload();
        list.reload();
      } else {
        setConfirmError(`确认后状态异常：${result?.relevance_status ?? "未知"}`);
      }
    } catch (err) {
      setConfirmError(err instanceof Error ? err.message : "确认失败，请稍后重试");
    } finally {
      setConfirming(false);
    }
  }

  return (
    <div>
      <div className="mb-6">
        <h1 className="text-xl font-semibold text-zinc-900">素材库</h1>
        <p className="mt-1 text-sm text-zinc-500">
          M2 素材库：类型 / 来源平台 / 相关性门 / 上传状态 / 评估标签筛选（GET /api/assets）
        </p>
      </div>

      {isMockMode() && (
        <div className="mb-4 rounded-lg border border-amber-200 bg-amber-50 px-4 py-2 text-xs text-amber-700">
          NEXT_PUBLIC_USE_MOCK=1：演示模式保留位（当前版本未注入 mock 数据，直连真实 API）
        </div>
      )}

      {/* 筛选栏 */}
      <div className="mb-4 rounded-lg border border-zinc-200 bg-white p-4">
        <div className="flex flex-wrap items-center gap-3">
          <label className="flex items-center gap-2 text-xs text-zinc-500">
            类型
            <select
              value={filters.assetType}
              onChange={(e) => setFilter("assetType", e.target.value)}
              className="rounded border border-zinc-200 bg-white px-2 py-1.5 text-xs text-zinc-700 outline-none"
            >
              <option value="">全部</option>
              {ASSET_TYPE_OPTIONS.map(([value, label]) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </select>
          </label>
          <label className="flex items-center gap-2 text-xs text-zinc-500">
            来源平台
            <select
              value={filters.sourcePlatform}
              onChange={(e) => setFilter("sourcePlatform", e.target.value)}
              className="rounded border border-zinc-200 bg-white px-2 py-1.5 text-xs text-zinc-700 outline-none"
            >
              <option value="">全部</option>
              {platforms.map((p) => (
                <option key={p} value={p}>
                  {p}
                </option>
              ))}
            </select>
          </label>
          <label className="flex items-center gap-2 text-xs text-zinc-500">
            相关性门
            <select
              value={filters.relevanceStatus}
              onChange={(e) => setFilter("relevanceStatus", e.target.value)}
              className="rounded border border-zinc-200 bg-white px-2 py-1.5 text-xs text-zinc-700 outline-none"
            >
              <option value="">全部</option>
              {RELEVANCE_OPTIONS.map(([value, label]) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </select>
          </label>
          <label className="flex items-center gap-2 text-xs text-zinc-500">
            上传状态
            <select
              value={filters.uploadStatus}
              onChange={(e) => setFilter("uploadStatus", e.target.value)}
              className="rounded border border-zinc-200 bg-white px-2 py-1.5 text-xs text-zinc-700 outline-none"
            >
              <option value="">全部</option>
              {UPLOAD_OPTIONS.map(([value, label]) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </select>
          </label>
          <label className="flex items-center gap-2 text-xs text-zinc-500">
            评估标签
            <select
              value={filters.evaluation}
              onChange={(e) => setFilter("evaluation", e.target.value)}
              className="rounded border border-zinc-200 bg-white px-2 py-1.5 text-xs text-zinc-700 outline-none"
            >
              <option value="">全部</option>
              {EVALUATION_OPTIONS.map(([value, label]) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </select>
          </label>
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

      {/* 列表 */}
      <div className="overflow-hidden rounded-lg border border-zinc-200 bg-white">
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead className="bg-zinc-50 text-xs text-zinc-500">
              <tr>
                <th className="px-4 py-2.5 font-medium">ID</th>
                <th className="px-4 py-2.5 font-medium">类型</th>
                <th className="px-4 py-2.5 font-medium">来源平台</th>
                <th className="px-4 py-2.5 font-medium">规格</th>
                <th className="px-4 py-2.5 font-medium">相关性门</th>
                <th className="px-4 py-2.5 font-medium">上传状态</th>
                <th className="px-4 py-2.5 font-medium">评估标签</th>
                <th className="px-4 py-2.5 font-medium">热度</th>
                <th className="px-4 py-2.5 font-medium">入库时间</th>
              </tr>
            </thead>
            <tbody>
              {!list.loading && items.length === 0 && (
                <tr>
                  <td colSpan={9} className="px-4 py-12 text-center text-xs text-zinc-400">
                    暂无素材
                  </td>
                </tr>
              )}
              {items.map((a) => (
                <tr
                  key={a.id}
                  onClick={() => setSelectedId(a.id)}
                  className={cn(
                    "cursor-pointer border-t border-zinc-100 transition hover:bg-teal-50/40",
                    list.loading && "opacity-60",
                  )}
                >
                  <td className="px-4 py-3 font-mono text-xs text-zinc-500">{a.id}</td>
                  <td className="px-4 py-3">
                    <StatusBadge
                      labels={ASSET_TYPE_LABELS}
                      value={a.asset_type}
                      tone={a.asset_type === "video" ? "blue" : "gray"}
                    />
                  </td>
                  <td className="px-4 py-3 text-xs text-zinc-600">{a.source_platform || "—"}</td>
                  <td className="px-4 py-3 text-xs text-zinc-600">
                    {a.asset_type === "video" ? `${formatDuration(a.duration ?? null)} · ` : ""}
                    {a.resolution || "—"} · {formatBytes(a.size ?? null)}
                  </td>
                  <td className="px-4 py-3">
                    <StatusBadge labels={RELEVANCE_STATUS_LABELS} value={a.relevance_status} />
                  </td>
                  <td className="px-4 py-3">
                    <StatusBadge labels={UPLOAD_STATUS_LABELS} value={a.upload_status} />
                  </td>
                  <td className="px-4 py-3">
                    <StatusBadge labels={EVALUATION_LABELS} value={a.evaluation ?? null} />
                  </td>
                  <td className="px-4 py-3 text-xs text-zinc-600">
                    {typeof a.heat_score === "number" ? a.heat_score.toFixed(1) : "—"}
                  </td>
                  <td className="whitespace-nowrap px-4 py-3 text-xs text-zinc-500">
                    {formatDateTime(a.created_at)}
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

      {/* 详情抽屉 */}
      {selectedId !== null && (
        <AssetDetailPanel
          asset={detail.data}
          uploads={uploads.data?.items ?? null}
          loading={detail.loading}
          uploadsLoading={uploads.loading}
          error={detail.error}
          onClose={() => setSelectedId(null)}
          onConfirmRelevance={(asset) => {
            setConfirmError(null);
            setConfirmAsset(asset);
          }}
          confirming={confirming}
        />
      )}

      {/* 相关性预审：确认目标款（放行） */}
      <ConfirmDialog
        open={confirmAsset !== null}
        title="确认目标款（放行）"
        message={
          <>
            确认素材 <span className="font-mono font-medium">#{confirmAsset?.id}</span> 为目标款，
            放行进入询价/上架链？
            <span className="mt-1 block text-amber-700">
              多款式素材必须人工确认目标款，禁止自动创建衍生商品（REC-迁移-03 C3）。
            </span>
          </>
        }
        confirmText="确认放行"
        busy={confirming}
        error={confirmError}
        onConfirm={() => void handleConfirmPass()}
        onCancel={() => {
          setConfirmAsset(null);
          setConfirmError(null);
        }}
      />
    </div>
  );
}
