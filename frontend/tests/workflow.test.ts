import { describe, expect, it } from "vitest";
import {
  canStartGeneration,
  canStartQuote,
  deriveWorkflowStage,
  isEliminated,
  LISTING_STATUSES,
  M5_CAMPAIGN_STATUSES,
  WORKFLOW_STAGES,
} from "../lib/workflow";

describe("M4 9 态 → 09 阶段（全部落阶段 6 待上架/已上架）", () => {
  it("9 态逐一映射 = 6", () => {
    const states = ["pending", "creating", "draft", "platform_auditing", "listed", "rejected", "retry_candidate", "manual", "failed"];
    expect(states).toHaveLength(LISTING_STATUSES.size);
    for (const status of states) {
      expect(deriveWorkflowStage({ listingStatus: status }), `listingStatus=${status}`).toBe(6);
    }
  });
});

describe("M5 托管状态 → 阶段 7", () => {
  it("5 态逐一映射 = 7", () => {
    const states = ["pending", "active", "paused", "not_eligible", "ended"];
    expect(states).toHaveLength(M5_CAMPAIGN_STATUSES.size);
    for (const status of states) {
      expect(deriveWorkflowStage({ campaignStatus: status }), `campaignStatus=${status}`).toBe(7);
    }
  });
});

describe("阶段推进（取最远已到达阶段）", () => {
  it("商品入池 → 1", () => {
    expect(deriveWorkflowStage({ productState: "pool" })).toBe(1);
    expect(deriveWorkflowStage({ complianceState: "candidate", productState: "pool" })).toBe(1);
  });

  it("素材放行/上传 → 2", () => {
    expect(deriveWorkflowStage({ relevanceStatus: "passed" })).toBe(2);
    expect(deriveWorkflowStage({ uploadStatus: "uploaded" })).toBe(2);
  });

  it("询价完成 → 3（覆盖素材 2）", () => {
    expect(deriveWorkflowStage({ hasQuotes: true, relevanceStatus: "passed" })).toBe(3);
  });

  it("已生图 → 4", () => {
    expect(deriveWorkflowStage({ hasGeneratedImages: true, hasQuotes: true })).toBe(4);
  });

  it("图片审核中/拒审 → 5", () => {
    expect(deriveWorkflowStage({ imageAuditStatus: "pending_audit", hasGeneratedImages: true })).toBe(5);
    expect(deriveWorkflowStage({ imageAuditStatus: "rejected", hasGeneratedImages: true })).toBe(5);
  });

  it("图片审核通过 → 6", () => {
    expect(deriveWorkflowStage({ imageAuditStatus: "approved", hasGeneratedImages: true })).toBe(6);
  });

  it("已上架 + 无托管 → 6；有托管 → 7", () => {
    expect(deriveWorkflowStage({ listingStatus: "listed" })).toBe(6);
    expect(deriveWorkflowStage({ listingStatus: "listed", campaignStatus: "active" })).toBe(7);
  });

  it("空输入 → 1", () => {
    expect(deriveWorkflowStage({})).toBe(1);
  });
});

describe("isEliminated 淘汰判定", () => {
  it("compliance hard_reject / products.state rejected / relevance failed / upload disabled", () => {
    expect(isEliminated({ complianceState: "hard_reject" })).toBe(true);
    expect(isEliminated({ productState: "rejected" })).toBe(true);
    expect(isEliminated({ relevanceStatus: "failed" })).toBe(true);
    expect(isEliminated({ uploadStatus: "disabled" })).toBe(true);
    expect(isEliminated({ productState: "pool", complianceState: "candidate" })).toBe(false);
  });
});

describe("canStartQuote / canStartGeneration", () => {
  it("池内无询价可询价；已询价/已淘汰不可", () => {
    expect(canStartQuote({ productState: "pool" })).toBe(true);
    expect(canStartQuote({ hasQuotes: true })).toBe(false);
    expect(canStartQuote({ complianceState: "hard_reject" })).toBe(false);
    expect(canStartQuote({ listingStatus: "pending" })).toBe(false);
  });

  it("询价完成可生图；未询价/已生图/已上架不可", () => {
    expect(canStartGeneration({ hasQuotes: true })).toBe(true);
    expect(canStartGeneration({ hasQuotes: false })).toBe(false);
    expect(canStartGeneration({ hasQuotes: true, hasGeneratedImages: true })).toBe(false);
    expect(canStartGeneration({ hasQuotes: true, listingStatus: "creating" })).toBe(false);
  });
});

describe("阶段条常量", () => {
  it("7 阶段（1 已选品 … 7 托管投放）", () => {
    expect(WORKFLOW_STAGES).toHaveLength(7);
    expect(WORKFLOW_STAGES[0]).toEqual({ id: 1, label: "已选品" });
    expect(WORKFLOW_STAGES[6]).toEqual({ id: 7, label: "托管投放" });
  });
});
