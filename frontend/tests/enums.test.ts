import { describe, expect, it } from "vitest";
import {
  COMPLIANCE_LABELS,
  enumLabel,
  ERROR_CODE_LABELS,
  errorCodeLabel,
  EVALUATION_LABELS,
  LISTING_STATUS_LABELS,
  M5_DIAGNOSIS_LABELS,
  M5_STATUS_LABELS,
  M5_TARGET_TYPE_LABELS,
  PRODUCT_STATE_LABELS,
  RELEVANCE_STATUS_LABELS,
  UPLOAD_STATUS_LABELS,
  workflowStageLabel,
  WORKFLOW_STAGES,
} from "../lib/enums";

describe("error_code（DA-008 7 码 + D10 局部 2 码）", () => {
  it("7 业务码映射", () => {
    expect(ERROR_CODE_LABELS.VERIFICATION_REQUIRED).toBe("验证码/安全验证");
    expect(ERROR_CODE_LABELS.AUTH_REQUIRED).toBe("登录失效");
    expect(ERROR_CODE_LABELS.RATE_LIMIT).toBe("限流");
    expect(ERROR_CODE_LABELS.TIMEOUT).toBe("超时");
    expect(ERROR_CODE_LABELS.NO_MATCH).toBe("无匹配");
    expect(ERROR_CODE_LABELS.PLATFORM_REJECT).toBe("平台驳回");
    expect(ERROR_CODE_LABELS.UNEXPECTED).toBe("未知");
  });

  it("D10 API 局部码：VALIDATION_ERROR / INVALID_STATE", () => {
    expect(ERROR_CODE_LABELS.VALIDATION_ERROR).toBe("请求参数校验失败");
    expect(ERROR_CODE_LABELS.INVALID_STATE).toBe("状态冲突");
    expect(errorCodeLabel("INVALID_STATE")).toBe("状态冲突");
  });
});

describe("M4 上架状态机 9 态", () => {
  it("9 态全部映射", () => {
    expect(LISTING_STATUS_LABELS).toEqual({
      pending: "待上架",
      creating: "创建中",
      draft: "草稿",
      platform_auditing: "平台审核中",
      listed: "已上架",
      rejected: "审核驳回",
      retry_candidate: "待重提",
      manual: "人工处理",
      failed: "失败",
    });
    expect(Object.keys(LISTING_STATUS_LABELS)).toHaveLength(9);
  });
});

describe("M1 / M2 枚举", () => {
  it("compliance 三态", () => {
    expect(COMPLIANCE_LABELS.hard_reject).toBe("已淘汰");
    expect(COMPLIANCE_LABELS.candidate).toBe("候选");
    expect(COMPLIANCE_LABELS.manual_review).toBe("待人工复核");
  });

  it("products.state 三态", () => {
    expect(PRODUCT_STATE_LABELS.pool).toBe("商品池");
    expect(PRODUCT_STATE_LABELS.manual_review).toBe("待人工复核");
    expect(PRODUCT_STATE_LABELS.rejected).toBe("已淘汰");
  });

  it("relevance_status 四态", () => {
    expect(RELEVANCE_STATUS_LABELS.pending).toBe("待判定");
    expect(RELEVANCE_STATUS_LABELS.passed).toBe("相关放行");
    expect(RELEVANCE_STATUS_LABELS.failed).toBe("不相关淘汰");
    expect(RELEVANCE_STATUS_LABELS.manual_review).toBe("待人工确认目标款");
  });

  it("upload_status 五态", () => {
    expect(UPLOAD_STATUS_LABELS.local).toBe("本地");
    expect(UPLOAD_STATUS_LABELS.uploading).toBe("上传中");
    expect(UPLOAD_STATUS_LABELS.uploaded).toBe("已上传");
    expect(UPLOAD_STATUS_LABELS.failed).toBe("失败");
    expect(UPLOAD_STATUS_LABELS.disabled).toBe("拒审下架");
  });

  it("evaluation 三态（M2/M3/M5 共口径）", () => {
    expect(EVALUATION_LABELS.exploring).toBe("探索期");
    expect(EVALUATION_LABELS.efficient).toBe("高效");
    expect(EVALUATION_LABELS.potential).toBe("潜力");
  });
});

describe("M5 英文枚举（D5：代码实测英文原值，前端翻译）", () => {
  it("status 五态", () => {
    expect(M5_STATUS_LABELS).toEqual({
      pending: "待托管",
      active: "托管中",
      paused: "已暂停",
      not_eligible: "不可投放",
      ended: "已结束",
    });
  });

  it("diagnosis 四态", () => {
    expect(M5_DIAGNOSIS_LABELS.excellent).toBe("优秀");
    expect(M5_DIAGNOSIS_LABELS.good).toBe("良好");
    expect(M5_DIAGNOSIS_LABELS.optimize_1).toBe("1项待优化");
    expect(M5_DIAGNOSIS_LABELS.optimize_n).toBe("N项待优化");
  });

  it("target_type 三态", () => {
    expect(M5_TARGET_TYPE_LABELS.roi).toBe("成交ROI");
    expect(M5_TARGET_TYPE_LABELS.net_roi).toBe("净成交ROI");
    expect(M5_TARGET_TYPE_LABELS.goods).toBe("商品成交");
  });
});

describe("enumLabel 通用翻译", () => {
  it("命中返回中文", () => {
    expect(enumLabel(LISTING_STATUS_LABELS, "listed")).toBe("已上架");
  });

  it("null / undefined / 空串 → 默认 —", () => {
    expect(enumLabel(LISTING_STATUS_LABELS, null)).toBe("—");
    expect(enumLabel(LISTING_STATUS_LABELS, undefined)).toBe("—");
    expect(enumLabel(LISTING_STATUS_LABELS, "")).toBe("—");
  });

  it("未知值原样透传（便于排障）", () => {
    expect(enumLabel(LISTING_STATUS_LABELS, "future_state")).toBe("future_state");
  });
});

describe("09 前端状态机阶段条", () => {
  it("7 阶段顺序", () => {
    expect(WORKFLOW_STAGES.map((s) => s.label)).toEqual([
      "已选品",
      "淘宝素材",
      "询价",
      "生图",
      "图片审核",
      "待上架/已上架",
      "托管投放",
    ]);
  });

  it("workflowStageLabel 1..7 / 越界 / null", () => {
    expect(workflowStageLabel(1)).toBe("已选品");
    expect(workflowStageLabel(6)).toBe("待上架/已上架");
    expect(workflowStageLabel(7)).toBe("托管投放");
    expect(workflowStageLabel(8)).toBe("—");
    expect(workflowStageLabel(null)).toBe("—");
  });
});
