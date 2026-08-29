/**
 * 托管素材绑定弹窗（v0.5 最小可用版 → v1.1 素材选择器升级）：
 * POST /api/ads/campaigns/{id}/materials
 *
 * v1.1：从「单行 material_ids 输入」升级为「素材列表选择器」——
 * - 复用 GET /api/assets（evaluation 评估标签 + relevance_status 相关性筛选 + page/page_size
 *   分页，buildAssetSelectorQuery）；
 * - 分页列表：素材 ID / material_id（platform_material_id）/ 类型 / 评估标签 / 上传状态 / 规格；
 * - 多选复选框 + 已选计数；确认后 POST materials（material_ids 为所选
 *   assetToMaterialId：优先 platform_material_id，缺失回落 String(id)，按后端端点接受字段定）；
 * - 「手动输入」兜底保留（parseMaterialIds 解析逗号/空白分隔）。
 * 成功展示后端 preferred_order（优选顺序：高效 > 潜力 > 探索期）与 note；
 * 失败展示后端 message（409 INVALID_STATE / 422 VALIDATION_ERROR 等）。
 */
"use client";

import { useEffect, useMemo, useState } from "react";
import { Layers, Loader2, ListPlus, Keyboard } from "lucide-react";

import {
  apiGet,
  type AdsCampaign,
  type AdsMaterialsResult,
  type AssetSummary,
  type Paginated,
} from "@/lib/api";
import { useAsyncData } from "@/lib/useAsyncData";
import { assetToMaterialId, buildAssetSelectorQuery, DEFAULT_ASSET_SELECTOR_FILTERS } from "@/lib/assets";
import { ASSET_TYPE_LABELS, EVALUATION_LABELS, RELEVANCE_STATUS_LABELS, UPLOAD_STATUS_LABELS } from "@/lib/enums";
import { formatBytes, formatDuration } from "@/lib/format";
import { parseMaterialIds } from "@/lib/ads";
import { Pagination } from "@/components/Pagination";
import { StatusBadge } from "@/components/StatusBadge";
import { cn } from "@/lib/cn";

const EVALUATION_OPTIONS = Object.entries(EVALUATION_LABELS);
const RELEVANCE_OPTIONS = Object.entries(RELEVANCE_STATUS_LABELS);
const PAGE_SIZE_OPTIONS = [10, 20, 50];

type Props = {
  open: boolean;
  campaign: AdsCampaign | null;
  busy: boolean;
  error: string | null;
  result: AdsMaterialsResult | null;
  /** 确认提交：material_ids（选择器所选或手动输入解析结果）。 */
  onSubmit: (materialIds: string[]) => void;
  onClose: () => void;
};

