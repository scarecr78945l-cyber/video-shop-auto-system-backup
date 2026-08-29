/**
 * 素材详情面板（v0.4 批次1）：GET /api/assets/{id} + /api/assets/uploads 抽屉内容。
 *
 * - 概览：类型/来源平台/作者/平台素材ID + 评估标签
 * - 完整规格：duration/resolution/size/tags/热度/合规/相关性/上传状态
 * - 双去重指纹：md5 / phash（长值截断，hover 全显）
 * - 二创义务标记 derivation_note
 * - 上传记录（upload_status 追踪，error_code 徽章）
 * - v0.6 批次3：相关性预审入口——relevance_status=manual_review 时显示
 *   「确认目标款」按钮（onConfirmRelevance 由父页注入，仅多款式待确认素材显示）。
 */
"use client";

import { Loader2, X } from "lucide-react";
import type { ReactNode } from "react";

import type { AssetSummary, AssetUploadRecord } from "@/lib/api";
import {
  ASSET_COMPLIANCE_LABELS,
  ASSET_TYPE_LABELS,
  EVALUATION_LABELS,
  RELEVANCE_STATUS_LABELS,
  UPLOAD_RECORD_STATUS_LABELS,
  UPLOAD_STATUS_LABELS,
} from "@/lib/enums";
import { formatBytes, formatDateTime, formatDuration } from "@/lib/format";
import { isManualReviewAsset } from "@/lib/review";
import { StatusBadge } from "@/components/StatusBadge";
import { cn } from "@/lib/cn";

type Props = {
  asset: AssetSummary | null;
  uploads: AssetUploadRecord[] | null;
  loading: boolean;
  uploadsLoading: boolean;
  error: string | null;
  onClose: () => void;
  /** v0.6 批次3：相关性预审「确认目标款」回调（仅 manual_review 素材显示）。 */
  onConfirmRelevance?: (asset: AssetSummary) => void;
  /** 确认请求进行中（按钮置灰）。 */
  confirming?: boolean;
};

/** 长字符串中段截断（指纹/路径展示用，hover 显示全文）。 */
function truncateMiddle(value: string | null | undefined, max = 40): string {
  if (!value) return "—";
  if (value.length <= max) return value;
  const keep = Math.floor((max - 3) / 2);
  return `${value.slice(0, keep)}…${value.slice(-keep)}`;
}

export function AssetDetailPanel({
  asset,
  uploads,
  loading,
  uploadsLoading,
  error,
  onClose,
  onConfirmRelevance,
  confirming = false,
}: Props) {
  const showConfirm = Boolean(asset && isManualReviewAsset(asset) && onConfirmRelevance);
  return (
    <div className="fixed inset-0 z-50 bg-black/30" onClick={onClose}>
      <div
        className="absolute inset-y-0 right-0 flex w-full max-w-2xl flex-col bg-white shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex h-14 shrink-0 items-center justify-between border-b border-zinc-200 px-5">
          <div className="text-sm font-semibold text-zinc-900">
            素材详情{asset ? ` #${asset.id}` : ""}
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

        {showConfirm && asset && (
          <div className="flex shrink-0 items-center justify-between gap-3 border-b border-amber-200 bg-amber-50 px-5 py-3">
            <div className="text-xs leading-5 text-amber-800">
              多款式素材待人工确认目标款（REC-迁移-03 C3）：确认后放行进入询价/上架链。
            </div>
            <button
              type="button"
              onClick={() => onConfirmRelevance?.(asset)}
              disabled={confirming}
              className="inline-flex shrink-0 items-center gap-1.5 rounded-lg bg-teal-600 px-3 py-1.5 text-xs font-medium text-white transition hover:bg-teal-700 disabled:opacity-50"
            >
              {confirming && <Loader2 size={13} className="animate-spin" />}
              确认目标款
            </button>
          </div>
        )}

        <div className="flex-1 overflow-y-auto p-5">
          {error && (
            <div className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-700">{error}</div>
          )}
          {loading && !asset && (
            <div className="grid h-48 place-items-center text-sm text-zinc-400">
              <span className="flex items-center gap-2">
                <Loader2 size={16} className="animate-spin" />
                加载中…
              </span>
            </div>
          )}
          {!error && asset && <DetailContent asset={asset} uploads={uploads} uploadsLoading={uploadsLoading} />}
        </div>
      </div>
    </div>
  );
}

