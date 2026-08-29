/**
 * 总览看板（v0.4 批次1）
 *
 * 取数：GET /api/overview（任务队列统计/今日漏斗/错误码分布/风控状态）
 *      + GET /api/jobs?page=1&page_size=10（最新任务，error_code 中文徽章）
 * 交互：一键全停开关 POST /api/kill-switch（KillSwitch 组件，管理员端点）。
 * 展示口径：金额 formatYuan（元零换算）、时间 formatDateTime（UTC→UTC+8）、
 *          枚举一律 lib/enums.ts 映射（本页无硬编码中文）。
 */
"use client";

import { useMemo, useState } from "react";
import type { ReactNode } from "react";
import { RefreshCw, ShieldAlert, TriangleAlert, Activity, ListOrdered, Filter } from "lucide-react";

import { apiGet, type JobSummary, type OverviewResponse, type Paginated } from "@/lib/api";
import { useAsyncData } from "@/lib/useAsyncData";
import { abnormalJobCount, countEntries, funnelEntries, sumRecord } from "@/lib/dashboard";
import {
  ADS_ACCOUNT_STATUS_LABELS,
  ERROR_CODE_LABELS,
  JOB_STAGE_LABELS,
  JOB_STATUS_LABELS,
} from "@/lib/enums";
import { formatDateTime } from "@/lib/format";
import { isMockMode } from "@/lib/env";
import { KillSwitch } from "@/components/KillSwitch";
import { StatusBadge } from "@/components/StatusBadge";
import { YuanText } from "@/components/YuanText";
import { cn } from "@/lib/cn";

