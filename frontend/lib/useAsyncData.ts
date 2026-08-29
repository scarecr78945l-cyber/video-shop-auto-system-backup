/**
 * 轻量异步取数 Hook（v0.4 批次1）
 *
 * 管理 loading / error / data + reload：deps 变化时重新加载；
 * 加载期间保留旧 data（避免列表/详情闪烁），仅失败时清空 error 并展示。
 *
 * ⚠️ 调用约定：deps 必须传**原始值/字符串**（如 [query, page]），
 * 不要传每次渲染新建的对象字面量（会因引用不同导致重复加载）。
 */

import { useCallback, useEffect, useRef, useState } from "react";

import { ApiError } from "./api";

export type AsyncData<T> = {
  data: T | null;
  loading: boolean;
  error: string | null;
  reload: () => void;
};

export function useAsyncData<T>(
  loader: () => Promise<T>,
  deps: ReadonlyArray<unknown>,
): AsyncData<T> {
  const [data, setData] = useState<T | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [tick, setTick] = useState(0);
  const loaderRef = useRef(loader);
  loaderRef.current = loader;

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    loaderRef.current()
      .then((result) => {
        if (!cancelled) setData(result);
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setError(err instanceof ApiError ? err.message : "加载失败，请稍后重试");
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, tick]);

  const reload = useCallback(() => setTick((t) => t + 1), []);

  return { data, loading, error, reload };
}