function DetailContent({
  asset,
  uploads,
  uploadsLoading,
}: {
  asset: AssetSummary;
  uploads: AssetUploadRecord[] | null;
  uploadsLoading: boolean;
}) {
  const specRows: Array<[string, ReactNode]> = [
    ["类型", <StatusBadge key="type" labels={ASSET_TYPE_LABELS} value={asset.asset_type} />],
    ["来源平台", asset.source_platform || "—"],
    ["来源作者", asset.source_author || "—"],
    ["平台素材ID", asset.platform_material_id || "—"],
    ["时长", formatDuration(asset.duration ?? null)],
    ["分辨率", asset.resolution || "—"],
    ["大小", formatBytes(asset.size ?? null)],
    ["热度", typeof asset.heat_score === "number" ? asset.heat_score.toFixed(1) : "—"],
    ["相关性门", <StatusBadge key="rel" labels={RELEVANCE_STATUS_LABELS} value={asset.relevance_status} />],
    ["上传状态", <StatusBadge key="up" labels={UPLOAD_STATUS_LABELS} value={asset.upload_status} />],
    ["合规状态", <StatusBadge key="comp" labels={ASSET_COMPLIANCE_LABELS} value={asset.compliance_status ?? null} />],
    ["评估标签", <StatusBadge key="eval" labels={EVALUATION_LABELS} value={asset.evaluation ?? null} />],
    ["入库时间", formatDateTime(asset.created_at, true)],
    ["更新时间", formatDateTime(asset.updated_at, true)],
  ];

  const tags = asset.tags_json && typeof asset.tags_json === "object" ? asset.tags_json : null;

  return (
    <div className="space-y-5">
      {/* 概览 + 规格 */}
      <section className="rounded-lg border border-zinc-200 p-4">
        <h3 className="text-sm font-semibold text-zinc-900">
          素材 #{asset.id}
          <span className="ml-2 text-xs font-normal text-zinc-400">{asset.source_platform || ""}</span>
        </h3>
        <dl className="mt-3 grid grid-cols-2 gap-x-6 gap-y-2 text-xs sm:grid-cols-3">
          {specRows.map(([label, value]) => (
            <div key={label} className="flex flex-col gap-0.5">
              <dt className="text-zinc-400">{label}</dt>
              <dd className="text-zinc-800">{value}</dd>
            </div>
          ))}
        </dl>
        {tags && Object.keys(tags).length > 0 && (
          <div className="mt-3">
            <div className="text-xs text-zinc-400">标签</div>
            <div className="mt-1 flex flex-wrap gap-1">
              {Object.entries(tags).map(([k, v]) => (
                <span key={k} className="rounded bg-zinc-100 px-2 py-0.5 text-xs text-zinc-600">
                  {k}: {typeof v === "string" || typeof v === "number" ? String(v) : JSON.stringify(v)}
                </span>
              ))}
            </div>
          </div>
        )}
        {asset.source_url && (
          <div className="mt-3 truncate text-xs text-zinc-400" title={asset.source_url}>
            来源地址（脱敏）：{asset.source_url}
          </div>
        )}
      </section>

      {/* 双去重指纹 */}
      <section className="rounded-lg border border-zinc-200 p-4">
        <h4 className="mb-2 text-sm font-semibold text-zinc-900">双去重指纹</h4>
        <div className="space-y-1.5 text-xs">
          <div className="flex items-center gap-2">
            <span className="w-12 shrink-0 text-zinc-400">md5</span>
            <code className="truncate font-mono text-zinc-700" title={asset.md5}>
              {truncateMiddle(asset.md5, 48)}
            </code>
          </div>
          <div className="flex items-start gap-2">
            <span className="w-12 shrink-0 text-zinc-400">phash</span>
            <code className="min-w-0 break-all font-mono text-zinc-700" title={asset.phash}>
              {truncateMiddle(asset.phash, 96)}
            </code>
          </div>
          <div className="flex items-center gap-2">
            <span className="w-12 shrink-0 text-zinc-400">文件</span>
            <span className="truncate text-zinc-600" title={asset.file_path}>
              {truncateMiddle(asset.file_path, 64) || "—"}
            </span>
          </div>
        </div>
      </section>

      {/* 二创义务 */}
      <section className="rounded-lg border border-zinc-200 p-4">
        <h4 className="mb-2 text-sm font-semibold text-zinc-900">二创义务标记</h4>
        {asset.derivation_note ? (
          <p className="whitespace-pre-wrap text-xs leading-5 text-zinc-700">{asset.derivation_note}</p>
        ) : (
          <p className="text-xs text-zinc-400">无（非二创或未登记）</p>
        )}
      </section>

      {/* 上传记录 */}
      <section className="rounded-lg border border-zinc-200 p-4">
        <h4 className="mb-3 text-sm font-semibold text-zinc-900">
          上传记录（{uploads?.length ?? 0}）
        </h4>
        {uploadsLoading ? (
          <p className="text-xs text-zinc-400">加载中…</p>
        ) : uploads && uploads.length > 0 ? (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead className="text-zinc-400">
                <tr>
                  <th className="px-2 py-1.5 font-medium">#</th>
                  <th className="px-2 py-1.5 font-medium">尝试</th>
                  <th className="px-2 py-1.5 font-medium">状态</th>
                  <th className="px-2 py-1.5 font-medium">平台素材ID</th>
                  <th className="px-2 py-1.5 font-medium">错误码</th>
                  <th className="px-2 py-1.5 font-medium">更新时间</th>
                </tr>
              </thead>
              <tbody className="text-zinc-700">
                {uploads.map((u) => (
                  <tr key={u.id} className="border-t border-zinc-100">
                    <td className="px-2 py-2">{u.id}</td>
                    <td className="px-2 py-2">第 {u.attempt} 次</td>
                    <td className="px-2 py-2">
                      <StatusBadge
                        labels={UPLOAD_RECORD_STATUS_LABELS}
                        value={u.status}
                        tone={
                          u.status === "success"
                            ? "green"
                            : u.status === "failed" || u.status === "disabled"
                              ? "red"
                              : "amber"
                        }
                      />
                    </td>
                    <td className="px-2 py-2">{u.platform_material_id || "—"}</td>
                    <td className={cn("px-2 py-2", u.error_code ? "text-red-600" : "text-zinc-400")}>
                      {u.error_code || "—"}
                    </td>
                    <td className="whitespace-nowrap px-2 py-2">{formatDateTime(u.updated_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <p className="text-xs text-zinc-400">暂无上传记录</p>
        )}
      </section>
    </div>
  );
}
