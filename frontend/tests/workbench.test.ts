import { describe, expect, it } from "vitest";
import type { WorkbenchException, WorkbenchGates, WorkbenchRetryBatchItem } from "../lib/api";
import {
  buildBatchRetryBody,
  buildExceptionsQuery,
  buildReviewProductsQuery,
  complianceReasonsSummary,
  evidenceSummary,
  exceptionGroups,
  GATE_DEFS,
  gateCount,
  retryConfirmText,
  sumBatchRetryResults,
  totalGateCount,
} from "../lib/workbench";

function makeGates(partial: Partial<WorkbenchGates["counts"]> = {}): WorkbenchGates {
  return {
    total: 0,
    counts: {
      sourcing_review: 0,
      listing_confirm: 0,
      image_review: 0,
      material_pre_review: 0,
      verification_takeover: 0,
      login_takeover: 0,
      ...partial,
    },
    generated_at: "2026-08-29T08:00:00Z",
  };
}

function makeException(partial: Partial<WorkbenchException>): WorkbenchException {
  return {
    id: 1,
    product_id: 101,
    stage: "listing_upload",
    status: "blocked",
    error_code: null,
    updated_at: "2026-08-29T08:00:00Z",
    ...partial,
  };
}

describe("GATE_DEFS（闸门卡片定义）", () => {
  it("6 类闸门齐全且 key 唯一", () => {
    expect(GATE_DEFS.length).toBe(6);
    expect(new Set(GATE_DEFS.map((d) => d.key)).size).toBe(6);
  });

  it("每个定义有 label/href/hint 且跳转目标符合任务书", () => {
    for (const def of GATE_DEFS) {
      expect(def.label.length).toBeGreaterThan(0);
      expect(def.href.startsWith("/")).toBe(true);
      expect(def.hint.length).toBeGreaterThan(0);
    }
    const hrefByKey = Object.fromEntries(GATE_DEFS.map((d) => [d.key, d.href]));
    expect(hrefByKey.sourcing_review).toContain("state=manual_review");
    expect(hrefByKey.listing_confirm).toContain("status=pending");
    expect(hrefByKey.image_review).toContain("tab=image");
    expect(hrefByKey.material_pre_review).toContain("tab=material");
    expect(hrefByKey.verification_takeover).toContain("status=waiting_verification");
    expect(hrefByKey.login_takeover).toContain("status=waiting_login");
  });
});

describe("gateCount / totalGateCount", () => {
  it("正常计数透传", () => {
    const gates = makeGates({ sourcing_review: 3, verification_takeover: 2 });
    expect(gateCount(gates, "sourcing_review")).toBe(3);
    expect(gateCount(gates, "verification_takeover")).toBe(2);
    expect(gateCount(gates, "login_takeover")).toBe(0);
  });

  it("null/undefined 安全 → 0", () => {
    expect(gateCount(null, "image_review")).toBe(0);
    expect(gateCount(undefined, "image_review")).toBe(0);
    expect(totalGateCount(null)).toBe(0);
  });

  it("totalGateCount = 六类求和", () => {
    const gates = makeGates({
      sourcing_review: 1,
      listing_confirm: 2,
      image_review: 3,
      material_pre_review: 4,
      verification_takeover: 5,
      login_takeover: 6,
    });
    expect(totalGateCount(gates)).toBe(21);
  });

  it("缺失 counts 安全 → 0", () => {
    expect(totalGateCount({ total: 0, counts: {} as never, generated_at: "" })).toBe(0);
  });
});

