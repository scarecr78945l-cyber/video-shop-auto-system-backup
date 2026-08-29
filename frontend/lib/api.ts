/**
 * API 客户端（重写版）—— 前端唯一取数通道（backend/api/ FastAPI）
 *
 * 契约要点（context/README.md 一、1.8 D1~D10 + backend/api/REPORT.md）：
 * - 金额：API 对外一律「元（float）」（DA-001），前端零换算（格式见 lib/format.ts）；
 * - 时间：ISO8601 UTC（`...Z`），字段 `*_at`；展示经 lib/format.ts 转 UTC+8；
 * - 错误：统一 `{code, message, detail?}`（DA-008 7 码 + D10 局部 VALIDATION_ERROR/INVALID_STATE）；
 * - 鉴权：httpOnly 会话 cookie（浏览器自动携带），前端不存 token；
 *   401 全局拦截 → 跳 /login（可经 setUnauthorizedHandler 覆盖，供测试/路由守卫）；
 * - 除 POST /api/auth/login 与 /api/health 外全部端点需登录。
 *
 * NEXT_PUBLIC_API_BASE：仅 API 地址（默认 http://127.0.0.1:8000；兼容带 /api 后缀写法）。
 */

const rawBase = process.env.NEXT_PUBLIC_API_BASE || "http://127.0.0.1:8000";

/** 归一化 API 根地址（去尾斜杠；兼容「…/api」写法 → 去掉后缀，路径统一以 /api/… 开头）。 */
export const API_BASE = rawBase.replace(/\/+$/, "").replace(/\/api$/, "");

export function getApiBase(): string {
  return API_BASE;
}

// ================================================================ 错误模型

/** API 统一错误体：{code, message, detail?} */
export type ApiErrorBody = {
  code?: string;
  message?: string;
  detail?: unknown;
};

/** API 业务/协议错误：code + message + status + detail（堆栈不进 UI，仅日志）。 */
export class ApiError extends Error {
  readonly code: string;
  readonly status: number;
  readonly detail?: unknown;

  constructor(code: string, message: string, status: number, detail?: unknown) {
    super(message);
    this.name = "ApiError";
    this.code = code;
    this.status = status;
    this.detail = detail;
  }
}

/** 401 未登录/会话失效：触发全局跳登录；登录页凭据错误亦抛本类（message 可直接展示）。 */
export class AuthError extends ApiError {
  constructor(message: string, status = 401) {
    super("AUTH_REQUIRED", message, status);
  }
}

// ---------------------------------------------------------------- 401 全局拦截

let unauthorizedHandler: (() => void) | null = null;

/** 覆盖 401 处理（默认：window.location 跳 /login；登录页自身不跳转防刷新循环）。 */
export function setUnauthorizedHandler(handler: (() => void) | null): void {
  unauthorizedHandler = handler;
}

function notifyUnauthorized(): void {
  if (unauthorizedHandler) {
    unauthorizedHandler();
    return;
  }
  if (typeof window !== "undefined" && !window.location.pathname.startsWith("/login")) {
    window.location.assign("/login");
  }
}

// ================================================================ 请求内核

async function parseErrorBody(response: Response): Promise<ApiErrorBody> {
  try {
    const text = await response.text();
    if (!text) return {};
    const parsed = JSON.parse(text) as ApiErrorBody;
    return {
      code: typeof parsed.code === "string" ? parsed.code : undefined,
      message: typeof parsed.message === "string" ? parsed.message : undefined,
      detail: parsed.detail,
    };
  } catch {
    return {};
  }
}

async function request<T>(path: string, method: string, body?: unknown): Promise<T> {
  const url = `${API_BASE}${path}`;
  let response: Response;
  try {
    response = await fetch(url, {
      method,
      headers: body === undefined ? undefined : { "Content-Type": "application/json" },
      body: body === undefined ? undefined : JSON.stringify(body),
      credentials: "include", // httpOnly 会话 cookie 跨域携带（后端 CORS 白名单含前端源）
      cache: "no-store",
    });
  } catch {
    throw new ApiError("NETWORK_ERROR", "无法连接后端服务，请确认 API 已启动", 0);
  }

  if (response.status === 401) {
    notifyUnauthorized();
    const err = await parseErrorBody(response);
    throw new AuthError(err.message || "未登录或会话已失效");
  }

  if (!response.ok) {
    const err = await parseErrorBody(response);
    throw new ApiError(
      err.code || "UNEXPECTED",
      err.message || `请求失败（HTTP ${response.status}）`,
      response.status,
      err.detail,
    );
  }

  if (response.status === 204) return undefined as T;
  const text = await response.text();
  if (!text) return undefined as T;
  try {
    return JSON.parse(text) as T;
  } catch {
    throw new ApiError("INVALID_RESPONSE", "响应格式错误", response.status);
  }
}

