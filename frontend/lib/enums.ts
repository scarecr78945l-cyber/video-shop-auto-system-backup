/**
 * 枚举中文映射表（唯一权威表，来源 context/README.md 2.3 节 + 1.8 节 D5/D10）
 *
 * 铁律：组件内禁止硬编码中文；一律经 `enumLabel` 或 `*_LABELS` 映射表翻译。
 * API 层枚举原样透传（英文/中文都不翻译），翻译只在展示层（lib/enums.ts）。
 *
 * 覆盖：
 * - error_code 7 码（DA-008）+ API 局部 2 码（D10：VALIDATION_ERROR / INVALID_STATE）
 * - M4 上架状态机 9 态
 * - M1 compliance 三态 / products.state 三态
 * - M2 relevance_status 四态 / upload_status 五态 / evaluation 三态
 * - M5 英文枚举（D5：status / diagnosis / target_type，代码实测英文原值）
 * - 09 前端状态机 7 阶段（阶段条）
 */

// ---------------------------------------------------------------- 通用翻译

/** 查表翻译：命中返回中文；null/undefined → fallback（默认 `—`）；未知值原样透传（便于排障）。 */
export function enumLabel(
  labels: Record<string, string>,
  value: string | null | undefined,
  fallback = "—",
): string {
  if (value === null || value === undefined || value === "") return fallback;
  return labels[value] ?? value;
}

// ---------------------------------------------------------------- error_code（DA-008 7 码 + D10 局部 2 码）

export const ERROR_CODE_LABELS: Record<string, string> = {
  VERIFICATION_REQUIRED: "验证码/安全验证",
  AUTH_REQUIRED: "登录失效",
  RATE_LIMIT: "限流",
  TIMEOUT: "超时",
  NO_MATCH: "无匹配",
  PLATFORM_REJECT: "平台驳回",
  UNEXPECTED: "未知",
  // API 层局部码（D10 / L4，非 DA-008 业务码）
  VALIDATION_ERROR: "请求参数校验失败",
  INVALID_STATE: "状态冲突",
};

/** error_code 快捷翻译。 */
export function errorCodeLabel(code: string | null | undefined): string {
  return enumLabel(ERROR_CODE_LABELS, code);
}

// ---------------------------------------------------------------- M4 上架状态机（9 态）

export const LISTING_STATUS_LABELS: Record<string, string> = {
  pending: "待上架",
  creating: "创建中",
  draft: "草稿",
  platform_auditing: "平台审核中",
  listed: "已上架",
  rejected: "审核驳回",
  retry_candidate: "待重提",
  manual: "人工处理",
  failed: "失败",
};

// ---------------------------------------------------------------- M1 选品

export const COMPLIANCE_LABELS: Record<string, string> = {
  hard_reject: "已淘汰",
  candidate: "候选",
  manual_review: "待人工复核",
};

export const PRODUCT_STATE_LABELS: Record<string, string> = {
  pool: "商品池",
  manual_review: "待人工复核",
  rejected: "已淘汰",
};

// ---------------------------------------------------------------- M2 素材

export const RELEVANCE_STATUS_LABELS: Record<string, string> = {
  pending: "待判定",
  passed: "相关放行",
  failed: "不相关淘汰",
  manual_review: "待人工确认目标款",
};

export const UPLOAD_STATUS_LABELS: Record<string, string> = {
  local: "本地",
  uploading: "上传中",
  uploaded: "已上传",
  failed: "失败",
  disabled: "拒审下架",
};

/** evaluation 标签（M2/M3/M5 共口径） */
export const EVALUATION_LABELS: Record<string, string> = {
  exploring: "探索期",
  efficient: "高效",
  potential: "潜力",
};

// ---------------------------------------------------------------- M5 投放/托管（D5：英文枚举原值，前端翻译）

export const M5_STATUS_LABELS: Record<string, string> = {
  pending: "待托管",
  active: "托管中",
  paused: "已暂停",
  not_eligible: "不可投放",
  ended: "已结束",
};

export const M5_DIAGNOSIS_LABELS: Record<string, string> = {
  excellent: "优秀",
  good: "良好",
  optimize_1: "1项待优化",
  optimize_n: "N项待优化",
};

export const M5_TARGET_TYPE_LABELS: Record<string, string> = {
  roi: "成交ROI",
  net_roi: "净成交ROI",
  goods: "商品成交",
};

// ---------------------------------------------------------------- 09 前端状态机（阶段条）

export const WORKFLOW_STAGES: ReadonlyArray<{ id: number; label: string }> = [
  { id: 1, label: "已选品" },
  { id: 2, label: "淘宝素材" },
  { id: 3, label: "询价" },
  { id: 4, label: "生图" },
  { id: 5, label: "图片审核" },
  { id: 6, label: "待上架/已上架" },
  { id: 7, label: "托管投放" },
];

/** 阶段 id → 中文（1..7；越界 → `—`）。 */
export function workflowStageLabel(stage: number | null | undefined): string {
  if (stage === null || stage === undefined) return "—";
  const hit = WORKFLOW_STAGES.find((s) => s.id === stage);
  return hit ? hit.label : "—";
}

