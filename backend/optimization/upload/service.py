"""M3 上传素材库 upload · 抽象基类与编排入口（v1.0 集成任务 3 · 子代理-F）。

REC-002 双轨 UploadService：``M3_UPLOAD_MODE=api|ui|semi``（默认 api 优先、
Playwright 兜底、半自动降级）。真实可用性待用户提供小店账号后实测，
本实现全部 fixtures/模拟（零真实网络、零真实浏览器，post/page_ops 可注入）。

- ``UploadResult``：上传结果统一模型（platform_material_id / platform_evaluation /
  status / error_code / evidence），error_code 复用 WorkflowJob 错误码表
  （AUTH_REQUIRED / RATE_LIMIT / TIMEOUT / PLATFORM_REJECT / UNEXPECTED / NO_MATCH）。
- ``UploadService``：抽象基类 —— ``upload_video(file_path, meta)`` /
  ``upload_image(file_path, meta)`` → UploadResult；构造可选 db/repo，成功后由
  子类经 ``_persist`` 写 opt_upload_records。
- ``deterministic_material_id``：确定性素材 ID（material_<hash8>，fixtures 模拟用）。
- ``upload_batch``：≤50/批串行编排入口（P-006），batch_no 递增、单条失败隔离。
"""

from __future__ import annotations

import hashlib
import json
import time
import uuid
from abc import ABC, abstractmethod
from typing import Any, Callable, Optional

from pydantic import BaseModel, Field, field_validator

from .repo import UploadRepo


def _load_cfg(config=None):
    """config 缺省时按 M3Config 默认加载（环境变量 M3_UPLOAD_MODE 生效）。"""
    if config is not None:
        return config
    from ..config import load_config

    return load_config()

# ---------------------------------------------------------------- 错误码（复用 WorkflowJob 表）

ERR_AUTH_REQUIRED = "AUTH_REQUIRED"          # 登录态失效，不自动重试 → 转人工（P-002）
ERR_RATE_LIMIT = "RATE_LIMIT"                # 平台节流，180s 退避重试（P-006）
ERR_TIMEOUT = "TIMEOUT"                      # 请求/等待超时
ERR_PLATFORM_REJECT = "PLATFORM_REJECT"      # 平台拒审/不支持（P-007）
ERR_UNEXPECTED = "UNEXPECTED"                # 未预期异常
ERR_NO_MATCH = "NO_MATCH"                    # 页面结构/素材不匹配（page_changed，P-003）

VALID_ERROR_CODES = frozenset({
    ERR_AUTH_REQUIRED,
    ERR_RATE_LIMIT,
    ERR_TIMEOUT,
    ERR_PLATFORM_REJECT,
    ERR_UNEXPECTED,
    ERR_NO_MATCH,
})

VALID_STATUSES = frozenset({"success", "failed", "waiting_manual"})

# ---------------------------------------------------------------- 结果模型


class UploadResult(BaseModel):
    """上传结果统一模型（task 硬性字段：platform_material_id/platform_evaluation/status/error_code/evidence）。"""

    status: str = "failed"                    # success / failed / waiting_manual
    platform_material_id: str = ""
    platform_evaluation: str = "exploration"  # 平台评估标签（探索期起步，06 文档）
    error_code: str = ""                      # 复用 WorkflowJob 错误码表
    evidence: dict[str, Any] = Field(default_factory=dict)

    @field_validator("status")
    @classmethod
    def _check_status(cls, v: str) -> str:
        if v not in VALID_STATUSES:
            raise ValueError(f"非法 status: {v!r}（可选 {sorted(VALID_STATUSES)}）")
        return v

    @field_validator("error_code")
    @classmethod
    def _check_error_code(cls, v: str) -> str:
        if v and v not in VALID_ERROR_CODES:
            raise ValueError(f"未知错误码: {v!r}（可选 {sorted(VALID_ERROR_CODES)}）")
        return v

    @property
    def ok(self) -> bool:
        return self.status == "success"


# ---------------------------------------------------------------- 通用工具


def hash8(text: str) -> str:
    """sha256 前 8 位十六进制（确定性短哈希）。"""
    return hashlib.sha256(str(text).encode("utf-8")).hexdigest()[:8]


def deterministic_material_id(file_path: str, meta: dict[str, Any]) -> str:
    """确定性素材 ID：material_<hash8>（fixtures 模拟；同 file_path+meta 幂等）。"""
    payload = json.dumps(
        {"file_path": str(file_path), "meta": meta or {}},
        sort_keys=True,
        ensure_ascii=False,
    )
    return f"material_{hash8(payload)}"


def derive_target_id(meta: dict[str, Any], file_path: str) -> str:
    """target_id 推导：优先取 meta 中已有主键（variant_id/image_id/asset_id/target_id），
    否则用 file_path 短哈希兜底。"""
    meta = meta or {}
    for key in ("target_id", "variant_id", "image_id", "asset_id"):
        if meta.get(key):
            return str(meta[key])
    return f"file_{hash8(str(file_path))}"


# ---------------------------------------------------------------- 抽象基类


