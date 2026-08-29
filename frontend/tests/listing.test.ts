import { describe, expect, it } from "vitest";
import type { ListingOpLog, ListingTask } from "../lib/api";
import {
  buildListingQuery,
  canConfirmTask,
  canRetryTask,
  extractListingTrajectory,
  filterTasksByKeyword,
  LISTING_BRANCH_FLOW,
  LISTING_MAIN_FLOW,
  LISTING_STATUSES_ORDERED,
  LISTING_TERMINAL_STATUSES,
  listingStatusCounts,
} from "../lib/listing";

function makeTask(partial: Partial<ListingTask>): ListingTask {
  return {
    task_id: "task-1",
    product_id: 1,
    status: "pending",
    title: null,
    attempts: 0,
    error_code: null,
    created_at: null,
    updated_at: null,
    ...partial,
  };
}

function makeLog(partial: Partial<ListingOpLog>): ListingOpLog {
  return {
    log_id: 1,
    request_id: "req",
    api: "state_machine",
    direction: "transition",
    payload_digest: "",
    status_code: null,
    error_code: null,
    platform_code: null,
    evidence: null,
    created_at: "2026-08-29T00:00:00Z",
    ...partial,
  };
}

describe("9 态状态机结构（对齐 state_machine.py ALLOWED_TRANSITIONS）", () => {
  it("LISTING_STATUSES_ORDERED 覆盖 9 态", () => {
    expect([...LISTING_STATUSES_ORDERED].sort()).toEqual(
      [
        "pending",
        "creating",
        "draft",
        "platform_auditing",
        "listed",
        "rejected",
        "retry_candidate",
        "manual",
        "failed",
      ].sort(),
    );
  });

  it("主链顺序 pending→creating→draft→platform_auditing→listed", () => {
    expect(LISTING_MAIN_FLOW).toEqual([
      "pending",
      "creating",
      "draft",
      "platform_auditing",
      "listed",
    ]);
  });

  it("分支：rejected→retry_candidate→creating（重提回主链）", () => {
    expect(LISTING_BRANCH_FLOW.map((b) => [b.from, b.to])).toEqual([
      ["rejected", "retry_candidate"],
      ["retry_candidate", "creating"],
    ]);
  });

  it("终态：manual / failed（listed 在主链末尾）", () => {
    expect([...LISTING_TERMINAL_STATUSES]).toEqual(["manual", "failed"]);
  });
});

describe("listingStatusCounts（状态机条计数）", () => {
  it("按状态计数", () => {
    const counts = listingStatusCounts([
      makeTask({ task_id: "a", status: "pending" }),
      makeTask({ task_id: "b", status: "pending" }),
      makeTask({ task_id: "c", status: "listed" }),
    ]);
    expect(counts).toEqual({ pending: 2, listed: 1 });
  });

  it("空列表 → {}", () => {
    expect(listingStatusCounts([])).toEqual({});
  });
});

describe("canConfirmTask / canRetryTask（人工操作可用性）", () => {
  it("仅 pending 可确认入队", () => {
    expect(canConfirmTask("pending")).toBe(true);
    expect(canConfirmTask("creating")).toBe(false);
    expect(canConfirmTask("listed")).toBe(false);
    expect(canConfirmTask(null)).toBe(false);
    expect(canConfirmTask(undefined)).toBe(false);
  });

  it("仅 rejected / retry_candidate 可重提", () => {
    expect(canRetryTask("rejected")).toBe(true);
    expect(canRetryTask("retry_candidate")).toBe(true);
    expect(canRetryTask("pending")).toBe(false);
    expect(canRetryTask("failed")).toBe(false);
    expect(canRetryTask(null)).toBe(false);
  });
});

describe("buildListingQuery（GET /api/listing/tasks）", () => {
  it("空筛选 → 仅分页参数", () => {
    expect(buildListingQuery("", 1, 20)).toBe("?page=1&page_size=20");
  });

  it("status 过滤 + 分页", () => {
    expect(buildListingQuery("pending", 2, 50)).toBe("?status=pending&page=2&page_size=50");
  });

  it("page 最小为 1", () => {
    expect(buildListingQuery("", 0, 20)).toBe("?page=1&page_size=20");
  });
});

describe("filterTasksByKeyword（客户端关键词）", () => {
  const items = [
    makeTask({ task_id: "TASK-100", product_id: 101, title: "夏季防晒衣" }),
    makeTask({ task_id: "task-200", product_id: 202, title: null }),
    makeTask({ task_id: "task-300", product_id: 303, title: "儿童防晒帽" }),
  ];

  it("命中 task_id（大小写不敏感）", () => {
    expect(filterTasksByKeyword(items, "task-100").map((t) => t.task_id)).toEqual(["TASK-100"]);
    expect(filterTasksByKeyword(items, "task-100").map((t) => t.task_id)).toEqual(["TASK-100"]);
  });

  it("命中 product_id 字符串", () => {
    expect(filterTasksByKeyword(items, "202").map((t) => t.product_id)).toEqual([202]);
  });

  it("命中 title（可空字段容错）", () => {
    expect(filterTasksByKeyword(items, "防晒").map((t) => t.task_id)).toEqual(["TASK-100", "task-300"]);
  });

  it("空/空白关键词 → 原样返回", () => {
    expect(filterTasksByKeyword(items, "")).toEqual(items);
    expect(filterTasksByKeyword(items, "   ")).toEqual(items);
  });

  it("无命中 → []", () => {
    expect(filterTasksByKeyword(items, "不存在")).toEqual([]);
  });
});

describe("extractListingTrajectory（从操作日志提取状态迁移）", () => {
  it("仅取 direction=transition 且 evidence{from,to}", () => {
    const logs = [
      makeLog({
        log_id: 1,
        direction: "request",
        api: "create_product",
        evidence: { from: "x", to: "y" },
      }),
      makeLog({
        log_id: 2,
        direction: "transition",
        evidence: { from: "pending", to: "creating", at: "t" },
      }),
      makeLog({ log_id: 3, direction: "transition", evidence: { from: "creating" } }), // 缺 to，跳过
      makeLog({ log_id: 4, direction: "transition", evidence: "not-an-object" }), // 非法，跳过
      makeLog({
        log_id: 5,
        direction: "transition",
        evidence: { from: "draft", to: "platform_auditing" },
      }),
    ];
    expect(extractListingTrajectory(logs)).toEqual([
      { from: "pending", to: "creating", at: "2026-08-29T00:00:00Z" },
      { from: "draft", to: "platform_auditing", at: "2026-08-29T00:00:00Z" },
    ]);
  });

  it("空日志 → []", () => {
    expect(extractListingTrajectory([])).toEqual([]);
  });
});
