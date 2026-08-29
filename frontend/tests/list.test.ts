import { describe, expect, it } from "vitest";
import type { AssetSummary, ProductSummary } from "../lib/api";
import {
  assetToMaterialId,
  buildAssetQuery,
  buildAssetSelectorQuery,
  DEFAULT_ASSET_FILTERS,
  distinctSourcePlatforms,
} from "../lib/assets";
import {
  buildProductQuery,
  DEFAULT_PRODUCT_FILTERS,
  distinctCategories,
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

describe("buildProductQuery（GET /api/products：v1.1 page/page_size 分页 + 服务端 keyword）", () => {
  it("空筛选 → 仅分页参数（page/page_size）", () => {
    expect(buildProductQuery(DEFAULT_PRODUCT_FILTERS, 1, 20)).toBe("?page=1&page_size=20");
  });

  it("类目 + 合规 + 分数区间（v1.1 无 limit/offset）", () => {
    const qs = buildProductQuery(
      { category: "服饰", compliance: "candidate", minScore: 60, maxScore: 90 },
      2,
      50,
    );
    expect(qs).toBe(
      "?category=%E6%9C%8D%E9%A5%B0&compliance=candidate&min_score=60&max_score=90&page=2&page_size=50",
    );
    expect(qs).not.toContain("limit");
    expect(qs).not.toContain("offset");
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

  it("page 直接映射（非 offset 换算）：page=2 → page=2", () => {
    expect(buildProductQuery(DEFAULT_PRODUCT_FILTERS, 2, 20)).toBe("?page=2&page_size=20");
    expect(buildProductQuery(DEFAULT_PRODUCT_FILTERS, 3, 20)).toBe("?page=3&page_size=20");
  });

  it("page 最小为 1", () => {
    expect(buildProductQuery(DEFAULT_PRODUCT_FILTERS, 0, 20)).toBe("?page=1&page_size=20");
  });

  it("非有限分数不参与查询", () => {
    const qs = buildProductQuery(
      { category: "", compliance: "", minScore: Number.NaN, maxScore: Number.POSITIVE_INFINITY },
      1,
      20,
    );
    expect(qs).toBe("?page=1&page_size=20");
  });

  it("keyword 非空时输出 keyword 参数（URL 编码）", () => {
    expect(buildProductQuery(DEFAULT_PRODUCT_FILTERS, 1, 20, "防晒衣")).toBe(
      "?keyword=%E9%98%B2%E6%99%92%E8%A1%A3&page=1&page_size=20",
    );
  });

  it("keyword 空白/空 → 不出 keyword 参数", () => {
    expect(buildProductQuery(DEFAULT_PRODUCT_FILTERS, 1, 20, "   ")).toBe("?page=1&page_size=20");
    expect(buildProductQuery(DEFAULT_PRODUCT_FILTERS, 1, 20, "")).toBe("?page=1&page_size=20");
  });

  it("keyword 与筛选参数共存", () => {
    const qs = buildProductQuery({ category: "服饰", compliance: "", minScore: null, maxScore: null }, 1, 20, "T恤");
    expect(qs).toBe(
      "?category=%E6%9C%8D%E9%A5%B0&keyword=T%E6%81%A4&page=1&page_size=20",
    );
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

describe("buildAssetSelectorQuery（v1.1 素材选择器：评估标签 + 相关性筛选）", () => {
  it("空筛选 → 仅分页参数", () => {
    expect(buildAssetSelectorQuery({ evaluation: "", relevanceStatus: "" }, 1, 10)).toBe(
      "?page=1&page_size=10",
    );
  });

  it("评估标签 + 相关性筛选", () => {
    expect(
      buildAssetSelectorQuery({ evaluation: "efficient", relevanceStatus: "passed" }, 2, 20),
    ).toBe("?relevance_status=passed&evaluation=efficient&page=2&page_size=20");
  });

  it("page 最小为 1", () => {
    expect(buildAssetSelectorQuery({ evaluation: "exploring", relevanceStatus: "" }, 0, 10)).toBe(
      "?evaluation=exploring&page=1&page_size=10",
    );
  });
});

describe("assetToMaterialId（素材选择器 → 后端 materials 端点接受的标识）", () => {
  it("优先 platform_material_id，缺失回落 String(id)", () => {
    expect(assetToMaterialId(makeAsset({ id: 5, platform_material_id: "mat-001" }))).toBe("mat-001");
    expect(assetToMaterialId(makeAsset({ id: 5, platform_material_id: null }))).toBe("5");
    expect(assetToMaterialId(makeAsset({ id: 5, platform_material_id: "" }))).toBe("5");
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
