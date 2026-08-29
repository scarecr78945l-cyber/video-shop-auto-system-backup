import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError, apiGet, apiPost, AuthError, setUnauthorizedHandler } from "../lib/api";

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

afterEach(() => {
  vi.unstubAllGlobals();
  setUnauthorizedHandler(null);
});

describe("apiGet 成功路径", () => {
  it("GET 携带 credentials=include / cache=no-store，解析 JSON 返回", async () => {
    const data = { total_jobs: 3, jobs_by_status: { running: 2 } };
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(data));
    vi.stubGlobal("fetch", fetchMock);

    const result = await apiGet<{ total_jobs: number }>("/api/overview");

    expect(result).toEqual(data);
    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("http://127.0.0.1:8000/api/overview");
    expect(init.credentials).toBe("include");
    expect(init.cache).toBe("no-store");
  });
});

describe("apiPost 成功路径", () => {
  it("POST 携带 JSON body 与 Content-Type", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ username: "admin", role: "admin" }));
    vi.stubGlobal("fetch", fetchMock);

    const result = await apiPost<{ username: string }>("/api/auth/login", { username: "admin", password: "x" });

    expect(result.username).toBe("admin");
    const [, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(init.method).toBe("POST");
    expect((init.headers as Record<string, string>)["Content-Type"]).toBe("application/json");
    expect(JSON.parse(init.body as string)).toEqual({ username: "admin", password: "x" });
  });
});

describe("401 → AuthError + 全局跳登录标记", () => {
  it("401 抛 AuthError（code=AUTH_REQUIRED），message 透传", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(jsonResponse({ code: "AUTH_REQUIRED", message: "用户名或密码错误" }, 401)));

    const promise = apiGet<unknown>("/api/auth/me");
    await expect(promise).rejects.toBeInstanceOf(AuthError);
    await expect(promise).rejects.toMatchObject({ code: "AUTH_REQUIRED", status: 401 });
  });

  it("setUnauthorizedHandler 注册的处理器被调用（路由守卫/测试注入点）", async () => {
    const handler = vi.fn();
    setUnauthorizedHandler(handler);
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(jsonResponse({ message: "未登录" }, 401)));

    await expect(apiGet<unknown>("/api/jobs")).rejects.toBeInstanceOf(AuthError);
    expect(handler).toHaveBeenCalledTimes(1);
  });

  it("未注册 handler 且非浏览器环境时不抛 window 错误（默认仅跳转逻辑被守卫跳过）", async () => {
    // node 环境 typeof window === "undefined"：notifyUnauthorized 静默
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(jsonResponse({}, 401)));
    await expect(apiGet<unknown>("/api/jobs")).rejects.toBeInstanceOf(AuthError);
  });
});

describe("统一错误格式 {code, message, detail?}", () => {
  it("409 INVALID_STATE（D10）抛 ApiError 且字段完整", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(jsonResponse({ code: "INVALID_STATE", message: "状态冲突", detail: "仅 pending 可确认" }, 409)));

    const promise = apiPost<unknown>("/api/listing/tasks/t1/confirm");
    await expect(promise).rejects.toBeInstanceOf(ApiError);
    await expect(promise).rejects.toMatchObject({
      code: "INVALID_STATE",
      message: "状态冲突",
      detail: "仅 pending 可确认",
      status: 409,
    });
  });

  it("422 VALIDATION_ERROR（D10）code/message 透传", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(jsonResponse({ code: "VALIDATION_ERROR", message: "请求参数校验失败" }, 422)));

    const promise = apiGet<unknown>("/api/listing/tasks");
    await expect(promise).rejects.toMatchObject({ code: "VALIDATION_ERROR", message: "请求参数校验失败", status: 422 });
  });

  it("非 JSON 错误体（纯文本 500）兜底为 ApiError UNEXPECTED + HTTP 状态", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response("boom", { status: 500 })));

    const promise = apiGet<unknown>("/api/overview");
    await expect(promise).rejects.toMatchObject({ code: "UNEXPECTED", status: 500 });
  });
});

describe("网络层错误", () => {
  it("fetch 拒绝 → ApiError NETWORK_ERROR（可展示连接失败）", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("fetch failed")));

    const promise = apiGet<unknown>("/api/overview");
    await expect(promise).rejects.toBeInstanceOf(ApiError);
    await expect(promise).rejects.toMatchObject({ code: "NETWORK_ERROR", status: 0 });
  });
});

describe("204 / 空响应", () => {
  it("204 无内容返回 undefined 不抛错", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(null, { status: 204 })));
    await expect(apiPost<unknown>("/api/auth/logout")).resolves.toBeUndefined();
  });
});
