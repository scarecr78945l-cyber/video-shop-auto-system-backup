"""M2 自动收集素材模块 · ORM 表（asset_* 7 表，严格对齐 database/README.md DDL）。

DDL 唯一口径：_management/modules/m2-materials/database/README.md 第二节。
约定：时间戳 TEXT ISO8601 UTC（models.iso_now）；布尔 INTEGER 0/1；
枚举 TEXT + CHECK 约束；JSON 用 TEXT。索引名与 DDL 完全一致。
"""

from __future__ import annotations

from sqlalchemy import (
    CheckConstraint,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from .models import iso_now


class Base(DeclarativeBase):
    pass


# ---------------------------------------------------------------- 1. 素材主表
class AssetItem(Base):
    """素材主表（Asset 实体，字段对齐 05 文档第四节 + 09 新增表 assets）。"""

    __tablename__ = "asset_items"
    __table_args__ = (
        CheckConstraint(
            "asset_type IN ('video', 'image')",
            name="ck_asset_items_asset_type",
        ),
        CheckConstraint(
            "evaluation IN ('exploring','efficient','potential') OR evaluation IS NULL",
            name="ck_asset_items_evaluation",
        ),
        CheckConstraint(
            "upload_status IN ('local','uploading','uploaded','failed','disabled')",
            name="ck_asset_items_upload_status",
        ),
        CheckConstraint(
            "compliance_status IN ('pending','passed','rejected')",
            name="ck_asset_items_compliance_status",
        ),
        CheckConstraint(
            "relevance_status IN ('pending','passed','failed','manual_review')",
            name="ck_asset_items_relevance_status",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    asset_type: Mapped[str] = mapped_column(String(20))          # video / image
    source_platform: Mapped[str] = mapped_column(String(40))     # 视频号/抖音/快手/...
    source_url: Mapped[str] = mapped_column(Text)                # 追溯与版权标记依据
    source_author: Mapped[str | None] = mapped_column(String(200), nullable=True)
    md5: Mapped[str] = mapped_column(String(32))                 # 32 位小写 hex
    phash: Mapped[str] = mapped_column(Text)                     # 图片整图 / 视频关键帧 phash(JSON)
    file_path: Mapped[str] = mapped_column(Text)                 # 存储键（本地相对键/MinIO 键）
    duration: Mapped[int | None] = mapped_column(Integer, nullable=True)   # 秒（video 必填）
    resolution: Mapped[str | None] = mapped_column(String(30), nullable=True)  # 宽x高
    size: Mapped[int] = mapped_column(Integer)                   # 字节，≤524288000
    tags_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    heat_score: Mapped[float | None] = mapped_column(Float, nullable=True)   # 0~100
    evaluation: Mapped[str | None] = mapped_column(String(20), nullable=True)  # M5 回写
    upload_status: Mapped[str] = mapped_column(String(20), default="local")
    platform_material_id: Mapped[str | None] = mapped_column(String(120), unique=True, nullable=True)
    compliance_status: Mapped[str] = mapped_column(String(20), default="pending")
    relevance_status: Mapped[str] = mapped_column(String(20), default="pending")  # M3 相关性门回写
    derivation_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[str] = mapped_column(String(40), default=iso_now)
    updated_at: Mapped[str] = mapped_column(String(40), default=iso_now, onupdate=iso_now)


Index("idx_asset_items_platform", AssetItem.source_platform)
Index("idx_asset_items_type_status", AssetItem.asset_type, AssetItem.upload_status)
Index("idx_asset_items_evaluation", AssetItem.evaluation)
Index("idx_asset_items_compliance", AssetItem.compliance_status)
Index("idx_asset_items_relevance", AssetItem.relevance_status)
Index("idx_asset_items_md5", AssetItem.md5)


# ---------------------------------------------------------- 2. 下载任务账本
class AssetDownloadJob(Base):
    """下载任务账本（状态/重试/节流/租约/证据；错误码复用全局码表）。"""

    __tablename__ = "asset_download_jobs"
    __table_args__ = (
        CheckConstraint(
            "status IN ('queued','running','success','failed','paused','blocked')",
            name="ck_asset_dl_status",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    asset_id: Mapped[int | None] = mapped_column(ForeignKey("asset_items.id"), nullable=True)  # 下载成功后回填
    source_platform: Mapped[str] = mapped_column(String(40))
    source_url: Mapped[str] = mapped_column(Text)
    job_type: Mapped[str] = mapped_column(String(30))   # video / image / video_page(取直链)
    status: Mapped[str] = mapped_column(String(20), default="queued")
    error_code: Mapped[str | None] = mapped_column(String(40), nullable=True)   # 全局错误码表
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)      # 脱敏后信息
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    max_retries: Mapped[int] = mapped_column(Integer, default=3)
    throttle_level: Mapped[int] = mapped_column(Integer, default=0)             # 0~4 退避级
    next_run_at: Mapped[str | None] = mapped_column(String(40), nullable=True)
    lease_owner: Mapped[str | None] = mapped_column(String(120), nullable=True)  # 租约持有者（实例 id）
    lease_expires_at: Mapped[str | None] = mapped_column(String(40), nullable=True)  # 过期回收
    evidence_json: Mapped[str | None] = mapped_column(Text, nullable=True)      # 不含 Cookie/密钥
    created_at: Mapped[str] = mapped_column(String(40), default=iso_now)
    updated_at: Mapped[str] = mapped_column(String(40), default=iso_now, onupdate=iso_now)


Index("idx_asset_dl_status", AssetDownloadJob.status, AssetDownloadJob.next_run_at)
Index("idx_asset_dl_platform", AssetDownloadJob.source_platform, AssetDownloadJob.status)


# ------------------------------------------------------------- 3. 采集源账本
class AssetSource(Base):
    """采集源/达人账本（游标/节流/熔断/空转；对齐 source_cursors + platform_states）。"""

    __tablename__ = "asset_sources"
    __table_args__ = (
        UniqueConstraint("source_platform", "source_key", name="uq_asset_sources_platform_key"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source_platform: Mapped[str] = mapped_column(String(40))
    source_key: Mapped[str] = mapped_column(String(200))   # 达人 id / 关键词 / 榜单 id
    source_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    cursor_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    next_run_at: Mapped[str | None] = mapped_column(String(40), nullable=True)
    completed_for_date: Mapped[str | None] = mapped_column(String(20), nullable=True)  # YYYY-MM-DD
    throttle_level: Mapped[int] = mapped_column(Integer, default=0)
    consecutive_failures: Mapped[int] = mapped_column(Integer, default=0)
    risk_control: Mapped[int] = mapped_column(Integer, default=0)   # 熔断：1=暂停该平台
    idle_runs: Mapped[int] = mapped_column(Integer, default=0)      # 空转计数（实时榜降频用）
    config_json: Mapped[str | None] = mapped_column(Text, nullable=True)  # 不含密钥
    created_at: Mapped[str] = mapped_column(String(40), default=iso_now)
    updated_at: Mapped[str] = mapped_column(String(40), default=iso_now, onupdate=iso_now)


# ---------------------------------------------------- 4. 去重指纹注册表
class AssetDedupFingerprint(Base):
    """去重指纹注册表（(type, value) 唯一，防并发重复入库认领）。"""

    __tablename__ = "asset_dedup_fingerprints"
    __table_args__ = (
        UniqueConstraint("fingerprint_type", "fingerprint_value", name="uq_asset_fp_type_value"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    fingerprint_type: Mapped[str] = mapped_column(String(30))   # md5 / video_phash / image_phash
    fingerprint_value: Mapped[str] = mapped_column(Text)        # 指纹值（phash 含帧标识）
    asset_id: Mapped[int] = mapped_column(ForeignKey("asset_items.id"))
    hits: Mapped[int] = mapped_column(Integer, default=1)       # 命中次数（重复素材计数）
    claimed_at: Mapped[str] = mapped_column(String(40), default=iso_now)


Index("idx_asset_fp_type", AssetDedupFingerprint.fingerprint_type)


# ------------------------------------------------------ 5. 评估标签回流审计
class AssetEvaluation(Base):
    """评估标签回流审计（M5 回写留痕；asset_items.evaluation 只存当前值）。"""

    __tablename__ = "asset_evaluations"
    __table_args__ = (
        CheckConstraint(
            "evaluation IN ('exploring','efficient','potential')",
            name="ck_asset_evaluations_evaluation",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    asset_id: Mapped[int] = mapped_column(ForeignKey("asset_items.id"))
    evaluation: Mapped[str] = mapped_column(String(20))
    evidence_json: Mapped[str | None] = mapped_column(Text, nullable=True)  # 回流批次/报表快照摘要
    source_agent: Mapped[str | None] = mapped_column(String(120), nullable=True)  # 回写方（M5）
    created_at: Mapped[str] = mapped_column(String(40), default=iso_now)


Index("idx_asset_eval_asset", AssetEvaluation.asset_id, AssetEvaluation.created_at)


# -------------------------------------------------------- 6. 内容预审记录
class AssetComplianceCheck(Base):
    """内容预审记录（供应链词/品牌词/功效词命中；复用 compliance.py 逻辑的落库）。"""

    __tablename__ = "asset_compliance_checks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    asset_id: Mapped[int] = mapped_column(ForeignKey("asset_items.id"))
    check_type: Mapped[str] = mapped_column(String(40))   # supply_chain_word / brand_word / efficacy_word
    result: Mapped[str] = mapped_column(String(20))       # pass / reject / review
    hit_words_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[str] = mapped_column(String(40), default=iso_now)


Index("idx_asset_cc_asset", AssetComplianceCheck.asset_id, AssetComplianceCheck.result)


# ---------------------------------------------------- 7. 上传小店素材库记录
class AssetUpload(Base):
    """上传小店素材库记录（M3 上传链路；platform_material_id 唯一防重复上传）。"""

    __tablename__ = "asset_uploads"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending','success','failed','disabled')",
            name="ck_asset_uploads_status",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    asset_id: Mapped[int] = mapped_column(ForeignKey("asset_items.id"))
    attempt: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    platform_material_id: Mapped[str | None] = mapped_column(String(120), unique=True, nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(40), nullable=True)
    evidence_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[str] = mapped_column(String(40), default=iso_now)
    updated_at: Mapped[str] = mapped_column(String(40), default=iso_now, onupdate=iso_now)


Index("idx_asset_up_asset", AssetUpload.asset_id, AssetUpload.status)
