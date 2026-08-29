import { describe, expect, it } from "vitest";
import type { AdsReportRow } from "../lib/api";
import {
  barMax,
  buildAdsQuery,
  buildAdsReportQuery,
  canEndCampaign,
  canPauseCampaign,
  canResumeCampaign,
  formatTargetBid,
  parseMaterialIds,
  reportRowsAscending,
  sumReportMetrics,
} from "../lib/ads";

function makeRow(partial: Partial<AdsReportRow>): AdsReportRow {
  return {
    date: "2026-08-29",
    impressions: 0,
    spend_yuan: 0,
    gmv_yuan: 0,
    subsidy_yuan: 0,
    campaign_count: 1,
    ...partial,
  };
}

describe("托管操作可用性（对齐 m5_ads.py _campaign_action）", () => {
  it("仅 active 可暂停", () => {
    expect(canPauseCampaign("active")).toBe(true);
    expect(canPauseCampaign("paused")).toBe(false);
    expect(canPauseCampaign("ended")).toBe(false);
    expect(canPauseCampaign(null)).toBe(false);
  });

  it("仅 paused 可恢复", () => {
    expect(canResumeCampaign("paused")).toBe(true);
    expect(canResumeCampaign("active")).toBe(false);
    expect(canResumeCampaign("ended")).toBe(false);
  });

  it("非 ended 可结束（空值不可）", () => {
    expect(canEndCampaign("active")).toBe(true);
    expect(canEndCampaign("paused")).toBe(true);
    expect(canEndCampaign("not_eligible")).toBe(true);
    expect(canEndCampaign("ended")).toBe(false);
    expect(canEndCampaign(null)).toBe(false);
  });
});

describe("buildAdsQuery（GET /api/ads/campaigns）", () => {
  it("空筛选 → 仅分页参数", () => {
    expect(buildAdsQuery("", 1, 20)).toBe("?page=1&page_size=20");
  });

  it("status 过滤 + 分页", () => {
    expect(buildAdsQuery("active", 2, 50)).toBe("?status=active&page=2&page_size=50");
  });

  it("page 最小为 1", () => {
    expect(buildAdsQuery("", 0, 20)).toBe("?page=1&page_size=20");
  });
});

describe("buildAdsReportQuery（GET /api/ads/report）", () => {
  it("常规天数", () => {
    expect(buildAdsReportQuery(7)).toBe("?days=7");
    expect(buildAdsReportQuery(30)).toBe("?days=30");
  });

  it("夹取到后端 1..90 范围", () => {
    expect(buildAdsReportQuery(0)).toBe("?days=1");
    expect(buildAdsReportQuery(999)).toBe("?days=90");
  });

  it("NaN/非法 → 默认 7", () => {
    expect(buildAdsReportQuery(Number.NaN)).toBe("?days=7");
  });
});

describe("formatTargetBid（目标出价：类型中文 + ROI）", () => {
  it("roi 类型", () => {
    expect(formatTargetBid("roi", 2.4)).toBe("成交ROI 2.40");
  });

  it("net_roi / goods", () => {
    expect(formatTargetBid("net_roi", 1.556)).toBe("净成交ROI 1.56");
    expect(formatTargetBid("goods", 0)).toBe("商品成交 0.00");
  });

  it("roi 空值 → —（即使类型存在）", () => {
    expect(formatTargetBid("roi", null)).toBe("—");
    expect(formatTargetBid("roi", undefined)).toBe("—");
    expect(formatTargetBid("roi", Number.NaN)).toBe("—");
  });

  it("未知类型原样透传（enumLabel 语义）", () => {
    expect(formatTargetBid("future_type", 3)).toBe("future_type 3.00");
  });
});

describe("sumReportMetrics（报表汇总卡）", () => {
  it("多行求和", () => {
    const totals = sumReportMetrics([
      makeRow({ impressions: 100, spend_yuan: 10.5, gmv_yuan: 20, subsidy_yuan: 1.25 }),
      makeRow({ impressions: 250, spend_yuan: 5, gmv_yuan: 30, subsidy_yuan: 0 }),
    ]);
    expect(totals).toEqual({ impressions: 350, spend_yuan: 15.5, gmv_yuan: 50, subsidy_yuan: 1.25 });
  });

  it("空列表 → 全 0", () => {
    expect(sumReportMetrics([])).toEqual({ impressions: 0, spend_yuan: 0, gmv_yuan: 0, subsidy_yuan: 0 });
  });

  it("undefined 字段按 0 处理", () => {
    expect(sumReportMetrics([makeRow({ impressions: undefined as unknown as number })])).toEqual({
      impressions: 0,
      spend_yuan: 0,
      gmv_yuan: 0,
      subsidy_yuan: 0,
    });
  });
});

describe("barMax（柱状图缩放基准）", () => {
  it("常规最大值", () => {
    expect(barMax([3, 7, 5])).toBe(7);
  });

  it("空/全 0 → 1（避免除零）", () => {
    expect(barMax([])).toBe(1);
    expect(barMax([0, 0])).toBe(1);
  });

  it("忽略负数与非有限值", () => {
    expect(barMax([-5, Number.NaN, Number.POSITIVE_INFINITY, 4])).toBe(4);
  });
});

describe("reportRowsAscending（API 降序 → 展示升序）", () => {
  it("按日期升序", () => {
    const rows = [
      makeRow({ date: "2026-08-30" }),
      makeRow({ date: "2026-08-28" }),
      makeRow({ date: "2026-08-29" }),
    ];
    expect(reportRowsAscending(rows).map((r) => r.date)).toEqual([
      "2026-08-28",
      "2026-08-29",
      "2026-08-30",
    ]);
  });

  it("不修改原数组", () => {
    const rows = [makeRow({ date: "2026-08-30" }), makeRow({ date: "2026-08-29" })];
    reportRowsAscending(rows);
    expect(rows.map((r) => r.date)).toEqual(["2026-08-30", "2026-08-29"]);
  });
});

describe("parseMaterialIds（素材输入解析）", () => {
  it("逗号/中文逗号/空白分隔 + 去空", () => {
    expect(parseMaterialIds("1001, 1002，1003")).toEqual(["1001", "1002", "1003"]);
    expect(parseMaterialIds(" 1001 1002\t1003\n")).toEqual(["1001", "1002", "1003"]);
  });

  it("去重", () => {
    expect(parseMaterialIds("a, a, b")).toEqual(["a", "b"]);
  });

  it("空输入 → []", () => {
    expect(parseMaterialIds("")).toEqual([]);
    expect(parseMaterialIds(" , ， ")).toEqual([]);
  });
});
