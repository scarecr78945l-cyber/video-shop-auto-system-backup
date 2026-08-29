/**
 * 素材/图片预览（v1.1）：GET /api/assets/{id}/preview 图片流 → fetch blob + objectURL。
 *
 * - 鉴权：fetch credentials:"include"（httpOnly 会话 cookie 随请求携带）；联调按 P-023
 *   前后端统一主机名（127.0.0.1:PORT / localhost:PORT），SameSite cookie 同站点自动携带；
 *   跨域场景由 fetch+credentials 显式携带（后端 CORS 需 allow_credentials）。
 * - 安全：file_path 白名单校验由后端承担（防路径穿越）；前端仅展示。
 * - 容错：preview 不可用（404/400/video 等）→ 静默回退占位（不打断审核/详情流程）；
 *   ?ts= 缓存破坏参数防止浏览器缓存旧图。
 * - 生命周期：objectURL 在卸载/换图时 revoke（防内存泄漏）。
 */
"use client";

import { useEffect, useState } from "react";
import type { ReactNode } from "react";
import { ImageOff, Loader2 } from "lucide-react";

import { API_BASE } from "@/lib/api";
import { cn } from "@/lib/cn";

type Props = {
  /** 素材 id（M2 asset.id 或 M3 图片标识；为空/非法时不请求）。 */
  assetId: number | string | null | undefined;
  /** 是否启用预览（video 等非图片类型传 false 保持占位，不发起请求）。 */
  enabled?: boolean;
  alt?: string;
  /** 容器宽高比（默认 aspect-square）。 */
  aspectClass?: string;
  className?: string;
  /** 占位内容（默认 ImageOff 图标）。 */
  placeholder?: ReactNode;
};

export function AssetPreview({
  assetId,
  enabled = true,
  alt,
  aspectClass = "aspect-square",
  className,
  placeholder,
}: Props) {
  const [url, setUrl] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let cancelled = false;
    let objectUrl: string | null = null;
    const id = assetId === null || assetId === undefined ? "" : String(assetId).trim();
    if (!enabled || id === "") {
      setUrl(null);
      setLoading(false);
      setFailed(false);
      return;
    }
    setLoading(true);
    setFailed(false);
    setUrl(null);
    fetch(`${API_BASE}/api/assets/${encodeURIComponent(id)}/preview?ts=${Date.now()}`, {
      credentials: "include",
      cache: "no-store",
    })
      .then((res) => {
        if (!res.ok) throw new Error(`preview http ${res.status}`);
        return res.blob();
      })
      .then((blob) => {
        if (cancelled) return;
        objectUrl = URL.createObjectURL(blob);
        setUrl(objectUrl);
        setLoading(false);
      })
      .catch(() => {
        if (!cancelled) {
          setFailed(true);
          setLoading(false);
        }
      });
    return () => {
      cancelled = true;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [assetId, enabled]);

  return (
    <div className={cn("relative grid place-items-center overflow-hidden bg-white", aspectClass, className)}>
      {url ? (
        // eslint-disable-next-line @next/next/no-img-element —— blob URL（非远程地址）
        <img
          src={url}
          alt={alt ?? `素材 ${assetId} 预览`}
          className="h-full w-full object-contain"
        />
      ) : loading ? (
        <Loader2 size={20} className="animate-spin text-zinc-300" />
      ) : (
        (placeholder ?? (
          <div className="grid place-items-center text-zinc-300">
            <ImageOff size={32} />
          </div>
        ))
      )}
    </div>
  );
}
