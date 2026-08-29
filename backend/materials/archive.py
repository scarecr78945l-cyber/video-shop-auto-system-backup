"""M2 素材归档能力（旧系统 product-image-archive 插件思路落地，P2-5）。

对齐旧系统 Codex 插件「产品图片归档技能」（SKILL.md + archive_product_images.py）：
按商品维度把素材归档为可交付文件包 + 清单 MANIFEST.json（对齐 P2-4 SHA-256
清单机制，数据可追溯），供人工核对与下游使用。

落地要点：
- 商品维度键 `derive_product_key(source_url)`：纯函数，从素材 source_url 提取
  商品键（淘宝 `id=` / 1688 `offer/` / 其他平台规范化 host+path），不落库不改表
  （asset_items 无 product 字段；C3 相关性门并行推进中，避免表结构变更冲突）；
- 归档查询复用 repo.list_assets（新增 source_url_contains 过滤，product 维度列出）；
- 归档复制幂等：目标已存在且 sha256 一致 → 跳过；不一致 → error 不覆盖（防数据异常）；
  单条失败隔离（R-M2-09 模式），不影响其他条；
- 清单每条含 sha256（P2-4 机制）+ 溯源字段（asset_id/source_url/source_author/
  file_path），满足宪法第 8 节「操作留证据」。
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Optional
from urllib.parse import parse_qs, urlparse, urlunparse

from .config import MaterialsConfig, load_config
from .storage import LocalStorage, Storage

# 归档工具版本（写进 MANIFEST，供溯源）
ARCHIVE_TOOL_VERSION = "m2-archive-1.0"


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def derive_product_key(source_url: str) -> str:
    """从素材 source_url 提取商品维度键（纯函数，归档分组/查询用）。

    - 淘宝：`https://item.taobao.com/item.htm?id=123456&xxx=1` → `taobao:123456`
    - 1688：`https://detail.1688.com/offer/123456789.html?spm=...` → `1688:123456789`
    - 其他：规范化 `scheme://netloc/path`（去 query/fragment、去尾斜杠）→ `web:...`
    - 解析失败/空 URL → `unknown`
    """
    if not source_url:
        return "unknown"
    try:
        parsed = urlparse(source_url.strip())
    except ValueError:
        return "unknown"
    netloc = (parsed.netloc or "").lower()
    if "taobao.com" in netloc or "tmall.com" in netloc:
        qs = parse_qs(parsed.query)
        item_id = (qs.get("id") or [None])[0]
        if item_id:
            return f"taobao:{item_id}"
        # 短链/无 id：退化 host+path
        return f"web:{parsed.scheme or 'https'}://{netloc}{parsed.path}"
    if "1688.com" in netloc:
        # /offer/123456789.html 或 /offer/123456789.html?spm=...
        parts = [p for p in parsed.path.split("/") if p]
        if len(parts) >= 2 and parts[0] == "offer":
            offer_id = parts[1].split(".")[0]
            if offer_id.isdigit():
                return f"1688:{offer_id}"
        return f"web:{parsed.scheme or 'https'}://{netloc}{parsed.path}"
    # 其他来源：规范化 scheme://netloc/path（去 query/fragment/尾斜杠）
    path = parsed.path.rstrip("/") or "/"
    normalized = urlunparse((parsed.scheme or "https", netloc, path, "", "", ""))
    return f"web:{normalized}"


class MaterialArchiver:
    """素材归档服务：product 维度查询 → 归档复制（幂等）→ MANIFEST 清单导出。"""

    def __init__(
        self,
        repo: Any,
        storage: Optional[Storage] = None,
        config: Optional[MaterialsConfig] = None,
    ):
        self.repo = repo
        self.config = config or load_config()
        self.storage = storage or LocalStorage(self.config.storage_dir)

    # ------------------------------------------------------------ 查询
    def list_product_assets(
        self,
        url_contains: str,
        source_platform: Optional[str] = None,
        limit: int = 500,
    ) -> list[dict[str, Any]]:
        """product 维度列出素材：复用 repo.list_assets（source_url_contains 过滤）。

        url_contains：source_url 子串（如 `id=123456` / `offer/123456789`），
        由调用方从商品 URL 提取；空子串返回空列表（防全表误扫）。
        """
        if not url_contains or not url_contains.strip():
            return []
        return self.repo.list_assets(
            source_url_contains=url_contains.strip(),
            source_platform=source_platform,
            limit=limit,
        )

    # ------------------------------------------------------------ 清单
    def build_manifest(self, assets: list[dict[str, Any]]) -> dict[str, Any]:
        """导出素材清单（对齐 P2-4 SHA-256 清单机制）。

        每条含 sha256（从存储读取文件计算；文件缺失 → error 字段标注，不中断）；
        空素材列表 → 空清单（entries=[]），不报错。
        """
        entries: list[dict[str, Any]] = []
        for a in assets:
            entry: dict[str, Any] = {
                "asset_id": a.get("id"),
                "asset_type": a.get("asset_type"),
                "source_platform": a.get("source_platform"),
                "source_url": a.get("source_url"),
                "source_author": a.get("source_author"),
                "file_path": a.get("file_path"),
                "size": a.get("size"),
                "created_at": a.get("created_at"),
                "sha256": None,
            }
            fp = a.get("file_path")
            if fp:
                try:
                    data = self.storage.read(fp)
                    entry["sha256"] = _sha256_bytes(data)
                except Exception as exc:  # 单条失败隔离：标注 error 不中断（R-M2-09）
                    entry["error"] = f"read_failed: {type(exc).__name__}"
            entries.append(entry)
        return {
            "tool": ARCHIVE_TOOL_VERSION,
            "format": "m2-material-archive-manifest",
            "entry_count": len(entries),
            "entries": entries,
        }

    # ------------------------------------------------------------ 归档
    def archive_product_assets(
        self,
        assets: list[dict[str, Any]],
        archive_dir: str | Path,
        product_key: Optional[str] = None,
    ) -> dict[str, Any]:
        """按商品归档素材到 archive_dir/<product_key>/，写 MANIFEST.json。

        幂等：目标文件已存在且 sha256 一致 → skipped；不一致 → error（不覆盖，防数据异常）；
        目标存在但源文件缺失 → error（不中断）；全部落盘后才写清单（失败不写半成品清单）。
        """
        if not assets:
            return {
                "product_key": product_key or "unknown",
                "archive_dir": str(archive_dir),
                "total": 0,
                "archived": 0,
                "skipped": 0,
                "errors": [],
                "manifest_path": None,
            }
        if product_key is None:
            product_key = derive_product_key(assets[0].get("source_url") or "")
        # Windows 路径安全：目录名中的非法字符（:?*"<>| 等）替换为 _（P2-5 归档
        # 集成测试暴露：taobao:123456 冒号在 Windows 非法）
        safe_key = "".join(
            c if c not in '\\/:*?"<>|' else "_" for c in product_key
        )
        base = Path(archive_dir) / safe_key
        base.mkdir(parents=True, exist_ok=True)

        archived_files: list[str] = []
        skipped_files: list[str] = []
        errors: list[dict[str, Any]] = []

        for a in assets:
            asset_id = a.get("id")
            fp = a.get("file_path")
            if not fp:
                errors.append({"asset_id": asset_id, "error": "missing_file_path"})
                continue
            try:
                data = self.storage.read(fp)
            except Exception as exc:
                errors.append(
                    {"asset_id": asset_id, "error": f"source_read_failed: {type(exc).__name__}"}
                )
                continue
            digest = _sha256_bytes(data)
            ext = Path(fp).suffix or ".bin"
            dest = base / f"{asset_id}{ext}"
            if dest.exists():
                if _sha256_bytes(dest.read_bytes()) == digest:
                    skipped_files.append(str(dest.relative_to(base)))
                    continue
                errors.append(
                    {"asset_id": asset_id, "error": "content_mismatch", "dest": str(dest)}
                )
                continue
            dest.write_bytes(data)
            archived_files.append(str(dest.relative_to(base)))

        manifest = self.build_manifest(assets)
        manifest_path = base / "MANIFEST.json"
        manifest_path.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
        )  # UTF-8 无 BOM（write_text 默认无 BOM；宪法第 11 节）

        return {
            "product_key": product_key,
            "archive_dir": str(base),
            "total": len(assets),
            "archived": len(archived_files),
            "skipped": len(skipped_files),
            "errors": errors,
            "manifest_path": str(manifest_path),
        }
