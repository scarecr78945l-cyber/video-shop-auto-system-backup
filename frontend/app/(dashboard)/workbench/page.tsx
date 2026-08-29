/**
 * 人工闸门工作台（v0.7）：跨模块闸门待办聚合 + 选品复核内联操作 + 一键全停快捷。
 *
 * - 闸门聚合：GET /api/workbench/gates → 6 类待办卡片（选品复核/上架确认/图片审核/
 *   素材预审/验证码接管/登录接管），count=0 置灰「无待办」；卡片跳转目标页
 *   （目标页运行时会读取 query 参数做初始筛选：products?state=manual_review、
 *   listing?status=pending、review?tab=image|material、exceptions?status=waiting_*）。
 * - 选品复核：SourcingReviewPanel 内联（GET /api/products?state=manual_review →
 *   POST /api/sourcing/gate-confirm，二次确认；成功回调刷新闸门计数）。
 * - 一键全停快捷：复用 components/KillSwitch（总览页同款，状态取 GET /api/overview risk）。
 * 展示口径：金额/时间/枚举全部走 lib 层（本页无金额）。
 */
"use client";

import {
  ClipboardCheck,
  ImageIcon,
  KeyRound,
  ListChecks,
  LogIn,
  Power,
  ScanLine,
} from "lucide-react";
import type { ComponentType } from "react";

import { apiGet, type OverviewResponse, type WorkbenchGates } from "@/lib/api";
import { useAsyncData } from "@/lib/useAsyncData";
import { GATE_DEFS, gateCount, totalGateCount, type GateKey } from "@/lib/workbench";
import { formatDateTime } from "@/lib/format";
import { GateTodoCard } from "@/components/GateTodoCard";
import { KillSwitch } from "@/components/KillSwitch";
import { SourcingReviewPanel } from "@/components/SourcingReviewPanel";

const GATE_ICONS: Record<GateKey, ComponentType<{ size?: number | string; className?: string }>> = {
  sourcing_review: ClipboardCheck,
  listing_confirm: ListChecks,
  image_review: ImageIcon,
  material_pre_review: ScanLine,
  verification_takeover: KeyRound,
  login_takeover: LogIn,
};

export default function WorkbenchPage() {
  const gates = useAsyncData<WorkbenchGates>(() => apiGet("/api/workbench/gates"), []);
  const overview = useAsyncData<OverviewResponse>(() => apiGet("/api/overview"), []);

  return (
    <div>
      <div className="mb-6">
        <h1 className="text-xl font-semibold text-zinc-900">闸门工作台</h1>
        <p className="mt-1 text-sm text-zinc-500">
          跨模块人工闸门待办聚合（GET /api/workbench/gates）：选品复核 / 上架确认 / 图片审核 /
          素材预审 / 验证码与登录接管 · 全自动流程的合规兜底
        </p>
      </div>

      {gates.error && (
        <div className="mb-4 rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-700">
          {gates.error}
          <button type="button" onClick={gates.reload} className="ml-3 underline">
            重试
          </button>
        </div>
      )}

      {/* 闸门待办卡片 */}
      <div className="mb-4 grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
        {GATE_DEFS.map((def) => (
          <GateTodoCard
            key={def.key}
            label={def.label}
            count={gateCount(gates.data, def.key)}
            hint={def.hint}
            href={def.href}
            icon={GATE_ICONS[def.key]}
          />
        ))}

        {/* 一键全停快捷卡（复用总览页 KillSwitch） */}
        <div className="rounded-lg border border-red-200 bg-red-50/50 p-4">
          <div className="flex items-start justify-between gap-2">
            <span className="grid size-9 place-items-center rounded-lg bg-red-100 text-red-600">
              <Power size={18} />
            </span>
            <span className="text-lg font-semibold tabular-nums text-zinc-400">
              {gates.data ? totalGateCount(gates.data) : 0}
            </span>
          </div>
          <div className="mt-3 text-sm font-medium text-zinc-900">一键全停</div>
          <div className="mt-0.5 text-[11px] text-zinc-400">S8 最高优先级 · POST /api/kill-switch</div>
          <div className="mt-2">
            <KillSwitch
              enabled={overview.data?.risk.kill_switch_enabled ?? false}
              onChange={() => overview.reload()}
            />
          </div>
        </div>
      </div>

      {gates.data && (
        <p className="mb-4 text-xs text-zinc-400">
          待办合计 {totalGateCount(gates.data)} 项 · 聚合时间 {formatDateTime(gates.data.generated_at)}
          （单模块库不可用不影响其余计数）
        </p>
      )}

      {/* 选品复核（内联操作） */}
      <SourcingReviewPanel onConfirmed={gates.reload} />
    </div>
  );
}
