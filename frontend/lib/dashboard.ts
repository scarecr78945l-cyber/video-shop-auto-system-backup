/**
 * 总览看板纯逻辑辅助（v0.4 批次1）
 *
 * 输入 = GET /api/overview 返回的计数 record（jobs_by_stage / jobs_by_status /
 * jobs_by_error_code / today_funnel）；输出 = 展示用有序条目。
 * 枚举中文一律经 lib/enums.ts 翻译（本文件只做聚合/排序，不做翻译定义）。
 * 全部为纯函数，配套单测 tests/dashboard.test.ts。
 */

import { JOB_STAGE_LABELS } from "./enums";

export type CountEntry = { key: string; count: number };
export type LabeledCountEntry = { key: string; label: string; count: number };

/** 计数 record 求和（null/undefined/非有限值按 0 处理）。 */
export function sumRecord(record: Record<string, number> | null | undefined): number {
  if (!record) return 0;
  return Object.values(record).reduce((sum, n) => sum + (Number.isFinite(n) ? n : 0), 0);
}

/** 计数 record → 按 count 降序条目（用于错误码分布等无序聚合；count>0 才输出）。 */
export function countEntries(record: Record<string, number> | null | undefined): CountEntry[] {
  return Object.entries(record ?? {})
    .filter(([, n]) => n > 0)
    .map(([key, count]) => ({ key, count }))
    .sort((a, b) => b.count - a.count);
}

/** 09 文档任务阶段顺序（workflow_jobs.stage 枚举，backend/foundation/tables.py STAGE_VALUES）。 */
const JOB_STAGE_ORDER: ReadonlyArray<string> = [
  "source_collect",
  "alibaba_quote",
  "taobao_reference",
  "image_generation",
  "listing_upload",
  "shop_ads_run",
  "shop_ads_report",
];

/**
 * 阶段计数（today_funnel / jobs_by_stage）→ 按阶段顺序输出，
 * label 经 enums.JOB_STAGE_LABELS 翻译；未知阶段按 count 降序排在末尾。
 */
export function funnelEntries(record: Record<string, number> | null | undefined): LabeledCountEntry[] {
  const counts = record ?? {};
  const known: LabeledCountEntry[] = [];
  for (const key of JOB_STAGE_ORDER) {
    const n = counts[key];
    if (typeof n === "number" && n > 0) {
      known.push({ key, label: JOB_STAGE_LABELS[key] ?? key, count: n });
    }
  }
  const unknown = countEntries(counts).filter((e) => !JOB_STAGE_ORDER.includes(e.key));
  return [...known, ...unknown.map((e) => ({ key: e.key, label: e.key, count: e.count }))];
}

/**
 * 异常任务数：blocked / failed / waiting_*（需人工介入或已失败，用于看板高亮口径）。
 */
export function abnormalJobCount(jobsByStatus: Record<string, number> | null | undefined): number {
  const record = jobsByStatus ?? {};
  let total = 0;
  for (const [key, n] of Object.entries(record)) {
    if ((key === "blocked" || key === "failed" || key.startsWith("waiting_")) && typeof n === "number") {
      total += n;
    }
  }
  return total;
}
