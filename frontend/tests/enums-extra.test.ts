import { describe, expect, it } from "vitest";
import {
  ADS_ACCOUNT_STATUS_LABELS,
  ASSET_COMPLIANCE_LABELS,
  ASSET_TYPE_LABELS,
  enumLabel,
  EVALUATION_LABELS,
  JOB_STAGE_LABELS,
  JOB_STATUS_LABELS,
  LISTING_OP_LOG_DIRECTION_LABELS,
  OPT_BATCH_STATUS_LABELS,
  OPT_IMAGE_REVIEW_STATUS_LABELS,
  OPT_IMAGE_TYPE_LABELS,
  OPT_QUALITY_LABELS,
  OPT_REVIEW_GATE_LABELS,
  OPT_REVIEW_RESULT_LABELS,
  RELEVANCE_STATUS_LABELS,
  SCORE_DIM_LABELS,
  SCORE_DIM_ORDER,
  UPLOAD_RECORD_STATUS_LABELS,
  UPLOAD_STATUS_LABELS,
} from "../lib/enums";

describe("v0.4 批次1 新增映射表", () => {
  it("JOB_STAGE_LABELS：workflow_jobs.stage 7 态（STAGE_VALUES）", () => {
    expect(JOB_STAGE_LABELS).toEqual({
      source_collect: "选品采集",
      alibaba_quote: "1688询价",
      taobao_reference: "淘宝素材",
      image_generation: "生图",
      listing_upload: "上架",
      shop_ads_run: "托管投放执行",
      shop_ads_report: "投放报表回读",
    });
    expect(Object.keys(JOB_STAGE_LABELS)).toHaveLength(7);
  });

  it("JOB_STATUS_LABELS：workflow_jobs.status 8 态（JOB_STATUSES）", () => {
    expect(JOB_STATUS_LABELS).toEqual({
      pending: "待执行",
      running: "执行中",
      waiting_login: "等待登录",
      waiting_verification: "等待验证码",
      blocked: "阻塞",
      success: "成功",
      failed: "失败",
      cancelled: "已取消",
    });
    expect(Object.keys(JOB_STATUS_LABELS)).toHaveLength(8);
  });

  it("ADS_ACCOUNT_STATUS_LABELS：M5 账户状态（含 unknown 兜底）", () => {
    expect(enumLabel(ADS_ACCOUNT_STATUS_LABELS, "active")).toBe("正常");
    expect(enumLabel(ADS_ACCOUNT_STATUS_LABELS, "risk_control")).toBe("风控中");
    expect(enumLabel(ADS_ACCOUNT_STATUS_LABELS, "unknown")).toBe("未知");
    expect(enumLabel(ADS_ACCOUNT_STATUS_LABELS, "paused")).toBe("已暂停");
  });

  it("ASSET_TYPE_LABELS：video/image", () => {
    expect(ASSET_TYPE_LABELS.video).toBe("视频");
    expect(ASSET_TYPE_LABELS.image).toBe("图片");
  });

  it("ASSET_COMPLIANCE_LABELS：pending/passed/rejected", () => {
    expect(ASSET_COMPLIANCE_LABELS.pending).toBe("待判定");
    expect(ASSET_COMPLIANCE_LABELS.passed).toBe("已通过");
    expect(ASSET_COMPLIANCE_LABELS.rejected).toBe("已驳回");
  });

  it("UPLOAD_RECORD_STATUS_LABELS：上传台账四态（与 upload_status 不同枚举）", () => {
    expect(UPLOAD_RECORD_STATUS_LABELS).toEqual({
      pending: "待上传",
      success: "已上传",
      failed: "失败",
      disabled: "拒审下架",
    });
  });

  it("SCORE_DIM_LABELS：五维（sourcing/scoring.py DIM_LABELS 同源）", () => {
    expect(SCORE_DIM_LABELS).toEqual({
      trend: "热度趋势",
      profit: "利润率",
      after_sale: "售后风险",
      supply: "供给稳定",
      ad_conversion: "投放转化",
    });
    expect(SCORE_DIM_ORDER).toEqual(["trend", "profit", "after_sale", "supply", "ad_conversion"]);
  });

  it("M2 三表复用一致性：relevance/upload/evaluation 翻译仍可用", () => {
    expect(enumLabel(RELEVANCE_STATUS_LABELS, "manual_review")).toBe("待人工确认目标款");
    expect(enumLabel(UPLOAD_STATUS_LABELS, "disabled")).toBe("拒审下架");
    expect(enumLabel(EVALUATION_LABELS, "potential")).toBe("潜力");
  });

  it("未知值原样透传（便于排障，不吞值）", () => {
    expect(enumLabel(JOB_STATUS_LABELS, "unknown_status")).toBe("unknown_status");
  });

  it("LISTING_OP_LOG_DIRECTION_LABELS：M4 操作日志方向（request/response/transition）", () => {
    expect(LISTING_OP_LOG_DIRECTION_LABELS).toEqual({
      request: "请求",
      response: "响应",
      transition: "状态迁移",
    });
    expect(enumLabel(LISTING_OP_LOG_DIRECTION_LABELS, "transition")).toBe("状态迁移");
    expect(enumLabel(LISTING_OP_LOG_DIRECTION_LABELS, null)).toBe("—");
  });
});