// ================================================================ 方法

export function apiGet<T>(path: string): Promise<T> {
  return request<T>(path, "GET");
}

export function apiPost<T>(path: string, body?: unknown): Promise<T> {
  return request<T>(path, "POST", body);
}

export function apiPut<T>(path: string, body?: unknown): Promise<T> {
  return request<T>(path, "PUT", body);
}

export function apiDelete<T>(path: string): Promise<T> {
  return request<T>(path, "DELETE");
}

// ================================================================ 类型定义（对齐 backend/api/schemas.py）

/** 分页信封（列表端点统一 {total, page, page_size, items}；部分端点仅 total+items） */
export type Paginated<T> = {
  total: number;
  page?: number;
  page_size?: number;
  items: T[];
};

// ---- 鉴权 ----

export type CurrentUser = { username: string; role: string };

// ---- M0 系统 ----

export type OverviewResponse = {
  total_jobs: number;
  jobs_by_stage: Record<string, number>;
  jobs_by_status: Record<string, number>;
  jobs_by_error_code: Record<string, number>;
  today_funnel: Record<string, number>;
  risk: OverviewRisk; // v0.4 批次1：Record<string, unknown> → 精确类型
  generated_at?: string; // v0.4 批次1：API 返回 ISO8601 UTC
};

export type JobSummary = {
  id: number;
  product_id: number;
  stage: string;
  status: string;
  error_code: string | null;
  error_message?: string;
  retry_count?: number;
  created_at?: string | null;
  updated_at?: string | null;
};

// ---- M1 选品 ----

export type ProductSummary = {
  id: number;
  fingerprint: string;
  title: string;
  sanitized_title?: string;
  category: string;
  platform_price: number | null; // 元（直接透传）
  real_cost: number | null;
  suggested_price: number | null;
  profit_margin: number | null;
  sales?: number;
  rank_best?: number;
  board_count?: number;
  score: number;
  state: string;
  compliance: ProductCompliance; // v0.4 批次1：Record<string, unknown> → 精确类型
  supplier_count?: number; // v0.4 批次1：API 返回（1688 同款供应商数）
  return_rate?: number | null; // v0.4 批次1：API 返回
  ad_conversion?: Record<string, unknown>; // v0.4 批次1：API 返回（sales_amount_yuan 已换算元）
  created_at?: string | null;
};

// ---- M2 素材 ----

export type AssetSummary = {
  id: number;
  asset_type: string;
  source_platform: string;
  source_url: string;
  source_author?: string;
  md5?: string;
  phash?: string;
  duration?: number | null;
  resolution?: string | null;
  size?: number | null;
  heat_score?: number | null;
  evaluation: string | null;
  upload_status: string;
  platform_material_id?: string | null;
  compliance_status?: string | null;
  relevance_status: string;
  derivation_note?: string | null; // v0.4 批次1：详情字段（list/detail 同构返回）
  file_path?: string; // v0.4 批次1：详情字段
  tags_json?: Record<string, unknown> | null; // v0.4 批次1：详情字段
  created_at?: string | null;
  updated_at?: string | null;
};

// ---- M3 优化/图片审核（v0.6 批次3：类型按 backend/api/routers/m3_optimization.py 实测字段重写） ----

/**
 * GET /api/optimization/batches 批次条目（源码 _batch_to_dict：
 * batch_id/product_id 为 String(64) 主键/外键，可能为字符串如 "101"）。
 * 注意：任务书草案字段 category_key/mode/generation_round 在 API 中不存在，
 * 实际为 image_type/plan/gate/target_count（差异已记 REPORT）。
 */
