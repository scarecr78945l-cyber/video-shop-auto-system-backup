/**
 * 托管看板（M5）纯逻辑辅助（v0.5 批次2）
 *
 * GET /api/ads/campaigns 使用 page/page_size 分页（status 过滤）；
 * GET /api/ads/report 按 days 聚合（返回日期**降序**，展示前经 reportRowsAscending 升序）。
 * 枚举翻译一律走 lib/enums.ts（M5_STATUS_LABELS / M5_DIAGNOSIS_LABELS /
 * M5_TARGET_TYPE_LABELS，D5 英文原值），本文件不含中文。
 * 金额一律为 API 已换算的元 float（DA-001），本文件不做分→元换算。
 * 全部为纯函数，配套单测 tests/ads.test.ts。
 */

import { enumLabel, M5_TARGET_TYPE_LABELS } from "./enums";
import type { AdsReportRow } from "./api";

/** 操作可用性（对齐 m5_ads.py _campaign_action 语义；后端仍会以 409/`already` 兜底）。 */
export function canPauseCampaign(status: string | null | undefined): boolean {
  return status === "active";
}

export function canResumeCampaign(status: string | null | undefined): boolean {
  return status === "paused";
}

export function canEndCampaign(status: string | null | undefined): boolean {
  return !!status && status !== "ended";
}

/** 构建 GET /api/ads/campaigns 查询串（status 过滤 + page/page_size 分页）。 */
export function buildAdsQuery(status: string, page: number, pageSize: number): string {
  const params = new URLSearchParams();
  if (status) params.set("status", status);
  params.set("page", String(Math.max(1, page)));
  params.set("page_size", String(pageSize));
  return `?${params.toString()}`;
}

/** 构建 GET /api/ads/report 查询串（days 夹取 1..90；非法值回落 7，避免后端 422）。 */
export function buildAdsReportQuery(days: number): string {
  const value = Number.isFinite(days) ? Math.trunc(days) : 7;
  const clamped = Math.min(90, Math.max(1, value));
  return `?days=${clamped}`;
}

/** 目标出价展示：`成交ROI 2.40`（target_type 中文 + target_roi 两位；roi 空 → —）。 */
export function formatTargetBid(
  targetType: string | null | undefined,
  targetRoi: number | null | undefined,
): string {
  if (targetRoi === null || targetRoi === undefined || Number.isNaN(targetRoi)) return "—";
  return `${enumLabel(M5_TARGET_TYPE_LABELS, targetType)} ${targetRoi.toFixed(2)}`;
}

/** 报表汇总（统计卡：总曝光/总花费/总成交/总补贴；金额元求和）。 */
export function sumReportMetrics(
  rows: AdsReportRow[],
): { impressions: number; spend_yuan: number; gmv_yuan: number; subsidy_yuan: number } {
  let impressions = 0;
  let spend = 0;
  let gmv = 0;
  let subsidy = 0;
  for (const r of rows) {
    impressions += r.impressions || 0;
    spend += r.spend_yuan || 0;
    gmv += r.gmv_yuan || 0;
    subsidy += r.subsidy_yuan || 0;
  }
  return { impressions, spend_yuan: spend, gmv_yuan: gmv, subsidy_yuan: subsidy };
}

/** 柱状图缩放基准：最大值（≥1，避免除零；非有限值忽略）。 */
export function barMax(values: ReadonlyArray<number>): number {
  let max = 0;
  for (const v of values) {
    if (Number.isFinite(v) && v > max) max = v;
  }
  return Math.max(1, max);
}

/** 报表按日期升序（API 返回降序，展示按时间先后）。 */
export function reportRowsAscending(rows: AdsReportRow[]): AdsReportRow[] {
  return [...rows].sort((a, b) => (a.date < b.date ? -1 : a.date > b.date ? 1 : 0));
}

/** 素材输入解析：逗号/中文逗号/空白分隔，去空去重（POST /api/ads/campaigns/{id}/materials body）。 */
export function parseMaterialIds(input: string): string[] {
  return [
    ...new Set(
      input
        .split(/[,，\s]+/)
        .map((s) => s.trim())
        .filter(Boolean),
    ),
  ];
}
