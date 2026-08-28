"""M3 上传素材库 upload · 小店素材库上传（REC-002 双轨 UploadService）。

v1.0 集成任务 3（子代理-F）：api（OpenAPI 假设 mock）｜ ui（Playwright 兜底
抽象，PageOps 注入）｜ semi（半自动预填清单）。全部 fixtures/模拟，零真实网络、
零真实浏览器（post / page_ops 可注入）；成功/失败/待人工统一落 opt_upload_records
（batch_no ≤50 递增）；upload_batch 提供 ≤50/批串行编排入口（P-006）。
"""

from __future__ import annotations

from .api import ApiUploader, UploadApiError
from .factory import VALID_MODES, create_uploader
from .repo import UploadRepo
from .semi import (
    DEFAULT_CONFIRM_POINTS,
    SemiManifest,
    SemiManifestEntry,
    SemiUploader,
)
from .service import (
    ERR_AUTH_REQUIRED,
    ERR_NO_MATCH,
    ERR_PLATFORM_REJECT,
    ERR_RATE_LIMIT,
    ERR_TIMEOUT,
    ERR_UNEXPECTED,
    VALID_ERROR_CODES,
    UploadResult,
    UploadService,
    derive_target_id,
    deterministic_material_id,
    hash8,
    upload_batch,
)
from .ui import (
    DEFAULT_SELECTORS,
    FAIL_TEXT,
    MockPageOps,
    PageChangedError,
    PageOps,
    UiUploader,
)

__all__ = [
    # 抽象与结果
    "UploadService",
    "UploadResult",
    "VALID_ERROR_CODES",
    "ERR_AUTH_REQUIRED",
    "ERR_RATE_LIMIT",
    "ERR_TIMEOUT",
    "ERR_PLATFORM_REJECT",
    "ERR_UNEXPECTED",
    "ERR_NO_MATCH",
    # 实现
    "ApiUploader",
    "UploadApiError",
    "UiUploader",
    "PageOps",
    "MockPageOps",
    "PageChangedError",
    "DEFAULT_SELECTORS",
    "FAIL_TEXT",
    "SemiUploader",
    "SemiManifest",
    "SemiManifestEntry",
    "DEFAULT_CONFIRM_POINTS",
    # 工厂与编排
    "create_uploader",
    "upload_batch",
    "VALID_MODES",
    # 落库
    "UploadRepo",
    # 工具
    "deterministic_material_id",
    "derive_target_id",
    "hash8",
]