export type OptimizationBatchSummary = {
  batch_id: string;
  product_id: string | number;
  image_type: string; // main / detail
  plan: Record<string, unknown> | null; // plan_json（Kimi 规划快照）
  target_count: number;
  gate: Record<string, unknown> | null; // gate_json（质量门禁统计）
  status: string; // generating / pending / reviewed / approved
  image_count: number; // 批内图片数（含已审）
  created_at?: string | null;
  updated_at?: string | null;
};

/** opt_review_records 审核流水（batch 详情 audit 数组元素）。 */
export type OptReviewRecord = {
  review_id: string;
  gate_type: string; // rule / evaluate / manual / relevance
  result: string; // pass / reject / manual_review
  reasons: Record<string, unknown> | null;
  reviewer: string;
  created_at: string | null;
};

/** GET /api/optimization/batches/{id} 批内单图（OptImage）。 */
export type OptimizationImage = {
  image_id: string;
  image_type: string; // main / detail
  variant_no: number;
  file_path: string;
  phash: string;
  width: number;
  height: number;
  quality: Record<string, unknown> | null;
  quality_ok: boolean;
  review_status: string; // pending / approved / rejected
  reject_reason: string;
  category_memory_key: string;
  audit: OptReviewRecord[];
  created_at: string | null;
  updated_at: string | null;
};

/** GET /api/optimization/batches/{id} 批次详情（批次字段 + assets）。 */
export type OptimizationBatchDetail = OptimizationBatchSummary & {
  assets: OptimizationImage[];
};

/** POST /api/optimization/assets/{id}/decision 响应（D6：rule_draft_created 规则草稿闭环）。 */
export type ImageDecisionResult = {
  ok: boolean;
  image_id: string;
  review_status: string;
  review_id: string;
  rule_draft_created: boolean;
  operator: string;
};

/** POST /api/optimization/batches/{id}/approve 响应（幂等：already_approved=true 表示已是目标态）。 */
export type BatchApproveResult = {
  ok: boolean;
  batch_id: string;
  status: string;
  already_approved?: boolean;
  images_approved?: number;
  operator: string;
};

/** POST /api/assets/{id}/relevance-confirm 响应（result 含 changed：同值重复回写为 false）。 */
export type RelevanceConfirmResult = {
  ok: boolean;
  asset_id: number;
  relevance_status: string;
  changed: boolean;
  reason?: string;
};

/** GET /api/optimization/copywrites 文案候选条目（只读 title/script/ad/badge）。 */
export type CopywriteItem = {
  copywrite_id: string;
  product_id: string | number;
  copy_type: string; // title / script / ad / badge
  variant_no: number;
  content: string;
  char_len: number;
  sku_basis: Record<string, unknown> | null;
  compliance: Record<string, unknown> | null;
  status: string;
  source: string;
  created_at: string | null;
};

// ---- M4 上架（D2/D3：title/error_code 为派生字段，可空） ----

export type ListingTask = {
  task_id: string;
  product_id: number;
  generation_version?: string | null;
  stage?: string | null;
  status: string; // 9 态
  title: string | null; // D3：关联最早 SPU title，无 SPU 为 null
  gate_result?: unknown;
  platform_spu_id?: string | null;
  product_link?: string | null;
  link_verified_at?: string | null;
  reject_reason_code?: string | null;
  attempts: number;
  error_code: string | null; // D2：最新 op_log 派生，无记录为 null
  lease_owner?: string | null;
  lease_expires_at?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
};

export type ListingReadyItem = {
  product_id: number;
  task_id: string;
  title: string | null;
  category_id?: number | null;
  product_link?: string | null;
  link_verified_at?: string | null;
  price_min_yuan: number | null; // 元（分→元换算完成）
  price_max_yuan: number | null;
};

// ---- M5 投放/托管（D4：金额一律元 float；D5：枚举英文原值） ----

export type AdsSnapshot = {
  id: number;
  recorded_at: string;
  impressions: number;
  spend_yuan: number; // 元
  gmv_yuan: number;
  subsidy_yuan: number;
  diagnosis: string | null;
  status: string;
};

export type AdsCampaign = {
  id: number;
  product_id: number;
  /** v1.1：跨库 join M1 products.title，缺失为 null（前端 #product_id 兜底）。 */
  product_name?: string | null;
  ad_mode: string;
  target_type: string; // roi / net_roi / goods（D5）
  target_roi: number | null;
  material_ids: string[];
  status: string; // pending / active / paused / not_eligible / ended（D5）
  diagnosis: string | null; // excellent / good / optimize_1 / optimize_n（D5）
  batch_id?: number | null;
  created_at?: string | null;
  updated_at?: string | null;
  latest_snapshot: AdsSnapshot | null;
};

