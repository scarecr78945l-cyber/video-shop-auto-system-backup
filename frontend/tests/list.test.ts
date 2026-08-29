import { describe, expect, it } from "vitest";
import type { AssetSummary, ProductSummary } from "../lib/api";
import {
  buildAssetQuery,
  DEFAULT_ASSET_FILTERS,
  distinctSourcePlatforms,
} from "../lib/assets";
import {
  buildProductQuery,
  DEFAULT_PRODUCT_FILTERS,
  distinctCategories,
  filterProductsByKeyword,
} from "../lib/products";

// ---------------------------------------------------------------- 商品池

function makeProduct(partial: Partial<ProductSummary>): ProductSummary {
  return {
    id: 1,
    fingerprint: "fp",
    title: "",
    category: "",
    platform_price: null,
    real_cost: null,
    suggested_price: null,
    profit_margin: null,
    score: 0,
    state: "pool",
    compliance: { state: "candidate", reasons: [] },
    created_at: null,
    ...partial,
  };
}

describe("filterProductsByKeyword（客户端关键词，标题/清洗后标题包含）", () => {
  const items = [
    makeProduct({ id: 1, title: "夏季防晒衣 女款", sanitized_title: "防晒衣 女" }),
    makeProduct({ id: 2, title: "男士短袖T恤", sanitized_title: "短袖T恤 男" }),
    makeProduct({ id: 3, title: "儿童防晒帽", sanitized_title: "" }),
  ];

  it("命中标题", () => {
    expect(filterProductsByKeyword(items, "防晒").map((p) => p.id)).toEqual([1, 3]);
  });

  it("命中清洗后标题", () => {
    expect(filterProductsByKeyword(items, "短袖").map((p) => p.id)).toEqual([2]);
  });

  it("大小写不敏感", () => {
    expect(filterProductsByKeyword(items, "T恤").map((p) => p.id)).toEqual([2]);
    expect(filterProductsByKeyword(items, "t恤").map((p) => p.id)).toEqual([2]);
  });

  it("空关键词 / 空白 → 原样返回", () => {
    expect(filterProductsByKeyword(items, "")).toEqual(items);
    expect(filterProductsByKeyword(items, "   ")).toEqual(items);
  });

  it("无命中 → []", () => {
    expect(filterProductsByKeyword(items, "不存在的词")).toEqual([]);
  });
});

describe("buildProductQuery（GET /api/products：limit/offset 分页）", () => {
  it("空筛选 → 仅分页参数", () => {
    const qs = buildProductQuery(DEFAULT_PRODUCT_FILTERS, 1, 20);
    expect(qs).toBe("?limit=20&offset=0");
  });

  it("类目 + 合规 + 分数区间", () => {
    const qs = buildProductQuery(
      { category: "服饰", compliance: "candidate", minScore: 60, maxScore: 90 },
      2,
      50,
    );
    expect(qs).toBe("?category=%E6%9C%8D%E9%A5%B0&compliance=candidate&min_score=60&max_score=90&limit=50&offset=50");
  });

  it("minScore/maxScore 为 null 时不出参", () => {
    const qs = buildProductQuery(
      { category: "", compliance: "", minScore: null, maxScore: null },
      1,
      20,
    );
    expect(qs).not.toContain("min_score");
    expect(qs).not.toContain("max_score");
  });

  it("page=1 offset=0；page=3 offset=(3-1)*pageSize", () => {
    expect(buildProductQuery(DEFAULT_PRODUCT_FILTERS, 1, 20)).toContain("offset=0");
    expect(buildProductQuery(DEFAULT_PRODUCT_FILTERS, 3, 20)).toContain("offset=40");
  });

  it("非有限分数不参与查询", () => {
    const qs = buildProductQuery(
      { category: "", compliance: "", minScore: Number.NaN, maxScore: Number.POSITIVE_INFINITY },
      1,
      20,
    );
    expect(qs).toBe("?limit=20&offset=0");
  });
});

describe("distinctCategories（当前页类目去重）", () => {
  it("去重 + localeCompare 排序（ICU zh-CN，拼音序：服饰 < 家居）", () => {
    const items = [
      makeProduct({ id: 1, category: "服饰" }),
      makeProduct({ id: 2, category: "家居" }),
      makeProduct({ id: 3, category: "服饰" }),
      makeProduct({ id: 4, category: "" }),
    ];
    expect(distinctCategories(items)).toEqual(["服饰", "家居"]);
  });

  it("空列表 → []", () => {
    expect(distinctCategories([])).toEqual([]);
  });
});

// ---------------------------------------------------------------- 素材库

function makeAsset(partial: Partial<AssetSummary>): AssetSummary {
  return {
    id: 1,
    asset_type: "video",
    source_platform: "视频号",
    source_url: "",
    evaluation: null,
    upload_status: "local",
    relevance_status: "pending",
    created_at: null,
    ...partial,
  };
}

describe("buildAssetQuery（GET /api/assets：page/page_size 分页）", () => {
  it("默认筛选 → 仅分页参数", () => {
    expect(buildAssetQuery(DEFAULT_ASSET_FILTERS, 1, 20)).toBe("?page=1&page_size=20");
  });

  it("全筛选参数输出（顺序对齐 router 参数名）", () => {
    const qs = buildAssetQuery(
      {
        assetType: "video",
        sourcePlatform: "抖音",
        relevanceStatus: "passed",
        uploadStatus: "uploaded",
        evaluation: "efficient",
      },
      2,
      50,
    );
    expect(qs).toBe(
      "?asset_type=video&source_platform=%E6%8A%96%E9%9F%B3&relevance_status=passed&upload_status=uploaded&evaluation=efficient&page=2&page_size=50",
    );
  });

  it("page 最小为 1", () => {
    expect(buildAssetQuery(DEFAULT_ASSET_FILTERS, 0, 20)).toBe("?page=1&page_size=20");
  });
});

describe("distinctSourcePlatforms（当前页平台去重）", () => {
  it("去重 + 中文排序", () => {
    const items = [
      makeAsset({ id: 1, source_platform: "抖音" }),
      makeAsset({ id: 2, source_platform: "视频号" }),
      makeAsset({ id: 3, source_platform: "抖音" }),
      makeAsset({ id: 4, source_platform: "" }),
    ];
    expect(distinctSourcePlatforms(items)).toEqual(["抖音", "视频号"]);
  });

  it("空列表 → []", () => {
    expect(distinctSourcePlatforms([])).toEqual([]);
  });
});
