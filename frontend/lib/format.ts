/**
 * 展示口径层 · 金额/时间格式化（唯一转换层，前端铁律：零换算、集中转换）
 *
 * 总控裁决（DA-001）：API 层对外金额一律「元（float）」——内部存储分不变，
 * API 层 ÷100 换算；M1 商品池元字段直接透传。**前端只消费元**：
 * - `formatYuan` 直接格式化元，**禁止任何组件/工具内做分→元换算**；
 * - `centsToYuan` 仅作兜底保留（注释注明仅供未来契约兼容，正常链路不调用）；
 * - `formatDateTime` 集中把 ISO8601 → UTC+8（Asia/Shanghai）展示，
 *   用 Intl.DateTimeFormat（标准做法，禁止手动 +8h）。
 */

/** 金额：元（float）→ `¥12.90`；null/undefined/NaN → `—`（D2/D3 可空字段口径）。 */
export function formatYuan(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  return `¥${value.toFixed(2)}`;
}

/**
 * 兜底换算：分（int）→ 元（float）。
 *
 * ⚠️ 仅供未来契约兼容使用（例如历史接口误发分时逐字段救急）；
 * 当前 API 已统一输出元，正常链路**禁止调用本函数**（硬性口径 1）。
 */
export function centsToYuan(cents: number | null | undefined): number | null {
  if (cents === null || cents === undefined || Number.isNaN(cents)) return null;
  return Math.round(cents) / 100;
}

/** 解析 ISO8601（带 Z 或 +08:00 均可，含 M1 generated_at 的 +08:00 契约值）→ UTC+8 展示。 */
function toShanghaiParts(iso: string, withSeconds: boolean): Record<string, string> {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return {};
  const fmt = new Intl.DateTimeFormat("zh-CN", {
    timeZone: "Asia/Shanghai",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: withSeconds ? "2-digit" : undefined,
    hourCycle: "h23",
  });
  const parts = fmt.formatToParts(date);
  const map: Record<string, string> = {};
  for (const part of parts) {
    if (part.type !== "literal") map[part.type] = part.value;
  }
  return map;
}

/**
 * 时间：ISO8601 → UTC+8 展示 `YYYY-MM-DD HH:mm`（列表）/ `YYYY-MM-DD HH:mm:ss`（详情）。
 * 非法/空值 → `—`。字段命名约定 `*_at`（DA-001）。
 */
export function formatDateTime(iso: string | null | undefined, withSeconds = false): string {
  if (!iso) return "—";
  const p = toShanghaiParts(iso, withSeconds);
  if (!p.year) return "—";
  const base = `${p.year}-${p.month}-${p.day} ${p.hour}:${p.minute}`;
  return withSeconds ? `${base}:${p.second}` : base;
}

// ================================================================ v0.4 批次1 新增（素材规格 / 比率展示）

/**
 * 时长：秒 → `X秒` / `X分Y秒` / `X小时X分[Y秒]`（M2 素材 duration，video 必填）。
 * null / undefined / NaN / 负数 → `—`。
 */
export function formatDuration(seconds: number | null | undefined): string {
  if (seconds === null || seconds === undefined || Number.isNaN(seconds) || seconds < 0) return "—";
  const total = Math.floor(seconds);
  const h = Math.floor(total / 3600);
  const m = Math.floor((total % 3600) / 60);
  const s = total % 60;
  if (h > 0) return s === 0 ? `${h}小时${m}分` : `${h}小时${m}分${s}秒`;
  if (m > 0) return s === 0 ? `${m}分钟` : `${m}分${s}秒`;
  return `${s}秒`;
}

/**
 * 字节 → `512 B` / `12.3 KB` / `45.6 MB` / `1.2 GB`（M2 素材 size，字节）。
 * null / undefined / NaN / 负数 → `—`。
 */
export function formatBytes(bytes: number | null | undefined): string {
  if (bytes === null || bytes === undefined || Number.isNaN(bytes) || bytes < 0) return "—";
  if (bytes < 1024) return `${bytes} B`;
  let value = bytes;
  for (const unit of ["KB", "MB", "GB", "TB"] as const) {
    value /= 1024;
    if (value < 1024) return `${value >= 100 ? value.toFixed(0) : value.toFixed(1)} ${unit}`;
  }
  return `${value.toFixed(1)} PB`;
}

/**
 * 比率（0~1）→ 百分比 `50.0%`（M1 profit_margin = (建议售价-成本)/建议售价 比率）。
 * null / undefined / NaN → `—`。仅展示换算，不做金额分→元换算（DA-001 铁律不受影响）。
 */
export function formatPercent(ratio: number | null | undefined): string {
  if (ratio === null || ratio === undefined || Number.isNaN(ratio)) return "—";
  return `${(ratio * 100).toFixed(1)}%`;
}
