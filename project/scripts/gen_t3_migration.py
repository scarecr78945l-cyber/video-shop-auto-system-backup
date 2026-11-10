# -*- coding: utf-8 -*-
"""T3 生成器：数据驱动生成 31 表 + 约束的 Alembic migration（round-53，round-55 R54-1~R54-4 回修）。

背景：上一版 `31tbl000001_31_tables_constraints.py` 因批量正则误伤跨行内容致 SyntaxError，
handoff 与 Codex round-52 确定方向为**重写为数据驱动生成器**（仿 T2 gen_enum_migration.py）：
- 31 表逐列 + 17 父候选键 + 58 组合 FK + 4 NULLS NOT DISTINCT + 2 exclusion +
  15 部分唯一 + 8 普通索引全部编码为**数据**（本文件 WAVES/PARENT_KEYS/COMPOSITE_FKS/
  NULLS_UNIQUE/PARTIAL_UNIQUE/PLAIN_INDEXES/TABLES/FK_ACTIONS）；
- emitter 确定性输出 canonical migration：文件名固定、Create Date 固定、产物哈希稳定；
- `--check`：只校验现有 migration 与应生成内容一致（缺失/漂移 → 失败），不写入。
- 关键经验：enum 用 `postgresql.ENUM(..., create_type=False)`（T2 已建 60 enum）；
  FK 约束名 `fk_<child>_<parent>`；NULLS NOT DISTINCT 索引名 `uq_<table>_nullsdistinct`；
  exclusion 中 'infinity' 用 `'infinity'::timestamptz`。

round-55 回修（Codex round-54 复核 R54-1~R54-4）：
- R54-1 字段 DDL：identity 用 `sa.Identity(always=True)`（GENERATED ALWAYS）；
  json 用 `postgresql.JSONB()`（23 列）；`public_id` 自动补 `gen_random_uuid()` 默认（14 列）；
  `tenants.name` 保留 NOT NULL（受控契约勘误，见 15-数据字典.md 标注与交接文档）。
- R54-2：新增 FK_ACTIONS（11 条冻结 ON DELETE：10 CASCADE + 1 RESTRICT），G5 emitter 透传。
- R54-4：downgrade 在每个 wave 内也逆序（W8->W0 且 wave 内子表先删）。

用法：
  python scripts/gen_t3_migration.py          # 生成/覆盖 canonical 文件（漂移时拒绝）
  python scripts/gen_t3_migration.py --check  # 只校验，不写入
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VERSIONS = ROOT / "migrations" / "versions"

REV = "31tbl000001"
DOWN = "60enum000000"
CREATE_DATE = "2026-09-03T13:00:00+00:00"
CANONICAL_NAME = f"{REV}_31_tables_constraints.py"
SCHEMA = "app"

# ---------------------------------------------------------------------------
# 31 表建表顺序（W0~W8，ddl-order.md §三）
# ---------------------------------------------------------------------------
WAVES = [
    ["tenants", "actor_registry", "policy_versions"],
    ["platform_accounts", "shops", "account_runtime_profiles", "credential_refs"],
    ["suppliers", "products", "product_skus", "supplier_offers"],
    ["assets", "shop_listings", "shop_listing_skus"],
    ["asset_product_bindings", "asset_shop_bindings", "asset_reviews"],
    ["cost_snapshots", "workflow_runs", "workflow_steps", "selection_decisions"],
    ["pricing_decisions", "listing_events"],
    ["ad_campaigns", "ad_campaign_assets", "ad_report_snapshots", "roi_feedback_events"],
    ["manual_tasks", "audit_events", "alert_events", "alert_deliveries"],
]

# 17 父候选键 UNIQUE(tenant_id, id)
PARENT_KEYS = [
    "platform_accounts", "shops", "suppliers", "products", "product_skus",
    "supplier_offers", "cost_snapshots", "assets", "asset_product_bindings",
    "asset_shop_bindings", "shop_listings", "shop_listing_skus", "ad_campaigns",
    "ad_report_snapshots", "workflow_runs", "policy_versions", "alert_events",
]

# 58 组合 FK：(child, parent, child_cols, parent_cols, nullable_ok)
COMPOSITE_FKS = [
    ("shops", "platform_accounts", ["tenant_id", "account_id"], ["tenant_id", "id"], False),
    ("account_runtime_profiles", "platform_accounts", ["tenant_id", "account_id"], ["tenant_id", "id"], False),
    ("credential_refs", "platform_accounts", ["tenant_id", "account_id"], ["tenant_id", "id"], False),
    ("product_skus", "products", ["tenant_id", "product_id"], ["tenant_id", "id"], False),
    ("supplier_offers", "suppliers", ["tenant_id", "supplier_id"], ["tenant_id", "id"], False),
    ("supplier_offers", "product_skus", ["tenant_id", "sku_id"], ["tenant_id", "id"], True),
    ("supplier_offers", "products", ["tenant_id", "product_id"], ["tenant_id", "id"], True),
    ("cost_snapshots", "shops", ["tenant_id", "shop_id"], ["tenant_id", "id"], True),
    ("cost_snapshots", "shop_listings", ["tenant_id", "shop_listing_id"], ["tenant_id", "id"], True),
    ("cost_snapshots", "supplier_offers", ["tenant_id", "offer_id"], ["tenant_id", "id"], True),
    ("selection_decisions", "products", ["tenant_id", "product_id"], ["tenant_id", "id"], False),
    ("selection_decisions", "platform_accounts", ["tenant_id", "source_account_id"], ["tenant_id", "id"], True),
    ("selection_decisions", "cost_snapshots", ["tenant_id", "cost_snapshot_id"], ["tenant_id", "id"], True),
    ("selection_decisions", "workflow_runs", ["tenant_id", "workflow_run_id"], ["tenant_id", "id"], True),
    ("assets", "platform_accounts", ["tenant_id", "source_account_id"], ["tenant_id", "id"], True),
    ("assets", "assets", ["tenant_id", "derived_from_asset_id"], ["tenant_id", "id"], True),
    ("asset_product_bindings", "assets", ["tenant_id", "asset_id"], ["tenant_id", "id"], False),
    ("asset_product_bindings", "products", ["tenant_id", "product_id"], ["tenant_id", "id"], False),
    ("asset_product_bindings", "product_skus", ["tenant_id", "product_sku_id"], ["tenant_id", "id"], True),
    ("asset_shop_bindings", "assets", ["tenant_id", "asset_id"], ["tenant_id", "id"], False),
    ("asset_shop_bindings", "shops", ["tenant_id", "shop_id"], ["tenant_id", "id"], False),
    ("asset_shop_bindings", "asset_product_bindings", ["tenant_id", "asset_product_binding_id"], ["tenant_id", "id"], True),
    ("asset_shop_bindings", "products", ["tenant_id", "product_id"], ["tenant_id", "id"], True),
    ("asset_shop_bindings", "shop_listings", ["tenant_id", "shop_listing_id"], ["tenant_id", "id"], True),
    ("asset_reviews", "assets", ["tenant_id", "asset_id"], ["tenant_id", "id"], False),
    ("shop_listings", "platform_accounts", ["tenant_id", "account_id"], ["tenant_id", "id"], False),
    ("shop_listings", "shops", ["tenant_id", "shop_id"], ["tenant_id", "id"], False),
    ("shop_listings", "products", ["tenant_id", "product_id"], ["tenant_id", "id"], False),
    ("shop_listing_skus", "shop_listings", ["tenant_id", "shop_listing_id"], ["tenant_id", "id"], False),
    ("shop_listing_skus", "product_skus", ["tenant_id", "sku_id"], ["tenant_id", "id"], False),
    ("pricing_decisions", "shops", ["tenant_id", "shop_id"], ["tenant_id", "id"], False),
    ("pricing_decisions", "shop_listings", ["tenant_id", "shop_listing_id"], ["tenant_id", "id"], False),
    ("pricing_decisions", "shop_listing_skus", ["tenant_id", "shop_listing_sku_id"], ["tenant_id", "id"], False),
    ("pricing_decisions", "cost_snapshots", ["tenant_id", "cost_snapshot_id"], ["tenant_id", "id"], False),
    ("listing_events", "shop_listings", ["tenant_id", "shop_listing_id"], ["tenant_id", "id"], False),
    ("ad_campaigns", "platform_accounts", ["tenant_id", "account_id"], ["tenant_id", "id"], False),
    ("ad_campaigns", "shops", ["tenant_id", "shop_id"], ["tenant_id", "id"], False),
    ("ad_campaigns", "shop_listings", ["tenant_id", "shop_listing_id"], ["tenant_id", "id"], False),
    ("ad_campaign_assets", "ad_campaigns", ["tenant_id", "campaign_id"], ["tenant_id", "id"], False),
    ("ad_campaign_assets", "asset_shop_bindings", ["tenant_id", "asset_shop_binding_id"], ["tenant_id", "id"], False),
    ("ad_report_snapshots", "platform_accounts", ["tenant_id", "account_id"], ["tenant_id", "id"], False),
    ("ad_report_snapshots", "shops", ["tenant_id", "shop_id"], ["tenant_id", "id"], False),
    ("ad_report_snapshots", "shop_listings", ["tenant_id", "shop_listing_id"], ["tenant_id", "id"], False),
    ("ad_report_snapshots", "shop_listing_skus", ["tenant_id", "shop_listing_sku_id"], ["tenant_id", "id"], True),
    ("ad_report_snapshots", "products", ["tenant_id", "product_id"], ["tenant_id", "id"], False),
    ("ad_report_snapshots", "ad_campaigns", ["tenant_id", "campaign_id"], ["tenant_id", "id"], False),
    ("ad_report_snapshots", "asset_shop_bindings", ["tenant_id", "asset_binding_id"], ["tenant_id", "id"], True),
    ("roi_feedback_events", "platform_accounts", ["tenant_id", "account_id"], ["tenant_id", "id"], False),
    ("roi_feedback_events", "shops", ["tenant_id", "shop_id"], ["tenant_id", "id"], False),
    ("roi_feedback_events", "shop_listings", ["tenant_id", "shop_listing_id"], ["tenant_id", "id"], False),
    ("roi_feedback_events", "shop_listing_skus", ["tenant_id", "shop_listing_sku_id"], ["tenant_id", "id"], True),
    ("roi_feedback_events", "products", ["tenant_id", "product_id"], ["tenant_id", "id"], False),
    ("roi_feedback_events", "ad_campaigns", ["tenant_id", "campaign_id"], ["tenant_id", "id"], False),
    ("roi_feedback_events", "asset_shop_bindings", ["tenant_id", "asset_binding_id"], ["tenant_id", "id"], True),
    ("roi_feedback_events", "ad_report_snapshots", ["tenant_id", "source_snapshot_id"], ["tenant_id", "id"], False),
    ("workflow_steps", "workflow_runs", ["tenant_id", "run_id"], ["tenant_id", "id"], False),
    ("policy_versions", "policy_versions", ["tenant_id", "supersedes_id"], ["tenant_id", "id"], True),
    ("alert_deliveries", "alert_events", ["tenant_id", "alert_event_id"], ["tenant_id", "id"], False),
]

# 11 条冻结 ON DELETE action（R54-2；v6 各表字段行显式声明；其余组合 FK 保持 NO ACTION）
FK_ACTIONS = {
    ("account_runtime_profiles", "platform_accounts"): "CASCADE",
    ("credential_refs", "platform_accounts"): "CASCADE",
    ("product_skus", "products"): "CASCADE",
    ("supplier_offers", "suppliers"): "RESTRICT",
    ("asset_product_bindings", "assets"): "CASCADE",
    ("asset_shop_bindings", "assets"): "CASCADE",
    ("asset_reviews", "assets"): "CASCADE",
    ("shop_listing_skus", "shop_listings"): "CASCADE",
    ("ad_campaign_assets", "ad_campaigns"): "CASCADE",
    ("workflow_steps", "workflow_runs"): "CASCADE",
    ("alert_deliveries", "alert_events"): "CASCADE",
}

# 27 个列级普通 CHECK（v6 各表字段行显式冻结；ddl-order G3「普通 CHECK」；round-55 R54-1 补齐）
COLUMN_CHECKS = {
    ("product_skus", "weight_g"): "weight_g >= 0",
    ("supplier_offers", "price"): "price >= 0",
    ("supplier_offers", "stock_observed"): "stock_observed >= 0",
    ("selection_decisions", "data_coverage"): "data_coverage >= 0 AND data_coverage <= 1",
    ("selection_decisions", "confidence"): "confidence >= 0 AND confidence <= 1",
    ("selection_decisions", "available_asset_count"): "available_asset_count >= 0",
    ("assets", "size_bytes"): "size_bytes >= 0",
    ("assets", "width"): "width >= 0",
    ("assets", "height"): "height >= 0",
    ("assets", "duration_ms"): "duration_ms >= 0",
    ("asset_product_bindings", "relevance"): "relevance >= 0 AND relevance <= 1",
    ("shop_listing_skus", "shop_price"): "shop_price >= 0",
    ("shop_listing_skus", "promo_price"): "promo_price >= 0",
    ("shop_listing_skus", "floor_price"): "floor_price >= 0",
    ("pricing_decisions", "cost_floor_price"): "cost_floor_price >= 0",
    ("pricing_decisions", "suggested_price"): "suggested_price >= 0",
    ("pricing_decisions", "daily_price"): "daily_price >= 0",
    ("pricing_decisions", "promo_price"): "promo_price >= 0",
    ("pricing_decisions", "floor_price"): "floor_price >= 0",
    ("pricing_decisions", "target_margin"): "target_margin >= 0",
    ("ad_campaigns", "approved_budget"): "approved_budget >= 0",
    ("ad_campaigns", "approved_daily_budget"): "approved_daily_budget >= 0",
    ("ad_campaigns", "approved_target_roi"): "approved_target_roi > 0",
    ("ad_campaigns", "approved_stop_loss"): "approved_stop_loss > 0",
    ("ad_campaigns", "current_budget"): "current_budget >= 0",
    ("ad_campaigns", "current_daily_budget"): "current_daily_budget >= 0",
    ("ad_campaigns", "feedback_coefficient"): "feedback_coefficient > 0",
}

# 4 × UNIQUE NULLS NOT DISTINCT（索引名 uq_<table>_nullsdistinct < 63 字符）
NULLS_UNIQUE = [
    ("asset_product_bindings", ["asset_id", "product_id", "product_sku_id", "purpose"]),
    ("asset_shop_bindings", ["asset_id", "shop_id", "product_id", "shop_listing_id", "purpose"]),
    ("ad_report_snapshots", ["campaign_id", "granularity", "shop_listing_sku_id", "asset_binding_id",
                             "window_start", "window_end", "attribution_mode", "report_version_key"]),
    ("policy_versions", ["tenant_id", "policy_type", "scope_type", "scope_key", "version"]),
]

# 15 部分唯一索引：(table, index, cols, where)
PARTIAL_UNIQUE = [
    ("tenants", "px_tenants_name", ["name"], "deleted_at IS NULL"),
    ("platform_accounts", "px_accounts_platform_key", ["tenant_id", "platform", "account_key"], "deleted_at IS NULL"),
    ("shops", "px_shops_account_shop", ["account_id", "platform_shop_id"], "deleted_at IS NULL"),
    ("account_runtime_profiles", "px_profiles_active", ["account_id", "purpose"], "status='active'"),
    ("credential_refs", "px_creds_valid", ["account_id", "purpose"], "status='valid'"),
    ("suppliers", "px_suppliers_code", ["tenant_id", "supplier_code"], "deleted_at IS NULL"),
    ("suppliers", "px_suppliers_platform", ["tenant_id", "source_platform", "platform_supplier_id"],
     "deleted_at IS NULL AND platform_supplier_id IS NOT NULL"),
    ("products", "px_products_title", ["tenant_id", "title_base"], "deleted_at IS NULL"),
    ("supplier_offers", "px_offers_preferred", ["sku_id", "preferred_status"], "preferred_status='current'"),
    ("assets", "px_assets_sha256", ["tenant_id", "content_sha256"], "deleted_at IS NULL"),
    ("shop_listings", "px_listings_shop_product", ["shop_id", "product_id"], "deleted_at IS NULL"),
    ("shop_listings", "px_listings_platform_product", ["tenant_id", "platform_product_id"],
     "platform_product_id IS NOT NULL AND deleted_at IS NULL"),
    ("ad_campaigns", "px_campaigns_platform", ["shop_listing_id", "platform_campaign_id"],
     "platform_campaign_id IS NOT NULL AND deleted_at IS NULL"),
    ("manual_tasks", "px_tasks_open", ["tenant_id", "ref_type", "ref_id", "task_type"],
     "status IN ('pending','in_progress')"),
    ("alert_events", "px_alerts_open", ["tenant_id", "fingerprint"], "status <> 'resolved'"),
]

# 8 普通索引（index-registry 显式项）
PLAIN_INDEXES = [
    ("workflow_steps", "ix_steps_status_updated", ["status", "updated_at"]),
    ("workflow_runs", "ix_runs_status_updated", ["status", "updated_at"]),
    ("manual_tasks", "ix_tasks_status", ["status"]),
    ("alert_deliveries", "ix_deliveries_pending", ["status"]),
    ("ad_report_snapshots", "ix_snaps_window", ["window_start", "window_end"]),
    ("selection_decisions", "ix_decisions_state", ["state"]),
    ("ad_campaigns", "ix_campaigns_listing", ["shop_listing_id"]),
    ("audit_events", "ix_audit_actor_time", ["actor_id", "created_at"]),
]

# 2 exclusion（G8；btree_gist 已由 T1 baseline 建）；SQL 在 build_content 内固定 emit。
EXCLUSION_NOTE = "G8: pricing_decisions(SKU current) + policy_versions(scope effective), btree_gist"


# ---------------------------------------------------------------------------
# 31 表列定义（数据 DSL）
# 列元组：(name, type_spec, nullable, extras)  —— nullable 未用，由 extras 的 notnull 决定
#   type_spec:
#     ("identity",)          -> sa.BigInteger(), sa.Identity()   [PK]
#     ("bigint",)             -> sa.BigInteger()
#     ("integer",)            -> sa.Integer()
#     ("uuid",)               -> sa.Uuid()
#     ("string", n)           -> sa.String(n)
#     ("text",)               -> sa.Text()
#     ("bool",)               -> sa.Boolean()
#     ("json",)               -> sa.JSON()
#     ("numeric",)            -> sa.Numeric()
#     ("numeric", p, s)       -> sa.Numeric(p, s)
#     ("timestamptz",)        -> sa.TIMESTAMP(timezone=True)
#     ("enum", NAME)          -> postgresql.ENUM(name=NAME, create_type=False)
#     ("computed", expr, st)  -> sa.Column(name, <st>, sa.Computed(expr, persisted=True), nullable=...)
#   extras（可多项）：
#     ("pk",)
#     ("notnull",)
#     ("default", VAL)        -> server_default="VAL"
#     ("default_now",)        -> server_default=sa.text("now()")
# 表级额外项（create_table 内紧跟列后）：
#     ("base_fk",) / ("base_fk_restrict",)
#     ("uc", [cols])
#     ("ck", name, expr)
# ---------------------------------------------------------------------------

TABLES = {
    "tenants": {
        "cols": [
            ("id", ("identity",), None, [("pk",)]),
            ("public_id", ("uuid",), None, [("notnull",)]),
            ("name", ("string", 128), None, [("notnull",)]),
            ("scope", ("string", 64), None, [("notnull",)]),
            ("contact_name", ("string", 64), None, []),
            ("contact_phone", ("string", 32), None, []),
            ("contact_email", ("string", 128), None, []),
            ("status", ("enum", "enum_entity_status"), None, [("notnull",), ("default", "active")]),
            ("created_at", ("timestamptz",), None, [("notnull",), ("default_now",)]),
            ("updated_at", ("timestamptz",), None, [("notnull",), ("default_now",)]),
            ("deleted_at", ("timestamptz",), None, []),
            ("row_version", ("integer",), None, [("notnull",), ("default", "1")]),
        ],
        "extra": [("uc", ["public_id"])],
    },
    "actor_registry": {
        "cols": [
            ("id", ("identity",), None, [("pk",)]),
            ("actor_id", ("uuid",), None, [("notnull",)]),
            ("actor_kind", ("enum", "enum_actor_kind"), None, [("notnull",)]),
            ("name", ("string", 64), None, [("notnull",)]),
            ("status", ("enum", "enum_actor_status"), None, [("notnull",), ("default", "active")]),
            ("created_at", ("timestamptz",), None, [("notnull",), ("default_now",)]),
        ],
        "extra": [("uc", ["actor_id"])],
    },
    "policy_versions": {
        "cols": [
            ("id", ("identity",), None, [("pk",)]),
            ("public_id", ("uuid",), None, [("notnull",)]),
            ("tenant_id", ("bigint",), None, []),
            ("policy_type", ("enum", "enum_policy_type"), None, [("notnull",)]),
            ("version", ("string", 32), None, [("notnull",)]),
            ("scope_type", ("enum", "enum_policy_scope"), None, [("notnull",)]),
            ("scope_id", ("string", 128), None, []),
            ("scope_key", ("computed", "CASE WHEN scope_id IS NULL THEN '<global>' ELSE scope_id END", ("string", 192)), None, [("notnull",)]),
            ("content", ("json",), None, [("notnull",)]),
            ("content_hash", ("string", 64), None, [("notnull",)]),
            ("effective_from", ("timestamptz",), None, [("notnull",)]),
            ("effective_to", ("timestamptz",), None, []),
            ("supersedes_id", ("bigint",), None, []),
            ("approved_by_actor_id", ("uuid",), None, [("notnull",)]),
            ("created_at", ("timestamptz",), None, [("notnull",), ("default_now",)]),
        ],
        "extra": [("uc", ["public_id"])],
    },
    "platform_accounts": {
        "cols": [
            ("id", ("identity",), None, [("pk",)]),
            ("public_id", ("uuid",), None, [("notnull",)]),
            ("tenant_id", ("bigint",), None, [("notnull",)]),
            ("platform", ("enum", "enum_platform"), None, [("notnull",)]),
            ("account_key", ("string", 128), None, [("notnull",)]),
            ("login_state", ("enum", "enum_login_state"), None, [("notnull",), ("default", "unknown")]),
            ("health_state", ("enum", "enum_health_state"), None, [("notnull",), ("default", "healthy")]),
            ("status", ("enum", "enum_account_status"), None, [("notnull",), ("default", "draft")]),
            ("rate_limit_cfg", ("json",), None, []),
            ("circuit_breaker", ("json",), None, []),
            ("created_at", ("timestamptz",), None, [("notnull",), ("default_now",)]),
            ("updated_at", ("timestamptz",), None, [("notnull",), ("default_now",)]),
            ("deleted_at", ("timestamptz",), None, []),
            ("row_version", ("integer",), None, [("notnull",), ("default", "1")]),
        ],
        "extra": [("base_fk_restrict",), ("uc", ["public_id"])],
    },
    "shops": {
        "cols": [
            ("id", ("identity",), None, [("pk",)]),
            ("public_id", ("uuid",), None, [("notnull",)]),
            ("tenant_id", ("bigint",), None, [("notnull",)]),
            ("account_id", ("bigint",), None, [("notnull",)]),
            ("platform_shop_id", ("string", 128), None, [("notnull",)]),
            ("name", ("string", 128), None, [("notnull",)]),
            ("category_qualifications", ("json",), None, []),
            ("freight_template_id", ("string", 64), None, []),
            ("return_address", ("json",), None, []),
            ("cid_policy_version_id", ("bigint",), None, []),
            ("status", ("enum", "enum_entity_status"), None, [("notnull",), ("default", "active")]),
            ("created_at", ("timestamptz",), None, [("notnull",), ("default_now",)]),
            ("updated_at", ("timestamptz",), None, [("notnull",), ("default_now",)]),
            ("deleted_at", ("timestamptz",), None, []),
            ("row_version", ("integer",), None, [("notnull",), ("default", "1")]),
        ],
        "extra": [("base_fk",), ("uc", ["public_id"])],
    },
    "account_runtime_profiles": {
        "cols": [
            ("id", ("identity",), None, [("pk",)]),
            ("tenant_id", ("bigint",), None, [("notnull",)]),
            ("account_id", ("bigint",), None, [("notnull",)]),
            ("purpose", ("enum", "enum_profile_purpose"), None, [("notnull",)]),
            ("rotation_seq", ("integer",), None, [("notnull",), ("default", "1")]),
            ("browser_profile_ref", ("string", 256), None, []),
            ("proxy_ref", ("string", 256), None, []),
            ("page_version", ("string", 64), None, []),
            ("selectors_version", ("string", 64), None, []),
            ("status", ("enum", "enum_profile_status"), None, [("notnull",), ("default", "active")]),
            ("created_at", ("timestamptz",), None, [("notnull",), ("default_now",)]),
            ("updated_at", ("timestamptz",), None, [("notnull",), ("default_now",)]),
        ],
        "extra": [("base_fk",), ("uc", ["account_id", "purpose", "rotation_seq"])],
    },
    "credential_refs": {
        "cols": [
            ("id", ("identity",), None, [("pk",)]),
            ("tenant_id", ("bigint",), None, [("notnull",)]),
            ("account_id", ("bigint",), None, [("notnull",)]),
            ("purpose", ("enum", "enum_credential_purpose"), None, [("notnull",)]),
            ("rotation_seq", ("integer",), None, [("notnull",), ("default", "1")]),
            ("secret_store_key", ("string", 256), None, [("notnull",)]),
            ("status", ("enum", "enum_credential_status"), None, [("notnull",), ("default", "valid")]),
            ("expires_at", ("timestamptz",), None, []),
            ("last_verified_at", ("timestamptz",), None, []),
            ("redacted_display", ("string", 64), None, []),
            ("created_at", ("timestamptz",), None, [("notnull",), ("default_now",)]),
            ("updated_at", ("timestamptz",), None, [("notnull",), ("default_now",)]),
        ],
        "extra": [("base_fk",), ("uc", ["account_id", "purpose", "rotation_seq"])],
    },
    "suppliers": {
        "cols": [
            ("id", ("identity",), None, [("pk",)]),
            ("public_id", ("uuid",), None, [("notnull",)]),
            ("tenant_id", ("bigint",), None, [("notnull",)]),
            ("supplier_code", ("string", 64), None, [("notnull",)]),
            ("name", ("string", 128), None, [("notnull",)]),
            ("source_platform", ("enum", "enum_supplier_platform"), None, [("notnull",)]),
            ("platform_supplier_id", ("string", 128), None, []),
            ("contact_ref", ("string", 256), None, []),
            ("settlement_terms", ("json",), None, []),
            ("payment_terms_days", ("integer",), None, []),
            ("fulfillment_mode", ("enum", "enum_fulfillment_mode"), None, []),
            ("return_policy", ("json",), None, []),
            ("health_state", ("enum", "enum_health_state"), None, [("notnull",), ("default", "healthy")]),
            ("status", ("enum", "enum_entity_status"), None, [("notnull",), ("default", "active")]),
            ("source", ("enum", "enum_common_source"), None, [("notnull",)]),
            ("mode", ("enum", "enum_common_mode"), None, [("notnull",)]),
            ("evidence_ref", ("string", 256), None, []),
            ("created_at", ("timestamptz",), None, [("notnull",), ("default_now",)]),
            ("updated_at", ("timestamptz",), None, [("notnull",), ("default_now",)]),
            ("deleted_at", ("timestamptz",), None, []),
            ("row_version", ("integer",), None, [("notnull",), ("default", "1")]),
        ],
        "extra": [("base_fk",), ("uc", ["public_id"])],
    },
    "products": {
        "cols": [
            ("id", ("identity",), None, [("pk",)]),
            ("public_id", ("uuid",), None, [("notnull",)]),
            ("tenant_id", ("bigint",), None, [("notnull",)]),
            ("title_base", ("string", 200), None, [("notnull",)]),
            ("category_id", ("string", 64), None, [("notnull",)]),
            ("material_requirements", ("json",), None, []),
            ("status", ("enum", "enum_product_status"), None, [("notnull",), ("default", "draft")]),
            ("created_at", ("timestamptz",), None, [("notnull",), ("default_now",)]),
            ("updated_at", ("timestamptz",), None, [("notnull",), ("default_now",)]),
            ("deleted_at", ("timestamptz",), None, []),
            ("row_version", ("integer",), None, [("notnull",), ("default", "1")]),
        ],
        "extra": [("base_fk",), ("uc", ["public_id"])],
    },
    "product_skus": {
        "cols": [
            ("id", ("identity",), None, [("pk",)]),
            ("tenant_id", ("bigint",), None, [("notnull",)]),
            ("product_id", ("bigint",), None, [("notnull",)]),
            ("attributes", ("json",), None, [("notnull",)]),
            ("attributes_hash", ("computed", "encode(sha256(attributes::text::bytea),'hex')", ("string", 64)), None, [("notnull",)]),
            ("weight_g", ("integer",), None, []),
            ("volume", ("string", 32), None, []),
            ("shipping_attrs", ("json",), None, []),
            ("compliance_status", ("enum", "enum_sku_compliance"), None, [("notnull",), ("default", "ok")]),
            ("salable_status", ("enum", "enum_sku_salable"), None, [("notnull",), ("default", "salable")]),
            ("created_at", ("timestamptz",), None, [("notnull",), ("default_now",)]),
            ("updated_at", ("timestamptz",), None, [("notnull",), ("default_now",)]),
        ],
        "extra": [("base_fk",), ("uc", ["product_id", "attributes_hash"])],
    },
    "supplier_offers": {
        "cols": [
            ("id", ("identity",), None, [("pk",)]),
            ("tenant_id", ("bigint",), None, [("notnull",)]),
            ("supplier_id", ("bigint",), None, [("notnull",)]),
            ("product_id", ("bigint",), None, []),
            ("sku_id", ("bigint",), None, []),
            ("supplier_sku_id", ("string", 64), None, [("notnull",)]),
            ("offer_id", ("string", 64), None, [("notnull",)]),
            ("price", ("numeric", 18, 6), None, [("notnull",)]),
            ("shipping", ("numeric", 18, 6), None, [("notnull",), ("default", "0")]),
            ("minimum_order", ("integer",), None, [("notnull",), ("default", "1")]),
            ("stock_observed", ("integer",), None, []),
            ("observed_at", ("timestamptz",), None, [("notnull",)]),
            ("expires_at", ("timestamptz",), None, [("notnull",)]),
            ("evidence_ref", ("string", 256), None, []),
            ("source", ("enum", "enum_offer_source"), None, [("notnull",)]),
            ("mode", ("enum", "enum_common_mode"), None, [("notnull",)]),
            ("is_preferred", ("bool",), None, [("notnull",), ("default", "false")]),
            ("preferred_status", ("enum", "enum_offer_preferred"), None, [("notnull",), ("default", "none")]),
            ("idempotency_key", ("string", 128), None, [("notnull",)]),
            ("created_at", ("timestamptz",), None, [("notnull",), ("default_now",)]),
        ],
        "extra": [("base_fk",), ("uc", ["tenant_id", "idempotency_key"])],
    },
    "assets": {
        "cols": [
            ("id", ("identity",), None, [("pk",)]),
            ("public_id", ("uuid",), None, [("notnull",)]),
            ("tenant_id", ("bigint",), None, [("notnull",)]),
            ("source_account_id", ("bigint",), None, []),
            ("content_sha256", ("string", 64), None, [("notnull",)]),
            ("perceptual_hash", ("string", 64), None, []),
            ("file_ref", ("string", 256), None, [("notnull",)]),
            ("mime_type", ("string", 64), None, [("notnull",)]),
            ("size_bytes", ("bigint",), None, [("notnull",)]),
            ("width", ("integer",), None, []),
            ("height", ("integer",), None, []),
            ("duration_ms", ("integer",), None, []),
            ("source_type", ("enum", "enum_asset_source_type"), None, [("notnull",)]),
            ("source_ref", ("string", 256), None, []),
            ("evidence_hash", ("string", 64), None, [("notnull",)]),
            ("rights_status", ("enum", "enum_rights_status"), None, [("notnull",), ("default", "unknown")]),
            ("rights_evidence", ("string", 256), None, []),
            ("captured_at", ("timestamptz",), None, [("notnull",)]),
            ("derived_from_asset_id", ("bigint",), None, []),
            ("transform_version", ("string", 64), None, []),
            ("quality_result", ("json",), None, []),
            ("relevance_result", ("json",), None, []),
            ("mode", ("enum", "enum_asset_mode"), None, [("notnull",)]),
            ("status", ("enum", "enum_asset_status"), None, [("notnull",), ("default", "active")]),
            ("created_at", ("timestamptz",), None, [("notnull",), ("default_now",)]),
            ("updated_at", ("timestamptz",), None, [("notnull",), ("default_now",)]),
            ("deleted_at", ("timestamptz",), None, []),
            ("row_version", ("integer",), None, [("notnull",), ("default", "1")]),
        ],
        "extra": [("base_fk",), ("uc", ["public_id"])],
    },
    "shop_listings": {
        "cols": [
            ("id", ("identity",), None, [("pk",)]),
            ("public_id", ("uuid",), None, [("notnull",)]),
            ("tenant_id", ("bigint",), None, [("notnull",)]),
            ("account_id", ("bigint",), None, [("notnull",)]),
            ("shop_id", ("bigint",), None, [("notnull",)]),
            ("product_id", ("bigint",), None, [("notnull",)]),
            ("platform_product_id", ("string", 128), None, []),
            ("title_effective", ("string", 200), None, [("notnull",)]),
            ("freight_template_id", ("string", 64), None, []),
            ("first_manual_confirm_actor_id", ("uuid",), None, []),
            ("auto_fix_count", ("integer",), None, [("notnull",), ("default", "0")]),
            ("idempotency_key", ("string", 128), None, [("notnull",)]),
            ("submit_version", ("integer",), None, [("notnull",), ("default", "1")]),
            ("status", ("enum", "enum_listing_status"), None, [("notnull",), ("default", "draft")]),
            ("created_at", ("timestamptz",), None, [("notnull",), ("default_now",)]),
            ("updated_at", ("timestamptz",), None, [("notnull",), ("default_now",)]),
            ("deleted_at", ("timestamptz",), None, []),
            ("row_version", ("integer",), None, [("notnull",), ("default", "1")]),
        ],
        "extra": [("base_fk",), ("uc", ["public_id"]), ("uc", ["tenant_id", "idempotency_key"])],
    },
    "shop_listing_skus": {
        "cols": [
            ("id", ("identity",), None, [("pk",)]),
            ("tenant_id", ("bigint",), None, [("notnull",)]),
            ("shop_listing_id", ("bigint",), None, [("notnull",)]),
            ("sku_id", ("bigint",), None, [("notnull",)]),
            ("platform_sku_id", ("string", 128), None, []),
            ("shop_price", ("bigint",), None, [("notnull",)]),
            ("promo_price", ("bigint",), None, []),
            ("floor_price", ("bigint",), None, []),
            ("allocated_stock", ("integer",), None, [("notnull",), ("default", "0")]),
            ("safety_stock", ("integer",), None, [("notnull",), ("default", "0")]),
            ("listing_status", ("enum", "enum_listing_sku_status"), None, [("notnull",), ("default", "listed")]),
            ("rejection_reason", ("string", 256), None, []),
            ("created_at", ("timestamptz",), None, [("notnull",), ("default_now",)]),
            ("updated_at", ("timestamptz",), None, [("notnull",), ("default_now",)]),
        ],
        "extra": [("base_fk",), ("uc", ["shop_listing_id", "sku_id"])],
    },
    "asset_product_bindings": {
        "cols": [
            ("id", ("identity",), None, [("pk",)]),
            ("tenant_id", ("bigint",), None, [("notnull",)]),
            ("asset_id", ("bigint",), None, [("notnull",)]),
            ("product_id", ("bigint",), None, [("notnull",)]),
            ("product_sku_id", ("bigint",), None, []),
            ("purpose", ("enum", "enum_media_purpose"), None, [("notnull",)]),
            ("relevance", ("numeric",), None, []),
            ("created_at", ("timestamptz",), None, [("notnull",), ("default_now",)]),
        ],
        "extra": [("base_fk",)],
    },
    "asset_shop_bindings": {
        "cols": [
            ("id", ("identity",), None, [("pk",)]),
            ("tenant_id", ("bigint",), None, [("notnull",)]),
            ("asset_id", ("bigint",), None, [("notnull",)]),
            ("asset_product_binding_id", ("bigint",), None, []),
            ("product_id", ("bigint",), None, []),
            ("shop_listing_id", ("bigint",), None, []),
            ("shop_id", ("bigint",), None, [("notnull",)]),
            ("purpose", ("enum", "enum_media_purpose"), None, [("notnull",)]),
            ("authorization_status", ("enum", "enum_shopbind_auth"), None, [("notnull",), ("default", "pending")]),
            ("review_status", ("enum", "enum_shopbind_review"), None, [("notnull",), ("default", "pending")]),
            ("bound_by_actor_id", ("uuid",), None, []),
            ("bound_at", ("timestamptz",), None, []),
            ("revoked_at", ("timestamptz",), None, []),
            ("created_at", ("timestamptz",), None, [("notnull",), ("default_now",)]),
            ("updated_at", ("timestamptz",), None, [("notnull",), ("default_now",)]),
        ],
        "extra": [("base_fk",)],
    },
    "asset_reviews": {
        "cols": [
            ("id", ("identity",), None, [("pk",)]),
            ("tenant_id", ("bigint",), None, [("notnull",)]),
            ("asset_id", ("bigint",), None, [("notnull",)]),
            ("review_scope", ("enum", "enum_review_scope"), None, [("notnull",)]),
            ("scope_ref_id", ("bigint",), None, [("notnull",)]),
            ("review_type", ("enum", "enum_review_type"), None, [("notnull",)]),
            ("attempt", ("integer",), None, [("notnull",), ("default", "1")]),
            ("reviewer_actor_id", ("uuid",), None, [("notnull",)]),
            ("decision", ("enum", "enum_review_decision"), None, [("notnull",)]),
            ("rejection_code", ("string", 64), None, []),
            ("platform_result", ("string", 256), None, []),
            ("reviewed_at", ("timestamptz",), None, [("notnull",)]),
            ("created_at", ("timestamptz",), None, [("notnull",), ("default_now",)]),
        ],
        "extra": [("base_fk",), ("uc", ["asset_id", "review_scope", "scope_ref_id", "review_type", "attempt"])],
    },
    "cost_snapshots": {
        "cols": [
            ("id", ("identity",), None, [("pk",)]),
            ("public_id", ("uuid",), None, [("notnull",)]),
            ("tenant_id", ("bigint",), None, [("notnull",)]),
            ("decision_object_type", ("enum", "enum_snapshot_objtype"), None, [("notnull",)]),
            ("decision_object_id", ("bigint",), None, [("notnull",)]),
            ("shop_id", ("bigint",), None, []),
            ("shop_listing_id", ("bigint",), None, []),
            ("offer_id", ("bigint",), None, []),
            ("policy_version_id", ("bigint",), None, [("notnull",)]),
            ("k_price", ("numeric", 18, 6), None, [("notnull",)]),
            ("j_service_fee", ("numeric", 18, 6), None, [("notnull",), ("default", "0")]),
            ("i_refund_reserve", ("numeric", 18, 6), None, [("notnull",), ("default", "0")]),
            ("h_shipping", ("numeric", 18, 6), None, [("notnull",), ("default", "0")]),
            ("g_product_cost", ("numeric", 18, 6), None, [("notnull",), ("default", "0")]),
            ("l_tax", ("numeric", 18, 6), None, [("notnull",), ("default", "0")]),
            ("consumption_rebate", ("numeric", 18, 6), None, [("notnull",), ("default", "0")]),
            ("technical_rebate", ("numeric", 18, 6), None, [("notnull",), ("default", "0")]),
            ("misc_cost", ("numeric", 18, 6), None, [("notnull",), ("default", "0")]),
            ("ad_pre_margin", ("numeric", 18, 6), None, [("notnull",)]),
            ("purchase_price_rounded", ("bigint",), None, []),
            ("idempotency_key", ("string", 128), None, [("notnull",)]),
            ("snapshot_at", ("timestamptz",), None, [("notnull",)]),
            ("created_at", ("timestamptz",), None, [("notnull",), ("default_now",)]),
        ],
        "extra": [("base_fk",), ("uc", ["public_id"]), ("uc", ["tenant_id", "idempotency_key"])],
    },
    "workflow_runs": {
        "cols": [
            ("id", ("identity",), None, [("pk",)]),
            ("public_id", ("uuid",), None, [("notnull",)]),
            ("tenant_id", ("bigint",), None, [("notnull",)]),
            ("run_type", ("enum", "enum_run_type"), None, [("notnull",)]),
            ("state", ("string", 64), None, []),
            ("input_ref", ("string", 256), None, []),
            ("output_ref", ("string", 256), None, []),
            ("status", ("enum", "enum_run_status"), None, [("notnull",), ("default", "running")]),
            ("idempotency_key", ("string", 128), None, [("notnull",)]),
            ("created_at", ("timestamptz",), None, [("notnull",), ("default_now",)]),
            ("updated_at", ("timestamptz",), None, [("notnull",), ("default_now",)]),
            ("row_version", ("integer",), None, [("notnull",), ("default", "1")]),
        ],
        "extra": [("base_fk",), ("uc", ["public_id"]), ("uc", ["tenant_id", "idempotency_key"])],
    },
    "workflow_steps": {
        "cols": [
            ("id", ("identity",), None, [("pk",)]),
            ("tenant_id", ("bigint",), None, [("notnull",)]),
            ("run_id", ("bigint",), None, [("notnull",)]),
            ("step_type", ("string", 64), None, [("notnull",)]),
            ("status", ("enum", "enum_step_status"), None, [("notnull",), ("default", "pending")]),
            ("attempt", ("integer",), None, [("notnull",), ("default", "1")]),
            ("gate_result", ("json",), None, []),
            ("evidence_ref", ("string", 256), None, []),
            ("error_code", ("string", 32), None, []),
            ("action_idempotency_key", ("string", 128), None, [("notnull",)]),
            ("created_at", ("timestamptz",), None, [("notnull",), ("default_now",)]),
            ("updated_at", ("timestamptz",), None, [("notnull",), ("default_now",)]),
        ],
        "extra": [("base_fk",), ("uc", ["run_id", "step_type", "attempt"]), ("uc", ["tenant_id", "action_idempotency_key"])],
    },
    "selection_decisions": {
        "cols": [
            ("id", ("identity",), None, [("pk",)]),
            ("public_id", ("uuid",), None, [("notnull",)]),
            ("tenant_id", ("bigint",), None, [("notnull",)]),
            ("product_id", ("bigint",), None, [("notnull",)]),
            ("source", ("enum", "enum_decision_source"), None, [("notnull",)]),
            ("source_account_id", ("bigint",), None, []),
            ("board_snapshot_ref", ("string", 256), None, []),
            ("page_evidence", ("json",), None, []),
            ("compliance_result", ("enum", "enum_decision_compliance"), None, [("notnull",)]),
            ("risk_tags", ("json",), None, []),
            ("human_review_note", ("string", 512), None, []),
            ("human_review_actor_id", ("uuid",), None, []),
            ("price_assumption", ("numeric", 18, 6), None, []),
            ("supply_price", ("numeric", 18, 6), None, []),
            ("shipping_cost", ("numeric", 18, 6), None, []),
            ("platform_fee", ("numeric", 18, 6), None, []),
            ("refund_reserve", ("numeric", 18, 6), None, []),
            ("ad_pre_margin", ("numeric", 18, 6), None, []),
            ("data_coverage", ("numeric",), None, []),
            ("confidence", ("numeric",), None, []),
            ("observed_at", ("timestamptz",), None, [("notnull",)]),
            ("quote_status", ("enum", "enum_quote_status"), None, [("notnull",), ("default", "none")]),
            ("quote_expires_at", ("timestamptz",), None, []),
            ("material_status", ("enum", "enum_material_status"), None, [("notnull",), ("default", "unknown")]),
            ("available_asset_count", ("integer",), None, []),
            ("source_url", ("string", 512), None, []),
            ("cost_snapshot_id", ("bigint",), None, []),
            ("policy_version_id", ("bigint",), None, []),
            ("workflow_run_id", ("bigint",), None, []),
            ("selection_batch_key", ("string", 128), None, [("notnull",)]),
            ("downstream_status", ("string", 64), None, []),
            ("block_reason", ("string", 256), None, []),
            ("state", ("enum", "enum_decision_state"), None, [("notnull",), ("default", "discovered")]),
            ("created_at", ("timestamptz",), None, [("notnull",), ("default_now",)]),
            ("updated_at", ("timestamptz",), None, [("notnull",), ("default_now",)]),
        ],
        "extra": [("base_fk",), ("uc", ["public_id"]), ("uc", ["tenant_id", "selection_batch_key", "product_id"])],
    },
    "pricing_decisions": {
        "cols": [
            ("id", ("identity",), None, [("pk",)]),
            ("public_id", ("uuid",), None, [("notnull",)]),
            ("tenant_id", ("bigint",), None, [("notnull",)]),
            ("shop_id", ("bigint",), None, [("notnull",)]),
            ("shop_listing_id", ("bigint",), None, [("notnull",)]),
            ("shop_listing_sku_id", ("bigint",), None, [("notnull",)]),
            ("cost_snapshot_id", ("bigint",), None, [("notnull",)]),
            ("policy_version_id", ("bigint",), None, [("notnull",)]),
            ("decision_type", ("enum", "enum_pricing_type"), None, [("notnull",)]),
            ("cost_floor_price", ("numeric", 18, 6), None, [("notnull",)]),
            ("suggested_price", ("numeric", 18, 6), None, [("notnull",)]),
            ("daily_price", ("numeric", 18, 6), None, []),
            ("promo_price", ("numeric", 18, 6), None, []),
            ("floor_price", ("numeric", 18, 6), None, [("notnull",)]),
            ("target_margin", ("numeric",), None, []),
            ("competitor_evidence", ("json",), None, []),
            ("bid_unrounded", ("numeric", 18, 6), None, []),
            ("bid_rounded_cents", ("bigint",), None, []),
            ("rounding_mode", ("string", 16), None, []),
            ("cid_inputs", ("json",), None, [("notnull",)]),
            ("cid_results", ("json",), None, [("notnull",)]),
            ("status", ("enum", "enum_pricing_status"), None, [("notnull",), ("default", "draft")]),
            ("approved_by_actor_id", ("uuid",), None, []),
            ("approved_at", ("timestamptz",), None, []),
            ("effective_from", ("timestamptz",), None, [("notnull",)]),
            ("effective_to", ("timestamptz",), None, []),
            ("evidence_ref", ("string", 256), None, []),
            ("idempotency_key", ("string", 128), None, [("notnull",)]),
            ("created_at", ("timestamptz",), None, [("notnull",), ("default_now",)]),
        ],
        "extra": [("base_fk",), ("uc", ["public_id"]), ("uc", ["tenant_id", "idempotency_key"])],
    },
    "listing_events": {
        "cols": [
            ("id", ("identity",), None, [("pk",)]),
            ("tenant_id", ("bigint",), None, [("notnull",)]),
            ("shop_listing_id", ("bigint",), None, [("notnull",)]),
            ("event_type", ("enum", "enum_listevent_type"), None, [("notnull",)]),
            ("from_state", ("string", 64), None, []),
            ("to_state", ("string", 64), None, [("notnull",)]),
            ("operator_actor_id", ("uuid",), None, [("notnull",)]),
            ("evidence_ref", ("string", 256), None, []),
            ("request_id", ("string", 128), None, [("notnull",)]),
            ("platform_request", ("json",), None, []),
            ("platform_response", ("json",), None, []),
            ("created_at", ("timestamptz",), None, [("notnull",), ("default_now",)]),
        ],
        "extra": [("base_fk",), ("uc", ["shop_listing_id", "event_type", "request_id"])],
    },
    "ad_campaigns": {
        "cols": [
            ("id", ("identity",), None, [("pk",)]),
            ("public_id", ("uuid",), None, [("notnull",)]),
            ("tenant_id", ("bigint",), None, [("notnull",)]),
            ("account_id", ("bigint",), None, [("notnull",)]),
            ("shop_id", ("bigint",), None, [("notnull",)]),
            ("shop_listing_id", ("bigint",), None, [("notnull",)]),
            ("platform_campaign_id", ("string", 128), None, []),
            ("idempotency_key", ("string", 128), None, [("notnull",)]),
            ("approved_budget", ("bigint",), None, [("notnull",)]),
            ("approved_daily_budget", ("bigint",), None, [("notnull",)]),
            ("approved_target_roi", ("numeric",), None, [("notnull",)]),
            ("approved_stop_loss", ("numeric",), None, [("notnull",)]),
            ("current_budget", ("bigint",), None, [("notnull",)]),
            ("current_daily_budget", ("bigint",), None, [("notnull",)]),
            ("current_target_roi", ("numeric",), None, [("notnull",)]),
            ("current_stop_loss", ("numeric",), None, [("notnull",)]),
            ("feedback_coefficient", ("numeric",), None, [("notnull",)]),
            ("cumulative_spend", ("bigint",), None, [("notnull",), ("default", "0")]),
            ("budget_policy_version_id", ("bigint",), None, [("notnull",)]),
            ("cid_policy_version_id", ("bigint",), None, [("notnull",)]),
            ("approval_ref", ("string", 256), None, []),
            ("status", ("enum", "enum_campaign_status"), None, [("notnull",), ("default", "draft")]),
            ("created_at", ("timestamptz",), None, [("notnull",), ("default_now",)]),
            ("updated_at", ("timestamptz",), None, [("notnull",), ("default_now",)]),
            ("deleted_at", ("timestamptz",), None, []),
            ("row_version", ("integer",), None, [("notnull",), ("default", "1")]),
        ],
        "extra": [("base_fk",), ("uc", ["public_id"]), ("uc", ["tenant_id", "idempotency_key"])],
    },
    "ad_campaign_assets": {
        "cols": [
            ("id", ("identity",), None, [("pk",)]),
            ("tenant_id", ("bigint",), None, [("notnull",)]),
            ("campaign_id", ("bigint",), None, [("notnull",)]),
            ("asset_shop_binding_id", ("bigint",), None, [("notnull",)]),
            ("created_at", ("timestamptz",), None, [("notnull",), ("default_now",)]),
        ],
        "extra": [("base_fk",), ("uc", ["campaign_id", "asset_shop_binding_id"])],
    },
    "ad_report_snapshots": {
        "cols": [
            ("id", ("identity",), None, [("pk",)]),
            ("tenant_id", ("bigint",), None, [("notnull",)]),
            ("account_id", ("bigint",), None, [("notnull",)]),
            ("shop_id", ("bigint",), None, [("notnull",)]),
            ("shop_listing_id", ("bigint",), None, [("notnull",)]),
            ("shop_listing_sku_id", ("bigint",), None, []),
            ("product_id", ("bigint",), None, [("notnull",)]),
            ("campaign_id", ("bigint",), None, [("notnull",)]),
            ("asset_binding_id", ("bigint",), None, []),
            ("granularity", ("enum", "enum_snapshot_granularity"), None, [("notnull",)]),
            ("window_start", ("timestamptz",), None, [("notnull",)]),
            ("window_end", ("timestamptz",), None, [("notnull",)]),
            ("attribution_mode", ("string", 64), None, [("notnull",)]),
            ("report_version_key", ("string", 128), None, [("notnull",)]),
            ("platform_updated_at", ("timestamptz",), None, []),
            ("captured_at", ("timestamptz",), None, [("notnull",)]),
            ("spend", ("bigint",), None, [("notnull",), ("default", "0")]),
            ("gmv", ("bigint",), None, [("notnull",), ("default", "0")]),
            ("roi", ("numeric",), None, []),
            ("impressions", ("integer",), None, [("notnull",), ("default", "0")]),
            ("clicks", ("integer",), None, [("notnull",), ("default", "0")]),
            ("orders", ("integer",), None, [("notnull",), ("default", "0")]),
            ("diagnosis", ("enum", "enum_snapshot_diag"), None, [("notnull",), ("default", "unknown")]),
            ("status", ("enum", "enum_snapshot_status"), None, [("notnull",), ("default", "unknown")]),
            ("raw_evidence_hash", ("string", 64), None, [("notnull",)]),
            ("created_at", ("timestamptz",), None, [("notnull",), ("default_now",)]),
        ],
        "extra": [("base_fk",)],
    },
    "roi_feedback_events": {
        "cols": [
            ("id", ("identity",), None, [("pk",)]),
            ("tenant_id", ("bigint",), None, [("notnull",)]),
            ("account_id", ("bigint",), None, [("notnull",)]),
            ("shop_id", ("bigint",), None, [("notnull",)]),
            ("shop_listing_id", ("bigint",), None, [("notnull",)]),
            ("shop_listing_sku_id", ("bigint",), None, []),
            ("product_id", ("bigint",), None, [("notnull",)]),
            ("campaign_id", ("bigint",), None, [("notnull",)]),
            ("asset_binding_id", ("bigint",), None, []),
            ("source_snapshot_id", ("bigint",), None, [("notnull",)]),
            ("window_start", ("timestamptz",), None, [("notnull",)]),
            ("window_end", ("timestamptz",), None, [("notnull",)]),
            ("attribution_mode", ("string", 64), None, [("notnull",)]),
            ("feedback_type", ("enum", "enum_feedback_type"), None, [("notnull",)]),
            ("subject_type", ("enum", "enum_feedback_subject"), None, [("notnull",)]),
            ("subject_key", ("string", 128), None, [("notnull",)]),
            ("value", ("numeric",), None, [("notnull",)]),
            ("extra_explanation", ("json",), None, []),
            ("aggregation_version", ("string", 64), None, [("notnull",)]),
            ("idempotency_key", ("string", 128), None, [("notnull",)]),
            ("created_at", ("timestamptz",), None, [("notnull",), ("default_now",)]),
        ],
        "extra": [
            ("base_fk",),
            ("ck", "ck_feedback_subject_map",
             "(feedback_type='product_score' AND subject_type='product') OR "
             "(feedback_type='category_score' AND subject_type='category') OR "
             "(feedback_type='material_score' AND subject_type='material') OR "
             "(feedback_type='sku_margin' AND subject_type='sku') OR "
             "(feedback_type='shop_strategy' AND subject_type='shop')"),
            ("uc", ["tenant_id", "idempotency_key"]),
            ("uc", ["source_snapshot_id", "feedback_type", "subject_type", "subject_key", "aggregation_version"]),
        ],
    },
    "manual_tasks": {
        "cols": [
            ("id", ("identity",), None, [("pk",)]),
            ("tenant_id", ("bigint",), None, [("notnull",)]),
            ("task_type", ("enum", "enum_task_type"), None, [("notnull",)]),
            ("ref_type", ("string", 64), None, [("notnull",)]),
            ("ref_id", ("bigint",), None, [("notnull",)]),
            ("status", ("enum", "enum_task_status"), None, [("notnull",), ("default", "pending")]),
            ("reason", ("string", 512), None, []),
            ("assignee_actor_id", ("uuid",), None, []),
            ("approved_by_actor_id", ("uuid",), None, []),
            ("before_state", ("string", 64), None, []),
            ("after_state", ("string", 64), None, []),
            ("policy_version_id", ("bigint",), None, []),
            ("evidence_ref", ("string", 256), None, []),
            ("created_at", ("timestamptz",), None, [("notnull",), ("default_now",)]),
            ("resolved_at", ("timestamptz",), None, []),
        ],
        "extra": [("base_fk",)],
    },
    "audit_events": {
        "cols": [
            ("id", ("identity",), None, [("pk",)]),
            ("tenant_id", ("bigint",), None, [("notnull",)]),
            ("actor_id", ("uuid",), None, [("notnull",)]),
            ("action", ("string", 64), None, [("notnull",)]),
            ("target_type", ("string", 64), None, [("notnull",)]),
            ("target_public_id", ("uuid",), None, [("notnull",)]),
            ("before", ("json",), None, []),
            ("after", ("json",), None, []),
            ("evidence_ref", ("string", 256), None, []),
            ("request_id", ("string", 128), None, []),
            ("created_at", ("timestamptz",), None, [("notnull",), ("default_now",)]),
        ],
        "extra": [("base_fk",)],
    },
    "alert_events": {
        "cols": [
            ("id", ("identity",), None, [("pk",)]),
            ("public_id", ("uuid",), None, [("notnull",)]),
            ("tenant_id", ("bigint",), None, [("notnull",)]),
            ("fingerprint", ("string", 128), None, [("notnull",)]),
            ("severity", ("enum", "enum_alert_severity"), None, [("notnull",)]),
            ("category", ("enum", "enum_alert_category"), None, [("notnull",)]),
            ("title", ("string", 128), None, [("notnull",)]),
            ("detail", ("text",), None, []),
            ("status", ("enum", "enum_alert_status"), None, [("notnull",), ("default", "open")]),
            ("first_seen_at", ("timestamptz",), None, [("notnull",)]),
            ("last_seen_at", ("timestamptz",), None, [("notnull",)]),
            ("occurrence_count", ("integer",), None, [("notnull",), ("default", "1")]),
            ("cooldown_until", ("timestamptz",), None, []),
            ("acknowledged_by_actor_id", ("uuid",), None, []),
            ("acknowledged_at", ("timestamptz",), None, []),
            ("resolved_by_actor_id", ("uuid",), None, []),
            ("resolved_at", ("timestamptz",), None, []),
            ("created_at", ("timestamptz",), None, [("notnull",), ("default_now",)]),
            ("updated_at", ("timestamptz",), None, [("notnull",), ("default_now",)]),
            ("row_version", ("integer",), None, [("notnull",), ("default", "1")]),
        ],
        "extra": [("base_fk",), ("uc", ["public_id"])],
    },
    "alert_deliveries": {
        "cols": [
            ("id", ("identity",), None, [("pk",)]),
            ("tenant_id", ("bigint",), None, [("notnull",)]),
            ("alert_event_id", ("bigint",), None, [("notnull",)]),
            ("channel", ("enum", "enum_delivery_channel"), None, [("notnull",)]),
            ("notification_type", ("enum", "enum_delivery_notif"), None, [("notnull",)]),
            ("status", ("enum", "enum_delivery_status"), None, [("notnull",), ("default", "pending")]),
            ("attempt", ("integer",), None, [("notnull",), ("default", "1")]),
            ("error_detail", ("string", 256), None, []),
            ("sent_at", ("timestamptz",), None, []),
            ("created_at", ("timestamptz",), None, [("notnull",), ("default_now",)]),
        ],
        "extra": [("base_fk",), ("uc", ["alert_event_id", "channel", "notification_type", "attempt"])],
    },
}


def _validate() -> None:
    tbl = [t for w in WAVES for t in w]
    assert len(tbl) == 31, f"WAVES 表数 == {len(tbl)} != 31"
    assert len(set(tbl)) == 31, "WAVES 有重复表"
    assert set(tbl) == set(TABLES), "WAVES 与 TABLES 键集不一致"
    assert len(PARENT_KEYS) == 17, f"PARENT_KEYS == {len(PARENT_KEYS)}"
    assert all(p in TABLES for p in PARENT_KEYS), "PARENT_KEYS 含未知表"
    from collections import Counter
    cnt = Counter(c for c, _p, _cc, _pc, _n in COMPOSITE_FKS)
    expected = {
        "shops": 1, "account_runtime_profiles": 1, "credential_refs": 1, "product_skus": 1,
        "supplier_offers": 3, "cost_snapshots": 3, "selection_decisions": 4, "assets": 2,
        "asset_product_bindings": 3, "asset_shop_bindings": 5, "asset_reviews": 1,
        "shop_listings": 3, "shop_listing_skus": 2, "pricing_decisions": 4, "listing_events": 1,
        "ad_campaigns": 3, "ad_campaign_assets": 2, "ad_report_snapshots": 7,
        "roi_feedback_events": 8, "workflow_steps": 1, "policy_versions": 1, "alert_deliveries": 1,
    }
    assert len(COMPOSITE_FKS) == 58, f"COMPOSITE_FKS == {len(COMPOSITE_FKS)} != 58"
    assert dict(cnt) == expected, "58 组合 FK 分组合计不匹配 ddl-order §五"
    assert len(NULLS_UNIQUE) == 4, f"NULLS_UNIQUE == {len(NULLS_UNIQUE)}"
    assert len(PARTIAL_UNIQUE) == 15, f"PARTIAL_UNIQUE == {len(PARTIAL_UNIQUE)}"
    assert len(PLAIN_INDEXES) == 8, f"PLAIN_INDEXES == {len(PLAIN_INDEXES)}"
    base = [t for t, d in TABLES.items() if any(e[0] in ("base_fk", "base_fk_restrict") for e in d["extra"])]
    assert len(base) == 28, f"基础 FK 表 == {len(base)} != 28"
    assert "tenants" not in base and "actor_registry" not in base and "policy_versions" not in base
    names = [f"fk_{c}_{p}" for c, p, _cc, _pc, _n in COMPOSITE_FKS]
    assert len(set(names)) == 58, "组合 FK 命名冲突"
    for c, p, cc, pc, _n in COMPOSITE_FKS:
        assert c in TABLES and p in TABLES, f"FK 未知表 {c}/{p}"
        for col in cc:
            assert col in [x[0] for x in TABLES[c]["cols"]], f"FK 子列 {c}.{col} 不存在"
    # R54-2：11 条冻结 ON DELETE action 必须全部落在组合 FK 键上，且值合法
    fk_pairs = {(c, p) for c, p, _cc, _pc, _n in COMPOSITE_FKS}
    assert set(FK_ACTIONS) <= fk_pairs, "FK_ACTIONS 含不在 COMPOSITE_FKS 的键"
    assert len(FK_ACTIONS) == 11, f"FK_ACTIONS == {len(FK_ACTIONS)} != 11"
    assert Counter(FK_ACTIONS.values()) == Counter({"CASCADE": 10, "RESTRICT": 1}), "FK_ACTIONS 应为 10 CASCADE + 1 RESTRICT"
    # R54-1：31 identity / 23 jsonb / 14 public_id
    idents = [c for d in TABLES.values() for c in d["cols"] if c[1][0] == "identity"]
    jsons = [c for d in TABLES.values() for c in d["cols"] if c[1][0] == "json"]
    pids = [c for d in TABLES.values() for c in d["cols"] if c[0] == "public_id"]
    assert len(idents) == 31, f"identity 列 == {len(idents)} != 31"
    assert len(jsons) == 23, f"jsonb 列 == {len(jsons)} != 23"
    assert len(pids) == 14, f"public_id 列 == {len(pids)} != 14"
    # R54-1 补强：27 个列级 CHECK 全部落在真实列上
    assert len(COLUMN_CHECKS) == 27, f"COLUMN_CHECKS == {len(COLUMN_CHECKS)} != 27"
    for (t, c), expr in COLUMN_CHECKS.items():
        assert t in TABLES, f"COLUMN_CHECKS 未知表 {t}"
        assert c in [x[0] for x in TABLES[t]["cols"]], f"COLUMN_CHECKS 未知列 {t}.{c}"
        assert ">= 0" in expr or "> 0" in expr, f"COLUMN_CHECKS 表达式异常 {t}.{c}: {expr}"
    for t, _i, cols, _w in PARTIAL_UNIQUE:
        for col in cols:
            assert col in [x[0] for x in TABLES[t]["cols"]], f"部分唯一列 {t}.{col} 不存在"
    for t, _i, cols in PLAIN_INDEXES:
        for col in cols:
            assert col in [x[0] for x in TABLES[t]["cols"]], f"普通索引列 {t}.{col} 不存在"


def _type_text(tp):
    if tp[0] == "identity":
        return "sa.BigInteger(), sa.Identity(always=True)"
    if tp[0] == "bigint":
        return "sa.BigInteger()"
    if tp[0] == "integer":
        return "sa.Integer()"
    if tp[0] == "uuid":
        return "sa.Uuid()"
    if tp[0] == "string":
        return f"sa.String({tp[1]})"
    if tp[0] == "text":
        return "sa.Text()"
    if tp[0] == "bool":
        return "sa.Boolean()"
    if tp[0] == "json":
        return "postgresql.JSONB()"
    if tp[0] == "numeric":
        return "sa.Numeric()" if len(tp) == 1 else f"sa.Numeric({tp[1]}, {tp[2]})"
    if tp[0] == "timestamptz":
        return "sa.TIMESTAMP(timezone=True)"
    if tp[0] == "enum":
        return f'postgresql.ENUM(name="{tp[1]}", create_type=False)'
    if tp[0] == "computed":
        return None  # 特殊处理
    raise ValueError(f"未知类型 {tp}")


def _col_text(rec, table):
    name, tp, _nullable, extras = rec
    has_pk = ("pk",) in [tuple(e) for e in extras]
    notnull = ("notnull",) in [tuple(e) for e in extras]
    if tp[0] == "computed":
        expr, st = tp[1], tp[2]
        parts = [f"\"{name}\", {_type_text(st)}, sa.Computed({expr!r}, persisted=True)", "nullable=False" if notnull else "nullable=True"]
        return "sa.Column(" + ", ".join(parts) + ")"
    parts = [f"\"{name}\", {_type_text(tp)}"]
    ck = COLUMN_CHECKS.get((table, name))
    if ck is not None:
        # CheckConstraint 为位置参数，须在 primary_key/nullable 关键字之前
        parts.append(f"sa.CheckConstraint({ck!r})")
    if has_pk:
        parts.append("primary_key=True")
    else:
        parts.append("nullable=False" if notnull else "nullable=True")
    for e in extras:
        t = tuple(e)
        if t[0] == "default":
            parts.append(f"server_default={t[1]!r}")
        elif t[0] == "default_now":
            parts.append('server_default=sa.text("now()")')
    if name == "public_id":
        # v6 §0.1：外部标识 public_id uuid not null default gen_random_uuid()
        parts.append('server_default=sa.text("gen_random_uuid()")')
    return "sa.Column(" + ", ".join(parts) + ")"


def _extra_text(e):
    if e[0] == "base_fk":
        return 'sa.ForeignKeyConstraint(["tenant_id"], ["app.tenants.id"])'
    if e[0] == "base_fk_restrict":
        return 'sa.ForeignKeyConstraint(["tenant_id"], ["app.tenants.id"], ondelete="RESTRICT")'
    if e[0] == "uc":
        cols = ", ".join(repr(c) for c in e[1])
        return f"sa.UniqueConstraint({cols})"
    if e[0] == "ck":
        return f"sa.CheckConstraint({e[2]!r}, name={e[1]!r})"
    raise ValueError(f"未知表级约束 {e}")


def build_content() -> str:
    L = []
    L.append('"""T3: 31 tables + constraints (data-driven generator, from 15-数据字典.md v6 + ddl-order.md, round-53)')
    L.append("")
    L.append("Revision ID: %s" % REV)
    L.append("Revises: %s" % DOWN)
    L.append("Create Date: %s" % CREATE_DATE)
    L.append('"""')
    L.append("from typing import Sequence, Union")
    L.append("")
    L.append("from alembic import op")
    L.append("import sqlalchemy as sa")
    L.append("from sqlalchemy.dialects import postgresql")
    L.append("")
    L.append("")
    L.append("revision: str = %r" % REV)
    L.append("down_revision: Union[str, Sequence[str], None] = %r" % DOWN)
    L.append("branch_labels: Union[str, Sequence[str], None] = None")
    L.append("depends_on: Union[str, Sequence[str], None] = None")
    L.append("")
    L.append("")
    L.append("SCHEMA = %r" % SCHEMA)
    L.append("")
    L.append("WAVES = [")
    for wave in WAVES:
        L.append("    %r," % wave)
    L.append("]")
    L.append("")
    L.append("PARENT_KEYS = [")
    for p in PARENT_KEYS:
        L.append("    %r," % p)
    L.append("]")
    L.append("")
    L.append("COMPOSITE_FKS = [")
    for c, p, cc, pc, n in COMPOSITE_FKS:
        L.append("    (%r, %r, %r, %r, %r)," % (c, p, cc, pc, n))
    L.append("]")
    L.append("")
    L.append("FK_ACTIONS = {")
    for (c, p), action in sorted(FK_ACTIONS.items()):
        L.append("    (%r, %r): %r," % (c, p, action))
    L.append("}")
    L.append("")
    L.append("NULLS_UNIQUE = [")
    for t, cols in NULLS_UNIQUE:
        L.append("    (%r, %r)," % (t, cols))
    L.append("]")
    L.append("")
    L.append("PARTIAL_UNIQUE = [")
    for t, idx, cols, w in PARTIAL_UNIQUE:
        L.append("    (%r, %r, %r, %r)," % (t, idx, cols, w))
    L.append("]")
    L.append("")
    L.append("PLAIN_INDEXES = [")
    for t, idx, cols in PLAIN_INDEXES:
        L.append("    (%r, %r, %r)," % (t, idx, cols))
    L.append("]")
    L.append("")

    L.append("")
    L.append("def upgrade() -> None:")
    L.append('    """W0~W8 建表；G4 父键；G5 组合 FK；G6 NULLS NOT DISTINCT；G8 exclusion；G9 索引。"""')

    # 建表
    for wi, wave in enumerate(WAVES):
        L.append("")
        L.append("    # ================= W%d =================" % wi)
        for t in wave:
            d = TABLES[t]
            L.append("    op.create_table(")
            L.append("        %r," % t)
            for col in d["cols"]:
                L.append("        " + _col_text(col, t) + ",")
            for e in d["extra"]:
                L.append("        " + _extra_text(e) + ",")
            L.append("        schema=SCHEMA,")
            L.append("    )")
            L.append("")

    # G4 17 父候选键
    L.append("    # ---- G4: 17 父候选键 UNIQUE(tenant_id, id) ----")
    L.append("    for t in PARENT_KEYS:")
    L.append('        op.create_unique_constraint("uq_" + t + "_tenant_id_id", t, ["tenant_id", "id"], schema=SCHEMA)')
    L.append("")

    # G5 58 组合 FK
    L.append("    # ---- G5: 58 组合 FK（命名 fk_<child>_<parent>，< 64 字符；11 条冻结 ON DELETE）----")
    L.append("    for child, parent, ccols, pcols, _nullable in COMPOSITE_FKS:")
    L.append("        op.create_foreign_key(")
    L.append('            "fk_" + child + "_" + parent,')
    L.append('            child, parent, ccols, pcols, source_schema=SCHEMA, referent_schema=SCHEMA,')
    L.append("            ondelete=FK_ACTIONS.get((child, parent)),")
    L.append("        )")
    L.append("")

    # G6 4 NULLS NOT DISTINCT
    L.append("    # ---- G6: 4 x UNIQUE NULLS NOT DISTINCT（索引名 uq_<table>_nullsdistinct < 63）----")
    L.append("    for table, cols in NULLS_UNIQUE:")
    L.append("        col_list = ', '.join('\"%s\"' % c for c in cols)")
    L.append("        op.execute('CREATE UNIQUE INDEX \"uq_' + table + '_nullsdistinct\" ON \"' + SCHEMA + '\".\"' + table + '\" (' + col_list + ') NULLS NOT DISTINCT')")
    L.append("")

    # G8 2 exclusion（btree_gist 已由 T1 baseline 建；'infinity' 用 ::timestamptz）
    L.append("    # ---- G8: 2 exclusion（btree_gist）----")
    L.append("    op.execute(")
    L.append("        f'ALTER TABLE \"{SCHEMA}\".pricing_decisions ADD CONSTRAINT ex_pricing_single_effective '")
    L.append("        f'EXCLUDE USING gist (shop_listing_sku_id WITH =, '")
    L.append("        f\"tstzrange(effective_from, COALESCE(effective_to,'infinity'::timestamptz)) WITH &&) \"")
    L.append("        f\"WHERE (status='approved')\"")
    L.append("    )")
    L.append("    op.execute(")
    L.append("        f'ALTER TABLE \"{SCHEMA}\".policy_versions ADD CONSTRAINT ex_policy_scope_effective '")
    L.append("        f'EXCLUDE USING gist (COALESCE(tenant_id,0) WITH =, policy_type WITH =, scope_type WITH =, '")
    L.append("        f\"scope_key WITH =, tstzrange(effective_from, COALESCE(effective_to,'infinity'::timestamptz)) WITH &&)\"")
    L.append("    )")
    L.append("")

    # G9 15 部分唯一 + 8 普通索引
    L.append("    # ---- G9: 15 部分唯一 + 8 普通索引（index-registry.md）----")
    L.append("    for table, idx, cols, where in PARTIAL_UNIQUE:")
    L.append("        col_list = ', '.join('\"%s\"' % c for c in cols)")
    L.append("        op.execute('CREATE UNIQUE INDEX \"' + idx + '\" ON \"' + SCHEMA + '\".\"' + table + '\" (' + col_list + ') WHERE ' + where)")
    L.append("")
    L.append("    for table, idx, cols in PLAIN_INDEXES:")
    L.append("        col_list = ', '.join('\"%s\"' % c for c in cols)")
    L.append("        op.execute('CREATE INDEX \"' + idx + '\" ON \"' + SCHEMA + '\".\"' + table + '\" (' + col_list + ')')")

    # downgrade
    L.append("")
    L.append("")
    L.append("def downgrade() -> None:")
    L.append('    """严格逆序：索引 -> exclusion -> NULLS/唯一 -> FK -> 父键 -> 表。"""')
    L.append("    for table, idx, _cols in reversed(PLAIN_INDEXES):")
    L.append("        op.execute('DROP INDEX IF EXISTS \"' + SCHEMA + '\".\"' + idx + '\"')")
    L.append("    for table, idx, _cols, _w in reversed(PARTIAL_UNIQUE):")
    L.append("        op.execute('DROP INDEX IF EXISTS \"' + SCHEMA + '\".\"' + idx + '\"')")
    L.append("    op.execute('ALTER TABLE \"' + SCHEMA + '\".pricing_decisions DROP CONSTRAINT IF EXISTS ex_pricing_single_effective')")
    L.append("    op.execute('ALTER TABLE \"' + SCHEMA + '\".policy_versions DROP CONSTRAINT IF EXISTS ex_policy_scope_effective')")
    L.append("    for table, _cols in reversed(NULLS_UNIQUE):")
    L.append("        op.execute('DROP INDEX IF EXISTS \"' + SCHEMA + '\".\"uq_' + table + '_nullsdistinct\"')")
    L.append("    for child, parent, _ccols, _pcols, _nullable in reversed(COMPOSITE_FKS):")
    L.append("        op.drop_constraint(\"fk_\" + child + \"_\" + parent, child, type_=\"foreignkey\", schema=SCHEMA)")
    L.append("    for t in reversed(PARENT_KEYS):")
    L.append("        op.drop_constraint(\"uq_\" + t + \"_tenant_id_id\", t, type_=\"unique\", schema=SCHEMA)")
    L.append("    # 严格逆序：W8->W0 且每个 wave 内也逆序（R54-4）")
    L.append("    for w in reversed(WAVES):")
    L.append("        for t in reversed(w):")
    L.append("            op.drop_table(t, schema=SCHEMA)")

    return "\n".join(L) + "\n"


def main():
    _validate()
    check_only = "--check" in sys.argv
    content = build_content()
    out = VERSIONS / CANONICAL_NAME

    if out.exists():
        existing = out.read_text(encoding="utf-8")
        if existing == content:
            print(f"[OK] {CANONICAL_NAME} 与生成器一致（无漂移）")
            return
        print(f"[FAIL] {CANONICAL_NAME} 内容与生成器漂移；拒绝覆盖。请人工核对。", file=sys.stderr)
        sys.exit(1)

    if check_only:
        print(f"[FAIL] --check：{CANONICAL_NAME} 不存在", file=sys.stderr)
        sys.exit(1)

    out.write_text(content, encoding="utf-8")
    print(f"[OK] generated {out} ({len(TABLES)} tables)")


if __name__ == "__main__":
    main()