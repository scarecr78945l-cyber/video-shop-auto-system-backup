/**
 * 上架任务（M4）· v0.5 批次2
 *
 * 取数：GET /api/listing/tasks（9 态 status 过滤 + page/page_size 分页；title/error_code
 *      派生可空 D2/D3）+ GET /api/listing/tasks/{id}（详情）+ /op-logs（操作日志）
 *      + GET /api/listing/ready（待上架快捷视图，可选）。
 * 交互：9 态状态机条（点击状态筛选）/ 关键词（客户端）/ 行点击详情抽屉 /
 *      人工确认闸门 POST confirm（pending→creating，二次确认 + 备注）/ 拒审重提 POST retry。
 * 展示口径：金额 formatYuan（元零换算）、时间 formatDateTime（UTC→UTC+8）、
 *          枚举一律 lib/enums.ts（LISTING_STATUS_LABELS / errorCodeLabel），组件不硬编码中文。
 */
"use client";

import { useEffect, useMemo, useState } from "react";
import { ListChecks, RefreshCw, Search, Store } from "lucide-react";

import {
  ApiError,
  apiGet,
  apiPost,
  type ListingActionResult,
  type ListingOpLogsResponse,
  type ListingReadyResponse,
  type ListingTask,
  type ListingTaskDetail,
  type Paginated,
} from "@/lib/api";
import { useAsyncData } from "@/lib/useAsyncData";
import {
  buildListingQuery,
  canConfirmTask,
  canRetryTask,
  filterTasksByKeyword,
  LISTING_STATUSES_ORDERED,
  listingStatusCounts,
} from "@/lib/listing";
import { errorCodeLabel, LISTING_STATUS_LABELS } from "@/lib/enums";
import { formatDateTime } from "@/lib/format";
import { isMockMode } from "@/lib/env";
import { ConfirmDialog } from "@/components/ConfirmDialog";
import { ListingStateMachine } from "@/components/ListingStateMachine";
import { ListingTaskDetailPanel } from "@/components/ListingTaskDetailPanel";
import { Pagination } from "@/components/Pagination";
import { StatusBadge } from "@/components/StatusBadge";
import { cn } from "@/lib/cn";

type ActionDialog = { kind: "confirm" | "retry"; taskId: string; status: string } | null;

