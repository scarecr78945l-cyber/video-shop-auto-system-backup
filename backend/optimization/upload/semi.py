"""M3 上传素材库 upload · SemiUploader（mode=semi，半自动降级）。

REC-002 最后兜底：系统生成预填清单（file_path + 预填字段 + 人工确认点），
返回 ``waiting_manual`` 状态，人工上传后回填素材 ID（断点续跑）。
不触碰任何平台接口/浏览器。
"""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field

from ..models import utcnow
from .service import UploadResult, UploadService, derive_target_id

# 默认人工确认点（人工闸门：内容合规/预填核对/上传动作/回填）
DEFAULT_CONFIRM_POINTS: list[str] = [
    "确认素材合规：无供应链词/品牌侵权/功效资质风险",
    "核对预填字段（标题/类目/规格）无误",
    "人工在小店素材库页面上传文件并确认提交",
    "上传完成后回填平台素材 ID（断点续跑）",
]


class SemiManifestEntry(BaseModel):
    """预填清单条目：file_path + 预填字段 + 人工确认点。"""

    file_path: str
    target_type: str = "video"              # video/image
    target_id: str = ""
    prefilled: dict[str, Any] = Field(default_factory=dict)
    confirm_points: list[str] = Field(default_factory=list)


class SemiManifest(BaseModel):
    """半自动预填清单（一批一个）。"""

    mode: str = "semi"
    batch_no: int = 1
    entries: list[SemiManifestEntry] = Field(default_factory=list)
    exported_at: str = ""


class SemiUploader(UploadService):
    """半自动降级：产出预填清单 + waiting_manual 状态（零平台交互）。"""

    mode = "semi"

    def __init__(self, config=None, db=None, repo=None, *, confirm_points: Optional[list[str]] = None):
        super().__init__(config, db, repo)
        self.confirm_points = (
            list(confirm_points) if confirm_points else list(DEFAULT_CONFIRM_POINTS)
        )

    # ---------------------------------------------------------------- 双轨接口

    def upload_video(self, file_path, meta, *, target_id=None, batch_no=1, batch_id=None):
        return self._upload("video", file_path, meta, target_id=target_id, batch_no=batch_no, batch_id=batch_id)

    def upload_image(self, file_path, meta, *, target_id=None, batch_no=1, batch_id=None):
        return self._upload("image", file_path, meta, target_id=target_id, batch_no=batch_no, batch_id=batch_id)

    # ---------------------------------------------------------------- 清单

    def build_manifest(
        self,
        items: list[dict[str, Any]],
        *,
        batch_no: int = 1,
        target_type: Optional[str] = None,
    ) -> SemiManifest:
        """生成预填清单：file_path + 预填字段（meta 非空值）+ 人工确认点。"""
        entries = [
            self._build_entry(
                str(item.get("target_type") or target_type or "video"),
                item["file_path"],
                item.get("meta") or {},
                item.get("target_id"),
                batch_no,
            )
            for item in items
        ]
        return SemiManifest(
            mode="semi",
            batch_no=int(batch_no),
            entries=entries,
            exported_at=utcnow().isoformat(),
        )

    # ---------------------------------------------------------------- 内部

    def _upload(self, target_type, file_path, meta, *, target_id, batch_no, batch_id):
        entry = self._build_entry(target_type, file_path, meta, target_id, batch_no)
        evidence: dict[str, Any] = {
            "mode": "semi",
            "manifest_entry": entry.model_dump(),
            "confirm_points": list(self.confirm_points),
            "pending_manual": True,   # 等待人工上传（断点续跑）
        }
        if batch_id:
            evidence["batch_id"] = batch_id
        result = UploadResult(
            status="waiting_manual",
            platform_material_id="",
            platform_evaluation="",   # 平台标签待人工上传后回填
            error_code="",
            evidence=evidence,
        )
        self._persist(target_type, entry.target_id, result, batch_no=batch_no)
        return result

    def _build_entry(self, target_type, file_path, meta, target_id, batch_no) -> SemiManifestEntry:
        meta = dict(meta or {})
        prefilled = {k: v for k, v in meta.items() if v not in (None, "")}
        prefilled.setdefault("file_name", str(file_path).replace("\\", "/").rsplit("/", 1)[-1])
        return SemiManifestEntry(
            file_path=str(file_path),
            target_type=str(target_type),
            target_id=target_id or derive_target_id(meta, file_path),
            prefilled=prefilled,
            confirm_points=list(self.confirm_points),
        )
