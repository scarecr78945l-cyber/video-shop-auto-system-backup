# -*- coding: utf-8 -*-
"""P0-2 批次 2（C1-b/c）：aggr_v1 manifest 单一真源（round-153 授权实现）。

依据 round-145 §3.4 / round-147 §2.5 / round-152 §三.7：
- `aggregation_version = aggr_v1` 独立常量 manifest（不新增 enum_policy_type、不触发 migration）；
- canonical payload = `json.dumps(MANIFEST, ensure_ascii=False, sort_keys=True, separators=(",", ":"))`；
- 预期 SHA-256 = `aeaa6cc2fe77a32b601c85700195ef047ca1dcc9ff01e9ddbd9f61258fdc62d1`；
- 五类 feedback_type 的 canonical granularity（无 fallback）、numerator/denominator、
  Decimal（prec=60 / ROUND_HALF_UP / storage_scale=6）、sample 阈值与类目商品数阈值。
- 升级规则：只增不改——新增 aggr_v2 条目（新 payload + 新哈希），旧事件保持原 aggregation_version。
"""
from __future__ import annotations

import hashlib
import json

AGGREGATION_VERSION = "aggr_v1"
EXPECTED_MANIFEST_SHA256 = "aeaa6cc2fe77a32b601c85700195ef047ca1dcc9ff01e9ddbd9f61258fdc62d1"

MANIFEST = {
    "category_min_products": 1,
    "decimal": {"precision": 60, "rounding": "ROUND_HALF_UP", "storage_scale": 6},
    "feedback_types": {
        "category_score": {"denominator": "spend", "granularity": ["campaign"], "numerator": "gmv"},
        "material_score": {"denominator": "spend", "granularity": ["campaign_asset"], "numerator": "gmv"},
        "product_score": {"denominator": "spend", "granularity": ["campaign"], "numerator": "gmv"},
        "shop_strategy": {"denominator": "spend", "granularity": ["campaign"], "numerator": "gmv"},
        "sku_margin": {"denominator": "1", "granularity": ["shop_listing_sku"], "numerator": "gmv_minus_spend"},
    },
    "min_sample_snapshot": 1,
    "version": "aggr_v1",
}

# 五类 feedback_type 的 canonical granularity（single value，无 fallback；round-152 §三.3）
CANONICAL_GRANULARITY = {
    feedback_type: spec["granularity"][0]
    for feedback_type, spec in MANIFEST["feedback_types"].items()
}

# ROI 类（Σgmv/Σspend，spend=0 → zero_spend_skipped）vs SKU 类（Σ(gmv−spend)，分，spend=0 非 skip）
ROI_TYPES = ("product_score", "category_score", "material_score", "shop_strategy")
SKU_TYPES = ("sku_margin",)
FEEDBACK_TYPES = tuple(sorted(MANIFEST["feedback_types"]))

DECIMAL_PRECISION = MANIFEST["decimal"]["precision"]
DECIMAL_ROUNDING = MANIFEST["decimal"]["rounding"]
STORAGE_SCALE = MANIFEST["decimal"]["storage_scale"]
MIN_SAMPLE_SNAPSHOT = MANIFEST["min_sample_snapshot"]
CATEGORY_MIN_PRODUCTS = MANIFEST["category_min_products"]


def canonical_payload() -> str:
    """canonical payload（递归键排序、UTF-8、紧凑 JSON、无尾随换行）。"""
    return json.dumps(MANIFEST, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def manifest_sha256() -> str:
    """canonical payload 的 SHA-256（小写 hex）。"""
    return hashlib.sha256(canonical_payload().encode("utf-8")).hexdigest()


def verify_manifest() -> bool:
    """复算 canonical payload 哈希并断言等于预期（单一真源自检）。"""
    return manifest_sha256() == EXPECTED_MANIFEST_SHA256
