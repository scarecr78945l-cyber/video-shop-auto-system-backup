/**
 * 托管看板（M5）· v0.5 批次2
 *
 * 取数：GET /api/ads/campaigns（**对齐后台列**：商品/目标出价/诊断/曝光/花费/成交/补贴/操作，
 *      status 过滤 + 分页）+ /api/ads/campaigns/{id}（详情：设置 + 报表快照序列）
 *      + /api/ads/account（账户状态卡：余额/节流/paused_until）
 *      + /api/ads/report?days=7|30（按日聚合报表：汇总卡 + 轻量柱状图 + 表格）。
 * 交互：暂停/恢复/结束（二次确认，`already`/409 处理，成功刷新）；素材绑定（最小可用版）。
 * 展示口径：金额 formatYuan（元零换算）、时间 formatDateTime（UTC→UTC+8）、
 *          枚举一律 lib/enums.ts（M5 三表 D5），组件不硬编码中文。
 */
"use client";

import { useMemo, useState } from "react";
import type { ReactNode } from "react";
import { RefreshCw } from "lucide-react";

import {
  ApiError,
  apiGet,
  apiPost,
  type AdsAccount,
  type AdsCampaign,
  type AdsCampaignDetail,
  type AdsMaterialsResult,
  type AdsReportResponse,
  type CampaignActionResult,
  type Paginated,
} from "@/lib/api";
import { useAsyncData } from "@/lib/useAsyncData";
import {
  barMax,
  buildAdsQuery,
  buildAdsReportQuery,
  canEndCampaign,
  canPauseCampaign,
  canResumeCampaign,
  campaignProductLabel,
  formatTargetBid,
  reportRowsAscending,
  sumReportMetrics,
} from "@/lib/ads";
import { ADS_ACCOUNT_STATUS_LABELS, M5_DIAGNOSIS_LABELS, M5_STATUS_LABELS } from "@/lib/enums";
import { formatDateTime } from "@/lib/format";
import { isMockMode } from "@/lib/env";
import { AdsCampaignDetailPanel } from "@/components/AdsCampaignDetailPanel";
import { AdsMaterialsDialog } from "@/components/AdsMaterialsDialog";
import { ConfirmDialog } from "@/components/ConfirmDialog";
import { GroupedBarChart, SimpleBarChart } from "@/components/ReportBars";
import { Pagination } from "@/components/Pagination";
import { StatusBadge } from "@/components/StatusBadge";
import { YuanText } from "@/components/YuanText";
import { cn } from "@/lib/cn";

const STATUS_OPTIONS = Object.entries(M5_STATUS_LABELS);

type ActionDialog = { kind: "pause" | "resume" | "end"; campaign: AdsCampaign } | null;

