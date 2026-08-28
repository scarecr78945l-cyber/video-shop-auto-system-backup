"""M3 主图/详情图管线（子代理-B2 · 迭代 v0.4）。

四能力：KimiImagePlanner（视觉策略规划）/ WanImageProvider（生图，离线 Pillow 占位图）/
ImageQualityGate（质量门禁 + Pillow 自实现 dHash/aHash + 打回重生成）/ CategoryListingMemory
（类目记忆）。全部支持 fixtures 离线模式（零 API Key 可跑通 plan → generate → gate → memory）。
"""

from __future__ import annotations

from .memory import CategoryListingMemory, MemoryPolicy
from .planner import BACKGROUND_PHRASES, KimiImagePlanner
from .provider import RATE_LIMIT_BACKOFF_SECONDS, WanImageError, WanImageProvider
from .quality_gate import (
    ImageQualityGate,
    hamming_distance,
    phash_ahash,
    phash_dhash,
    regenerate_until_ok,
)

__all__ = [
    "KimiImagePlanner",
    "BACKGROUND_PHRASES",
    "WanImageProvider",
    "WanImageError",
    "RATE_LIMIT_BACKOFF_SECONDS",
    "ImageQualityGate",
    "phash_dhash",
    "phash_ahash",
    "hamming_distance",
    "regenerate_until_ok",
    "CategoryListingMemory",
    "MemoryPolicy",
]