// ================================================================ v0.4 批次1 新增映射（M0 任务队列 / M5 账户 / M2 素材 / M1 打分维度）

/** workflow_jobs/tasks.stage（09 文档第二节 STAGE_VALUES，backend/foundation/tables.py） */
export const JOB_STAGE_LABELS: Record<string, string> = {
  source_collect: "选品采集",
  alibaba_quote: "1688询价",
  taobao_reference: "淘宝素材",
  image_generation: "生图",
  listing_upload: "上架",
  shop_ads_run: "托管投放执行",
  shop_ads_report: "投放报表回读",
};

/** workflow_jobs/tasks.status（JOB_STATUSES 8 态） */
export const JOB_STATUS_LABELS: Record<string, string> = {
  pending: "待执行",
  running: "执行中",
  waiting_login: "等待登录",
  waiting_verification: "等待验证码",
  blocked: "阻塞",
  success: "成功",
  failed: "失败",
  cancelled: "已取消",
};

/** M5 投放账户状态（ads account.status；与 M5 托管 campaign status 不同表，D5 英文原值） */
export const ADS_ACCOUNT_STATUS_LABELS: Record<string, string> = {
  active: "正常",
  risk_control: "风控中",
  paused: "已暂停",
  waiting_login: "等待登录",
  waiting_verification: "等待验证码",
  unknown: "未知",
};

/** M2 素材类型（asset_type） */
export const ASSET_TYPE_LABELS: Record<string, string> = {
  video: "视频",
  image: "图片",
};

/** M2 素材合规状态（compliance_status：pending/passed/rejected） */
export const ASSET_COMPLIANCE_LABELS: Record<string, string> = {
  pending: "待判定",
  passed: "已通过",
  rejected: "已驳回",
};

/** M2 上传台账状态（asset_uploads.status：与 asset_items.upload_status 不同枚举） */
export const UPLOAD_RECORD_STATUS_LABELS: Record<string, string> = {
  pending: "待上传",
  success: "已上传",
  failed: "失败",
  disabled: "拒审下架",
};

/** M1 五维打分维度 key（sourcing/scoring.py DIM_LABELS 同源；detail 内 dimension.label 兜底） */
export const SCORE_DIM_LABELS: Record<string, string> = {
  trend: "热度趋势",
  profit: "利润率",
  after_sale: "售后风险",
  supply: "供给稳定",
  ad_conversion: "投放转化",
};

/** M1 五维打分固定展示顺序（detail.score_breakdown.dimensions 键序兜底） */
export const SCORE_DIM_ORDER: ReadonlyArray<string> = [
  "trend",
  "profit",
  "after_sale",
  "supply",
  "ad_conversion",
];

// ================================================================ v0.5 批次2 追加（M4 操作日志方向）

/**
 * M4 微信操作日志 direction（listing/tables.py ListingOpLogRow.direction：
 * request / response；listing/state_machine.py 迁移证据写 transition）。
 */
export const LISTING_OP_LOG_DIRECTION_LABELS: Record<string, string> = {
  request: "请求",
  response: "响应",
  transition: "状态迁移",
};

// ================================================================ v0.6 批次3 追加（M3 生图批次 / 图片审核 / 审核记录）

/**
 * M3 生图批次 image_type（optimization/tables.py OptImageBatch.image_type：main/detail）。
 */
export const OPT_IMAGE_TYPE_LABELS: Record<string, string> = {
  main: "主图",
  detail: "详情图",
};

/**
 * M3 生图批次 status（optimization/repo.py create_batch=generating / tables 默认 pending /
 * api 整批通过=approved；测试链路另见 reviewed）。
 */
export const OPT_BATCH_STATUS_LABELS: Record<string, string> = {
  generating: "生成中",
  pending: "待审核",
  reviewed: "已审核",
  approved: "已通过",
};

/**
 * M3 图片审核状态 review_status（optimization/tables.py OptImage.review_status：
 * pending / approved / rejected；api image_decision 写 approved/rejected）。
 */
export const OPT_IMAGE_REVIEW_STATUS_LABELS: Record<string, string> = {
  pending: "待审核",
  approved: "已通过",
  rejected: "已驳回",
};

/**
 * M3 审核流水 gate_type（optimization/review/gate.py：rule/evaluate/manual/
 * relevance；api 人工判定写 manual）。
 */
export const OPT_REVIEW_GATE_LABELS: Record<string, string> = {
  rule: "规则预审",
  evaluate: "素材评估",
  manual: "人工复核",
  relevance: "相关性门",
};

/**
 * M3 审核流水 result（gate.result：pass/reject/manual_review；api 人工判定
 * approve→pass / reject→reject）。
 */
export const OPT_REVIEW_RESULT_LABELS: Record<string, string> = {
  pass: "通过",
  reject: "驳回",
  manual_review: "待人工复核",
};

/**
 * M3 图片质检标记 quality_ok（optimization/tables.py OptImage.quality_ok；
 * 布尔值经 String() 入表翻译）。
 */
export const OPT_QUALITY_LABELS: Record<string, string> = {
  true: "质检合格",
  false: "质检不合格",
};
