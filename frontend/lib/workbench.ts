/**
 * 人工闸门工作台 + 异常中心 · 纯逻辑辅助（v0.7）
 *
 * 对齐 backend/api/routers/workbench.py 实测契约：
 * - GET  /api/workbench/gates       → {total, counts{sourcing_review, listing_confirm,
 *                                     image_review, material_pre_review,
 *                                     verification_takeover, login_takeover}, generated_at}
 * - GET  /api/workbench/exceptions  → {total, items[]}（blocked/waiting_*，error_code/
 *                                     error_message / retry_after / lease 字段 / evidence 脱敏）
 * - POST /api/workbench/retry/{id}  → {ok, id, status, stage, error_code, operator}
 * - POST /api/sourcing/gate-confirm → {ok, product_id, title, state, operator}（409 INVALID_STATE）
 *
 * 全部为纯函数，配套单测 tests/workbench.test.ts。展示口径：枚举中文一律走
 * lib/enums.ts（errorCodeLabel / JOB_STATUS_LABELS / JOB_STAGE_LABELS），本文件不重复建表。
 */

import type { WorkbenchException, WorkbenchGates } from "./api";
import { errorCodeLabel, JOB_STATUS_LABELS } from "./enums";

// ================================================================ 闸门卡片（定义 + 计数）

export type GateKey = keyof WorkbenchGates["counts"];

/** 闸门卡片定义：展示顺序即数组顺序；label/hint 集中在 lib 层（组件不硬编码中文）。 */
export type GateDef = {
  key: GateKey;
  label: string;
  /** 统计口径说明（来源字段/状态）。 */
  hint: string;
  /** 跳转目标：目标页运行时会读取 query 参数做初始筛选（products/review/listing/exceptions）。 */
  href: string;
};

export const GATE_DEFS: ReadonlyArray<GateDef> = [
  {
    key: "sourcing_review",
    label: "选品复核",
    hint: "products.state = manual_review",
    href: "/products?state=manual_review",
  },
  {
    key: "listing_confirm",
    label: "上架确认",
    hint: "listing_tasks.status = pending",
    href: "/listing?status=pending",
  },
  {
    key: "image_review",
    label: "图片审核",
    hint: "opt_images.review_status = pending",
    href: "/review?tab=image",
  },
  {
    key: "material_pre_review",
    label: "素材预审",
    hint: "asset_items.relevance_status = manual_review",
    href: "/review?tab=material",
  },
  {
    key: "verification_takeover",
    label: "验证码接管",
    hint: "workflow_jobs.status = waiting_verification",
    href: "/exceptions?status=waiting_verification",
  },
  {
    key: "login_takeover",
    label: "登录接管",
    hint: "workflow_jobs.status = waiting_login",
    href: "/exceptions?status=waiting_login",
  },
];

/** 安全读取单个闸门计数（API 缺 key / 未加载 → 0）。 */
export function gateCount(
  gates: WorkbenchGates | null | undefined,
  key: GateKey,
): number {
  const raw = gates?.counts?.[key];
  return typeof raw === "number" && Number.isFinite(raw) ? raw : 0;
}

/** 六类闸门待办合计（等价 API total；缺数据 → 0）。 */
export function totalGateCount(gates: WorkbenchGates | null | undefined): number {
  if (!gates?.counts) return 0;
  return GATE_DEFS.reduce((sum, def) => sum + gateCount(gates, def.key), 0);
}

// ================================================================ 异常中心分组统计

/** 按 error_code 分组后的一个桶（中文标签；error_code 为空时按 status 标签兜底）。 */
export type ExceptionGroup = {
  errorCode: string | null;
  label: string;
  count: number;
};

/**
 * 异常清单按 error_code 分组计数（降序）：
 * - error_code 存在 → errorCodeLabel 中文（VERIFICATION_REQUIRED→验证码/安全验证 …）；
 * - error_code 为空 → 按 status 标签兜底（blocked→阻塞 等），再兜底「未分类」。
 */
