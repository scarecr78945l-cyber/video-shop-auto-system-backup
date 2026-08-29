"""M0 基座备份协议：SHA-256 清单（MANIFEST.json）机制（P2-4）。

对齐旧系统机制（《旧系统第二波融合清单》P2-4：迁移包 SHA-256 清单机制，数据可追溯）：
- 旧 `backend/runtime/build_material_manifest.py`：清单含 local_path + size_bytes + policy；
- 旧 `tools/migration_audit.py`：迁移数据完整性与敏感配置审计；
- 本模块为通用版：为关键交付物（schema DDL / 迁移脚本 / 词表 / 语料）生成 SHA-256 校验清单，
  备份/迁移/交接后可用 verify 校验完整性（防篡改 / 防漏拷 / 防损坏）。

用法（代码）：
    manifest = build_manifest(files, base_dir=Path("."), meta={"policy": "..."})
    save_manifest(manifest, Path("MANIFEST.json"))
    result = verify_manifest(Path("MANIFEST.json"), base_dir=Path("."))
    assert result.ok

用法（CLI，见 __main__.py）：
    python -m foundation manifest build -o MANIFEST.json --base-dir . file1 file2
    python -m foundation manifest verify -m MANIFEST.json --base-dir .
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Iterable

MANIFEST_FORMAT = "m0-manifest-v1"
_HASH_CHUNK_BYTES = 1024 * 1024


def sha256_file(path: Path | str) -> str:
    """分块计算文件 SHA-256（1 MiB 块，大文件安全）。"""
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(_HASH_CHUNK_BYTES), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _resolve_under_base(file: Path | str, base: Path) -> Path:
    """相对路径按 base 解析（与 cwd 解耦）；绝对路径原样。"""
    raw = Path(file)
    return (base / raw).resolve() if not raw.is_absolute() else raw.resolve()


def _rel_posix(path: Path, base_dir: Path) -> str:
    return PurePosixPath(path.relative_to(base_dir)).as_posix()


def build_manifest(
    files: Iterable[Path | str],
    *,
    base_dir: Path | str | None = None,
    title: str = "",
    meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """生成 MANIFEST.json 结构（确定性：files 按相对路径排序）。

    - files：待校验文件列表；文件必须存在（缺失抛 FileNotFoundError——清单必须完整）；
    - base_dir：相对路径基准（默认当前工作目录）；清单内 path 一律 posix 相对路径，可移植；
    - title / meta：业务说明（对齐旧系统 policy/gate 语义的扩展点，
      如 {"policy": "...", "next_gate": "..."}，禁止写明文密钥）；
    重复相对路径 → ValueError。
    """
    base = Path(base_dir or ".").resolve()
    seen: set[str] = set()
    entries: list[dict[str, Any]] = []
    for f in files:
        p = _resolve_under_base(f, base)
        rel = _rel_posix(p, base)
        if rel in seen:
            raise ValueError(f"重复路径：{rel}")
        seen.add(rel)
        entries.append(
            {"path": rel, "sha256": sha256_file(p), "size_bytes": p.stat().st_size}
        )
    entries.sort(key=lambda e: e["path"])
    return {
        "format": MANIFEST_FORMAT,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "tool": "foundation.manifest",
        "title": title,
        "meta": meta or {},
        "files": entries,
    }


def save_manifest(manifest: dict[str, Any], path: Path | str) -> None:
    """清单落盘（UTF-8、ensure_ascii=False、缩进 + 末尾换行）。"""
    Path(path).write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def load_manifest(path: Path | str) -> dict[str, Any]:
    """读取清单并校验 format（不匹配抛 ValueError）。"""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if data.get("format") != MANIFEST_FORMAT:
        raise ValueError(f"非 {MANIFEST_FORMAT} 清单：{path}")
    return data


@dataclass
class ManifestVerification:
    """校验结果：不抛异常，聚合全部问题（missing/mismatch 均列出）。"""

    ok: bool
    total: int
    matched: int
    missing: int
    mismatched: int
    errors: list[str] = field(default_factory=list)
    files: list[dict[str, Any]] = field(default_factory=list)


def verify_manifest(
    manifest: dict[str, Any] | Path | str,
    *,
    base_dir: Path | str | None = None,
) -> ManifestVerification:
    """校验清单：文件存在性 + SHA-256 一致性。

    - 缺失文件 → missing；哈希不一致 → mismatch；两类问题均聚合返回不中断；
    - base_dir 默认当前工作目录（与 build 默认一致；校验时按需传入生成时基准）。
    """
    data = (
        load_manifest(manifest) if isinstance(manifest, (Path, str)) else manifest
    )
    if data.get("format") != MANIFEST_FORMAT:
        raise ValueError(f"非 {MANIFEST_FORMAT} 清单")
    base = Path(base_dir or ".").resolve()
    result = ManifestVerification(
        ok=True, total=0, matched=0, missing=0, mismatched=0
    )
    for entry in data.get("files", []):
        rel = entry.get("path", "")
        expected = entry.get("sha256")
        result.total += 1
        p = base / rel
        if not p.exists():
            result.missing += 1
            result.ok = False
            result.files.append(
                {"path": rel, "status": "missing", "expected_sha256": expected, "actual_sha256": None}
            )
            result.errors.append(f"缺失文件：{rel}")
            continue
        actual = sha256_file(p)
        if actual != expected:
            result.mismatched += 1
            result.ok = False
            result.files.append(
                {"path": rel, "status": "mismatch", "expected_sha256": expected, "actual_sha256": actual}
            )
            result.errors.append(f"哈希不一致：{rel}")
        else:
            result.matched += 1
            result.files.append(
                {"path": rel, "status": "ok", "expected_sha256": expected, "actual_sha256": actual}
            )
    return result


__all__ = [
    "MANIFEST_FORMAT",
    "sha256_file",
    "build_manifest",
    "save_manifest",
    "load_manifest",
    "verify_manifest",
    "ManifestVerification",
]