export type AdsAccount = {
  balance_yuan: number | null; // 元
  status: string; // active / risk_control / waiting_* / paused
  throttle_level: number;
  paused_until?: string | null;
  pause_reason?: string;
  min_balance_yuan?: number;
  updated_at?: string | null;
};

export type AdsReportRow = {
  date: string;
  impressions: number;
  spend_yuan: number;
  gmv_yuan: number;
  subsidy_yuan: number;
  campaign_count: number;
};

// ---- 工作台 ----

export type WorkbenchGates = {
  total: number;
  counts: {
    sourcing_review: number;
    listing_confirm: number;
    image_review: number;
    material_pre_review: number;
    verification_takeover: number;
    login_takeover: number;
  };
  generated_at: string;
};

/**
 * GET /api/workbench/exceptions 条目（源码 workbench.py `exceptions`：
 * 字段对齐 WorkflowJob 表 + iso_z 时间 + redact_value 证据）。
 * 注意：任务书草案「paused_until」在 API 中不存在——暂停截止语义由 retry_after
 * （下次可重试时间）承担，前端以「可重试时间」展示（差异记 REPORT）。
 */
export type WorkbenchException = {
  id: number;
  product_id: number; // foundation WorkflowJob.product_id nullable=False
  stage: string;
  status: string; // blocked / waiting_verification / waiting_login（EXCEPTION_STATUSES）
  error_code: string | null;
  error_message?: string; // 后端截断 200
  retry_count?: number;
  retry_after?: string | null; // 下次可重试时间（暂停截止语义）
  lease_owner?: string | null;
  lease_expires_at?: string | null;
  evidence?: Record<string, unknown>; // 已递归脱敏
  created_at?: string | null;
  updated_at?: string | null;
};

/** POST /api/workbench/retry/{id} 响应（waiting_* / blocked → pending，断点续跑）。 */
export type WorkbenchRetryResult = {
  ok: boolean;
  id: number;
  status: string; // pending
  stage: string;
  error_code: string | null;
  operator: string;
};

// ---- v1.1：异常中心批量接管（POST /api/workbench/retry-batch） ----

/** 批量接管单 job 结果（error 为 {code,message}；单 job 失败不影响其余）。 */
export type WorkbenchRetryBatchItem = {
  job_id: number;
  ok: boolean;
  status?: string | null;
  error?: { code: string; message: string } | null;
};

/** POST /api/workbench/retry-batch 响应（body {job_ids: []}；空数组 → 422）。 */
export type WorkbenchRetryBatchResult = {
  results: WorkbenchRetryBatchItem[];
};

/** POST /api/sourcing/gate-confirm 响应（manual_review → pool；已在池中 → 409 INVALID_STATE）。 */
export type GateConfirmResult = {
  ok: boolean;
  product_id: number;
  title: string;
  state: string; // pool
  operator: string;
};

// ================================================================ v0.4 批次1 新增类型（总览风控 / 商品详情 / 素材详情 / 上传记录）

/** GET /api/overview 返回 risk（_risk_status：kill_switch + M5 投放账户）。 */
export type OverviewRisk = {
  kill_switch_enabled: boolean;
  kill_switch_key: string;
  ad_balance_yuan: number | null; // 元
  ad_account_status: string; // active / risk_control / waiting_* / paused / unknown
  ad_throttle_level: number;
};

/** M1 compliance 字段（{state, reasons}，list/detail 同构）。 */
export type ProductCompliance = {
  state: string;
  reasons?: string[];
};

/** M1 五维打分单维（sourcing/models.py ScoreDimension）。 */
export type ScoreDimension = {
  key: string;
  label: string;
  raw: number;
  weight: number;
  weighted: number;
  active: boolean;
  reasons: string[];
};

/** M1 五维打分整体（sourcing/models.py ScoreBreakdown）。 */
export type ScoreBreakdown = {
  total: number;
  dimensions: Record<string, ScoreDimension>;
  rank?: number;
  note?: string;
};

