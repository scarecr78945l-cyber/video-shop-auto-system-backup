/**
 * 异常中心（v0.7）：blocked / waiting_verification / waiting_login 任务清单 + 人工接管重试。
 *
 * - 取数：GET /api/workbench/exceptions（status 筛选 + limit，buildExceptionsQuery）；
 * - 顶部统计：待接管总数 + 按 error_code 分组计数卡片（ExceptionCenter 内）；
 * - 人工接管：POST /api/workbench/retry/{jobId} → pending（断点续跑，立即可领取）；
 *   409 INVALID_STATE / 404 message 展示在弹窗内（D8：三类状态均支持重试）；
 * - 闸门工作台跳转 `?status=waiting_*`：挂载时读取 query 参数做初始筛选（仅客户端运行时，
 *   不影响静态生成）。
 * 展示口径：时间 formatDateTime、枚举 enumLabel/StatusBadge、摘要走 lib/workbench.ts。
 */
"use client";

import { useEffect, useState } from "react";

import { apiGet, type WorkbenchException } from "@/lib/api";
import { useAsyncData } from "@/lib/useAsyncData";
import { buildExceptionsQuery } from "@/lib/workbench";
import { JOB_STATUS_LABELS } from "@/lib/enums";
import { cn } from "@/lib/cn";
import { ExceptionCenter } from "@/components/ExceptionCenter";

/** 异常中心关注的状态（对齐 workbench.py EXCEPTION_STATUSES；"" = 全部）。 */
const STATUS_FILTERS: ReadonlyArray<string> = [
  "",
  "blocked",
  "waiting_verification",
  "waiting_login",
];

type ExceptionsResponse = { total: number; items: WorkbenchException[] };

export default function ExceptionsPage() {
  const [status, setStatus] = useState("");

  // 闸门卡片跳转 `?status=waiting_*` 初始筛选（仅客户端；静态生成不受影响）
  useEffect(() => {
    const param = new URLSearchParams(window.location.search).get("status");
    if (param && STATUS_FILTERS.includes(param)) {
      setStatus(param);
    }
  }, []);

  const query = buildExceptionsQuery(status, 100);
  const list = useAsyncData<ExceptionsResponse>(
    () => apiGet(`/api/workbench/exceptions${query}`),
    [query],
  );

  const items = list.data?.items ?? [];

  return (
    <div>
      <div className="mb-6">
        <h1 className="text-xl font-semibold text-zinc-900">异常中心</h1>
        <p className="mt-1 text-sm text-zinc-500">
          blocked / waiting_verification / waiting_login 任务清单 · 人工接管后断点续跑
          （GET /api/workbench/exceptions + POST /api/workbench/retry/{"{id}"}）
        </p>
      </div>

      {/* 状态筛选 chips */}
      <div className="mb-4 flex flex-wrap items-center gap-2">
        {STATUS_FILTERS.map((value) => {
          const active = status === value;
          return (
            <button
              key={value || "all"}
              type="button"
              onClick={() => setStatus(value)}
              className={cn(
                "h-8 rounded-lg border px-3 text-xs transition",
                active
                  ? "border-teal-600 bg-teal-50 font-medium text-teal-700"
                  : "border-zinc-200 bg-white text-zinc-500 hover:bg-zinc-50",
              )}
            >
              {value === "" ? "全部" : (JOB_STATUS_LABELS[value] ?? value)}
            </button>
          );
        })}
        {list.data && (
          <span className="ml-auto text-xs text-zinc-400">
            当前筛选共 {list.data.total} 项（接口 limit=100）
          </span>
        )}
      </div>

      <ExceptionCenter
        items={items}
        loading={list.loading}
        error={list.error}
        onRefresh={list.reload}
      />
    </div>
  );
}
