"""M3 上传素材库 upload · 工厂（REC-002 双轨创建入口）。

``create_uploader(mode=None)``：显式 mode（api|ui|semi，大小写不敏感）或
取 config.upload.mode（环境变量 M3_UPLOAD_MODE）；非法 mode 抛 ValueError。
fixtures 阶段所有实现可 mock 注入（api 注 post、ui 注 page_ops），零网络零浏览器。
"""

from __future__ import annotations

from typing import Any, Optional

from ..config import load_config
from .api import ApiUploader
from .semi import SemiUploader
from .service import UploadService
from .ui import UiUploader

VALID_MODES = ("api", "ui", "semi")


def create_uploader(
    mode: Optional[str] = None,
    *,
    config=None,
    db=None,
    post=None,
    page_ops=None,
    **kwargs: Any,
) -> UploadService:
    """按 mode（显式或 config.upload.mode）返回对应 UploadService 实现。

    - mode=None → config.upload.mode（默认 api）；
    - "api" → ApiUploader（post 可注入，缺省内置 mock）；
    - "ui"  → UiUploader（page_ops 可注入，缺省 MockPageOps）；
    - "semi" → SemiUploader（半自动降级）；
    - 其余 → ValueError（REC-002 可选值之外）。
    """
    cfg = config or load_config()
    m = (mode if mode not in (None, "") else cfg.upload.mode or "api").strip().lower()
    if m == "api":
        return ApiUploader(cfg, db=db, post=post, **kwargs)
    if m == "ui":
        return UiUploader(cfg, db=db, page_ops=page_ops, **kwargs)
    if m == "semi":
        return SemiUploader(cfg, db=db, **kwargs)
    raise ValueError(f"非法 upload mode: {mode!r}（可选 {VALID_MODES}，REC-002）")