export default function AdsPage() {
  const [statusFilter, setStatusFilter] = useState("");
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [actionDialog, setActionDialog] = useState<ActionDialog>(null);
  const [materialTarget, setMaterialTarget] = useState<AdsCampaign | null>(null);
  const [materialResult, setMaterialResult] = useState<AdsMaterialsResult | null>(null);
  const [actionBusy, setActionBusy] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const [reportDays, setReportDays] = useState(7);

  const query = useMemo(
    () => buildAdsQuery(statusFilter, page, pageSize),
    [statusFilter, page, pageSize],
  );
  const campaigns = useAsyncData<Paginated<AdsCampaign>>(
    () => apiGet(`/api/ads/campaigns${query}`),
    [query],
  );
  const account = useAsyncData<AdsAccount>(() => apiGet("/api/ads/account"), []);
  const detail = useAsyncData<AdsCampaignDetail | null>(
    () => (selectedId === null ? Promise.resolve(null) : apiGet(`/api/ads/campaigns/${selectedId}`)),
    [selectedId],
  );
  const report = useAsyncData<AdsReportResponse | null>(
    () => apiGet(`/api/ads/report${buildAdsReportQuery(reportDays)}`),
    [reportDays],
  );

  const items = campaigns.data?.items ?? [];
  const reportRows = useMemo(() => reportRowsAscending(report.data?.items ?? []), [report.data]);
  const totals = useMemo(() => sumReportMetrics(reportRows), [reportRows]);
  const impressionMax = useMemo(() => barMax(reportRows.map((r) => r.impressions)), [reportRows]);
  const moneyMax = useMemo(
    () =>
      barMax(
        reportRows.flatMap((r) => [r.spend_yuan, r.gmv_yuan, r.subsidy_yuan]),
      ),
    [reportRows],
  );

  function changeStatusFilter(status: string) {
    setStatusFilter(status);
    setPage(1);
  }

  function handlePageSizeChange(size: number) {
    setPageSize(size);
    setPage(1);
  }

  function refreshAll() {
    campaigns.reload();
    account.reload();
    report.reload();
    if (selectedId !== null) detail.reload();
  }

  async function runCampaignAction() {
    if (!actionDialog || actionBusy) return;
    setActionBusy(true);
    setActionError(null);
    try {
      const { kind, campaign } = actionDialog;
      const res = await apiPost<CampaignActionResult>(`/api/ads/campaigns/${campaign.id}/${kind}`);
      void res; // already=true 视为成功（已是目标状态），409/404 由 ApiError 抛出展示 message
      setActionDialog(null);
      campaigns.reload();
      if (selectedId === campaign.id) detail.reload();
    } catch (err) {
      setActionError(err instanceof ApiError ? err.message : "操作失败，请稍后重试");
    } finally {
      setActionBusy(false);
    }
  }

  function openMaterials(campaign: AdsCampaign) {
    setMaterialTarget(campaign);
    setMaterialResult(null);
    setActionError(null);
  }

  async function submitMaterials(ids: string[]) {
    if (!materialTarget || actionBusy) return;
    if (ids.length === 0) {
      setActionError("请选择或输入至少一个素材 ID");
      return;
    }
    setActionBusy(true);
    setActionError(null);
    setMaterialResult(null);
    try {
      const res = await apiPost<AdsMaterialsResult>(
        `/api/ads/campaigns/${materialTarget.id}/materials`,
        { material_ids: ids },
      );
      setMaterialResult(res);
      campaigns.reload();
      if (selectedId === materialTarget.id) detail.reload();
    } catch (err) {
      setActionError(err instanceof ApiError ? err.message : "操作失败，请稍后重试");
    } finally {
      setActionBusy(false);
    }
  }

  const acct = account.data;

  return (
    <div>
      <div className="mb-6 flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold text-zinc-900">托管看板</h1>
          <p className="mt-1 text-sm text-zinc-500">
            M5 商品托管：目标出价 / 诊断 / 曝光 / 花费 / 成交 / 补贴（GET /api/ads/campaigns）
          </p>
        </div>
        <button
          type="button"
          onClick={refreshAll}
          className="inline-flex items-center gap-1.5 rounded border border-zinc-200 bg-white px-3 py-1.5 text-xs text-zinc-600 transition hover:bg-zinc-50"
        >
          <RefreshCw size={14} />
          刷新
        </button>
      </div>

      {isMockMode() && (
        <div className="mb-4 rounded-lg border border-amber-200 bg-amber-50 px-4 py-2 text-xs text-amber-700">
          NEXT_PUBLIC_USE_MOCK=1：演示模式保留位（当前版本未注入 mock 数据，直连真实 API）
        </div>
      )}

      {/* 账户状态卡 */}
      <div className="mb-4 rounded-lg border border-zinc-200 bg-white p-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h2 className="text-sm font-semibold text-zinc-900">投放账户</h2>
            <p className="mt-0.5 text-xs text-zinc-400">
              GET /api/ads/account{acct?.updated_at ? ` · 更新 ${formatDateTime(acct.updated_at, true)}` : ""}
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-x-5 gap-y-2">
            <div>
              <div className="text-xs text-zinc-400">余额</div>
              <div className={cn("text-lg font-semibold", acct && acct.balance_yuan !== null && acct.min_balance_yuan !== undefined && acct.balance_yuan < acct.min_balance_yuan ? "text-red-600" : "text-zinc-900")}>
                <YuanText value={acct?.balance_yuan} />
              </div>
            </div>
            {acct && acct.balance_yuan !== null && acct.min_balance_yuan !== undefined && acct.balance_yuan < acct.min_balance_yuan && (
              <div className="rounded bg-red-50 px-2.5 py-1.5 text-xs text-red-700 ring-1 ring-inset ring-red-200">
                低于最低余额阈值（<YuanText value={acct.min_balance_yuan} />），S5 余额告警
              </div>
            )}
            <div>
              <div className="text-xs text-zinc-400">状态</div>
              <div className="mt-0.5">
                <StatusBadge labels={ADS_ACCOUNT_STATUS_LABELS} value={acct?.status} />
              </div>
            </div>
            <div>
              <div className="text-xs text-zinc-400">节流级别</div>
              <div className="mt-0.5 text-sm font-medium text-zinc-800">
                {acct?.throttle_level ?? 0} / 5
              </div>
            </div>
            <div>
              <div className="text-xs text-zinc-400">暂停截止</div>
              <div className="mt-0.5 text-sm text-zinc-800">{formatDateTime(acct?.paused_until)}</div>
            </div>
            {acct?.pause_reason && (
              <div className="max-w-[260px] text-xs text-zinc-500">
                暂停原因：<span className="text-zinc-700">{acct.pause_reason}</span>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* 筛选栏 */}
      <div className="mb-4 rounded-lg border border-zinc-200 bg-white p-4">
        <label className="flex items-center gap-2 text-xs text-zinc-500">
          状态
          <select
            value={statusFilter}
            onChange={(e) => changeStatusFilter(e.target.value)}
            className="rounded border border-zinc-200 bg-white px-2 py-1.5 text-xs text-zinc-700 outline-none"
          >
            <option value="">全部</option>
            {STATUS_OPTIONS.map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
        </label>
      </div>

      {campaigns.error && (
        <div className="mb-4 rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-700">
          {campaigns.error}
          <button type="button" onClick={campaigns.reload} className="ml-3 underline">
            重试
          </button>
        </div>
      )}

      {/* 托管列表（对齐后台列） */}
      <div className="overflow-hidden rounded-lg border border-zinc-200 bg-white">
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead className="bg-zinc-50 text-xs text-zinc-500">
              <tr>
                <th className="px-4 py-2.5 font-medium">商品</th>
                <th className="px-4 py-2.5 font-medium">目标出价</th>
                <th className="px-4 py-2.5 font-medium">诊断</th>
                <th className="px-4 py-2.5 font-medium">曝光</th>
                <th className="px-4 py-2.5 font-medium">花费</th>
                <th className="px-4 py-2.5 font-medium">成交</th>
                <th className="px-4 py-2.5 font-medium">补贴</th>
                <th className="px-4 py-2.5 font-medium">状态</th>
                <th className="px-4 py-2.5 font-medium">操作</th>
              </tr>
            </thead>
            <tbody>
              {!campaigns.loading && items.length === 0 && (
                <tr>
                  <td colSpan={9} className="px-4 py-12 text-center text-xs text-zinc-400">
                    暂无托管计划
                  </td>
                </tr>
              )}
              {items.map((campaign) => {
                const snap = campaign.latest_snapshot;
                return (
                  <tr
                    key={campaign.id}
                    onClick={() => setSelectedId(campaign.id)}
                    className={cn(
                      "cursor-pointer border-t border-zinc-100 transition hover:bg-teal-50/40",
                      campaigns.loading && "opacity-60",
                    )}
                  >
                    <td className="px-4 py-3">
                      <span className="font-medium text-zinc-800">
                        {campaignProductLabel(campaign)}
                      </span>
                      <span className="ml-1.5 text-xs text-zinc-400">计划 {campaign.id}</span>
                    </td>
                    <td className="whitespace-nowrap px-4 py-3 text-xs text-zinc-700">
                      {formatTargetBid(campaign.target_type, campaign.target_roi)}
                    </td>
                    <td className="px-4 py-3">
                      <StatusBadge labels={M5_DIAGNOSIS_LABELS} value={campaign.diagnosis} />
                    </td>
                    <td className="px-4 py-3 text-xs text-zinc-700">
                      {snap ? snap.impressions.toLocaleString("zh-CN") : "—"}
                    </td>
                    <td className="px-4 py-3 text-xs text-zinc-700">
                      <YuanText value={snap?.spend_yuan} />
                    </td>
                    <td className="px-4 py-3 text-xs text-zinc-700">
                      <YuanText value={snap?.gmv_yuan} />
                    </td>
                    <td className="px-4 py-3 text-xs text-zinc-700">
                      <YuanText value={snap?.subsidy_yuan} />
                    </td>
                    <td className="px-4 py-3">
                      <StatusBadge labels={M5_STATUS_LABELS} value={campaign.status} />
                    </td>
                    <td className="whitespace-nowrap px-4 py-3" onClick={(e) => e.stopPropagation()}>
                      <div className="flex items-center gap-1.5">
                        <button
                          type="button"
                          onClick={() => setSelectedId(campaign.id)}
                          className="rounded border border-zinc-200 px-2 py-1 text-xs text-zinc-600 transition hover:bg-zinc-50"
                        >
                          详情
                        </button>
                        {canPauseCampaign(campaign.status) && (
                          <button
                            type="button"
                            onClick={() => {
                              setActionError(null);
                              setActionDialog({ kind: "pause", campaign });
                            }}
                            className="rounded border border-amber-300 bg-amber-50 px-2 py-1 text-xs font-medium text-amber-800 transition hover:bg-amber-100"
                          >
                            暂停
                          </button>
                        )}
                        {canResumeCampaign(campaign.status) && (
                          <button
                            type="button"
                            onClick={() => {
                              setActionError(null);
                              setActionDialog({ kind: "resume", campaign });
                            }}
                            className="rounded border border-emerald-300 bg-emerald-50 px-2 py-1 text-xs font-medium text-emerald-800 transition hover:bg-emerald-100"
                          >
                            恢复
                          </button>
                        )}
                        {canEndCampaign(campaign.status) && (
                          <button
                            type="button"
                            onClick={() => {
                              setActionError(null);
                              setActionDialog({ kind: "end", campaign });
                            }}
                            className="rounded border border-red-200 bg-red-50 px-2 py-1 text-xs font-medium text-red-700 transition hover:bg-red-100"
                          >
                            结束
                          </button>
                        )}
                        <button
                          type="button"
                          onClick={() => openMaterials(campaign)}
                          className="rounded border border-zinc-200 px-2 py-1 text-xs text-zinc-600 transition hover:bg-zinc-50"
                        >
                          素材
                        </button>
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
        <Pagination
          page={page}
          pageSize={pageSize}
          total={campaigns.data?.total ?? 0}
          onPageChange={setPage}
          onPageSizeChange={handlePageSizeChange}
        />
      </div>

      {/* 报表（GET /api/ads/report） */}
      <section className="mt-6 overflow-hidden rounded-lg border border-zinc-200 bg-white">
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-zinc-200 px-4 py-3">
          <div>
            <h2 className="text-sm font-semibold text-zinc-900">投放报表（按日聚合）</h2>
            <p className="mt-0.5 text-xs text-zinc-400">
              GET /api/ads/report{report.data ? ` · ${report.data.total} 天有数据` : ""}
            </p>
          </div>
          <div className="flex items-center gap-1 rounded-lg bg-zinc-100 p-1">
            {[7, 30].map((days) => (
              <button
                key={days}
                type="button"
                onClick={() => setReportDays(days)}
                className={cn(
                  "rounded-md px-3 py-1 text-xs transition",
                  reportDays === days ? "bg-white font-medium text-teal-700 shadow-sm" : "text-zinc-500 hover:text-zinc-700",
                )}
              >
                近 {days} 天
              </button>
            ))}
          </div>
        </div>

        {report.error && (
          <div className="px-4 py-3 text-xs text-red-700">
            {report.error}
            <button type="button" onClick={report.reload} className="ml-2 underline">
              重试
            </button>
          </div>
        )}

        {report.loading && !report.data && (
          <div className="grid h-40 place-items-center text-xs text-zinc-400">加载中…</div>
        )}

        {report.data && report.data.items.length === 0 && (
          <div className="grid h-40 place-items-center text-xs text-zinc-400">近 {reportDays} 天暂无报表数据</div>
        )}

        {report.data && report.data.items.length > 0 && (
          <div className="p-4">
            {/* 汇总卡 */}
            <div className="mb-4 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
              <SummaryCard label="总曝光" value={totals.impressions.toLocaleString("zh-CN")} note="次" />
              <SummaryCard label="总花费" value={<YuanText value={totals.spend_yuan} />} note="元" />
              <SummaryCard label="总成交" value={<YuanText value={totals.gmv_yuan} />} note="元" />
              <SummaryCard label="总补贴" value={<YuanText value={totals.subsidy_yuan} />} note="元" />
            </div>

            {/* 曝光柱状图 */}
            <div className="rounded-lg border border-zinc-100 p-3">
              <div className="mb-2 flex items-center justify-between">
                <span className="text-xs font-medium text-zinc-700">每日曝光</span>
                <span className="text-[11px] text-zinc-400">hover 查看数值</span>
              </div>
              <SimpleBarChart
                data={reportRows.map((r) => ({
                  label: r.date.slice(5),
                  value: r.impressions,
                  title: `${r.date} · 曝光 ${r.impressions.toLocaleString("zh-CN")}`,
                }))}
                max={impressionMax}
                height={120}
                valueFormat={(v) => v.toLocaleString("zh-CN")}
              />
            </div>

            {/* 金额分组柱状图 */}
            <div className="mt-3 rounded-lg border border-zinc-100 p-3">
              <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
                <span className="text-xs font-medium text-zinc-700">每日 花费 / 成交 / 补贴</span>
                <span className="flex items-center gap-3 text-[11px] text-zinc-500">
                  <LegendDot className="bg-sky-500" label="花费" />
                  <LegendDot className="bg-emerald-500" label="成交" />
                  <LegendDot className="bg-amber-500" label="补贴" />
                </span>
              </div>
              <GroupedBarChart
                data={reportRows.map((r) => ({
                  label: r.date.slice(5),
                  series: [
                    { key: "spend", value: r.spend_yuan, colorClass: "bg-sky-500", name: "花费" },
                    { key: "gmv", value: r.gmv_yuan, colorClass: "bg-emerald-500", name: "成交" },
                    { key: "subsidy", value: r.subsidy_yuan, colorClass: "bg-amber-500", name: "补贴" },
                  ],
                }))}
                max={moneyMax}
                height={120}
                valueFormat={(v) => `¥${v.toFixed(2)}`}
              />
            </div>

            {/* 报表表格 */}
            <div className="mt-3 overflow-x-auto">
              <table className="w-full text-left text-xs">
                <thead className="text-zinc-400">
                  <tr>
                    <th className="px-2 py-1.5 font-medium">日期</th>
                    <th className="px-2 py-1.5 font-medium">曝光</th>
                    <th className="px-2 py-1.5 font-medium">花费</th>
                    <th className="px-2 py-1.5 font-medium">成交</th>
                    <th className="px-2 py-1.5 font-medium">补贴</th>
                    <th className="px-2 py-1.5 font-medium">覆盖计划数</th>
                  </tr>
                </thead>
                <tbody className="text-zinc-700">
                  {reportRows.map((r) => (
                    <tr key={r.date} className="border-t border-zinc-100">
                      <td className="whitespace-nowrap px-2 py-2">{r.date}</td>
                      <td className="px-2 py-2">{r.impressions.toLocaleString("zh-CN")}</td>
                      <td className="px-2 py-2"><YuanText value={r.spend_yuan} /></td>
                      <td className="px-2 py-2"><YuanText value={r.gmv_yuan} /></td>
                      <td className="px-2 py-2"><YuanText value={r.subsidy_yuan} /></td>
                      <td className="px-2 py-2">{r.campaign_count}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </section>

      {/* 详情抽屉 */}
      {selectedId !== null && (
        <AdsCampaignDetailPanel
          detail={detail.data}
          loading={detail.loading}
          error={detail.error}
          onClose={() => setSelectedId(null)}
        />
      )}

      {/* 暂停/恢复/结束 二次确认 */}
      <ConfirmDialog
        open={actionDialog !== null}
        title={
          actionDialog?.kind === "pause"
            ? "暂停托管"
            : actionDialog?.kind === "resume"
              ? "恢复托管"
              : "结束托管"
        }
        tone={actionDialog?.kind === "end" ? "danger" : "primary"}
        message={
          actionDialog && (
            <>
              {actionDialog.kind === "pause" && "暂停后该计划停止投放，可随时恢复。操作人由后端记录。"}
              {actionDialog.kind === "resume" && "恢复后该计划重新进入托管投放。操作人由后端记录。"}
              {actionDialog.kind === "end" && (
                <>
                  结束后该计划<b>不可恢复</b>（后端对已结束计划恢复返回 409）。操作人由后端记录。
                </>
              )}
              <span className="mt-1 block text-xs text-zinc-400">
                计划 #{actionDialog.campaign.id} · 商品 #{actionDialog.campaign.product_id} ·
                当前状态：{M5_STATUS_LABELS[actionDialog.campaign.status] ?? actionDialog.campaign.status}
              </span>
            </>
          )
        }
        confirmText={actionDialog?.kind === "pause" ? "确认暂停" : actionDialog?.kind === "resume" ? "确认恢复" : "确认结束"}
        busy={actionBusy}
        error={actionError}
        onConfirm={runCampaignAction}
        onCancel={() => {
          if (!actionBusy) {
            setActionDialog(null);
            setActionError(null);
          }
        }}
      />

      {/* 素材绑定弹窗（v1.1：素材选择器 + 手动输入兜底） */}
      <AdsMaterialsDialog
        open={materialTarget !== null}
        campaign={materialTarget}
        busy={actionBusy}
        error={actionError}
        result={materialResult}
        onSubmit={submitMaterials}
        onClose={() => {
          if (!actionBusy) {
            setMaterialTarget(null);
            setMaterialResult(null);
            setActionError(null);
          }
        }}
      />
    </div>
  );
}

function SummaryCard({ label, value, note }: { label: string; value: ReactNode; note: string }) {
  return (
    <div className="rounded-lg border border-zinc-200 p-3">
      <div className="text-xs text-zinc-400">{label}</div>
      <div className="mt-1 text-lg font-semibold text-zinc-900">{value}</div>
      <div className="text-[11px] text-zinc-400">单位：{note}</div>
    </div>
  );
}

function LegendDot({ className, label }: { className: string; label: string }) {
  return (
    <span className="inline-flex items-center gap-1">
      <span className={cn("size-2 rounded-sm", className)} />
      {label}
    </span>
  );
}
