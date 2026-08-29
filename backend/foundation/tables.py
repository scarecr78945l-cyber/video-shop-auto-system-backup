"""M0 基座与数据治理：共享表 ORM。

对齐 `_management/modules/m0-foundation/database/README.md` 五表最终 DDL（v0.2）：
workflow_jobs / tasks / logs / app_config / error_codes（无前缀，归属 M0，全员只读）。

数据口径（总控裁决 REC-005 / DA-001）：
- 金额一律「分」int 存储（含 JSON 内金额），展示层转元；
- 时间一律 UTC（ISO8601 带时区），时间戳字段后缀 `_at`，展示层转 UTC+8。
字段命名与 DDL 一致：重试时间 `retry_after`、结果证据 `evidence_json`。
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy import types


def utcnow() -> datetime:
    """统一 UTC 时间（REC-005）。SQLite 存 naive UTC（近似），PostgreSQL TIMESTAMPTZ 真带时区。"""
    return datetime.now(timezone.utc)


class AwareUTCDateTime(types.TypeDecorator):
    """强制 aware UTC 的时间列类型（REC-005：时间一律 UTC 带时区）。

    SQLite 无时区类型：存储时转 naive UTC（近似 ISO8601），读取时补回 UTC tzinfo，
    保证 Python 层永远得到 aware UTC，杜绝 naive/aware 混用（TypeError）。
    PostgreSQL 的 TIMESTAMPTZ 原生带时区，此装饰器对读取结果补 tzinfo（幂等）。
    """

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect):
        if value is not None and value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value

    def process_result_value(self, value: datetime | None, dialect):
        if value is not None and value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value


class Base(DeclarativeBase):
    pass


class WorkflowJob(Base):
    """任务队列主表（09 文档第二节；最终 DDL v0.2）。

    租约 45min（config.lease_minutes 可配，lease_expires_at 过期回收）；
    幂等键 (product_id, stage, generation_version)；
    失败隔离：waiting_*/blocked 等状态不被 claim，不阻塞其他 job 排队。
    """

    __tablename__ = "workflow_jobs"
    __table_args__ = (
        UniqueConstraint(
            "product_id", "stage", "generation_version", name="uq_wj_idempotency"
        ),
        Index("idx_wj_status", "status"),
        Index("idx_wj_stage", "stage"),
        Index("idx_wj_retry", "retry_after"),
        Index("idx_wj_lease", "lease_expires_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    product_id: Mapped[int] = mapped_column(Integer, nullable=False)  # 跨库业务引用，不建 FK 防跨库
    stage: Mapped[str] = mapped_column(String(40), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    error_code: Mapped[str | None] = mapped_column(String(40), nullable=True)  # 见 error_codes 表
    error_message: Mapped[str] = mapped_column(Text, default="")
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)  # 已重试次数
    retry_after: Mapped[datetime | None] = mapped_column(  # 下次可重试时间（UTC；error_codes.backoff_seconds 计算）
        AwareUTCDateTime(), nullable=True
    )
    lease_owner: Mapped[str | None] = mapped_column(String(120), nullable=True)  # 租约持有者（worker id）
    lease_expires_at: Mapped[datetime | None] = mapped_column(  # 租约过期时间（45min，过期回收）
        AwareUTCDateTime(), nullable=True
    )
    generation_version: Mapped[str] = mapped_column(String(40), nullable=False, default="v1")
    payload: Mapped[dict] = mapped_column(JSON, default=dict)  # 入队参数/断点；JSON 内金额按分 int（REC-005）
    evidence_json: Mapped[dict] = mapped_column(JSON, default=dict)  # 结果证据（09/02 文档 evidence_json 留痕）
    created_at: Mapped[datetime] = mapped_column(AwareUTCDateTime(), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        AwareUTCDateTime(), default=utcnow, onupdate=utcnow
    )


class Task(Base):
    """任务明细/子任务（最终 DDL v0.2；job_id 归属 workflow_jobs，跨库暂不建 FK）。"""

    __tablename__ = "tasks"
    __table_args__ = (
        UniqueConstraint("job_id", "task_type", name="uq_tk_idempotency"),  # 同一 job 下同类型子任务唯一
        Index("idx_tk_job", "job_id"),
        Index("idx_tk_status", "status"),
        Index("idx_tk_retry", "retry_after"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_id: Mapped[int] = mapped_column(Integer, nullable=False)  # 任务归属（workflow_jobs.id）
    stage: Mapped[str] = mapped_column(String(40), nullable=False)  # 与 workflow_jobs.stage 同枚举
    task_type: Mapped[str] = mapped_column(String(60), nullable=False, default="")
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    error_code: Mapped[str | None] = mapped_column(String(40), nullable=True)
    error_message: Mapped[str] = mapped_column(Text, default="")
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    retry_after: Mapped[datetime | None] = mapped_column(AwareUTCDateTime(), nullable=True)
    lease_owner: Mapped[str | None] = mapped_column(String(120), nullable=True)
    lease_expires_at: Mapped[datetime | None] = mapped_column(AwareUTCDateTime(), nullable=True)
    payload: Mapped[dict] = mapped_column(JSON, default=dict)  # 金额按分 int（REC-005）
    evidence_json: Mapped[dict] = mapped_column(JSON, default=dict)  # 结果证据（留痕）
    created_at: Mapped[datetime] = mapped_column(AwareUTCDateTime(), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        AwareUTCDateTime(), default=utcnow, onupdate=utcnow
    )


class LogEntry(Base):
    """操作留痕（脱敏：evidence 写入前必须经 _redact_text）。"""

    __tablename__ = "logs"
    __table_args__ = (Index("idx_logs_module_ts", "module", "created_at"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    created_at: Mapped[datetime] = mapped_column(AwareUTCDateTime(), default=utcnow)
    module: Mapped[str] = mapped_column(String(20), nullable=False)  # m0/m1/.../m5
    level: Mapped[str] = mapped_column(String(10), nullable=False)
    event: Mapped[str] = mapped_column(String(120), default="")
    message: Mapped[str] = mapped_column(Text, default="")
    evidence: Mapped[dict] = mapped_column(JSON, default=dict)  # 敏感字段写入前必须 _redact_text


class AppConfigRow(Base):
    """全局配置（键值+JSON，M0 拥有，全员只读）。

    与 backend/sourcing/tables.py 的 AppConfigRow 同构，键约定统一；物理库归属随迁移包整合。
    金额类配置按「分」int（REC-005）。
    """

    __tablename__ = "app_config"

    key: Mapped[str] = mapped_column(String(120), primary_key=True)
    value: Mapped[dict] = mapped_column(JSON, default=dict)  # 值一律 JSON；金额类配置按分 int
    description: Mapped[str] = mapped_column(String(500), default="")
    updated_at: Mapped[datetime] = mapped_column(
        AwareUTCDateTime(), default=utcnow, onupdate=utcnow
    )


class ErrorCode(Base):
    """错误码 → 重试策略映射（M0 唯一权威，宪法第 8 节，对齐 09 文档错误码表）。"""

    __tablename__ = "error_codes"

    code: Mapped[str] = mapped_column(String(40), primary_key=True)
    retryable: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    backoff_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    action: Mapped[str] = mapped_column(String(60), nullable=False)  # retry|manual_takeover|block_forever
    description: Mapped[str] = mapped_column(String(300), default="")


class LearningRuleDraft(Base):
    """REC-融合 P0-2：人审→规则草稿闭环（旧系统 learning_rule_drafts 迁移）。

    人工审核决定（approve/reject + 理由）→ 沉淀为规则草稿 → 人工确认后生效
    （status: draft → active）；草稿按 stage 聚类（素材规格/文案/主图/上架）。
    规则文本 rule_text 为自然语言/JSON 规则描述，命中判定由对应模块实现。
    """

    __tablename__ = "learning_rule_drafts"
    __table_args__ = (
        UniqueConstraint("stage", "rule_key", name="uq_rule_draft_stage_key"),
        Index("idx_rule_drafts_status", "status"),
    )

    draft_id: Mapped[str] = mapped_column(String(40), primary_key=True)
    stage: Mapped[str] = mapped_column(String(40), nullable=False)  # 对齐 STAGE_VALUES 语义
    rule_key: Mapped[str] = mapped_column(String(120), nullable=False)  # 规则标识（幂等键）
    rule_text: Mapped[str] = mapped_column(Text, nullable=False)  # 规则描述（JSON/自然语言）
    sample_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="draft")  # draft|active|rejected
    evidence: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON 证据（含脱敏摘要）
    created_at: Mapped[str] = mapped_column(String(40), nullable=False)
    updated_at: Mapped[str] = mapped_column(String(40), nullable=False)


# 任务阶段（09 文档第二节 stage 枚举；workflow_jobs/tasks.stage 共用）
STAGE_VALUES: list[str] = [
    "source_collect",      # 选品采集（调度器驱动）
    "alibaba_quote",       # 1688 逐 SKU 询价
    "taobao_reference",    # 淘宝素材参考
    "image_generation",    # 生图
    "listing_upload",      # 上架（OpenAPI 主 / UI 兜底）
    "shop_ads_run",        # 托管投放执行
    "shop_ads_report",     # 投放报表回读
]

# 任务状态（workflow_jobs/tasks.status 共用）
JOB_STATUSES: list[str] = [
    "pending", "running", "waiting_login", "waiting_verification",
    "blocked", "success", "failed", "cancelled",
]

ERROR_CODE_SEEDS: list[dict] = [
    {"code": "VERIFICATION_REQUIRED", "retryable": False, "backoff_seconds": 0, "action": "manual_takeover", "description": "验证码/安全验证：单任务暂停 60min 等人工"},
    {"code": "AUTH_REQUIRED", "retryable": False, "backoff_seconds": 0, "action": "manual_takeover", "description": "登录失效：人工登录后断点续跑"},
    {"code": "RATE_LIMIT", "retryable": True, "backoff_seconds": 180, "action": "retry", "description": "限流/频繁：180s 退避"},
    {"code": "TIMEOUT", "retryable": True, "backoff_seconds": 60, "action": "retry", "description": "超时：60s 退避"},
    {"code": "NO_MATCH", "retryable": True, "backoff_seconds": 120, "action": "retry", "description": "无同款：120s 退避"},
    {"code": "INSUFFICIENT_REFERENCES", "retryable": True, "backoff_seconds": 120, "action": "retry", "description": "素材/参考不足：120s 退避"},
    {"code": "PLATFORM_REJECT", "retryable": False, "backoff_seconds": 0, "action": "block_forever", "description": "平台驳回（资质/内容）：记录原因转人工/修复候选"},
    {"code": "UNEXPECTED", "retryable": True, "backoff_seconds": 60, "action": "retry", "description": "未知错误：60s 退避，留证据"},
    {"code": "PAGE_CHANGED", "retryable": True, "backoff_seconds": 120, "action": "retry", "description": "页面改版：选择器失效，留证据（P-003）"},
]


def seed_error_codes(session) -> int:
    """幂等写入错误码种子：已存在的 code 跳过（不覆盖运行时调整），返回新增条数。"""
    added = 0
    for spec in ERROR_CODE_SEEDS:
        if session.get(ErrorCode, spec["code"]) is None:
            session.add(ErrorCode(**spec))
            added += 1
    return added


class AdminUserRow(Base):
    """M6 管理后台用户（REC：鉴权会话表挂 M0，跨模块共享；API 层只消费）。

    - password_hash = SHA-256 hex（M6 api/auth.py 约定，m0 模式由本表校验）；
    - 默认管理员由环境变量 ADMIN_PASSWORD 播种（未设置→跳过并告警，生产必配）。
    """

    __tablename__ = "admin_users"
    __table_args__ = (Index("idx_admin_users_enabled", "enabled"),)

    username: Mapped[str] = mapped_column(String(80), primary_key=True)
    password_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    role: Mapped[str] = mapped_column(String(30), nullable=False, default="admin")
    enabled: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[str] = mapped_column(String(40), nullable=False)
    updated_at: Mapped[str] = mapped_column(String(40), nullable=False)


class AuthSessionRow(Base):
    """管理后台登录会话（token 主键，过期自动失效；M6 AuthStore m0 模式消费）。"""

    __tablename__ = "auth_sessions"
    __table_args__ = (Index("idx_auth_sessions_user", "username"),)

    token: Mapped[str] = mapped_column(String(64), primary_key=True)
    username: Mapped[str] = mapped_column(String(80), nullable=False)
    expires_at: Mapped[str] = mapped_column(String(40), nullable=False)
    created_at: Mapped[str] = mapped_column(String(40), nullable=False)