/** 询价明细（sourcing/tables.py Sku）。 */
export type QuoteItem = {
  id: number;
  supplier_name: string;
  sku_name: string;
  unit_cost: number | null;
  min_order: number;
  freight: number;
  raw_url: string;
  quoted_at: string | null;
};

/** 来源证据（sourcing/tables.py ProductSourceEvidence；raw 已脱敏）。 */
export type SourceEvidenceItem = {
  id: number;
  source: string;
  board: string;
  platform_item_id: string;
  title: string;
  price: number;
  sales: number;
  rank: number;
  image_urls: string[];
  raw: unknown;
  collected_at: string | null;
};

/** GET /api/products/{id} 详情（ProductSummary 基础上追加五维/quotes/evidence）。 */
export type ProductDetail = ProductSummary & {
  score_breakdown: ScoreBreakdown;
  quotes: QuoteItem[];
  source_evidence: SourceEvidenceItem[];
};

/** 上传记录（materials/tables.py AssetUpload；evidence 已脱敏）。 */
export type AssetUploadRecord = {
  id: number;
  asset_id: number;
  attempt: number;
  status: string;
  platform_material_id: string | null;
  error_code: string | null;
  evidence: unknown;
  created_at: string | null;
  updated_at: string | null;
};

// ================================================================ v0.5 批次2 新增类型（M4 上架任务详情 / M5 托管详情）

/** M4 任务详情 SPU 映射（GET /api/listing/tasks/{id} 返回 spu；无 SPU 为 null）。 */
export type ListingSpu = {
  spu_id: string;
  title: string;
  category_id: number | null;
  status: string; // 平台原样状态（无固定枚举，直展）
  audit_id: string | null;
};

/** M4 拒审记录（task_detail.audit_records；fix_candidate/evidence 已脱敏 json_safe）。 */
export type ListingAuditRecord = {
  audit_record_id: number;
  audit_id: string | null;
  submit_at: string | null;
  last_query_at: string | null;
  audit_status: string | null; // 平台原样状态（无固定枚举，直展）
  reject_reason: string | null;
  reject_category: string | null;
  fix_candidate: unknown;
  resubmit_required: boolean;
  evidence: unknown;
};

/** M4 任务详情（列表字段 + spu + audit_records）。 */
export type ListingTaskDetail = ListingTask & {
  spu: ListingSpu | null;
  audit_records: ListingAuditRecord[];
};

/** M4 微信操作日志条目（GET /api/listing/tasks/{id}/op-logs；evidence 已脱敏）。 */
export type ListingOpLog = {
  log_id: number;
  request_id: string;
  api: string;
  direction: string; // request / response / transition（state_machine 写 transition）
  payload_digest: string;
  status_code: number | null;
  error_code: string | null;
  platform_code: string | null;
  evidence: unknown;
  created_at: string | null;
};

/** GET /api/listing/tasks/{id}/op-logs 响应。 */
export type ListingOpLogsResponse = {
  task_id: string;
  total: number;
  items: ListingOpLog[];
};

/** GET /api/listing/ready 响应（价格已 分→元；evidence 为候选池最近证据摘要）。 */
export type ListingReadyResponse = {
  total: number;
  evidence: unknown;
  items: ListingReadyItem[];
};

/** POST /api/listing/tasks/{id}/confirm | /retry 响应。 */
export type ListingActionResult = {
  ok: boolean;
  task_id: string;
  status: string;
  operator: string;
};

/** M5 托管详情（设置 + 报表快照序列，recorded_at 升序；latest_snapshot 恒为 null）。 */
export type AdsCampaignDetail = AdsCampaign & {
  snapshots: AdsSnapshot[];
  snapshot_count: number;
};

/** POST /api/ads/campaigns/{id}/pause|resume|end 响应（already=true 表示已是目标状态）。 */
export type CampaignActionResult = {
  ok: boolean;
  campaign_id: number;
  status: string;
  already?: boolean;
  operator: string;
};

/** POST /api/ads/campaigns/{id}/materials 响应（preferred_order 优选顺序 + note 提示）。 */
export type AdsMaterialsResult = {
  ok: boolean;
  campaign_id: number;
  material_ids: string[];
  preferred_order: string[];
  note: string;
  operator: string;
};

/** GET /api/ads/report 响应（按日聚合，日期降序）。 */
export type AdsReportResponse = {
  days: number;
  total: number;
  items: AdsReportRow[];
};
