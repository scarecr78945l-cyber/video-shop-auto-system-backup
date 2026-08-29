/**
 * 上架任务（M4）列表/状态机纯逻辑辅助（v0.5 批次2）
 *
 * GET /api/listing/tasks 使用 page/page_size 分页，筛选对齐 backend/api/routers/m4_listing.py
 * （status/product_id）。9 态迁移语义对齐 backend/listing/state_machine.py
 * ALLOWED_TRANSITIONS（pending→creating→draft→platform_auditing→listed 主链；
 * creating/draft→failed；platform_auditing→rejected→retry_candidate→creating 重提分支；
 * rejected/retry_candidate→manual；终态 listed/manual/failed）。
 * 枚举中文翻译一律走 lib/enums.ts（LISTING_STATUS_LABELS），本文件不含中文。
 * 全部为纯函数，配套单测 tests/listing.test.ts。
 */

import type { ListingOpLog, ListingTask } from "./api";

/** 9 态展示顺序（状态机条/筛选下拉用；与 enums.LISTING_STATUS_LABELS 键一致）。 */
export const LISTING_STATUSES_ORDERED: ReadonlyArray<string> = [
  "pending",
  "creating",
  "draft",
  "platform_auditing",
  "listed",
  "rejected",
  "retry_candidate",
  "manual",
  "failed",
];

/** 主链（箭头顺序）：pending→creating→draft→platform_auditing→listed。 */
export const LISTING_MAIN_FLOW: ReadonlyArray<string> = [
  "pending",
  "creating",
  "draft",
  "platform_auditing",
  "listed",
];

/** 拒审/重提分支（rejected→retry_candidate→creating 回主链；两者均可转 manual）。 */
export const LISTING_BRANCH_FLOW: ReadonlyArray<{ from: string; to: string; note: string }> = [
  { from: "rejected", to: "retry_candidate", note: "驳回 → 修复候选；或 → 人工处理" },
  { from: "retry_candidate", to: "creating", note: "二次门禁重提，回主链；或 → 人工处理" },
];

/** 其余终态（listed 已在主链末尾；manual/failed 无出边，state_machine.TERMINAL_STATUSES）。 */
export const LISTING_TERMINAL_STATUSES: ReadonlyArray<string> = ["manual", "failed"];

/** 各状态任务计数（状态机条用；未出现状态不占键，组件按 `counts[status] ?? 0` 展示）。 */
export function listingStatusCounts(items: ListingTask[]): Record<string, number> {
  const counts: Record<string, number> = {};
  for (const t of items) {
    counts[t.status] = (counts[t.status] ?? 0) + 1;
  }
  return counts;
}

/** 是否可人工确认入队：仅 pending（m4_listing.py POST /tasks/{id}/confirm 语义）。 */
export function canConfirmTask(status: string | null | undefined): boolean {
  return status === "pending";
}

/** 是否可拒审重提：仅 rejected / retry_candidate（D7 v1.0 简化语义，二次门禁由前端确认）。 */
export function canRetryTask(status: string | null | undefined): boolean {
  return status === "rejected" || status === "retry_candidate";
}

/** 构建 GET /api/listing/tasks 查询串（status 过滤 + page/page_size 分页）。 */
export function buildListingQuery(status: string, page: number, pageSize: number): string {
  const params = new URLSearchParams();
  if (status) params.set("status", status);
  params.set("page", String(Math.max(1, page)));
  params.set("page_size", String(pageSize));
  return `?${params.toString()}`;
}

/** 客户端关键词过滤：task_id / product_id / title 包含（大小写不敏感）。
 *  API 无关键词参数（REPORT 遗留项登记），本函数作用于已取回的分页条目。 */
export function filterTasksByKeyword(items: ListingTask[], keyword: string): ListingTask[] {
  const kw = keyword.trim().toLowerCase();
  if (!kw) return items;
  return items.filter((t) => {
    const taskId = (t.task_id ?? "").toLowerCase();
    const title = (t.title ?? "").toLowerCase();
    const productId = t.product_id != null ? String(t.product_id) : "";
    return taskId.includes(kw) || title.includes(kw) || productId.includes(kw);
  });
}

/** 从操作日志提取状态机轨迹（direction=transition 且 evidence{from,to}）。
 *  op-logs 接口按 log_id 升序返回（listing/repo.py list_op_logs），天然时间正序。 */
export function extractListingTrajectory(
  logs: ListingOpLog[],
): Array<{ from: string; to: string; at: string | null }> {
  const steps: Array<{ from: string; to: string; at: string | null }> = [];
  for (const log of logs) {
    if (log.direction !== "transition") continue;
    const ev = log.evidence;
    if (ev && typeof ev === "object" && !Array.isArray(ev)) {
      const record = ev as Record<string, unknown>;
      if (typeof record.from === "string" && typeof record.to === "string") {
        steps.push({ from: record.from, to: record.to, at: log.created_at });
      }
    }
  }
  return steps;
}