export default function DashboardPage() {
  const [killOverride, setKillOverride] = useState<boolean | null>(null);

  const overview = useAsyncData<OverviewResponse>(() => apiGet("/api/overview"), []);
  const jobs = useAsyncData<Paginated<JobSummary>>(
    () => apiGet("/api/jobs?page=1&page_size=10"),
    [],
  );

  const data = overview.data;
  const killEnabled = killOverride ?? data?.risk?.kill_switch_enabled ?? false;
  const funnel = useMemo(() => funnelEntries(data?.today_funnel), [data]);
  const errorEntries = useMemo(() => countEntries(data?.jobs_by_error_code), [data]);
  const statusEntries = useMemo(() => countEntries(data?.jobs_by_status), [data]);
  const funnelMax = useMemo(
    () => Math.max(1, ...funnel.map((e) => e.count)),
    [funnel],
  );

  const error = overview.error || jobs.error;

  return (
    <div>
      <div className="mb-6 flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold text-zinc-900">总览</h1>
          <p className="mt-1 text-sm text-zinc-500">
            任务队列 / 今日漏斗 / 错误码分布 / 风控状态聚合看板
            {data?.generated_at && (
              <span className="ml-2 text-xs text-zinc-400">
                数据时间 {formatDateTime(data.generated_at, true)}
              </span>
            )}
          </p>
        </div>
        <button
          type="button"
          onClick={() => {
            overview.reload();
            jobs.reload();
          }}
          className="inline-flex items-center gap-1.5 rounded border border-zinc-200 bg-white px-3 py-1.5 text-xs text-zinc-600 transition hover:bg-zinc-50"
        >
          <RefreshCw size={14} />
          刷新
        </button>
      </div>

      {isMockMode() && (
        <div className="mb-4 rounded-lg border border-amber-200 bg-amber-50 px-4 py-2 text-xs text-amber-700">
          NEXT_PUBLIC_USE_MOCK=1：演示模式保留位（当前版本未注入 mock 数据，直连真实 API）
        </div>
      )}

      {error && (
        <div className="mb-4 rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-700">
          {error}
          <button
            type="button"
            onClick={() => {
              overview.reload();
              jobs.reload();
            }}
            className="ml-3 underline"
          >
            重试
          </button>
        </div>
      )}

      {!error && (overview.loading || jobs.loading) && !data && (
        <div className="grid h-48 place-items-center text-sm text-zinc-400">加载中…</div>
      )}

      {data && (
        <>
          {/* 顶部统计 */}
          <div className="mb-4 grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
            <StatCard
              icon={<Activity size={20} />}
              label="任务总数"
              value={String(data.total_jobs)}
              note="workflow_jobs 全量"
            />
            <StatCard
              icon={<ListOrdered size={20} />}
              label="今日新增任务"
              value={String(sumRecord(data.today_funnel))}
              note="UTC 今日 0 点起按阶段计数"
            />
            <StatCard
              icon={<Filter size={20} />}
              label="执行中"
              value={String(data.jobs_by_status["running"] ?? 0)}
              note="running 状态任务"
            />
            <StatCard
              icon={<TriangleAlert size={20} />}
              label="异常任务"
              value={String(abnormalJobCount(data.jobs_by_status))}
              note="blocked / failed / waiting_*"
              highlight={abnormalJobCount(data.jobs_by_status) > 0}
            />
          </div>

          <div className="grid gap-4 xl:grid-cols-2">
            {/* 任务队列统计 */}
            <section className="rounded-lg border border-zinc-200 bg-white p-5">
              <h2 className="flex items-center gap-2 text-sm font-semibold text-zinc-900">
                <span className="grid size-8 place-items-center rounded bg-teal-50 text-teal-600">
                  <Activity size={16} />
                </span>
                任务队列统计
              </h2>
              <div className="mt-4">
                <div className="text-xs text-zinc-400">按阶段（stage）</div>
                <div className="mt-2 flex flex-wrap gap-2">
                  {funnel.length === 0 && <span className="text-xs text-zinc-400">暂无任务</span>}
                  {funnel.map((e) => (
                    <span key={e.key} className="rounded bg-zinc-100 px-2 py-1 text-xs text-zinc-700">
                      {e.label} <span className="font-semibold text-zinc-900">{e.count}</span>
                    </span>
                  ))}
                </div>
              </div>
              <div className="mt-4">
                <div className="text-xs text-zinc-400">按状态（status）</div>
                <div className="mt-2 flex flex-wrap gap-2">
                  {statusEntries.length === 0 && <span className="text-xs text-zinc-400">暂无任务</span>}
                  {statusEntries.map((e) => (
                    <span key={e.key} className="inline-flex items-center gap-1.5">
                      <StatusBadge labels={JOB_STATUS_LABELS} value={e.key} />
                      <span className="text-xs text-zinc-500">{e.count}</span>
                    </span>
                  ))}
                </div>
              </div>
            </section>

            {/* 今日漏斗 */}
            <section className="rounded-lg border border-zinc-200 bg-white p-5">
              <h2 className="flex items-center gap-2 text-sm font-semibold text-zinc-900">
                <span className="grid size-8 place-items-center rounded bg-teal-50 text-teal-600">
                  <ListOrdered size={16} />
                </span>
                今日漏斗
                <span className="ml-auto text-xs font-normal text-zinc-400">
                  合计 {sumRecord(data.today_funnel)}
                </span>
              </h2>
              <div className="mt-4 space-y-2.5">
                {funnel.length === 0 && (
                  <p className="py-6 text-center text-xs text-zinc-400">今日暂无任务</p>
                )}
                {funnel.map((e) => (
                  <div key={e.key} className="flex items-center gap-3">
                    <span className="w-24 shrink-0 text-xs text-zinc-600">{e.label}</span>
                    <div className="h-2.5 flex-1 overflow-hidden rounded-full bg-zinc-100">
                      <div
                        className="h-full rounded-full bg-teal-500"
                        style={{ width: `${Math.round((e.count / funnelMax) * 100)}%` }}
                      />
                    </div>
                    <span className="w-8 shrink-0 text-right text-xs font-semibold text-zinc-800">
                      {e.count}
                    </span>
                  </div>
                ))}
              </div>
            </section>

            {/* 错误码分布 */}
            <section className="rounded-lg border border-zinc-200 bg-white p-5">
              <h2 className="flex items-center gap-2 text-sm font-semibold text-zinc-900">
                <span className="grid size-8 place-items-center rounded bg-teal-50 text-teal-600">
                  <TriangleAlert size={16} />
                </span>
                错误码分布
              </h2>
              <div className="mt-4 space-y-2">
                {errorEntries.length === 0 && (
                  <p className="py-6 text-center text-xs text-zinc-400">无错误任务 🎉</p>
                )}
                {errorEntries.map((e) => (
                  <div key={e.key} className="flex items-center justify-between gap-3">
                    <StatusBadge labels={ERROR_CODE_LABELS} value={e.key} />
                    <span className="text-sm font-semibold text-zinc-800">{e.count}</span>
                  </div>
                ))}
              </div>
            </section>

            {/* 风控状态 */}
            <section className="rounded-lg border border-zinc-200 bg-white p-5">
              <h2 className="flex items-center gap-2 text-sm font-semibold text-zinc-900">
                <span className="grid size-8 place-items-center rounded bg-teal-50 text-teal-600">
                  <ShieldAlert size={16} />
                </span>
                风控状态
              </h2>
              <div className="mt-4 space-y-4">
                <div className="flex items-center justify-between gap-3">
                  <div>
                    <div className="text-sm text-zinc-700">一键全停（kill_switch）</div>
                    <div className="mt-0.5 text-xs text-zinc-400">
                      {killEnabled ? "所有自动任务已暂停执行" : "自动任务正常运行"}
                    </div>
                  </div>
                  <KillSwitch enabled={killEnabled} onChange={setKillOverride} />
                </div>
                <div className="grid grid-cols-3 gap-3 border-t border-zinc-100 pt-4">
                  <div>
                    <div className="text-xs text-zinc-400">投放账户余额</div>
                    <div className={cn("mt-1 text-base font-semibold", (data.risk.ad_balance_yuan ?? 0) <= 0 ? "text-red-600" : "text-zinc-900")}>
                      <YuanText value={data.risk.ad_balance_yuan} />
                    </div>
                  </div>
                  <div>
                    <div className="text-xs text-zinc-400">账户状态</div>
                    <div className="mt-1">
                      <StatusBadge
                        labels={ADS_ACCOUNT_STATUS_LABELS}
                        value={data.risk.ad_account_status}
                        tone={
                          data.risk.ad_account_status === "active"
                            ? "green"
                            : data.risk.ad_account_status === "unknown"
                              ? "gray"
                              : "red"
                        }
                      />
                    </div>
                  </div>
                  <div>
                    <div className="text-xs text-zinc-400">节流级别</div>
                    <div className={cn("mt-1 text-base font-semibold", data.risk.ad_throttle_level > 0 ? "text-amber-600" : "text-zinc-900")}>
                      {data.risk.ad_throttle_level > 0 ? `Lv.${data.risk.ad_throttle_level}` : "正常"}
                    </div>
                  </div>
                </div>
              </div>
            </section>
          </div>

          {/* 最新任务 */}
          <section className="mt-4 overflow-hidden rounded-lg border border-zinc-200 bg-white">
            <div className="flex h-12 items-center justify-between border-b border-zinc-200 px-5">
              <h2 className="text-sm font-semibold text-zinc-900">最新任务</h2>
              <span className="text-xs text-zinc-400">GET /api/jobs · 最近 10 条</span>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-left text-sm">
                <thead className="bg-zinc-50 text-xs text-zinc-500">
                  <tr>
                    <th className="px-4 py-2.5 font-medium">任务ID</th>
                    <th className="px-4 py-2.5 font-medium">商品ID</th>
                    <th className="px-4 py-2.5 font-medium">阶段</th>
                    <th className="px-4 py-2.5 font-medium">状态</th>
                    <th className="px-4 py-2.5 font-medium">错误码</th>
                    <th className="px-4 py-2.5 font-medium">重试</th>
                    <th className="px-4 py-2.5 font-medium">更新时间</th>
                  </tr>
                </thead>
                <tbody>
                  {(jobs.data?.items ?? []).length === 0 && (
                    <tr>
                      <td colSpan={7} className="px-4 py-10 text-center text-xs text-zinc-400">
                        暂无任务
                      </td>
                    </tr>
                  )}
                  {(jobs.data?.items ?? []).map((job) => (
                    <tr key={job.id} className="border-t border-zinc-100 hover:bg-zinc-50/60">
                      <td className="px-4 py-2.5 font-mono text-xs text-zinc-500">{job.id}</td>
                      <td className="px-4 py-2.5 font-mono text-xs text-zinc-600">{job.product_id}</td>
                      <td className="px-4 py-2.5">
                        <StatusBadge labels={JOB_STAGE_LABELS} value={job.stage} />
                      </td>
                      <td className="px-4 py-2.5">
                        <StatusBadge labels={JOB_STATUS_LABELS} value={job.status} />
                      </td>
                      <td className="px-4 py-2.5">
                        {job.error_code ? (
                          <StatusBadge labels={ERROR_CODE_LABELS} value={job.error_code} tone="red" />
                        ) : (
                          <span className="text-xs text-zinc-400">—</span>
                        )}
                      </td>
                      <td className="px-4 py-2.5 text-xs text-zinc-600">{job.retry_count ?? 0}</td>
                      <td className="whitespace-nowrap px-4 py-2.5 text-xs text-zinc-500">
                        {formatDateTime(job.updated_at)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        </>
      )}
    </div>
  );
}

function StatCard({
  icon,
  label,
  value,
  note,
  highlight = false,
}: {
  icon: ReactNode;
  label: string;
  value: string;
  note: string;
  highlight?: boolean;
}) {
  return (
    <div className="rounded-lg border border-zinc-200 bg-white p-5">
      <div className="flex items-center justify-between">
        <span
          className={cn(
            "grid size-10 place-items-center rounded",
            highlight ? "bg-red-50 text-red-600" : "bg-teal-50 text-teal-600",
          )}
        >
          {icon}
        </span>
        <span className={cn("text-2xl font-semibold", highlight ? "text-red-600" : "text-zinc-900")}>
          {value}
        </span>
      </div>
      <h2 className="mt-3 text-sm font-semibold text-zinc-900">{label}</h2>
      <p className="mt-1 text-xs leading-5 text-zinc-400">{note}</p>
    </div>
  );
}
