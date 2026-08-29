import { describe, expect, it } from "vitest";
import { formatBytes, formatDuration, formatPercent } from "../lib/format";

describe("formatDuration（素材时长：秒 → 中文可读）", () => {
  it("小于 60 秒 → X秒", () => {
    expect(formatDuration(0)).toBe("0秒");
    expect(formatDuration(5)).toBe("5秒");
    expect(formatDuration(59)).toBe("59秒");
  });

  it("60 秒整 → X分钟", () => {
    expect(formatDuration(60)).toBe("1分钟");
    expect(formatDuration(120)).toBe("2分钟");
  });

  it("非整分 → X分Y秒", () => {
    expect(formatDuration(83)).toBe("1分23秒");
    expect(formatDuration(365)).toBe("6分5秒");
  });

  it("小时 → X小时X分（不足分钟省略秒）", () => {
    expect(formatDuration(3600)).toBe("1小时0分");
    expect(formatDuration(3661)).toBe("1小时1分1秒");
  });

  it("null / undefined / NaN / 负数 → —", () => {
    expect(formatDuration(null)).toBe("—");
    expect(formatDuration(undefined)).toBe("—");
    expect(formatDuration(Number.NaN)).toBe("—");
    expect(formatDuration(-1)).toBe("—");
  });
});

describe("formatBytes（素材大小：字节 → 可读单位）", () => {
  it("B 级", () => {
    expect(formatBytes(0)).toBe("0 B");
    expect(formatBytes(512)).toBe("512 B");
  });

  it("KB / MB / GB", () => {
    expect(formatBytes(1536)).toBe("1.5 KB");
    expect(formatBytes(1048576)).toBe("1.0 MB");
    expect(formatBytes(1024 * 1024 * 1024)).toBe("1.0 GB");
  });

  it("≥100 的数值省略小数位", () => {
    expect(formatBytes(1024 * 100)).toBe("100 KB");
  });

  it("null / undefined / NaN / 负数 → —", () => {
    expect(formatBytes(null)).toBe("—");
    expect(formatBytes(undefined)).toBe("—");
    expect(formatBytes(Number.NaN)).toBe("—");
    expect(formatBytes(-5)).toBe("—");
  });
});

describe("formatPercent（比率 → 百分比展示）", () => {
  it("0.5 → 50.0%", () => {
    expect(formatPercent(0.5)).toBe("50.0%");
  });

  it("0 → 0.0%", () => {
    expect(formatPercent(0)).toBe("0.0%");
  });

  it("null / undefined / NaN → —", () => {
    expect(formatPercent(null)).toBe("—");
    expect(formatPercent(undefined)).toBe("—");
    expect(formatPercent(Number.NaN)).toBe("—");
  });
});