class UploadService(ABC):
    """上传抽象基类（REC-002 双轨）。子类必须实现 upload_video/upload_image。"""

    mode: str = "abstract"

    def __init__(self, config=None, db=None, repo: Optional[UploadRepo] = None):
        self.config = _load_cfg(config)
        self.db = db
        self.repo = repo or (UploadRepo(db) if db is not None else None)

    @abstractmethod
    def upload_video(
        self,
        file_path: str,
        meta: dict[str, Any],
        *,
        target_id: Optional[str] = None,
        batch_no: int = 1,
        batch_id: Optional[str] = None,
    ) -> UploadResult:
        """上传视频素材 → UploadResult。"""

    @abstractmethod
    def upload_image(
        self,
        file_path: str,
        meta: dict[str, Any],
        *,
        target_id: Optional[str] = None,
        batch_no: int = 1,
        batch_id: Optional[str] = None,
    ) -> UploadResult:
        """上传图片素材 → UploadResult。"""

    # ---------- 内部工具 ----------

    def _persist(
        self,
        target_type: str,
        target_id: str,
        result: UploadResult,
        batch_no: int = 1,
    ) -> Optional[str]:
        """有 db/repo 时写 opt_upload_records；无则跳过（fixtures 纯计算模式）。"""
        if self.repo is None:
            return None
        return self.repo.record(
            target_type=target_type,
            target_id=target_id,
            result=result,
            batch_no=batch_no,
            mode=self.mode,
        )


# ---------------------------------------------------------------- 批量编排（≤50/批串行）


def upload_batch(
    service: UploadService,
    items: list[Any],
    *,
    db=None,
    batch_size: Optional[int] = None,
    target_type: Optional[str] = None,
    sleep_fn: Optional[Callable[[float], None]] = None,
    item_interval_s: float = 0.0,
) -> dict[str, Any]:
    """≤50/批串行上传编排（P-006）：batch_no 递增、单条失败不阻塞整批。

    items：list[dict]，每项含 file_path（必填）+ meta（可选）+ target_type（可选，
    video/image）；也兼容裸路径字符串。target_type 未给时用 batch 级 target_type，
    再缺省 "video"。

    返回统计 {mode,total,batch_size,batch_ids,success,failed,waiting_manual,results}；
    results 每项含 file_path/target_type/batch_no/batch_id/status/error_code/
    platform_material_id。失败隔离：service 抛异常 → 捕获记 UNEXPECTED 继续。
    """
    if not isinstance(service, UploadService):
        raise ValueError(f"service 必须是 UploadService 实例，got {type(service).__name__}")
    cfg = service.config
    batch_size = int(batch_size) if batch_size is not None else int(cfg.upload.batch_size)
    if not 1 <= batch_size <= 50:
        raise ValueError(f"batch_size 必须 1~50（P-006 ≤50/批），got {batch_size}")
    sleep_fn = sleep_fn or time.sleep

    normalized = [_normalize_item(it, target_type) for it in items]
    repo = service.repo or (UploadRepo(db) if db is not None else None)

    chunks = [
        normalized[i : i + batch_size] for i in range(0, len(normalized), batch_size)
    ]
    batch_ids: list[str] = []
    results: list[dict[str, Any]] = []
    counts = {"success": 0, "failed": 0, "waiting_manual": 0}

    for chunk in chunks:
        batch_id = f"upb_{uuid.uuid4().hex[:8]}"
        batch_ids.append(batch_id)
        for batch_no, item in enumerate(chunk, start=1):
            item_result = _run_one(service, item, repo, batch_no=batch_no, batch_id=batch_id)
            results.append(item_result)
            counts[item_result["status"]] = counts.get(item_result["status"], 0) + 1
            if item_interval_s > 0 and not (
                batch_no == len(chunk) and chunk is chunks[-1]
            ):
                sleep_fn(float(item_interval_s))

    return {
        "mode": service.mode,
        "total": len(normalized),
        "batch_size": batch_size,
        "batch_ids": batch_ids,
        "success": counts["success"],
        "failed": counts["failed"],
        "waiting_manual": counts["waiting_manual"],
        "results": results,
    }


def _normalize_item(item: Any, default_target_type: Optional[str]) -> dict[str, Any]:
    if isinstance(item, str):
        return {"file_path": str(item), "meta": {}, "target_type": default_target_type or "video"}
    if not isinstance(item, dict) or not item.get("file_path"):
        raise ValueError(f"item 必须是 dict（含 file_path）或路径字符串: {item!r}")
    ttype = str(item.get("target_type") or default_target_type or "video")
    if ttype not in ("video", "image"):
        raise ValueError(f"非法 target_type: {ttype!r}（可选 video/image）")
    return {
        "file_path": str(item["file_path"]),
        "meta": dict(item.get("meta") or {}),
        "target_type": ttype,
    }


def _run_one(
    service: UploadService,
    item: dict[str, Any],
    repo: Optional[UploadRepo],
    *,
    batch_no: int,
    batch_id: str,
) -> dict[str, Any]:
    file_path, meta, ttype = item["file_path"], item["meta"], item["target_type"]
    try:
        if ttype == "image":
            result = service.upload_image(file_path, meta, batch_no=batch_no, batch_id=batch_id)
        else:
            result = service.upload_video(file_path, meta, batch_no=batch_no, batch_id=batch_id)
    except Exception as exc:  # noqa: BLE001 —— 单条失败隔离，不阻塞整批
        result = UploadResult(
            status="failed",
            error_code=ERR_UNEXPECTED,
            evidence={
                "error": f"{type(exc).__name__}: {exc}",
                "file_path": file_path,
                "batch_id": batch_id,
                "isolated": True,
            },
        )
        if repo is not None:
            repo.record(
                target_type=ttype,
                target_id=derive_target_id(meta, file_path),
                result=result,
                batch_no=batch_no,
                mode=service.mode,
            )
    return {
        "file_path": file_path,
        "target_type": ttype,
        "batch_no": batch_no,
        "batch_id": batch_id,
        "status": result.status,
        "error_code": result.error_code,
        "platform_material_id": result.platform_material_id,
    }