describe("exceptionGroups（按 error_code 分组计数）", () => {
  it("error_code 分组 + 中文标签 + 降序", () => {
    const items = [
      makeException({ error_code: "VERIFICATION_REQUIRED" }),
      makeException({ error_code: "VERIFICATION_REQUIRED" }),
      makeException({ error_code: "VERIFICATION_REQUIRED" }),
      makeException({ error_code: "AUTH_REQUIRED" }),
      makeException({ error_code: "UNEXPECTED" }),
    ];
    const { total, groups } = exceptionGroups(items);
    expect(total).toBe(5);
    expect(groups[0]).toEqual({ errorCode: "VERIFICATION_REQUIRED", label: "验证码/安全验证", count: 3 });
    expect(groups.map((g) => g.label)).toEqual(["验证码/安全验证", "登录失效", "未知"]);
  });

  it("error_code 为空的 blocked 任务按 status 标签兜底（阻塞）", () => {
    const items = [makeException({ status: "blocked", error_code: null })];
    const { groups } = exceptionGroups(items);
    expect(groups).toEqual([{ errorCode: null, label: "阻塞", count: 1 }]);
  });

  it("完全未知 status+error_code → 未分类", () => {
    const items = [makeException({ status: "weird", error_code: null })];
    const { groups } = exceptionGroups(items);
    expect(groups).toEqual([{ errorCode: null, label: "未分类", count: 1 }]);
  });

  it("空数组 → total 0 / groups []", () => {
    expect(exceptionGroups([])).toEqual({ total: 0, groups: [] });
  });
});

describe("retryConfirmText（人工接管二次确认文案）", () => {
  it("按 status 区分三类", () => {
    expect(retryConfirmText("waiting_verification", "VERIFICATION_REQUIRED")).toBe("确认验证码已通过，恢复执行");
    expect(retryConfirmText("waiting_login", "AUTH_REQUIRED")).toBe("确认已重新登录，从断点续跑");
    expect(retryConfirmText("blocked", "UNEXPECTED")).toBe("确认问题已解决，重试");
  });

  it("未知 status 按 error_code 兜底", () => {
    expect(retryConfirmText("weird", "VERIFICATION_REQUIRED")).toBe("确认验证码已通过，恢复执行");
    expect(retryConfirmText("weird", "AUTH_REQUIRED")).toBe("确认已重新登录，从断点续跑");
  });

  it("完全未知 → 通用文案", () => {
    expect(retryConfirmText(null, null)).toBe("确认已处理，恢复执行");
    expect(retryConfirmText("weird", "UNEXPECTED")).toBe("确认已处理，恢复执行");
  });
});

describe("evidenceSummary（脱敏摘要截断）", () => {
  it("非空对象 → JSON 摘要；超长截断带省略号", () => {
    const summary = evidenceSummary({ code: "VERIFICATION_REQUIRED", step: "wechat_login" }, 30);
    expect(summary.endsWith("…")).toBe(true);
    expect(summary.length).toBeLessThanOrEqual(31);
    expect(evidenceSummary({ step: "ok" })).toBe('{"step":"ok"}');
  });

  it("空对象/空数组/缺失 → —", () => {
    expect(evidenceSummary({})).toBe("—");
    expect(evidenceSummary(null)).toBe("—");
    expect(evidenceSummary(undefined)).toBe("—");
  });
});

describe("complianceReasonsSummary（选品复核合规摘要）", () => {
  it("字符串数组合并", () => {
    expect(complianceReasonsSummary(["品牌风险", "商标近似"])).toBe("品牌风险；商标近似");
  });

  it("过滤空串 / 非数组 / 空 → —", () => {
    expect(complianceReasonsSummary(["a", " ", ""])).toBe("a");
    expect(complianceReasonsSummary([])).toBe("—");
    expect(complianceReasonsSummary("not-array")).toBe("—");
    expect(complianceReasonsSummary(undefined)).toBe("—");
  });

  it("超长截断带省略号", () => {
    const long = Array.from({ length: 20 }, (_, i) => `理由${i}号很长很长很长很长很长`);
    const summary = complianceReasonsSummary(long, 50);
    expect(summary.endsWith("…")).toBe(true);
    expect(summary.length).toBeLessThanOrEqual(51);
  });
});

