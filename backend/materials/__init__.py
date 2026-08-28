"""视频号小店全自动系统 — M2 自动收集素材模块（素材库基座）。

交付：asset_* 7 表 ORM + AssetRepo 数据访问层 + 建库/查询 CLI。
- 一模块一库：backend/data/db/m2-materials.db（SQLite 开发；生产切 PostgreSQL）
- 表前缀 asset_*（宪法第 4 节）；硬规格常量集中在 config.py（P-007 防复发）
- 双去重：asset_dedup_fingerprints 唯一约束 (fingerprint_type, fingerprint_value)
  防并发重复入库（先认领后入库，冲突抛 DuplicateAssetError 不静默吞）
- 时间戳：DDL 约定 TEXT ISO8601 UTC（models.iso_now，固定 microseconds 宽度，
  同格式字符串可字典序比较，支撑租约/退避判断）
"""

from __future__ import annotations

__version__ = "0.1.0"

from .config import MaterialsConfig, load_config  # noqa: F401
from .db import Database, default_database  # noqa: F401

__all__ = ["MaterialsConfig", "load_config", "Database", "default_database"]
