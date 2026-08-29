/**
 * 登录表单（客户端）：POST /api/auth/login → 成功由后端设 httpOnly 会话 cookie →
 * 跳转工作台。密码输入 type=password（不展示明文）；错误仅展示 ApiError.message。
 */
"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Sparkles } from "lucide-react";
import { getCurrentUser, login } from "@/lib/auth";
import { ApiError } from "@/lib/api";

export function LoginForm() {
  const router = useRouter();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  // 已登录用户访问登录页 → 直接回工作台（R-API-04：守卫统一走 /api/auth/me）
  useEffect(() => {
    let cancelled = false;
    getCurrentUser()
      .then((user) => {
        if (!cancelled && user) router.replace("/");
      })
      .catch(() => {
        /* 网络异常留在登录页 */
      });
    return () => {
      cancelled = true;
    };
  }, [router]);

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!username.trim() || !password) {
      setError("请输入用户名和密码");
      return;
    }
    setLoading(true);
    setError(null);
    try {
      await login(username.trim(), password);
      router.replace("/");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "登录失败，请稍后重试");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="w-full max-w-sm rounded-lg border border-zinc-200 bg-white p-8 shadow-sm">
      <div className="mb-6 flex flex-col items-center gap-2">
        <span className="grid size-11 place-items-center rounded bg-teal-500 text-white">
          <Sparkles size={22} />
        </span>
        <h1 className="text-lg font-semibold text-zinc-900">视频号小店全自动系统</h1>
        <p className="text-xs text-zinc-500">管理控制台登录</p>
      </div>

      <form onSubmit={handleSubmit} className="space-y-4">
        <div>
          <label htmlFor="username" className="mb-1 block text-sm font-medium text-zinc-700">
            用户名
          </label>
          <input
            id="username"
            name="username"
            type="text"
            autoComplete="username"
            required
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            className="w-full rounded border border-zinc-300 px-3 py-2 text-sm outline-none transition focus:border-teal-500 focus:ring-1 focus:ring-teal-500"
          />
        </div>
        <div>
          <label htmlFor="password" className="mb-1 block text-sm font-medium text-zinc-700">
            密码
          </label>
          <input
            id="password"
            name="password"
            type="password"
            autoComplete="current-password"
            required
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            className="w-full rounded border border-zinc-300 px-3 py-2 text-sm outline-none transition focus:border-teal-500 focus:ring-1 focus:ring-teal-500"
          />
        </div>

        {error && (
          <p role="alert" className="rounded bg-red-50 px-3 py-2 text-xs text-red-600">
            {error}
          </p>
        )}

        <button
          type="submit"
          disabled={loading}
          className="w-full rounded bg-teal-600 px-3 py-2 text-sm font-medium text-white transition hover:bg-teal-700 disabled:cursor-not-allowed disabled:opacity-60"
        >
          {loading ? "登录中…" : "登 录"}
        </button>
      </form>

      <p className="mt-4 text-center text-xs leading-5 text-zinc-400">
        登录账号由后端环境变量配置（fixtures 模式）或 M0 鉴权表（m0 模式）；密钥不落前端。
      </p>
    </div>
  );
}
