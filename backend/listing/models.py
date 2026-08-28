"""M4 自动上架领域模型（pydantic v2）。

ListingTask 字段与 database/README.md DDL v0 的 listing_tasks 表一一对应；
时间戳一律 ISO8601 UTC 文本（TEXT `_at` 列），与模块库统一口径。
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from pydantic import BaseModel, Field


def utcnow_iso() -> str:
    """当前 UTC 时间的 ISO8601 文本（统一格式，保证文本字典序=时间序）。"""
    return datetime.now(timezone.utc).isoformat()


class ListingTask(BaseModel):
    """一条上架任务（listing_tasks 表行，状态机主表）。"""

    task_id: str  # = workflow_jobs 关联 ID
    product_id: int  # 基座 products.id（M1）
    generation_version: str  # 幂等键组成（M1/M3 版本号）
    stage: str = "listing_upload"  # 流水线阶段（对接 workflow_jobs.stage）
    status: str = "pending"  # 状态机状态（见 context/README.md 第二节枚举）
    gate_result: Optional[dict[str, Any]] = None  # 上架前校验硬门禁结果
    platform_spu_id: Optional[str] = None  # create_spu 返回
    product_link: Optional[str] = None  # 真实链接，验证通过前为空（R22）
    link_verified_at: Optional[str] = None  # 链接验证通过时间（已上架判据）
    reject_reason_code: Optional[str] = None  # 拒审原因分类码
    attempts: int = 0  # 已尝试次数（幂等重试/重新提交计数）
    lease_owner: Optional[str] = None  # 任务租约持有者
    lease_expires_at: Optional[str] = None  # 租约过期时间（45min 回收）
    created_at: str = Field(default_factory=utcnow_iso)
    updated_at: str = Field(default_factory=utcnow_iso)


class ListingOpLog(BaseModel):
    """一条微信操作日志（listing_op_logs 行，证据留痕只读视图）。

    仅用于回查/断言；写入统一走 ListingRepo.append_op_log。
    """

    log_id: int
    task_id: str
    request_id: str
    api: str
    direction: str  # request / response / transition
    payload_digest: Optional[str] = None  # 脱敏摘要，无密钥/无敏感值
    status_code: Optional[int] = None
    error_code: Optional[str] = None  # WorkflowJob 错误码
    platform_code: Optional[str] = None  # 平台业务错误码原样
    evidence_json: Optional[str] = None  # 证据 JSON（敏感字段脱敏）
    created_at: str