export function exceptionGroups(
  items: WorkbenchException[],
): { total: number; groups: ExceptionGroup[] } {
  const map = new Map<string, ExceptionGroup>();
  for (const item of items ?? []) {
    const errorCode = item.error_code ?? null;
    const status = item.status ?? "";
    const key = errorCode ?? `__status__${status}`;
    const existing = map.get(key);
    if (existing) {
      existing.count += 1;
    } else {
      const label = errorCode
        ? errorCodeLabel(errorCode)
        : (JOB_STATUS_LABELS[status] ?? "未分类");
      map.set(key, { errorCode, label, count: 1 });
    }
  }
  const groups = [...map.values()].sort((a, b) => b.count - a.count);
  return { total: items?.length ?? 0, groups };
}

// ================================================================ 人工接管重试

/**
 * 二次确认文案（按任务类型区分，任务书口径）：
 * - waiting_verification → 「确认验证码已通过，恢复执行」
 * - waiting_login        → 「确认已重新登录，从断点续跑」
 * - blocked              → 「确认问题已解决，重试」
 * - 未知 status 时按 error_code 兜底（VERIFICATION_REQUIRED / AUTH_REQUIRED），再兜底通用文案。
 */
export function retryConfirmText(
  status: string | null | undefined,
  errorCode: string | null | undefined,
): string {
  if (status === "waiting_verification") return "确认验证码已通过，恢复执行";
  if (status === "waiting_login") return "确认已重新登录，从断点续跑";
  if (status === "blocked") return "确认问题已解决，重试";
  if (errorCode === "VERIFICATION_REQUIRED") return "确认验证码已通过，恢复执行";
  if (errorCode === "AUTH_REQUIRED") return "确认已重新登录，从断点续跑";
  return "确认已处理，恢复执行";
}

// ================================================================ evidence 摘要（脱敏截断）

/**
 * evidence 摘要：JSON 序列化 + 截断（后端已递归脱敏，前端只做展示摘要）。
 * 空对象/空数组/缺失 → `—`。
 */
export function evidenceSummary(
  evidence: Record<string, unknown> | null | undefined,
  maxLen = 80,
): string {
  if (!evidence) return "—";
  let text: string;
  try {
    text = JSON.stringify(evidence);
  } catch {
    return "—";
  }
  if (!text || text === "{}" || text === "[]") return "—";
  return text.length > maxLen ? `${text.slice(0, maxLen)}…` : text;
}

/**
 * compliance.reasons 摘要：字符串数组合并 + 截断（选品复核列表展示用）。
 * 非数组/空/全空串 → `—`。
 */
export function complianceReasonsSummary(reasons: unknown, maxLen = 60): string {
  if (!Array.isArray(reasons)) return "—";
  const text = reasons
    .filter((r): r is string => typeof r === "string" && r.trim().length > 0)
    .join("；");
  if (!text) return "—";
  return text.length > maxLen ? `${text.slice(0, maxLen)}…` : text;
}

// ================================================================ 查询串构建

/**
 * 选品复核列表查询：GET /api/products?state=manual_review（limit/offset 分页，
 * 对齐 m1_sourcing.py list_products；limit 上限 500）。
 */
export function buildReviewProductsQuery(page: number, pageSize: number): string {
  const p = Math.max(1, Math.floor(page) || 1);
  const size = Math.min(Math.max(1, Math.floor(pageSize) || 20), 500);
  return `?state=manual_review&limit=${size}&offset=${(p - 1) * size}`;
}

/**
 * 异常清单查询：GET /api/workbench/exceptions（status 可选 + limit 上限 500）。
 */
export function buildExceptionsQuery(status: string, limit = 100): string {
  const size = Math.min(Math.max(1, Math.floor(limit) || 100), 500);
  const params = new URLSearchParams();
  if (status) params.set("status", status);
  params.set("limit", String(size));
  return params.toString() ? `?${params.toString()}` : "";
}