describe("查询串构建", () => {
  it("buildReviewProductsQuery：state=manual_review + page/page_size 分页（v1.1 迁移）", () => {
    expect(buildReviewProductsQuery(1, 20)).toBe("?state=manual_review&page=1&page_size=20");
    expect(buildReviewProductsQuery(2, 50)).toBe("?state=manual_review&page=2&page_size=50");
  });

  it("buildReviewProductsQuery：page 最小 1 / pageSize 夹取 1..100（不含 limit/offset）", () => {
    expect(buildReviewProductsQuery(0, 20)).toBe("?state=manual_review&page=1&page_size=20");
    expect(buildReviewProductsQuery(1, 999)).toBe("?state=manual_review&page=1&page_size=100");
    expect(buildReviewProductsQuery(3, 20)).not.toContain("limit");
    expect(buildReviewProductsQuery(3, 20)).not.toContain("offset");
  });

  it("buildExceptionsQuery：空 status → 仅分页参数（v1.1 limit 迁移为 page/page_size）", () => {
    expect(buildExceptionsQuery("", 1)).toBe("?page=1&page_size=20");
  });

  it("buildExceptionsQuery：status 过滤 + page/page_size 夹取 1..100", () => {
    expect(buildExceptionsQuery("blocked", 2, 50)).toBe("?status=blocked&page=2&page_size=50");
    expect(buildExceptionsQuery("waiting_login", 3, 999)).toBe(
      "?status=waiting_login&page=3&page_size=100",
    );
    expect(buildExceptionsQuery("", 0, 20)).toBe("?page=1&page_size=20");
    expect(buildExceptionsQuery("blocked", 1, 20)).not.toContain("limit");
  });
});

describe("buildBatchRetryBody（POST /api/workbench/retry-batch body）", () => {
  it("正常 id 列表透传", () => {
    expect(buildBatchRetryBody([1, 2, 3])).toEqual({ job_ids: [1, 2, 3] });
  });

  it("去空去重 + 过滤非法（0/负数/NaN/Infinity）", () => {
    expect(buildBatchRetryBody([1, 1, 2, 0, -3, Number.NaN, Number.POSITIVE_INFINITY])).toEqual({
      job_ids: [1, 2],
    });
  });

  it("空数组 → {job_ids: []}（后端 422，前端按钮已禁用兜底）", () => {
    expect(buildBatchRetryBody([])).toEqual({ job_ids: [] });
  });
});

describe("sumBatchRetryResults（批量接管结果汇总）", () => {
  function item(partial: Partial<WorkbenchRetryBatchItem>): WorkbenchRetryBatchItem {
    return { job_id: 1, ok: true, ...partial };
  }

  it("全成功 → ok=N / failed=0", () => {
    const results = [item({ job_id: 1 }), item({ job_id: 2 })];
    expect(sumBatchRetryResults(results)).toEqual({ ok: 2, failed: 0, failedItems: [] });
  });

  it("部分失败 → 失败明细含 error.message（缺失回退 code/未知）", () => {
    const results = [
      item({ job_id: 1 }),
      item({ job_id: 2, ok: false, error: { code: "INVALID_STATE", message: "状态冲突" } }),
      item({ job_id: 3, ok: false, error: { code: "UNEXPECTED", message: "" } }),
      item({ job_id: 4, ok: false }),
    ];
    expect(sumBatchRetryResults(results)).toEqual({
      ok: 1,
      failed: 3,
      failedItems: [
        { job_id: 2, message: "状态冲突" },
        { job_id: 3, message: "UNEXPECTED" },
        { job_id: 4, message: "未知错误" },
      ],
    });
  });

  it("空/undefined 结果 → 全 0", () => {
    expect(sumBatchRetryResults([])).toEqual({ ok: 0, failed: 0, failedItems: [] });
    expect(sumBatchRetryResults(undefined as unknown as WorkbenchRetryBatchItem[])).toEqual({
      ok: 0,
      failed: 0,
      failedItems: [],
    });
  });
});