export function AdsMaterialsDialog({
  open,
  campaign,
  busy,
  error,
  result,
  onSubmit,
  onClose,
}: Props) {
  const [mode, setMode] = useState<"picker" | "manual">("picker");
  const [filters, setFilters] = useState(DEFAULT_ASSET_SELECTOR_FILTERS);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(10);
  const [selected, setSelected] = useState<string[]>([]);
  const [manualInput, setManualInput] = useState("");
  const [localError, setLocalError] = useState<string | null>(null);

  // 打开时重置选择器状态（组件常驻挂载，open 翻转时清空）
  useEffect(() => {
    if (open) {
      setMode("picker");
      setFilters(DEFAULT_ASSET_SELECTOR_FILTERS);
      setPage(1);
      setPageSize(10);
      setSelected([]);
      setManualInput("");
      setLocalError(null);
    }
  }, [open, campaign?.id]);

  const query = useMemo(() => buildAssetSelectorQuery(filters, page, pageSize), [filters, page, pageSize]);
  const assets = useAsyncData<Paginated<AssetSummary> | null>(
    () => (open ? apiGet<Paginated<AssetSummary>>(`/api/assets${query}`) : Promise.resolve(null)),
    [query, open],
  );

  if (!open) return null;

  const assetItems = assets.data?.items ?? [];

  function setFilter(key: keyof typeof filters, value: string) {
    setFilters((f) => ({ ...f, [key]: value }));
    setPage(1);
  }

  function toggleMaterial(materialId: string) {
    setSelected((prev) =>
      prev.includes(materialId) ? prev.filter((x) => x !== materialId) : [...prev, materialId],
    );
  }

  function handleConfirm() {
    if (busy) return;
    setLocalError(null);
    if (mode === "manual") {
      const ids = parseMaterialIds(manualInput);
      if (ids.length === 0) {
        setLocalError("请输入至少一个素材 ID（逗号/空白分隔）");
        return;
      }
      onSubmit(ids);
    } else {
      if (selected.length === 0) {
        setLocalError("请至少选择一个素材");
        return;
      }
      onSubmit(selected);
    }
  }

  return (
    <div className="fixed inset-0 z-[60] grid place-items-center bg-black/40 p-4" onClick={busy ? undefined : onClose}>
      <div
        className="w-full max-w-3xl rounded-xl bg-white p-5 shadow-2xl"
        onClick={(e) => e.stopPropagation()}
        role="dialog"
        aria-modal="true"
      >
        <h3 className="flex items-center gap-2 text-base font-semibold text-zinc-900">
          <Layers size={16} className="text-teal-600" />
          托管素材绑定{campaign ? ` #${campaign.id}` : ""}
        </h3>
        <p className="mt-2 text-xs leading-5 text-zinc-500">
          从素材库选择（评估标签/相关性筛选 + 分页多选），或切换手动输入；提交后后端按优选顺序
          高效(efficient) &gt; 潜力(potential) &gt; 探索期(exploring) 排序提示。
        </p>

        {/* 模式切换：素材选择器 / 手动输入（兜底） */}
        <div className="mt-3 flex w-fit items-center gap-1 rounded-lg bg-zinc-100 p-1">
          <button
            type="button"
            onClick={() => {
              setMode("picker");
              setLocalError(null);
            }}
            className={cn(
              "inline-flex items-center gap-1.5 rounded-md px-3 py-1.5 text-xs transition",
              mode === "picker" ? "bg-white font-medium text-teal-700 shadow-sm" : "text-zinc-500 hover:text-zinc-700",
            )}
          >
            <ListPlus size={13} />
            素材选择器
          </button>
          <button
            type="button"
            onClick={() => {
              setMode("manual");
              setLocalError(null);
            }}
            className={cn(
              "inline-flex items-center gap-1.5 rounded-md px-3 py-1.5 text-xs transition",
              mode === "manual" ? "bg-white font-medium text-teal-700 shadow-sm" : "text-zinc-500 hover:text-zinc-700",
            )}
          >
            <Keyboard size={13} />
            手动输入
          </button>
        </div>

        {mode === "picker" ? (
          <>
            {/* 筛选：评估标签 + 相关性 */}
            <div className="mt-3 flex flex-wrap items-center gap-3">
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
              <label className="flex items-center gap-2 text-xs text-zinc-500">
                相关性
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
              <span className="ml-auto text-xs text-zinc-400">
                {assets.loading ? "加载中…" : `共 ${assets.data?.total ?? 0} 个素材`}
              </span>
            </div>

            {/* 素材列表 */}
            <div className="mt-2 overflow-hidden rounded-lg border border-zinc-200">
              <div className="max-h-[300px] overflow-y-auto">
                {assets.error ? (
                  <div className="px-4 py-8 text-center text-xs text-red-600">
                    {assets.error}
                    <button type="button" onClick={assets.reload} className="ml-2 underline">
                      重试
                    </button>
                  </div>
                ) : !assets.loading && assetItems.length === 0 ? (
                  <div className="px-4 py-10 text-center text-xs text-zinc-400">暂无匹配素材</div>
                ) : (
                  <table className="w-full text-left text-xs">
                    <thead className="sticky top-0 bg-zinc-50 text-zinc-500">
                      <tr>
                        <th className="w-10 px-3 py-2">
                          <input
                            type="checkbox"
                            checked={assetItems.length > 0 && assetItems.every((a) => selected.includes(assetToMaterialId(a)))}
                            onChange={() => {
                              const all = assetItems.map((a) => assetToMaterialId(a));
                              const allSelected = all.every((id) => selected.includes(id));
                              setSelected((prev) =>
                                allSelected ? prev.filter((id) => !all.includes(id)) : [...new Set([...prev, ...all])],
                              );
                            }}
                            disabled={busy}
                            aria-label="全选本页素材"
                            className="size-3.5 accent-teal-600"
                          />
                        </th>
                        <th className="px-3 py-2 font-medium">素材 ID</th>
                        <th className="px-3 py-2 font-medium">material_id</th>
                        <th className="px-3 py-2 font-medium">类型</th>
                        <th className="px-3 py-2 font-medium">评估标签</th>
                        <th className="px-3 py-2 font-medium">上传状态</th>
                        <th className="px-3 py-2 font-medium">规格</th>
                      </tr>
                    </thead>
                    <tbody className="text-zinc-700">
                      {assetItems.map((a) => {
                        const materialId = assetToMaterialId(a);
                        const checked = selected.includes(materialId);
                        return (
                          <tr
                            key={a.id}
                            onClick={() => toggleMaterial(materialId)}
                            className={cn(
                              "cursor-pointer border-t border-zinc-100 transition hover:bg-teal-50/40",
                              checked && "bg-teal-50/50",
                              assets.loading && "opacity-60",
                            )}
                          >
                            <td className="px-3 py-2" onClick={(e) => e.stopPropagation()}>
                              <input
                                type="checkbox"
                                checked={checked}
                                onChange={() => toggleMaterial(materialId)}
                                disabled={busy}
                                aria-label={`选择素材 #${a.id}`}
                                className="size-3.5 accent-teal-600"
                              />
                            </td>
                            <td className="px-3 py-2 font-mono text-zinc-500">{a.id}</td>
                            <td className="px-3 py-2 font-mono text-zinc-600">{a.platform_material_id || "—"}</td>
                            <td className="px-3 py-2">
                              <StatusBadge
                                labels={ASSET_TYPE_LABELS}
                                value={a.asset_type}
                                tone={a.asset_type === "video" ? "blue" : "gray"}
                              />
                            </td>
                            <td className="px-3 py-2">
                              <StatusBadge labels={EVALUATION_LABELS} value={a.evaluation ?? null} />
                            </td>
                            <td className="px-3 py-2">
                              <StatusBadge labels={UPLOAD_STATUS_LABELS} value={a.upload_status} />
                            </td>
                            <td className="max-w-[180px] truncate px-3 py-2 text-zinc-500" title={assetSpec(a)}>
                              {assetSpec(a)}
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                )}
              </div>
              <Pagination
                page={page}
                pageSize={pageSize}
                total={assets.data?.total ?? 0}
                onPageChange={setPage}
                onPageSizeChange={(size) => {
                  setPageSize(size);
                  setPage(1);
                }}
                pageSizeOptions={PAGE_SIZE_OPTIONS}
              />
            </div>
          </>
        ) : (
          <label className="mt-3 block">
            <span className="text-xs text-zinc-500">素材 ID（material_ids，逗号/空白分隔）</span>
            <input
              value={manualInput}
              onChange={(e) => setManualInput(e.target.value)}
              placeholder="如 1001, 1002, 1003"
              disabled={busy}
              className="mt-1 w-full rounded border border-zinc-200 bg-white px-3 py-2 text-sm text-zinc-800 outline-none transition focus:border-teal-400 disabled:opacity-60"
            />
          </label>
        )}

        {(localError || error) && (
          <div className="mt-3 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-xs leading-5 text-red-700">
            {localError ?? error}
          </div>
        )}

        {result && (
          <div className="mt-3 rounded-lg border border-emerald-200 bg-emerald-50 px-3 py-2 text-xs leading-5 text-emerald-800">
            <div className="font-medium">绑定成功（{result.material_ids.length} 个）</div>
            <div className="mt-1">
              优选顺序：
              <span className="ml-1 inline-flex flex-wrap gap-1">
                {result.preferred_order.map((id) => (
                  <span key={id} className="rounded bg-white px-1.5 py-0.5 font-mono text-[11px] text-emerald-700 ring-1 ring-inset ring-emerald-200">
                    {id}
                  </span>
                ))}
              </span>
            </div>
            {result.note && <div className="mt-1 text-emerald-700">{result.note}</div>}
            <div className="mt-1 text-emerald-600">操作人：{result.operator}</div>
          </div>
        )}

        <div className="mt-5 flex items-center justify-between gap-2">
          <span className="text-xs text-zinc-500">
            {mode === "picker" && selected.length > 0 ? `已选 ${selected.length} 个素材` : ""}
          </span>
          <div className="flex justify-end gap-2">
            <button
              type="button"
              onClick={onClose}
              disabled={busy}
              className="rounded-lg border border-zinc-200 bg-white px-4 py-2 text-sm text-zinc-600 transition hover:bg-zinc-50 disabled:opacity-50"
            >
              {result ? "关闭" : "取消"}
            </button>
            {!result && (
              <button
                type="button"
                onClick={handleConfirm}
                disabled={busy}
                className="inline-flex items-center gap-1.5 rounded-lg bg-teal-600 px-4 py-2 text-sm font-medium text-white transition hover:bg-teal-700 disabled:opacity-60"
              >
                {busy && <Loader2 size={14} className="animate-spin" />}
                提交绑定
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

/** 素材规格摘要（视频：时长 · 分辨率 · 大小；图片：分辨率 · 大小）。 */
function assetSpec(asset: AssetSummary): string {
  const parts: string[] = [];
  if (asset.asset_type === "video" && asset.duration) parts.push(formatDuration(asset.duration));
  if (asset.resolution) parts.push(asset.resolution);
  parts.push(formatBytes(asset.size ?? null));
  return parts.join(" · ");
}