export default function ListingPage() {
  const [statusFilter, setStatusFilter] = useState("");
  const [keyword, setKeyword] = useState("");
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [showReady, setShowReady] = useState(false);
  const [dialog, setDialog] = useState<ActionDialog>(null);
  const [note, setNote] = useState("");
  const [actionBusy, setActionBusy] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);

  // 闸门工作台跳转 `?status=pending`：挂载时读取 query 参数做初始状态筛选（仅客户端运行时）
  useEffect(() => {
    const statusParam = new URLSearchParams(window.location.search).get("status");
    if (statusParam) setStatusFilter(statusParam);
  }, []);

  const query = useMemo(
    () => buildListingQuery(statusFilter, page, pageSize),
    [statusFilter, page, pageSize],
  );
  const list = useAsyncData<Paginated<ListingTask>>(
    () => apiGet(`/api/listing/tasks${query}`),
    [query],
  );
  const detail = useAsyncData<ListingTaskDetail | null>(
    () =>
      selectedId === null
        ? Promise.resolve(null)
        : apiGet(`/api/listing/tasks/${selectedId}`),
    [selectedId],
  );
  const logs = useAsyncData<ListingOpLogsResponse | null>(
    () =>
      selectedId === null
        ? Promise.resolve(null)
        : apiGet(`/api/listing/tasks/${selectedId}/op-logs?limit=100`),
    [selectedId],
  );
  const ready = useAsyncData<ListingReadyResponse | null>(
    () => (showReady ? apiGet("/api/listing/ready?page=1&page_size=20") : Promise.resolve(null)),
    [showReady],
  );

  const items = list.data?.items ?? [];
  const visibleItems = useMemo(() => filterTasksByKeyword(items, keyword), [items, keyword]);
  const counts = useMemo(() => listingStatusCounts(items), [items]);
  const keywordHit = keyword.trim() ? `${visibleItems.length} 条 / 当前页 ${items.length} 条` : null;

  function changeStatusFilter(status: string | null) {
    setStatusFilter(status ?? "");
    setPage(1);
  }

  function handlePageSizeChange(size: number) {
    setPageSize(size);
    setPage(1);
  }

  function openDetail(task: ListingTask) {
    setSelectedId(task.task_id);
  }

  function refreshAll() {
    list.reload();
    if (selectedId) {
      detail.reload();
      logs.reload();
    }
  }

  async function runAction() {
    if (!dialog || actionBusy) return;
    setActionBusy(true);
    setActionError(null);
    try {
      const action = dialog.kind;
      const path = `/api/listing/tasks/${dialog.taskId}/${action}`;
      await apiPost<ListingActionResult>(
        path,
        action === "confirm" ? { note: note.trim() || undefined } : undefined,
      );
      setDialog(null);
      setNote("");
      list.reload();
      if (selectedId === dialog.taskId) {
        detail.reload();
        logs.reload();
      }
    } catch (err) {
      setActionError(err instanceof ApiError ? err.message : "操作失败，请稍后重试");
    } finally {
      setActionBusy(false);
    }
  }

  return (
    <div>
      <div className="mb-6 flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold text-zinc-900">上架任务</h1>
          <p className="mt-1 text-sm text-zinc-500">
            M4 上架状态机（9 态）/ 人工确认闸门 / 拒审重提（GET /api/listing/tasks）
          </p>
        </div>
        <button
          type="button"
          onClick={refreshAll}
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

      {/* 9 态状态机可视化 */}
      <div className="mb-4">
        <ListingStateMachine
          counts={counts}
          activeStatus={statusFilter || null}
          onSelectStatus={changeStatusFilter}
        />
        <p className="mt-1.5 text-[11px] text-zinc-400">
          状态计数为当前页数据（列表接口分页返回，翻页后变化）；点击状态 chip 切换列表筛选。
        </p>
      </div>

      {/* 筛选栏 */}
      <div className="mb-4 rounded-lg border border-zinc-200 bg-white p-4">
        <div className="flex flex-wrap items-center gap-3">
          <label className="flex items-center gap-2 text-xs text-zinc-500">
            状态
            <select
              value={statusFilter}
              onChange={(e) => changeStatusFilter(e.target.value)}
              className="rounded border border-zinc-200 bg-white px-2 py-1.5 text-xs text-zinc-700 outline-none"
            >
              <option value="">全部</option>
              {LISTING_STATUSES_ORDERED.map((status) => (
                <option key={status} value={status}>
                  {LISTING_STATUS_LABELS[status] ?? status}
                </option>
              ))}
            </select>
          </label>
          <label className="flex min-w-[240px] flex-1 items-center gap-2 rounded border border-zinc-200 bg-zinc-50 px-3">
            <Search size={14} className="shrink-0 text-zinc-400" />
            <input
              value={keyword}
              onChange={(e) => {
                setKeyword(e.target.value);
                setPage(1);
              }}
              placeholder="关键词过滤（任务ID/商品ID/标题，客户端）"
              className="min-w-0 flex-1 bg-transparent py-1.5 text-xs outline-none"
            />
          </label>
          <button
            type="button"
            onClick={() => {
              setShowReady((v) => !v);
              if (!showReady) ready.reload();
            }}
            className={cn(
              "inline-flex items-center gap-1.5 rounded border px-3 py-1.5 text-xs transition",
              showReady
                ? "border-teal-300 bg-teal-50 text-teal-700"
                : "border-zinc-200 bg-white text-zinc-600 hover:bg-zinc-50",
            )}
          >
            <Store size={14} />
            待上架快捷视图
          </button>
        </div>
      </div>

      {list.error && (
        <div className="mb-4 rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-700">
          {list.error}
          <button type="button" onClick={list.reload} className="ml-3 underline">
            重试
          </button>
        </div>
      )}

      {/* 待上架快捷视图（GET /api/listing/ready） */}
      {showReady && (
        <div className="mb-4 overflow-hidden rounded-lg border border-zinc-200 bg-white">
          <div className="flex items-center justify-between border-b border-zinc-100 px-4 py-2.5">
            <span className="inline-flex items-center gap-1.5 text-xs font-medium text-zinc-700">
              <ListChecks size={14} className="text-teal-600" />
              待上架商品（已上架且链接已验证）
            </span>
            <span className="text-xs text-zinc-400">共 {ready.data?.total ?? 0} 条</span>
          </div>
          {ready.error && (
            <div className="px-4 py-3 text-xs text-red-700">
              {ready.error}
              <button type="button" onClick={ready.reload} className="ml-2 underline">
                重试
              </button>
            </div>
          )}
          {ready.loading && !ready.data && (
            <div className="grid h-20 place-items-center text-xs text-zinc-400">加载中…</div>
          )}
          {ready.data && ready.data.items.length === 0 && (
            <div className="grid h-20 place-items-center text-xs text-zinc-400">暂无待上架商品</div>
          )}
          {ready.data && ready.data.items.length > 0 && (
            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs">
                <thead className="bg-zinc-50 text-zinc-500">
                  <tr>
                    <th className="px-4 py-2 font-medium">商品</th>
                    <th className="px-4 py-2 font-medium">标题</th>
                    <th className="px-4 py-2 font-medium">价格区间</th>
                    <th className="px-4 py-2 font-medium">链接验证时间</th>
                    <th className="px-4 py-2 font-medium">商品链接</th>
                  </tr>
                </thead>
                <tbody className="text-zinc-700">
                  {ready.data.items.map((item) => (
                    <tr key={item.task_id} className="border-t border-zinc-100">
                      <td className="px-4 py-2">
                        <span className="font-medium text-zinc-800">#{item.product_id}</span>
                        <span className="ml-1 text-zinc-400">({item.task_id})</span>
                      </td>
                      <td className="max-w-[240px] truncate px-4 py-2" title={item.title ?? undefined}>
                        {item.title || "—"}
                      </td>
                      <td className="whitespace-nowrap px-4 py-2">
                        <YuanRangeText min={item.price_min_yuan} max={item.price_max_yuan} />
                      </td>
                      <td className="whitespace-nowrap px-4 py-2">{formatDateTime(item.link_verified_at)}</td>
                      <td className="max-w-[220px] truncate px-4 py-2">
                        {item.product_link ? (
                          <a
                            href={item.product_link}
                            target="_blank"
                            rel="noreferrer"
                            className="text-teal-700 underline-offset-2 hover:underline"
                          >
                            {item.product_link}
                          </a>
                        ) : (
                          "—"
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {/* 任务列表 */}
      <div className="overflow-hidden rounded-lg border border-zinc-200 bg-white">
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead className="bg-zinc-50 text-xs text-zinc-500">
              <tr>
                <th className="px-4 py-2.5 font-medium">任务 / 商品</th>
                <th className="px-4 py-2.5 font-medium">状态</th>
                <th className="px-4 py-2.5 font-medium">尝试</th>
                <th className="px-4 py-2.5 font-medium">错误码</th>
                <th className="px-4 py-2.5 font-medium">更新时间</th>
                <th className="px-4 py-2.5 font-medium">操作</th>
              </tr>
            </thead>
            <tbody>
              {!list.loading && visibleItems.length === 0 && (
                <tr>
                  <td colSpan={6} className="px-4 py-12 text-center text-xs text-zinc-400">
                    {keyword.trim() ? "当前页无匹配关键词的上架任务" : "暂无上架任务"}
                  </td>
                </tr>
              )}
              {visibleItems.map((task) => (
                <tr
                  key={task.task_id}
                  onClick={() => openDetail(task)}
                  className={cn(
                    "cursor-pointer border-t border-zinc-100 transition hover:bg-teal-50/40",
                    list.loading && "opacity-60",
                  )}
                >
                  <td className="px-4 py-3">
                    <div className="max-w-[300px]">
                      <div className="truncate font-medium text-zinc-800" title={task.task_id}>
                        {task.task_id}
                      </div>
                      <div className="mt-0.5 flex items-center gap-2 text-xs">
                        <span className="text-zinc-400">商品 #{task.product_id}</span>
                        {task.title && (
                          <span className="truncate text-zinc-500" title={task.title}>
                            {task.title}
                          </span>
                        )}
                      </div>
                    </div>
                  </td>
                  <td className="px-4 py-3">
                    <StatusBadge labels={LISTING_STATUS_LABELS} value={task.status} />
                  </td>
                  <td className="px-4 py-3 text-xs text-zinc-600">{task.attempts ?? 0}</td>
                  <td className="px-4 py-3">
                    {task.error_code ? (
                      <span className="inline-flex items-center rounded bg-red-50 px-2 py-0.5 text-xs text-red-700 ring-1 ring-inset ring-red-200">
                        {errorCodeLabel(task.error_code)}
                      </span>
                    ) : (
                      <span className="text-xs text-zinc-300">—</span>
                    )}
                  </td>
                  <td className="whitespace-nowrap px-4 py-3 text-xs text-zinc-500">
                    {formatDateTime(task.updated_at)}
                  </td>
                  <td className="whitespace-nowrap px-4 py-3" onClick={(e) => e.stopPropagation()}>
                    <div className="flex items-center gap-1.5">
                      <button
                        type="button"
                        onClick={() => openDetail(task)}
                        className="rounded border border-zinc-200 px-2 py-1 text-xs text-zinc-600 transition hover:bg-zinc-50"
                      >
                        详情
                      </button>
                      {canConfirmTask(task.status) && (
                        <button
                          type="button"
                          onClick={() => {
                            setNote("");
                            setActionError(null);
                            setDialog({ kind: "confirm", taskId: task.task_id, status: task.status });
                          }}
                          className="rounded bg-teal-600 px-2 py-1 text-xs font-medium text-white transition hover:bg-teal-700"
                        >
                          确认上架
                        </button>
                      )}
                      {canRetryTask(task.status) && (
                        <button
                          type="button"
                          onClick={() => {
                            setNote("");
                            setActionError(null);
                            setDialog({ kind: "retry", taskId: task.task_id, status: task.status });
                          }}
                          className="rounded border border-amber-300 bg-amber-50 px-2 py-1 text-xs font-medium text-amber-800 transition hover:bg-amber-100"
                        >
                          重提
                        </button>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <Pagination
          page={page}
          pageSize={pageSize}
          total={list.data?.total ?? 0}
          onPageChange={setPage}
          onPageSizeChange={handlePageSizeChange}
        />
        {keywordHit && (
          <div className="border-t border-zinc-100 px-4 py-2 text-xs text-zinc-400">
            关键词为客户端过滤：当前页命中 {keywordHit}（API 无关键词参数，见 REPORT 遗留项）
          </div>
        )}
      </div>

      {/* 详情抽屉 */}
      {selectedId !== null && (
        <ListingTaskDetailPanel
          detail={detail.data}
          logs={logs.data}
          loading={detail.loading}
          error={detail.error}
          onClose={() => setSelectedId(null)}
          onConfirm={(task) => {
            setNote("");
            setActionError(null);
            setDialog({ kind: "confirm", taskId: task.task_id, status: task.status });
          }}
          onRetry={(task) => {
            setNote("");
            setActionError(null);
            setDialog({ kind: "retry", taskId: task.task_id, status: task.status });
          }}
        />
      )}

      {/* 二次确认弹窗（confirm / retry） */}
      <ConfirmDialog
        open={dialog !== null}
        title={dialog?.kind === "confirm" ? "确认上架（最终闸门）" : "拒审修复后重提"}
        message={
          dialog?.kind === "confirm" ? (
            <>
              确认后任务将从「待上架」入队创建（pending → creating），由系统执行微信小店
              上架流程，操作人由后端记录。此操作<b>不可撤销</b>。
              {dialog && (
                <span className="mt-1 block text-xs text-zinc-400">
                  任务 {dialog.taskId} · 当前状态：{LISTING_STATUS_LABELS[dialog.status] ?? dialog.status}
                </span>
              )}
            </>
          ) : (
            <>
              确认已按拒审记录完成修复？重提后任务将重新入队创建（rejected/retry_candidate →
              creating），操作人由后端记录。
              {dialog && (
                <span className="mt-1 block text-xs text-zinc-400">
                  任务 {dialog.taskId} · 当前状态：{LISTING_STATUS_LABELS[dialog.status] ?? dialog.status}
                </span>
              )}
            </>
          )
        }
        confirmText={dialog?.kind === "confirm" ? "确认上架" : "确认重提"}
        busy={actionBusy}
        error={actionError}
        inputLabel={dialog?.kind === "confirm" ? "确认备注（可选）" : undefined}
        inputPlaceholder="备注将随操作日志记录"
        inputValue={note}
        onInputChange={setNote}
        onConfirm={runAction}
        onCancel={() => {
          if (!actionBusy) {
            setDialog(null);
            setActionError(null);
          }
        }}
      />
    </div>
  );
}

/** 价格区间展示（价格已 分→元；单值/双值/空值）。 */
function YuanRangeText({ min, max }: { min: number | null; max: number | null }) {
  if (min === null && max === null) return <span className="text-zinc-400">—</span>;
  const lo = min === null ? null : `¥${min.toFixed(2)}`;
  const hi = max === null ? null : `¥${max.toFixed(2)}`;
  if (lo === hi) return <span>{lo}</span>;
  return (
    <span>
      {lo ?? "—"} ~ {hi ?? "—"}
    </span>
  );
}
