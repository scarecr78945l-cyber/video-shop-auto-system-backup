/**
 * 鉴权辅助：登录 / 登出 / 当前用户 / 路由守卫辅助（R-API-04）
 *
 * 鉴权模型：httpOnly + SameSite=Lax 会话 cookie（浏览器自动携带），
 * 前端不存任何 token/密码；401 由 lib/api.ts 全局拦截跳 /login。
 */

import { apiGet, apiPost, AuthError, type CurrentUser } from "./api";

export type { CurrentUser } from "./api";

/** 登录：POST /api/auth/login（成功由后端 Set-Cookie httpOnly 会话；前端不落凭证）。 */
export async function login(username: string, password: string): Promise<CurrentUser> {
  return apiPost<CurrentUser>("/api/auth/login", { username, password });
}

/** 登出：POST /api/auth/logout（失效会话并清 cookie）。失败不抛——登出本地状态同样清除。 */
export async function logout(): Promise<void> {
  try {
    await apiPost<unknown>("/api/auth/logout");
  } catch {
    // 会话已失效/网络异常均视为登出完成（R-API-04：前端状态必须清）
  }
}

/**
 * 当前用户（路由守卫用）：GET /api/auth/me。
 * 未登录（AuthError）→ null（401 全局拦截已负责跳转）；其他错误上抛。
 */
export async function getCurrentUser(): Promise<CurrentUser | null> {
  try {
    return await apiGet<CurrentUser>("/api/auth/me");
  } catch (error) {
    if (error instanceof AuthError) return null;
    throw error;
  }
}

/** 路由守卫辅助：未登录返回 null 时由调用方（工作台布局）重定向 /login。 */
export function isLoggedIn(user: CurrentUser | null): boolean {
  return user !== null && user.username.length > 0;
}
