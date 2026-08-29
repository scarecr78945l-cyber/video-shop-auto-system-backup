import { afterEach, describe, expect, it, vi } from "vitest";
import { isMockMode } from "../lib/env";

describe("isMockMode（NEXT_PUBLIC_USE_MOCK 保留位）", () => {
  const original = process.env.NEXT_PUBLIC_USE_MOCK;

  afterEach(() => {
    if (original === undefined) delete process.env.NEXT_PUBLIC_USE_MOCK;
    else process.env.NEXT_PUBLIC_USE_MOCK = original;
    vi.restoreAllMocks();
  });

  it("未设置 / 0 / 空串 → false（默认直连真实 API）", () => {
    delete process.env.NEXT_PUBLIC_USE_MOCK;
    expect(isMockMode()).toBe(false);
    process.env.NEXT_PUBLIC_USE_MOCK = "0";
    expect(isMockMode()).toBe(false);
    process.env.NEXT_PUBLIC_USE_MOCK = "";
    expect(isMockMode()).toBe(false);
  });

  it("1 / true → true", () => {
    process.env.NEXT_PUBLIC_USE_MOCK = "1";
    expect(isMockMode()).toBe(true);
    process.env.NEXT_PUBLIC_USE_MOCK = "true";
    expect(isMockMode()).toBe(true);
  });
});
