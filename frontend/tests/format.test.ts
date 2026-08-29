import { describe, expect, it } from "vitest";
import { centsToYuan, formatDateTime, formatYuan } from "../lib/format";

describe("formatYuan（元 → ¥xx.xx；前端零换算，DA-001）", () => {
  it("12.9 元 → ¥12.90", () => {
    expect(formatYuan(12.9)).toBe("¥12.90");
  });

  it("整数元原样格式化（1290 视为元，不做事分换算）", () => {
    expect(formatYuan(1290)).toBe("¥1290.00");
  });

  it("整数场景 12 → ¥12.00", () => {
    expect(formatYuan(12)).toBe("¥12.00");
  });

  it("0 → ¥0.00", () => {
    expect(formatYuan(0)).toBe("¥0.00");
  });

  it("null / undefined / NaN → —（可空字段口径 D2/D3）", () => {
    expect(formatYuan(null)).toBe("—");
    expect(formatYuan(undefined)).toBe("—");
    expect(formatYuan(Number.NaN)).toBe("—");
  });
});

describe("centsToYuan（兜底换算：仅供未来契约兼容，正常链路禁止调用）", () => {
  it("1290 分 → 12.9 元", () => {
    expect(centsToYuan(1290)).toBe(12.9);
  });

  it("50000 分 → 500 元", () => {
    expect(centsToYuan(50000)).toBe(500);
  });

  it("null / undefined → null", () => {
    expect(centsToYuan(null)).toBeNull();
    expect(centsToYuan(undefined)).toBeNull();
  });

  it("端到端：1290 分（内部存储）→ API 元 → formatYuan → ¥12.90", () => {
    expect(formatYuan(centsToYuan(1290))).toBe("¥12.90");
  });
});

describe("formatDateTime（ISO8601 → UTC+8，Intl 标准做法，禁止手动 +8h）", () => {
  it("UTC Z → UTC+8：2026-08-29T08:00:00Z → 2026-08-29 16:00", () => {
    expect(formatDateTime("2026-08-29T08:00:00Z")).toBe("2026-08-29 16:00");
  });

  it("显式 +08:00 契约值（M1 generated_at）原时区展示：08:00+08:00 → 08:00", () => {
    expect(formatDateTime("2026-08-29T08:00:00+08:00")).toBe("2026-08-29 08:00");
  });

  it("withSeconds → YYYY-MM-DD HH:mm:ss", () => {
    expect(formatDateTime("2026-08-29T08:00:00Z", true)).toBe("2026-08-29 16:00:00");
  });

  it("null / undefined / 空串 → —", () => {
    expect(formatDateTime(null)).toBe("—");
    expect(formatDateTime(undefined)).toBe("—");
    expect(formatDateTime("")).toBe("—");
  });

  it("非法时间串 → —", () => {
    expect(formatDateTime("not-a-date")).toBe("—");
  });

  it("午夜边界 h23：2026-08-29T16:00:00Z → 2026-08-30 00:00", () => {
    expect(formatDateTime("2026-08-29T16:00:00Z")).toBe("2026-08-30 00:00");
  });
});