describe("v0.6 批次3 新增映射表（M3 生图批次 / 图片审核 / 审核记录）", () => {
  it("OPT_IMAGE_TYPE_LABELS：main/detail", () => {
    expect(OPT_IMAGE_TYPE_LABELS).toEqual({ main: "主图", detail: "详情图" });
    expect(enumLabel(OPT_IMAGE_TYPE_LABELS, "main")).toBe("主图");
    expect(enumLabel(OPT_IMAGE_TYPE_LABELS, "detail")).toBe("详情图");
  });

  it("OPT_BATCH_STATUS_LABELS：generating/pending/reviewed/approved", () => {
    expect(OPT_BATCH_STATUS_LABELS).toEqual({
      generating: "生成中",
      pending: "待审核",
      reviewed: "已审核",
      approved: "已通过",
    });
    expect(enumLabel(OPT_BATCH_STATUS_LABELS, "pending")).toBe("待审核");
    expect(enumLabel(OPT_BATCH_STATUS_LABELS, "unknown_status")).toBe("unknown_status");
  });

  it("OPT_IMAGE_REVIEW_STATUS_LABELS：pending/approved/rejected", () => {
    expect(OPT_IMAGE_REVIEW_STATUS_LABELS).toEqual({
      pending: "待审核",
      approved: "已通过",
      rejected: "已驳回",
    });
    expect(enumLabel(OPT_IMAGE_REVIEW_STATUS_LABELS, "rejected")).toBe("已驳回");
  });

  it("OPT_REVIEW_GATE_LABELS：rule/evaluate/manual/relevance", () => {
    expect(OPT_REVIEW_GATE_LABELS).toEqual({
      rule: "规则预审",
      evaluate: "素材评估",
      manual: "人工复核",
      relevance: "相关性门",
    });
    expect(enumLabel(OPT_REVIEW_GATE_LABELS, "manual")).toBe("人工复核");
  });

  it("OPT_REVIEW_RESULT_LABELS：pass/reject/manual_review", () => {
    expect(OPT_REVIEW_RESULT_LABELS).toEqual({
      pass: "通过",
      reject: "驳回",
      manual_review: "待人工复核",
    });
    expect(enumLabel(OPT_REVIEW_RESULT_LABELS, "pass")).toBe("通过");
    expect(enumLabel(OPT_REVIEW_RESULT_LABELS, null)).toBe("—");
  });

  it("OPT_QUALITY_LABELS：quality_ok 布尔经 String() 翻译", () => {
    expect(enumLabel(OPT_QUALITY_LABELS, String(true))).toBe("质检合格");
    expect(enumLabel(OPT_QUALITY_LABELS, String(false))).toBe("质检不合格");
  });
});
