/**
 * 工作台外壳（参考旧系统 AppShell 的 WorkspaceView 枚举改造为路由导航）。
 * 侧边导航 + 顶栏（当前用户/登出）；移动端底部导航。
 * 导航项对应 app/(dashboard)/ 下的路由页。
 */
"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  AlertTriangle,
  ClipboardCheck,
  ImageIcon,
  LayoutDashboard,
  LogOut,
  Megaphone,
  Package,
  Settings,
  ShieldCheck,
  Sparkles,
  Store,
} from "lucide-react";
import type { ReactNode } from "react";
import type { CurrentUser } from "@/lib/auth";
import { cn } from "@/lib/cn";

const NAV_ITEMS = [
  { href: "/", label: "总览", icon: LayoutDashboard },
  { href: "/products", label: "商品池", icon: Package },
  { href: "/assets", label: "素材库", icon: ImageIcon },
  { href: "/review", label: "审核工作台", icon: ShieldCheck },
  { href: "/listing", label: "上架管理", icon: Store },
  { href: "/ads", label: "托管投放", icon: Megaphone },
  { href: "/workbench", label: "闸门工作台", icon: ClipboardCheck },
  { href: "/exceptions", label: "异常中心", icon: AlertTriangle },
  { href: "/settings", label: "系统设置", icon: Settings },
] as const;

type Props = {
  user: CurrentUser | null;
  onLogout: () => void;
  children: ReactNode;
};

export function AppShell({ user, onLogout, children }: Props) {
  const pathname = usePathname();

  const isActive = (href: string): boolean =>
    href === "/" ? pathname === "/" : pathname === href || pathname.startsWith(`${href}/`);

  return (
    <div className="min-h-screen bg-[#f4f6f8] text-zinc-900">
      {/* 桌面侧边栏 */}
      <aside className="fixed inset-y-0 left-0 z-30 hidden w-[224px] flex-col bg-[#111b24] text-zinc-200 lg:flex">
        <div className="flex h-16 items-center gap-3 border-b border-white/10 px-5">
          <span className="grid size-9 place-items-center rounded bg-teal-500 text-white">
            <Sparkles size={18} />
          </span>
          <div>
            <div className="text-sm font-semibold text-white">视频号小店全自动系统</div>
            <div className="text-xs text-zinc-400">管理控制台</div>
          </div>
        </div>
        <nav className="flex flex-1 flex-col gap-1 p-3">
          {NAV_ITEMS.map((item) => {
            const Icon = item.icon;
            const active = isActive(item.href);
            return (
              <Link
                key={item.href}
                href={item.href}
                className={cn(
                  "flex h-11 items-center gap-3 rounded px-3 text-sm transition",
                  active
                    ? "bg-teal-500/15 font-medium text-teal-300"
                    : "text-zinc-400 hover:bg-white/5 hover:text-white",
                )}
              >
                <Icon size={18} />
                {item.label}
              </Link>
            );
          })}
        </nav>
        <div className="border-t border-white/10 px-5 py-4 text-xs leading-5 text-zinc-500">
          数据来源：backend/api（M0~M5 聚合）。金额口径：元；时间：UTC+8。
        </div>
      </aside>

      {/* 主区 */}
      <div className="flex min-h-screen flex-col lg:pl-[224px]">
        {/* 顶栏 */}
        <header className="sticky top-0 z-20 flex h-16 items-center justify-between border-b border-zinc-200 bg-white/90 px-4 backdrop-blur lg:px-8">
          <div className="flex items-center gap-2 lg:hidden">
            <span className="grid size-8 place-items-center rounded bg-teal-500 text-white">
              <Sparkles size={16} />
            </span>
            <span className="text-sm font-semibold">视频号小店控制台</span>
          </div>
          <div className="hidden text-sm text-zinc-500 lg:block">M6 前端控制台 · v0.7（批次4：闸门工作台 / 异常中心）</div>
          <div className="flex items-center gap-3">
            {user && (
              <span className="text-sm text-zinc-600">
                当前用户：<span className="font-medium text-zinc-900">{user.username}</span>
                <span className="ml-2 rounded bg-zinc-100 px-1.5 py-0.5 text-xs text-zinc-500">{user.role}</span>
              </span>
            )}
            <button
              type="button"
              onClick={onLogout}
              className="inline-flex items-center gap-1.5 rounded border border-zinc-200 px-2.5 py-1.5 text-xs text-zinc-600 transition hover:border-zinc-300 hover:bg-zinc-50 hover:text-zinc-900"
            >
              <LogOut size={14} />
              退出登录
            </button>
          </div>
        </header>

        <main className="flex-1 p-4 lg:p-8">{children}</main>
      </div>

      {/* 移动端底部导航 */}
      <nav className="fixed inset-x-0 bottom-0 z-40 flex overflow-x-auto border-t border-zinc-200 bg-white lg:hidden">
        {NAV_ITEMS.map((item) => {
          const Icon = item.icon;
          const active = isActive(item.href);
          return (
            <Link
              key={item.href}
              href={item.href}
              className={cn(
                "grid h-16 min-w-20 flex-1 place-items-center text-[11px]",
                active ? "text-teal-700" : "text-zinc-500",
              )}
            >
              <span className="grid justify-items-center gap-1">
                <Icon size={18} />
                {item.label}
              </span>
            </Link>
          );
        })}
      </nav>
    </div>
  );
}
