import { describe, expect, it } from "vitest";
import {
  abnormalJobCount,
  countEntries,
  funnelEntries,
  sumRecord,
} from "../lib/dashboard";

describe("sumRecord（计数 record 求和）", () => {
  it("正常 record 求和", () => {
    expect(sumRecord({ a: 1, b: 2, c: 3 })).toBe(6);
  });

  it("空对象 → 0", () => {
    expect(sumRecord({})).toBe(0);
  });

  it("null / undefined → 0", () => {
    expect(sumRecord(null)).toBe(0);
    expect(sumRecord(undefined)).toBe(0);
  });

  it("非有限值按 0 处理", () => {
    expect(sumRecord({ a: 1, b: Number.NaN, c: Number.POSITIVE_INFINITY })).toBe(1);
  });
});

describe("countEntries（按 count 降序）", () => {
  it("降序排列且只输出 count>0", () => {
    expect(countEntries({ a: 3, b: 1, c: 0, d: 2 })).toEqual([
      { key: "a", count: 3 },
      { key: "d", count: 2 },
      { key: "b", count: 1 },
    ]);
  });

  it("空 / null → []", () => {
    expect(countEntries({})).toEqual([]);
    expect(countEntries(null)).toEqual([]);
  });
});

describe("funnelEntries（按 09 文档阶段顺序，label 经 enums 翻译）", () => {
  it("已知阶段按固定顺序输出，并翻译中文 label", () => {
    const result = funnelEntries({
      shop_ads_run: 2,
      source_collect: 5,
      image_generation: 1,
    });
    expect(result).toEqual([
      { key: "source_collect", label: "选品采集", count: 5 },
      { key: "image_generation", label: "生图", count: 1 },
      { key: "shop_ads_run", label: "托管投放执行", count: 2 },
    ]);
  });

  it("未知阶段排末尾（按 count 降序）", () => {
    const result = funnelEntries({ unknown_stage: 3, source_collect: 1 });
    expect(result).toEqual([
      { key: "source_collect", label: "选品采集", count: 1 },
      { key: "unknown_stage", label: "unknown_stage", count: 3 },
    ]);
  });

  it("count=0 的阶段不输出", () => {
    expect(funnelEntries({ source_collect: 0, alibaba_quote: 2 })).toEqual([
      { key: "alibaba_quote", label: "1688询价", count: 2 },
    ]);
  });

  it("null / undefined → []", () => {
    expect(funnelEntries(null)).toEqual([]);
  });
});

describe("abnormalJobCount（blocked / failed / waiting_* 聚合）", () => {
  it("统计需人工介入或失败状态", () => {
    expect(
      abnormalJobCount({
        pending: 3,
        running: 2,
        success: 10,
        failed: 1,
        blocked: 2,
        waiting_login: 1,
        waiting_verification: 1,
        cancelled: 1,
      }),
    ).toBe(5);
  });

  it("空 / null → 0", () => {
    expect(abnormalJobCount({})).toBe(0);
    expect(abnormalJobCount(null)).toBe(0);
  });
});
