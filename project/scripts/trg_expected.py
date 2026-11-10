# -*- coding: utf-8 -*-
"""T4 独立期望快照（round-61 R60-1~R60-4 生成；来源 15-数据字典.md v6 §8 + ddl-order.md §六 + error-codes.yaml）。

assert_triggers.py 以本文件为唯一 expected-set，与 pg_catalog 逐项比对（不从生成器导入，
避免同源假通过）。修改冻结契约后须重新生成本快照并同步迁移。

字段说明：
  TRIGGERS：17 项 (name, table, event_cols_or_None, business_code, custom_sqlstate)
    - event_cols=None 表示整表 BEFORE INSERT OR UPDATE（无 OF 子句）
    - event_cols=("c1","c2",...) 表示 BEFORE INSERT OR UPDATE OF <cols>（按 v6 §8 冻结列序）
  INSTALL_ORDER：与 ddl-order §六 G7 原序一致（upgrade 安装序 / downgrade 严格逆序）
  BUSINESS_CODES / SQLSTATE_MAP：error-codes.yaml 7 个 trigger 码 -> ZT 自定义 SQLSTATE
"""
# G7 冻结安装顺序（ddl-order.md §六）
INSTALL_ORDER = [
    "trg_policy_supersede_scope",
    "trg_shops_policy_ref",
    "trg_cost_policy_ref",
    "trg_selection_policy_ref",
    "trg_pricing_policy_ref",
    "trg_campaigns_policy_ref",
    "trg_manual_policy_ref",
    "trg_offers_sku_product_consistency",
    "trg_bindings_sku_product_consistency",
    "trg_listings_account_shop_consistency",
    "trg_cost_context_consistency",
    "trg_shopbind_context_consistency",
    "trg_pricing_context_consistency",
    "trg_campaigns_scope_consistency",
    "trg_campassets_same_scope",
    "trg_snapshots_dimension_consistency",
    "trg_feedback_dimension_consistency",
]

# 17 项 trigger（事件列按 v6 §8 冻结；supersede 按 round-61 最小勘误补 policy_type/scope_type/scope_id）
TRIGGERS = [
    ("trg_policy_supersede_scope", "policy_versions",
     ("supersedes_id", "tenant_id", "policy_type", "scope_type", "scope_id"),
     "SUPERSEDE_MISMATCH", "ZT007"),
    ("trg_shops_policy_ref", "shops",
     ("cid_policy_version_id", "tenant_id"),
     "INVALID_POLICY_REF", "ZT001"),
    ("trg_cost_policy_ref", "cost_snapshots",
     ("policy_version_id", "tenant_id"),
     "INVALID_POLICY_REF", "ZT001"),
    ("trg_selection_policy_ref", "selection_decisions",
     ("policy_version_id", "tenant_id"),
     "INVALID_POLICY_REF", "ZT001"),
    ("trg_pricing_policy_ref", "pricing_decisions",
     ("policy_version_id", "tenant_id"),
     "INVALID_POLICY_REF", "ZT001"),
    ("trg_campaigns_policy_ref", "ad_campaigns",
     ("budget_policy_version_id", "cid_policy_version_id", "tenant_id"),
     "INVALID_POLICY_REF", "ZT001"),
    ("trg_manual_policy_ref", "manual_tasks",
     ("policy_version_id", "tenant_id"),
     "INVALID_POLICY_REF", "ZT001"),
    ("trg_offers_sku_product_consistency", "supplier_offers",
     ("sku_id", "product_id", "tenant_id"),
     "SKU_PRODUCT_MISMATCH", "ZT002"),
    ("trg_bindings_sku_product_consistency", "asset_product_bindings",
     ("product_sku_id", "product_id", "tenant_id"),
     "SKU_PRODUCT_MISMATCH", "ZT002"),
    ("trg_listings_account_shop_consistency", "shop_listings",
     ("account_id", "shop_id", "tenant_id"),
     "ACCOUNT_SHOP_MISMATCH", "ZT004"),
    ("trg_cost_context_consistency", "cost_snapshots",
     None,
     "CONTEXT_MISMATCH", "ZT003"),
    ("trg_shopbind_context_consistency", "asset_shop_bindings",
     None,
     "CONTEXT_MISMATCH", "ZT003"),
    ("trg_pricing_context_consistency", "pricing_decisions",
     None,
     "CONTEXT_MISMATCH", "ZT003"),
    ("trg_campaigns_scope_consistency", "ad_campaigns",
     ("account_id", "shop_id", "shop_listing_id", "tenant_id"),
     "SCOPE_MISMATCH", "ZT005"),
    ("trg_campassets_same_scope", "ad_campaign_assets",
     None,
     "SCOPE_MISMATCH", "ZT005"),
    ("trg_snapshots_dimension_consistency", "ad_report_snapshots",
     None,
     "DIMENSION_MISMATCH", "ZT006"),
    ("trg_feedback_dimension_consistency", "roi_feedback_events",
     None,
     "DIMENSION_MISMATCH", "ZT006"),
]

BUSINESS_CODES = [
    "INVALID_POLICY_REF", "SKU_PRODUCT_MISMATCH", "CONTEXT_MISMATCH",
    "ACCOUNT_SHOP_MISMATCH", "SCOPE_MISMATCH", "DIMENSION_MISMATCH",
    "SUPERSEDE_MISMATCH",
]

# 自定义 SQLSTATE（round-61 R60-3：避开 PostgreSQL/PL-pgSQL 已登记条件 P0001~P0004，
# 使用 psycopg2.errorcodes 未占用且服务端实测接受的 ZT 类）
SQLSTATE_MAP = {
    "INVALID_POLICY_REF": "ZT001",
    "SKU_PRODUCT_MISMATCH": "ZT002",
    "CONTEXT_MISMATCH": "ZT003",
    "ACCOUNT_SHOP_MISMATCH": "ZT004",
    "SCOPE_MISMATCH": "ZT005",
    "DIMENSION_MISMATCH": "ZT006",
    "SUPERSEDE_MISMATCH": "ZT007",
}
