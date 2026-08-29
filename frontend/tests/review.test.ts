import { describe, expect, it } from "vitest";
import type { AssetSummary, OptimizationBatchDetail, OptimizationImage } from "../lib/api";
import {
  buildBatchQuery,
  buildPassedAssetQuery,
  buildPreReviewAssetQuery,
  canApproveBatch,
  countReviewStatus,
  filterAssetsByType,
  formatImageSpec,
  isManualReviewAsset,
  REJECTION_REASONS,
  relevanceConfirmLabel,
  reviewProgress,
} from "../lib/review";

function makeImage(partial: Partial<OptimizationImage>): OptimizationImage {
  return {
    image_id: "img-1",
    image_type: "main",
    variant_no: 1,
    file_path: "images/g1.png",
    phash: "",
    width: 800,
    height: 800,
    quality: null,
    quality_ok: true,
    review_status: "pending",
    reject_reason: "",
    category_memory_key: "",
    audit: [],
    created_at: null,
    updated_at: null,
    ...partial,
  };
}

function makeBatch(partial: Partial<OptimizationBatchDetail>): OptimizationBatchDetail {
  return {
    batch_id: "batch-001",
    product_id: "101",
    image_type: "main",
    plan: null,
    target_count: 5,
    gate: null,
    status: "pending",
    image_count: 2,
    created_at: null,
    updated_at: null,
    assets: [],
    ...partial,
  };
}

function makeAsset(partial: Partial<AssetSummary>): AssetSummary {
  return {
    id: 1,
    asset_type: "video",
    source_platform: "抖音",
    source_url: "",
    evaluation: null,
    upload_status: "local",
    relevance_status: "pending",
    ...partial,
  };
}

describe("buildBatchQuery（GET /api/optimization/batches）", () => {
  it("空筛选 → 仅分页参数", () => {
    expect(buildBatchQuery("", 1, 20)).toBe("?page=1&page_size=20");
  });

  it("status 过滤 + 分页", () => {
    expect(buildBatchQuery("pending", 2, 50)).toBe("?status=pending&page=2&page_size=50");
  });

  it("page 最小为 1", () => {
    expect(buildBatchQuery("approved", 0, 20)).toBe("?status=approved&page=1&page_size=20");
  });
});

describe("countReviewStatus / reviewProgress（批内统计）", () => {
  it("三态计数：pending/approved/rejected", () => {
    const assets = [
      makeImage({ review_status: "pending" }),
      makeImage({ review_status: "approved" }),
      makeImage({ review_status: "rejected" }),
      makeImage({ review_status: "approved" }),
    ];
    expect(countReviewStatus(assets)).toEqual({ total: 4, approved: 2, rejected: 1, pending: 1 });
  });

  it("未知状态归入 pending（防吞值）", () => {
    const assets = [makeImage({ review_status: "weird" })];
    expect(countReviewStatus(assets)).toEqual({ total: 1, approved: 0, rejected: 0, pending: 1 });
  });

  it("空数组 → 全 0", () => {
    expect(countReviewStatus([])).toEqual({ total: 0, approved: 0, rejected: 0, pending: 0 });
  });

  it("reviewProgress：已审（approved/rejected）/总数 百分比", () => {
    const assets = [
      makeImage({ review_status: "approved" }),
      makeImage({ review_status: "rejected" }),
      makeImage({ review_status: "pending" }),
      makeImage({ review_status: "pending" }),
    ];
    expect(reviewProgress(assets)).toEqual({ done: 2, total: 4, percent: 50 });
  });

  it("reviewProgress：空批 → 0/0/0", () => {
    expect(reviewProgress([])).toEqual({ done: 0, total: 0, percent: 0 });
  });
});

describe("canApproveBatch（整批通过可用性）", () => {
  it("null → 不可通过", () => {
    expect(canApproveBatch(null)).toBe(false);
  });

  it("待审核批次有图 → 可整批通过", () => {
    expect(canApproveBatch(makeBatch({ assets: [makeImage({})] }))).toBe(true);
  });

  it("已通过批次 → 不可（幂等，后端 already_approved 已视为成功）", () => {
    expect(canApproveBatch(makeBatch({ status: "approved", assets: [makeImage({})] }))).toBe(false);
  });

  it("空批 → 不可", () => {
    expect(canApproveBatch(makeBatch({ assets: [] }))).toBe(false);
  });
});

describe("filterAssetsByType / formatImageSpec", () => {
  it("按 main/detail 过滤（tab 切换）", () => {
    const assets = [
      makeImage({ image_id: "a", image_type: "main" }),
      makeImage({ image_id: "b", image_type: "detail" }),
      makeImage({ image_id: "c", image_type: "main" }),
    ];
    expect(filterAssetsByType(assets, "main").map((a) => a.image_id)).toEqual(["a", "c"]);
    expect(filterAssetsByType(assets, "detail").map((a) => a.image_id)).toEqual(["b"]);
  });

  it("formatImageSpec：宽×高 / 无尺寸 → —", () => {
    expect(formatImageSpec(makeImage({ width: 800, height: 1200 }))).toBe("800×1200");
    expect(formatImageSpec(makeImage({ width: 0, height: 0 }))).toBe("—");
  });
});

describe("素材相关性预审查询/判定", () => {
  it("buildPreReviewAssetQuery：固定 relevance_status=manual_review + 分页", () => {
    expect(buildPreReviewAssetQuery(1, 20)).toBe("?relevance_status=manual_review&page=1&page_size=20");
    expect(buildPreReviewAssetQuery(3, 50)).toBe("?relevance_status=manual_review&page=3&page_size=50");
  });

  it("buildPassedAssetQuery：relevance_status=passed（已放行列表）", () => {
    expect(buildPassedAssetQuery(1, 20)).toBe("?relevance_status=passed&page=1&page_size=20");
  });

  it("isManualReviewAsset：仅 manual_review 为待确认", () => {
    expect(isManualReviewAsset(makeAsset({ relevance_status: "manual_review" }))).toBe(true);
    expect(isManualReviewAsset(makeAsset({ relevance_status: "passed" }))).toBe(false);
    expect(isManualReviewAsset(makeAsset({ relevance_status: "pending" }))).toBe(false);
  });

  it("relevanceConfirmLabel：pass/reject/manual_review 中文 + 未知透传", () => {
    expect(relevanceConfirmLabel("pass")).toBe("确认目标款（放行）");
    expect(relevanceConfirmLabel("reject")).toBe("不相关（淘汰）");
    expect(relevanceConfirmLabel("manual_review")).toBe("继续人工复核");
    expect(relevanceConfirmLabel("unknown")).toBe("unknown");
  });
});

describe("驳回理由预置（对齐 10 文档第五节投放素材预审语义）", () => {
  it("6 项预置 + 去重 + 非空", () => {
    expect(REJECTION_REASONS.length).toBe(6);
    expect(new Set(REJECTION_REASONS).size).toBe(6);
    expect(REJECTION_REASONS).toContain("产品不一致");
    expect(REJECTION_REASONS).toContain("卖点不清晰");
    expect(REJECTION_REASONS.every((r) => r.trim().length > 0)).toBe(true);
  });
});
