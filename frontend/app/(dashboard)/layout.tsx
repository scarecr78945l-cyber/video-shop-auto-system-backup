/**
 * 工作台布局（路由守卫）：挂载时 GET /api/auth/me 校验会话；
 * 未登录 → 401 全局拦截跳 /login（兜底 router.replace）。
 * 登录态 OK → 渲染 AppShell（侧边导航 + 顶栏）+ 子页面。
 */
"use client";

import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { AppShell } from "@/components/AppShell";
import { getCurrentUser, logout, type CurrentUser } from "@/lib/auth";

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const [user, setUser] = useState<CurrentUser | null>(null);
  const [checking, setChecking] = useState(true);

  useEffect(() => {
    let cancelled = false;
    getCurrentUser()
      .then((current) => {
        if (cancelled) return;
        if (current) {
          setUser(current);
        } else {
          // 401 已由 lib/api.ts 全局拦截跳转；这里兜底（如自定义 handler 场景）
          router.replace("/login");
        }
        setChecking(false);
      })
      .catch(() => {
        if (!cancelled) setChecking(false);
      });
    return () => {
      cancelled = true;
    };
  }, [router]);

  const handleLogout = useCallback(async () => {
    await logout();
    router.replace("/login");
  }, [router]);

  if (checking) {
    return (
      <div className="grid min-h-screen place-items-center bg-[#f4f6f8] text-sm text-zinc-500">
        正在验证登录状态…
      </div>
    );
  }

  if (!user) return null; // 守卫已重定向

  return <AppShell user={user} onLogout={handleLogout}>{children}</AppShell>;
}
