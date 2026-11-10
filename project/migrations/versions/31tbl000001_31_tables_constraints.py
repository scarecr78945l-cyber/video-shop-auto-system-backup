"""T3: 31 tables + constraints (data-driven generator, from 15-数据字典.md v6 + ddl-order.md, round-53)

Revision ID: 31tbl000001
Revises: 60enum000000
Create Date: 2026-09-03T13:00:00+00:00
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = '31tbl000001'
down_revision: Union[str, Sequence[str], None] = '60enum000000'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


SCHEMA = 'app'

WAVES = [
    ['tenants', 'actor_registry', 'policy_versions'],
    ['platform_accounts', 'shops', 'account_runtime_profiles', 'credential_refs'],
    ['suppliers', 'products', 'product_skus', 'supplier_offers'],
    ['assets', 'shop_listings', 'shop_listing_skus'],
    ['asset_product_bindings', 'asset_shop_bindings', 'asset_reviews'],
    ['cost_snapshots', 'workflow_runs', 'workflow_steps', 'selection_decisions'],
    ['pricing_decisions', 'listing_events'],
    ['ad_campaigns', 'ad_campaign_assets', 'ad_report_snapshots', 'roi_feedback_events'],
    ['manual_tasks', 'audit_events', 'alert_events', 'alert_deliveries'],
]

PARENT_KEYS = [
    'platform_accounts',
    'shops',
    'suppliers',
    'products',
    'product_skus',
    'supplier_offers',
    'cost_snapshots',
    'assets',
    'asset_product_bindings',
    'asset_shop_bindings',
    'shop_listings',
    'shop_listing_skus',
    'ad_campaigns',
    'ad_report_snapshots',
    'workflow_runs',
    'policy_versions',
    'alert_events',
]

COMPOSITE_FKS = [
    ('shops', 'platform_accounts', ['tenant_id', 'account_id'], ['tenant_id', 'id'], False),
    ('account_runtime_profiles', 'platform_accounts', ['tenant_id', 'account_id'], ['tenant_id', 'id'], False),
    ('credential_refs', 'platform_accounts', ['tenant_id', 'account_id'], ['tenant_id', 'id'], False),
    ('product_skus', 'products', ['tenant_id', 'product_id'], ['tenant_id', 'id'], False),
    ('supplier_offers', 'suppliers', ['tenant_id', 'supplier_id'], ['tenant_id', 'id'], False),
    ('supplier_offers', 'product_skus', ['tenant_id', 'sku_id'], ['tenant_id', 'id'], True),
    ('supplier_offers', 'products', ['tenant_id', 'product_id'], ['tenant_id', 'id'], True),
    ('cost_snapshots', 'shops', ['tenant_id', 'shop_id'], ['tenant_id', 'id'], True),
    ('cost_snapshots', 'shop_listings', ['tenant_id', 'shop_listing_id'], ['tenant_id', 'id'], True),
    ('cost_snapshots', 'supplier_offers', ['tenant_id', 'offer_id'], ['tenant_id', 'id'], True),
    ('selection_decisions', 'products', ['tenant_id', 'product_id'], ['tenant_id', 'id'], False),
    ('selection_decisions', 'platform_accounts', ['tenant_id', 'source_account_id'], ['tenant_id', 'id'], True),
    ('selection_decisions', 'cost_snapshots', ['tenant_id', 'cost_snapshot_id'], ['tenant_id', 'id'], True),
    ('selection_decisions', 'workflow_runs', ['tenant_id', 'workflow_run_id'], ['tenant_id', 'id'], True),
    ('assets', 'platform_accounts', ['tenant_id', 'source_account_id'], ['tenant_id', 'id'], True),
    ('assets', 'assets', ['tenant_id', 'derived_from_asset_id'], ['tenant_id', 'id'], True),
    ('asset_product_bindings', 'assets', ['tenant_id', 'asset_id'], ['tenant_id', 'id'], False),
    ('asset_product_bindings', 'products', ['tenant_id', 'product_id'], ['tenant_id', 'id'], False),
    ('asset_product_bindings', 'product_skus', ['tenant_id', 'product_sku_id'], ['tenant_id', 'id'], True),
    ('asset_shop_bindings', 'assets', ['tenant_id', 'asset_id'], ['tenant_id', 'id'], False),
    ('asset_shop_bindings', 'shops', ['tenant_id', 'shop_id'], ['tenant_id', 'id'], False),
    ('asset_shop_bindings', 'asset_product_bindings', ['tenant_id', 'asset_product_binding_id'], ['tenant_id', 'id'], True),
    ('asset_shop_bindings', 'products', ['tenant_id', 'product_id'], ['tenant_id', 'id'], True),
    ('asset_shop_bindings', 'shop_listings', ['tenant_id', 'shop_listing_id'], ['tenant_id', 'id'], True),
    ('asset_reviews', 'assets', ['tenant_id', 'asset_id'], ['tenant_id', 'id'], False),
    ('shop_listings', 'platform_accounts', ['tenant_id', 'account_id'], ['tenant_id', 'id'], False),
    ('shop_listings', 'shops', ['tenant_id', 'shop_id'], ['tenant_id', 'id'], False),
    ('shop_listings', 'products', ['tenant_id', 'product_id'], ['tenant_id', 'id'], False),
    ('shop_listing_skus', 'shop_listings', ['tenant_id', 'shop_listing_id'], ['tenant_id', 'id'], False),
    ('shop_listing_skus', 'product_skus', ['tenant_id', 'sku_id'], ['tenant_id', 'id'], False),
    ('pricing_decisions', 'shops', ['tenant_id', 'shop_id'], ['tenant_id', 'id'], False),
    ('pricing_decisions', 'shop_listings', ['tenant_id', 'shop_listing_id'], ['tenant_id', 'id'], False),
    ('pricing_decisions', 'shop_listing_skus', ['tenant_id', 'shop_listing_sku_id'], ['tenant_id', 'id'], False),
    ('pricing_decisions', 'cost_snapshots', ['tenant_id', 'cost_snapshot_id'], ['tenant_id', 'id'], False),
    ('listing_events', 'shop_listings', ['tenant_id', 'shop_listing_id'], ['tenant_id', 'id'], False),
    ('ad_campaigns', 'platform_accounts', ['tenant_id', 'account_id'], ['tenant_id', 'id'], False),
    ('ad_campaigns', 'shops', ['tenant_id', 'shop_id'], ['tenant_id', 'id'], False),
    ('ad_campaigns', 'shop_listings', ['tenant_id', 'shop_listing_id'], ['tenant_id', 'id'], False),
    ('ad_campaign_assets', 'ad_campaigns', ['tenant_id', 'campaign_id'], ['tenant_id', 'id'], False),
    ('ad_campaign_assets', 'asset_shop_bindings', ['tenant_id', 'asset_shop_binding_id'], ['tenant_id', 'id'], False),
    ('ad_report_snapshots', 'platform_accounts', ['tenant_id', 'account_id'], ['tenant_id', 'id'], False),
    ('ad_report_snapshots', 'shops', ['tenant_id', 'shop_id'], ['tenant_id', 'id'], False),
    ('ad_report_snapshots', 'shop_listings', ['tenant_id', 'shop_listing_id'], ['tenant_id', 'id'], False),
    ('ad_report_snapshots', 'shop_listing_skus', ['tenant_id', 'shop_listing_sku_id'], ['tenant_id', 'id'], True),
    ('ad_report_snapshots', 'products', ['tenant_id', 'product_id'], ['tenant_id', 'id'], False),
    ('ad_report_snapshots', 'ad_campaigns', ['tenant_id', 'campaign_id'], ['tenant_id', 'id'], False),
    ('ad_report_snapshots', 'asset_shop_bindings', ['tenant_id', 'asset_binding_id'], ['tenant_id', 'id'], True),
    ('roi_feedback_events', 'platform_accounts', ['tenant_id', 'account_id'], ['tenant_id', 'id'], False),
    ('roi_feedback_events', 'shops', ['tenant_id', 'shop_id'], ['tenant_id', 'id'], False),
    ('roi_feedback_events', 'shop_listings', ['tenant_id', 'shop_listing_id'], ['tenant_id', 'id'], False),
    ('roi_feedback_events', 'shop_listing_skus', ['tenant_id', 'shop_listing_sku_id'], ['tenant_id', 'id'], True),
    ('roi_feedback_events', 'products', ['tenant_id', 'product_id'], ['tenant_id', 'id'], False),
    ('roi_feedback_events', 'ad_campaigns', ['tenant_id', 'campaign_id'], ['tenant_id', 'id'], False),
    ('roi_feedback_events', 'asset_shop_bindings', ['tenant_id', 'asset_binding_id'], ['tenant_id', 'id'], True),
    ('roi_feedback_events', 'ad_report_snapshots', ['tenant_id', 'source_snapshot_id'], ['tenant_id', 'id'], False),
    ('workflow_steps', 'workflow_runs', ['tenant_id', 'run_id'], ['tenant_id', 'id'], False),
    ('policy_versions', 'policy_versions', ['tenant_id', 'supersedes_id'], ['tenant_id', 'id'], True),
    ('alert_deliveries', 'alert_events', ['tenant_id', 'alert_event_id'], ['tenant_id', 'id'], False),
]

FK_ACTIONS = {
    ('account_runtime_profiles', 'platform_accounts'): 'CASCADE',
    ('ad_campaign_assets', 'ad_campaigns'): 'CASCADE',
    ('alert_deliveries', 'alert_events'): 'CASCADE',
    ('asset_product_bindings', 'assets'): 'CASCADE',
    ('asset_reviews', 'assets'): 'CASCADE',
    ('asset_shop_bindings', 'assets'): 'CASCADE',
    ('credential_refs', 'platform_accounts'): 'CASCADE',
    ('product_skus', 'products'): 'CASCADE',
    ('shop_listing_skus', 'shop_listings'): 'CASCADE',
    ('supplier_offers', 'suppliers'): 'RESTRICT',
    ('workflow_steps', 'workflow_runs'): 'CASCADE',
}

NULLS_UNIQUE = [
    ('asset_product_bindings', ['asset_id', 'product_id', 'product_sku_id', 'purpose']),
    ('asset_shop_bindings', ['asset_id', 'shop_id', 'product_id', 'shop_listing_id', 'purpose']),
    ('ad_report_snapshots', ['campaign_id', 'granularity', 'shop_listing_sku_id', 'asset_binding_id', 'window_start', 'window_end', 'attribution_mode', 'report_version_key']),
    ('policy_versions', ['tenant_id', 'policy_type', 'scope_type', 'scope_key', 'version']),
]

PARTIAL_UNIQUE = [
    ('tenants', 'px_tenants_name', ['name'], 'deleted_at IS NULL'),
    ('platform_accounts', 'px_accounts_platform_key', ['tenant_id', 'platform', 'account_key'], 'deleted_at IS NULL'),
    ('shops', 'px_shops_account_shop', ['account_id', 'platform_shop_id'], 'deleted_at IS NULL'),
    ('account_runtime_profiles', 'px_profiles_active', ['account_id', 'purpose'], "status='active'"),
    ('credential_refs', 'px_creds_valid', ['account_id', 'purpose'], "status='valid'"),
    ('suppliers', 'px_suppliers_code', ['tenant_id', 'supplier_code'], 'deleted_at IS NULL'),
    ('suppliers', 'px_suppliers_platform', ['tenant_id', 'source_platform', 'platform_supplier_id'], 'deleted_at IS NULL AND platform_supplier_id IS NOT NULL'),
    ('products', 'px_products_title', ['tenant_id', 'title_base'], 'deleted_at IS NULL'),
    ('supplier_offers', 'px_offers_preferred', ['sku_id', 'preferred_status'], "preferred_status='current'"),
    ('assets', 'px_assets_sha256', ['tenant_id', 'content_sha256'], 'deleted_at IS NULL'),
    ('shop_listings', 'px_listings_shop_product', ['shop_id', 'product_id'], 'deleted_at IS NULL'),
    ('shop_listings', 'px_listings_platform_product', ['tenant_id', 'platform_product_id'], 'platform_product_id IS NOT NULL AND deleted_at IS NULL'),
    ('ad_campaigns', 'px_campaigns_platform', ['shop_listing_id', 'platform_campaign_id'], 'platform_campaign_id IS NOT NULL AND deleted_at IS NULL'),
    ('manual_tasks', 'px_tasks_open', ['tenant_id', 'ref_type', 'ref_id', 'task_type'], "status IN ('pending','in_progress')"),
    ('alert_events', 'px_alerts_open', ['tenant_id', 'fingerprint'], "status <> 'resolved'"),
]

PLAIN_INDEXES = [
    ('workflow_steps', 'ix_steps_status_updated', ['status', 'updated_at']),
    ('workflow_runs', 'ix_runs_status_updated', ['status', 'updated_at']),
    ('manual_tasks', 'ix_tasks_status', ['status']),
    ('alert_deliveries', 'ix_deliveries_pending', ['status']),
    ('ad_report_snapshots', 'ix_snaps_window', ['window_start', 'window_end']),
    ('selection_decisions', 'ix_decisions_state', ['state']),
    ('ad_campaigns', 'ix_campaigns_listing', ['shop_listing_id']),
    ('audit_events', 'ix_audit_actor_time', ['actor_id', 'created_at']),
]


def upgrade() -> None:
    """W0~W8 建表；G4 父键；G5 组合 FK；G6 NULLS NOT DISTINCT；G8 exclusion；G9 索引。"""

    # ================= W0 =================
    op.create_table(
        'tenants',
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), primary_key=True),
        sa.Column("public_id", sa.Uuid(), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("scope", sa.String(64), nullable=False),
        sa.Column("contact_name", sa.String(64), nullable=True),
        sa.Column("contact_phone", sa.String(32), nullable=True),
        sa.Column("contact_email", sa.String(128), nullable=True),
        sa.Column("status", postgresql.ENUM(name="enum_entity_status", create_type=False), nullable=False, server_default='active'),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("deleted_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("row_version", sa.Integer(), nullable=False, server_default='1'),
        sa.UniqueConstraint('public_id'),
        schema=SCHEMA,
    )

    op.create_table(
        'actor_registry',
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), primary_key=True),
        sa.Column("actor_id", sa.Uuid(), nullable=False),
        sa.Column("actor_kind", postgresql.ENUM(name="enum_actor_kind", create_type=False), nullable=False),
        sa.Column("name", sa.String(64), nullable=False),
        sa.Column("status", postgresql.ENUM(name="enum_actor_status", create_type=False), nullable=False, server_default='active'),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint('actor_id'),
        schema=SCHEMA,
    )

    op.create_table(
        'policy_versions',
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), primary_key=True),
        sa.Column("public_id", sa.Uuid(), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", sa.BigInteger(), nullable=True),
        sa.Column("policy_type", postgresql.ENUM(name="enum_policy_type", create_type=False), nullable=False),
        sa.Column("version", sa.String(32), nullable=False),
        sa.Column("scope_type", postgresql.ENUM(name="enum_policy_scope", create_type=False), nullable=False),
        sa.Column("scope_id", sa.String(128), nullable=True),
        sa.Column("scope_key", sa.String(192), sa.Computed("CASE WHEN scope_id IS NULL THEN '<global>' ELSE scope_id END", persisted=True), nullable=False),
        sa.Column("content", postgresql.JSONB(), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("effective_from", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("effective_to", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("supersedes_id", sa.BigInteger(), nullable=True),
        sa.Column("approved_by_actor_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint('public_id'),
        schema=SCHEMA,
    )


    # ================= W1 =================
    op.create_table(
        'platform_accounts',
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), primary_key=True),
        sa.Column("public_id", sa.Uuid(), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", sa.BigInteger(), nullable=False),
        sa.Column("platform", postgresql.ENUM(name="enum_platform", create_type=False), nullable=False),
        sa.Column("account_key", sa.String(128), nullable=False),
        sa.Column("login_state", postgresql.ENUM(name="enum_login_state", create_type=False), nullable=False, server_default='unknown'),
        sa.Column("health_state", postgresql.ENUM(name="enum_health_state", create_type=False), nullable=False, server_default='healthy'),
        sa.Column("status", postgresql.ENUM(name="enum_account_status", create_type=False), nullable=False, server_default='draft'),
        sa.Column("rate_limit_cfg", postgresql.JSONB(), nullable=True),
        sa.Column("circuit_breaker", postgresql.JSONB(), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("deleted_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("row_version", sa.Integer(), nullable=False, server_default='1'),
        sa.ForeignKeyConstraint(["tenant_id"], ["app.tenants.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint('public_id'),
        schema=SCHEMA,
    )

    op.create_table(
        'shops',
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), primary_key=True),
        sa.Column("public_id", sa.Uuid(), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", sa.BigInteger(), nullable=False),
        sa.Column("account_id", sa.BigInteger(), nullable=False),
        sa.Column("platform_shop_id", sa.String(128), nullable=False),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("category_qualifications", postgresql.JSONB(), nullable=True),
        sa.Column("freight_template_id", sa.String(64), nullable=True),
        sa.Column("return_address", postgresql.JSONB(), nullable=True),
        sa.Column("cid_policy_version_id", sa.BigInteger(), nullable=True),
        sa.Column("status", postgresql.ENUM(name="enum_entity_status", create_type=False), nullable=False, server_default='active'),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("deleted_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("row_version", sa.Integer(), nullable=False, server_default='1'),
        sa.ForeignKeyConstraint(["tenant_id"], ["app.tenants.id"]),
        sa.UniqueConstraint('public_id'),
        schema=SCHEMA,
    )

    op.create_table(
        'account_runtime_profiles',
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), primary_key=True),
        sa.Column("tenant_id", sa.BigInteger(), nullable=False),
        sa.Column("account_id", sa.BigInteger(), nullable=False),
        sa.Column("purpose", postgresql.ENUM(name="enum_profile_purpose", create_type=False), nullable=False),
        sa.Column("rotation_seq", sa.Integer(), nullable=False, server_default='1'),
        sa.Column("browser_profile_ref", sa.String(256), nullable=True),
        sa.Column("proxy_ref", sa.String(256), nullable=True),
        sa.Column("page_version", sa.String(64), nullable=True),
        sa.Column("selectors_version", sa.String(64), nullable=True),
        sa.Column("status", postgresql.ENUM(name="enum_profile_status", create_type=False), nullable=False, server_default='active'),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["tenant_id"], ["app.tenants.id"]),
        sa.UniqueConstraint('account_id', 'purpose', 'rotation_seq'),
        schema=SCHEMA,
    )

    op.create_table(
        'credential_refs',
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), primary_key=True),
        sa.Column("tenant_id", sa.BigInteger(), nullable=False),
        sa.Column("account_id", sa.BigInteger(), nullable=False),
        sa.Column("purpose", postgresql.ENUM(name="enum_credential_purpose", create_type=False), nullable=False),
        sa.Column("rotation_seq", sa.Integer(), nullable=False, server_default='1'),
        sa.Column("secret_store_key", sa.String(256), nullable=False),
        sa.Column("status", postgresql.ENUM(name="enum_credential_status", create_type=False), nullable=False, server_default='valid'),
        sa.Column("expires_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("last_verified_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("redacted_display", sa.String(64), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["tenant_id"], ["app.tenants.id"]),
        sa.UniqueConstraint('account_id', 'purpose', 'rotation_seq'),
        schema=SCHEMA,
    )


    # ================= W2 =================
    op.create_table(
        'suppliers',
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), primary_key=True),
        sa.Column("public_id", sa.Uuid(), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", sa.BigInteger(), nullable=False),
        sa.Column("supplier_code", sa.String(64), nullable=False),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("source_platform", postgresql.ENUM(name="enum_supplier_platform", create_type=False), nullable=False),
        sa.Column("platform_supplier_id", sa.String(128), nullable=True),
        sa.Column("contact_ref", sa.String(256), nullable=True),
        sa.Column("settlement_terms", postgresql.JSONB(), nullable=True),
        sa.Column("payment_terms_days", sa.Integer(), nullable=True),
        sa.Column("fulfillment_mode", postgresql.ENUM(name="enum_fulfillment_mode", create_type=False), nullable=True),
        sa.Column("return_policy", postgresql.JSONB(), nullable=True),
        sa.Column("health_state", postgresql.ENUM(name="enum_health_state", create_type=False), nullable=False, server_default='healthy'),
        sa.Column("status", postgresql.ENUM(name="enum_entity_status", create_type=False), nullable=False, server_default='active'),
        sa.Column("source", postgresql.ENUM(name="enum_common_source", create_type=False), nullable=False),
        sa.Column("mode", postgresql.ENUM(name="enum_common_mode", create_type=False), nullable=False),
        sa.Column("evidence_ref", sa.String(256), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("deleted_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("row_version", sa.Integer(), nullable=False, server_default='1'),
        sa.ForeignKeyConstraint(["tenant_id"], ["app.tenants.id"]),
        sa.UniqueConstraint('public_id'),
        schema=SCHEMA,
    )

    op.create_table(
        'products',
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), primary_key=True),
        sa.Column("public_id", sa.Uuid(), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", sa.BigInteger(), nullable=False),
        sa.Column("title_base", sa.String(200), nullable=False),
        sa.Column("category_id", sa.String(64), nullable=False),
        sa.Column("material_requirements", postgresql.JSONB(), nullable=True),
        sa.Column("status", postgresql.ENUM(name="enum_product_status", create_type=False), nullable=False, server_default='draft'),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("deleted_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("row_version", sa.Integer(), nullable=False, server_default='1'),
        sa.ForeignKeyConstraint(["tenant_id"], ["app.tenants.id"]),
        sa.UniqueConstraint('public_id'),
        schema=SCHEMA,
    )

    op.create_table(
        'product_skus',
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), primary_key=True),
        sa.Column("tenant_id", sa.BigInteger(), nullable=False),
        sa.Column("product_id", sa.BigInteger(), nullable=False),
        sa.Column("attributes", postgresql.JSONB(), nullable=False),
        sa.Column("attributes_hash", sa.String(64), sa.Computed("encode(sha256(attributes::text::bytea),'hex')", persisted=True), nullable=False),
        sa.Column("weight_g", sa.Integer(), sa.CheckConstraint('weight_g >= 0'), nullable=True),
        sa.Column("volume", sa.String(32), nullable=True),
        sa.Column("shipping_attrs", postgresql.JSONB(), nullable=True),
        sa.Column("compliance_status", postgresql.ENUM(name="enum_sku_compliance", create_type=False), nullable=False, server_default='ok'),
        sa.Column("salable_status", postgresql.ENUM(name="enum_sku_salable", create_type=False), nullable=False, server_default='salable'),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["tenant_id"], ["app.tenants.id"]),
        sa.UniqueConstraint('product_id', 'attributes_hash'),
        schema=SCHEMA,
    )

    op.create_table(
        'supplier_offers',
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), primary_key=True),
        sa.Column("tenant_id", sa.BigInteger(), nullable=False),
        sa.Column("supplier_id", sa.BigInteger(), nullable=False),
        sa.Column("product_id", sa.BigInteger(), nullable=True),
        sa.Column("sku_id", sa.BigInteger(), nullable=True),
        sa.Column("supplier_sku_id", sa.String(64), nullable=False),
        sa.Column("offer_id", sa.String(64), nullable=False),
        sa.Column("price", sa.Numeric(18, 6), sa.CheckConstraint('price >= 0'), nullable=False),
        sa.Column("shipping", sa.Numeric(18, 6), nullable=False, server_default='0'),
        sa.Column("minimum_order", sa.Integer(), nullable=False, server_default='1'),
        sa.Column("stock_observed", sa.Integer(), sa.CheckConstraint('stock_observed >= 0'), nullable=True),
        sa.Column("observed_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("expires_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("evidence_ref", sa.String(256), nullable=True),
        sa.Column("source", postgresql.ENUM(name="enum_offer_source", create_type=False), nullable=False),
        sa.Column("mode", postgresql.ENUM(name="enum_common_mode", create_type=False), nullable=False),
        sa.Column("is_preferred", sa.Boolean(), nullable=False, server_default='false'),
        sa.Column("preferred_status", postgresql.ENUM(name="enum_offer_preferred", create_type=False), nullable=False, server_default='none'),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["tenant_id"], ["app.tenants.id"]),
        sa.UniqueConstraint('tenant_id', 'idempotency_key'),
        schema=SCHEMA,
    )


    # ================= W3 =================
    op.create_table(
        'assets',
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), primary_key=True),
        sa.Column("public_id", sa.Uuid(), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", sa.BigInteger(), nullable=False),
        sa.Column("source_account_id", sa.BigInteger(), nullable=True),
        sa.Column("content_sha256", sa.String(64), nullable=False),
        sa.Column("perceptual_hash", sa.String(64), nullable=True),
        sa.Column("file_ref", sa.String(256), nullable=False),
        sa.Column("mime_type", sa.String(64), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), sa.CheckConstraint('size_bytes >= 0'), nullable=False),
        sa.Column("width", sa.Integer(), sa.CheckConstraint('width >= 0'), nullable=True),
        sa.Column("height", sa.Integer(), sa.CheckConstraint('height >= 0'), nullable=True),
        sa.Column("duration_ms", sa.Integer(), sa.CheckConstraint('duration_ms >= 0'), nullable=True),
        sa.Column("source_type", postgresql.ENUM(name="enum_asset_source_type", create_type=False), nullable=False),
        sa.Column("source_ref", sa.String(256), nullable=True),
        sa.Column("evidence_hash", sa.String(64), nullable=False),
        sa.Column("rights_status", postgresql.ENUM(name="enum_rights_status", create_type=False), nullable=False, server_default='unknown'),
        sa.Column("rights_evidence", sa.String(256), nullable=True),
        sa.Column("captured_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("derived_from_asset_id", sa.BigInteger(), nullable=True),
        sa.Column("transform_version", sa.String(64), nullable=True),
        sa.Column("quality_result", postgresql.JSONB(), nullable=True),
        sa.Column("relevance_result", postgresql.JSONB(), nullable=True),
        sa.Column("mode", postgresql.ENUM(name="enum_asset_mode", create_type=False), nullable=False),
        sa.Column("status", postgresql.ENUM(name="enum_asset_status", create_type=False), nullable=False, server_default='active'),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("deleted_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("row_version", sa.Integer(), nullable=False, server_default='1'),
        sa.ForeignKeyConstraint(["tenant_id"], ["app.tenants.id"]),
        sa.UniqueConstraint('public_id'),
        schema=SCHEMA,
    )

    op.create_table(
        'shop_listings',
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), primary_key=True),
        sa.Column("public_id", sa.Uuid(), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", sa.BigInteger(), nullable=False),
        sa.Column("account_id", sa.BigInteger(), nullable=False),
        sa.Column("shop_id", sa.BigInteger(), nullable=False),
        sa.Column("product_id", sa.BigInteger(), nullable=False),
        sa.Column("platform_product_id", sa.String(128), nullable=True),
        sa.Column("title_effective", sa.String(200), nullable=False),
        sa.Column("freight_template_id", sa.String(64), nullable=True),
        sa.Column("first_manual_confirm_actor_id", sa.Uuid(), nullable=True),
        sa.Column("auto_fix_count", sa.Integer(), nullable=False, server_default='0'),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("submit_version", sa.Integer(), nullable=False, server_default='1'),
        sa.Column("status", postgresql.ENUM(name="enum_listing_status", create_type=False), nullable=False, server_default='draft'),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("deleted_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("row_version", sa.Integer(), nullable=False, server_default='1'),
        sa.ForeignKeyConstraint(["tenant_id"], ["app.tenants.id"]),
        sa.UniqueConstraint('public_id'),
        sa.UniqueConstraint('tenant_id', 'idempotency_key'),
        schema=SCHEMA,
    )

    op.create_table(
        'shop_listing_skus',
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), primary_key=True),
        sa.Column("tenant_id", sa.BigInteger(), nullable=False),
        sa.Column("shop_listing_id", sa.BigInteger(), nullable=False),
        sa.Column("sku_id", sa.BigInteger(), nullable=False),
        sa.Column("platform_sku_id", sa.String(128), nullable=True),
        sa.Column("shop_price", sa.BigInteger(), sa.CheckConstraint('shop_price >= 0'), nullable=False),
        sa.Column("promo_price", sa.BigInteger(), sa.CheckConstraint('promo_price >= 0'), nullable=True),
        sa.Column("floor_price", sa.BigInteger(), sa.CheckConstraint('floor_price >= 0'), nullable=True),
        sa.Column("allocated_stock", sa.Integer(), nullable=False, server_default='0'),
        sa.Column("safety_stock", sa.Integer(), nullable=False, server_default='0'),
        sa.Column("listing_status", postgresql.ENUM(name="enum_listing_sku_status", create_type=False), nullable=False, server_default='listed'),
        sa.Column("rejection_reason", sa.String(256), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["tenant_id"], ["app.tenants.id"]),
        sa.UniqueConstraint('shop_listing_id', 'sku_id'),
        schema=SCHEMA,
    )


    # ================= W4 =================
    op.create_table(
        'asset_product_bindings',
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), primary_key=True),
        sa.Column("tenant_id", sa.BigInteger(), nullable=False),
        sa.Column("asset_id", sa.BigInteger(), nullable=False),
        sa.Column("product_id", sa.BigInteger(), nullable=False),
        sa.Column("product_sku_id", sa.BigInteger(), nullable=True),
        sa.Column("purpose", postgresql.ENUM(name="enum_media_purpose", create_type=False), nullable=False),
        sa.Column("relevance", sa.Numeric(), sa.CheckConstraint('relevance >= 0 AND relevance <= 1'), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["tenant_id"], ["app.tenants.id"]),
        schema=SCHEMA,
    )

    op.create_table(
        'asset_shop_bindings',
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), primary_key=True),
        sa.Column("tenant_id", sa.BigInteger(), nullable=False),
        sa.Column("asset_id", sa.BigInteger(), nullable=False),
        sa.Column("asset_product_binding_id", sa.BigInteger(), nullable=True),
        sa.Column("product_id", sa.BigInteger(), nullable=True),
        sa.Column("shop_listing_id", sa.BigInteger(), nullable=True),
        sa.Column("shop_id", sa.BigInteger(), nullable=False),
        sa.Column("purpose", postgresql.ENUM(name="enum_media_purpose", create_type=False), nullable=False),
        sa.Column("authorization_status", postgresql.ENUM(name="enum_shopbind_auth", create_type=False), nullable=False, server_default='pending'),
        sa.Column("review_status", postgresql.ENUM(name="enum_shopbind_review", create_type=False), nullable=False, server_default='pending'),
        sa.Column("bound_by_actor_id", sa.Uuid(), nullable=True),
        sa.Column("bound_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["tenant_id"], ["app.tenants.id"]),
        schema=SCHEMA,
    )

    op.create_table(
        'asset_reviews',
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), primary_key=True),
        sa.Column("tenant_id", sa.BigInteger(), nullable=False),
        sa.Column("asset_id", sa.BigInteger(), nullable=False),
        sa.Column("review_scope", postgresql.ENUM(name="enum_review_scope", create_type=False), nullable=False),
        sa.Column("scope_ref_id", sa.BigInteger(), nullable=False),
        sa.Column("review_type", postgresql.ENUM(name="enum_review_type", create_type=False), nullable=False),
        sa.Column("attempt", sa.Integer(), nullable=False, server_default='1'),
        sa.Column("reviewer_actor_id", sa.Uuid(), nullable=False),
        sa.Column("decision", postgresql.ENUM(name="enum_review_decision", create_type=False), nullable=False),
        sa.Column("rejection_code", sa.String(64), nullable=True),
        sa.Column("platform_result", sa.String(256), nullable=True),
        sa.Column("reviewed_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["tenant_id"], ["app.tenants.id"]),
        sa.UniqueConstraint('asset_id', 'review_scope', 'scope_ref_id', 'review_type', 'attempt'),
        schema=SCHEMA,
    )


    # ================= W5 =================
    op.create_table(
        'cost_snapshots',
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), primary_key=True),
        sa.Column("public_id", sa.Uuid(), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", sa.BigInteger(), nullable=False),
        sa.Column("decision_object_type", postgresql.ENUM(name="enum_snapshot_objtype", create_type=False), nullable=False),
        sa.Column("decision_object_id", sa.BigInteger(), nullable=False),
        sa.Column("shop_id", sa.BigInteger(), nullable=True),
        sa.Column("shop_listing_id", sa.BigInteger(), nullable=True),
        sa.Column("offer_id", sa.BigInteger(), nullable=True),
        sa.Column("policy_version_id", sa.BigInteger(), nullable=False),
        sa.Column("k_price", sa.Numeric(18, 6), nullable=False),
        sa.Column("j_service_fee", sa.Numeric(18, 6), nullable=False, server_default='0'),
        sa.Column("i_refund_reserve", sa.Numeric(18, 6), nullable=False, server_default='0'),
        sa.Column("h_shipping", sa.Numeric(18, 6), nullable=False, server_default='0'),
        sa.Column("g_product_cost", sa.Numeric(18, 6), nullable=False, server_default='0'),
        sa.Column("l_tax", sa.Numeric(18, 6), nullable=False, server_default='0'),
        sa.Column("consumption_rebate", sa.Numeric(18, 6), nullable=False, server_default='0'),
        sa.Column("technical_rebate", sa.Numeric(18, 6), nullable=False, server_default='0'),
        sa.Column("misc_cost", sa.Numeric(18, 6), nullable=False, server_default='0'),
        sa.Column("ad_pre_margin", sa.Numeric(18, 6), nullable=False),
        sa.Column("purchase_price_rounded", sa.BigInteger(), nullable=True),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("snapshot_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["tenant_id"], ["app.tenants.id"]),
        sa.UniqueConstraint('public_id'),
        sa.UniqueConstraint('tenant_id', 'idempotency_key'),
        schema=SCHEMA,
    )

    op.create_table(
        'workflow_runs',
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), primary_key=True),
        sa.Column("public_id", sa.Uuid(), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", sa.BigInteger(), nullable=False),
        sa.Column("run_type", postgresql.ENUM(name="enum_run_type", create_type=False), nullable=False),
        sa.Column("state", sa.String(64), nullable=True),
        sa.Column("input_ref", sa.String(256), nullable=True),
        sa.Column("output_ref", sa.String(256), nullable=True),
        sa.Column("status", postgresql.ENUM(name="enum_run_status", create_type=False), nullable=False, server_default='running'),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("row_version", sa.Integer(), nullable=False, server_default='1'),
        sa.ForeignKeyConstraint(["tenant_id"], ["app.tenants.id"]),
        sa.UniqueConstraint('public_id'),
        sa.UniqueConstraint('tenant_id', 'idempotency_key'),
        schema=SCHEMA,
    )

    op.create_table(
        'workflow_steps',
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), primary_key=True),
        sa.Column("tenant_id", sa.BigInteger(), nullable=False),
        sa.Column("run_id", sa.BigInteger(), nullable=False),
        sa.Column("step_type", sa.String(64), nullable=False),
        sa.Column("status", postgresql.ENUM(name="enum_step_status", create_type=False), nullable=False, server_default='pending'),
        sa.Column("attempt", sa.Integer(), nullable=False, server_default='1'),
        sa.Column("gate_result", postgresql.JSONB(), nullable=True),
        sa.Column("evidence_ref", sa.String(256), nullable=True),
        sa.Column("error_code", sa.String(32), nullable=True),
        sa.Column("action_idempotency_key", sa.String(128), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["tenant_id"], ["app.tenants.id"]),
        sa.UniqueConstraint('run_id', 'step_type', 'attempt'),
        sa.UniqueConstraint('tenant_id', 'action_idempotency_key'),
        schema=SCHEMA,
    )

    op.create_table(
        'selection_decisions',
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), primary_key=True),
        sa.Column("public_id", sa.Uuid(), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", sa.BigInteger(), nullable=False),
        sa.Column("product_id", sa.BigInteger(), nullable=False),
        sa.Column("source", postgresql.ENUM(name="enum_decision_source", create_type=False), nullable=False),
        sa.Column("source_account_id", sa.BigInteger(), nullable=True),
        sa.Column("board_snapshot_ref", sa.String(256), nullable=True),
        sa.Column("page_evidence", postgresql.JSONB(), nullable=True),
        sa.Column("compliance_result", postgresql.ENUM(name="enum_decision_compliance", create_type=False), nullable=False),
        sa.Column("risk_tags", postgresql.JSONB(), nullable=True),
        sa.Column("human_review_note", sa.String(512), nullable=True),
        sa.Column("human_review_actor_id", sa.Uuid(), nullable=True),
        sa.Column("price_assumption", sa.Numeric(18, 6), nullable=True),
        sa.Column("supply_price", sa.Numeric(18, 6), nullable=True),
        sa.Column("shipping_cost", sa.Numeric(18, 6), nullable=True),
        sa.Column("platform_fee", sa.Numeric(18, 6), nullable=True),
        sa.Column("refund_reserve", sa.Numeric(18, 6), nullable=True),
        sa.Column("ad_pre_margin", sa.Numeric(18, 6), nullable=True),
        sa.Column("data_coverage", sa.Numeric(), sa.CheckConstraint('data_coverage >= 0 AND data_coverage <= 1'), nullable=True),
        sa.Column("confidence", sa.Numeric(), sa.CheckConstraint('confidence >= 0 AND confidence <= 1'), nullable=True),
        sa.Column("observed_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("quote_status", postgresql.ENUM(name="enum_quote_status", create_type=False), nullable=False, server_default='none'),
        sa.Column("quote_expires_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("material_status", postgresql.ENUM(name="enum_material_status", create_type=False), nullable=False, server_default='unknown'),
        sa.Column("available_asset_count", sa.Integer(), sa.CheckConstraint('available_asset_count >= 0'), nullable=True),
        sa.Column("source_url", sa.String(512), nullable=True),
        sa.Column("cost_snapshot_id", sa.BigInteger(), nullable=True),
        sa.Column("policy_version_id", sa.BigInteger(), nullable=True),
        sa.Column("workflow_run_id", sa.BigInteger(), nullable=True),
        sa.Column("selection_batch_key", sa.String(128), nullable=False),
        sa.Column("downstream_status", sa.String(64), nullable=True),
        sa.Column("block_reason", sa.String(256), nullable=True),
        sa.Column("state", postgresql.ENUM(name="enum_decision_state", create_type=False), nullable=False, server_default='discovered'),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["tenant_id"], ["app.tenants.id"]),
        sa.UniqueConstraint('public_id'),
        sa.UniqueConstraint('tenant_id', 'selection_batch_key', 'product_id'),
        schema=SCHEMA,
    )


    # ================= W6 =================
    op.create_table(
        'pricing_decisions',
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), primary_key=True),
        sa.Column("public_id", sa.Uuid(), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", sa.BigInteger(), nullable=False),
        sa.Column("shop_id", sa.BigInteger(), nullable=False),
        sa.Column("shop_listing_id", sa.BigInteger(), nullable=False),
        sa.Column("shop_listing_sku_id", sa.BigInteger(), nullable=False),
        sa.Column("cost_snapshot_id", sa.BigInteger(), nullable=False),
        sa.Column("policy_version_id", sa.BigInteger(), nullable=False),
        sa.Column("decision_type", postgresql.ENUM(name="enum_pricing_type", create_type=False), nullable=False),
        sa.Column("cost_floor_price", sa.Numeric(18, 6), sa.CheckConstraint('cost_floor_price >= 0'), nullable=False),
        sa.Column("suggested_price", sa.Numeric(18, 6), sa.CheckConstraint('suggested_price >= 0'), nullable=False),
        sa.Column("daily_price", sa.Numeric(18, 6), sa.CheckConstraint('daily_price >= 0'), nullable=True),
        sa.Column("promo_price", sa.Numeric(18, 6), sa.CheckConstraint('promo_price >= 0'), nullable=True),
        sa.Column("floor_price", sa.Numeric(18, 6), sa.CheckConstraint('floor_price >= 0'), nullable=False),
        sa.Column("target_margin", sa.Numeric(), sa.CheckConstraint('target_margin >= 0'), nullable=True),
        sa.Column("competitor_evidence", postgresql.JSONB(), nullable=True),
        sa.Column("bid_unrounded", sa.Numeric(18, 6), nullable=True),
        sa.Column("bid_rounded_cents", sa.BigInteger(), nullable=True),
        sa.Column("rounding_mode", sa.String(16), nullable=True),
        sa.Column("cid_inputs", postgresql.JSONB(), nullable=False),
        sa.Column("cid_results", postgresql.JSONB(), nullable=False),
        sa.Column("status", postgresql.ENUM(name="enum_pricing_status", create_type=False), nullable=False, server_default='draft'),
        sa.Column("approved_by_actor_id", sa.Uuid(), nullable=True),
        sa.Column("approved_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("effective_from", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("effective_to", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("evidence_ref", sa.String(256), nullable=True),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["tenant_id"], ["app.tenants.id"]),
        sa.UniqueConstraint('public_id'),
        sa.UniqueConstraint('tenant_id', 'idempotency_key'),
        schema=SCHEMA,
    )

    op.create_table(
        'listing_events',
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), primary_key=True),
        sa.Column("tenant_id", sa.BigInteger(), nullable=False),
        sa.Column("shop_listing_id", sa.BigInteger(), nullable=False),
        sa.Column("event_type", postgresql.ENUM(name="enum_listevent_type", create_type=False), nullable=False),
        sa.Column("from_state", sa.String(64), nullable=True),
        sa.Column("to_state", sa.String(64), nullable=False),
        sa.Column("operator_actor_id", sa.Uuid(), nullable=False),
        sa.Column("evidence_ref", sa.String(256), nullable=True),
        sa.Column("request_id", sa.String(128), nullable=False),
        sa.Column("platform_request", postgresql.JSONB(), nullable=True),
        sa.Column("platform_response", postgresql.JSONB(), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["tenant_id"], ["app.tenants.id"]),
        sa.UniqueConstraint('shop_listing_id', 'event_type', 'request_id'),
        schema=SCHEMA,
    )


    # ================= W7 =================
    op.create_table(
        'ad_campaigns',
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), primary_key=True),
        sa.Column("public_id", sa.Uuid(), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", sa.BigInteger(), nullable=False),
        sa.Column("account_id", sa.BigInteger(), nullable=False),
        sa.Column("shop_id", sa.BigInteger(), nullable=False),
        sa.Column("shop_listing_id", sa.BigInteger(), nullable=False),
        sa.Column("platform_campaign_id", sa.String(128), nullable=True),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("approved_budget", sa.BigInteger(), sa.CheckConstraint('approved_budget >= 0'), nullable=False),
        sa.Column("approved_daily_budget", sa.BigInteger(), sa.CheckConstraint('approved_daily_budget >= 0'), nullable=False),
        sa.Column("approved_target_roi", sa.Numeric(), sa.CheckConstraint('approved_target_roi > 0'), nullable=False),
        sa.Column("approved_stop_loss", sa.Numeric(), sa.CheckConstraint('approved_stop_loss > 0'), nullable=False),
        sa.Column("current_budget", sa.BigInteger(), sa.CheckConstraint('current_budget >= 0'), nullable=False),
        sa.Column("current_daily_budget", sa.BigInteger(), sa.CheckConstraint('current_daily_budget >= 0'), nullable=False),
        sa.Column("current_target_roi", sa.Numeric(), nullable=False),
        sa.Column("current_stop_loss", sa.Numeric(), nullable=False),
        sa.Column("feedback_coefficient", sa.Numeric(), sa.CheckConstraint('feedback_coefficient > 0'), nullable=False),
        sa.Column("cumulative_spend", sa.BigInteger(), nullable=False, server_default='0'),
        sa.Column("budget_policy_version_id", sa.BigInteger(), nullable=False),
        sa.Column("cid_policy_version_id", sa.BigInteger(), nullable=False),
        sa.Column("approval_ref", sa.String(256), nullable=True),
        sa.Column("status", postgresql.ENUM(name="enum_campaign_status", create_type=False), nullable=False, server_default='draft'),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("deleted_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("row_version", sa.Integer(), nullable=False, server_default='1'),
        sa.ForeignKeyConstraint(["tenant_id"], ["app.tenants.id"]),
        sa.UniqueConstraint('public_id'),
        sa.UniqueConstraint('tenant_id', 'idempotency_key'),
        schema=SCHEMA,
    )

    op.create_table(
        'ad_campaign_assets',
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), primary_key=True),
        sa.Column("tenant_id", sa.BigInteger(), nullable=False),
        sa.Column("campaign_id", sa.BigInteger(), nullable=False),
        sa.Column("asset_shop_binding_id", sa.BigInteger(), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["tenant_id"], ["app.tenants.id"]),
        sa.UniqueConstraint('campaign_id', 'asset_shop_binding_id'),
        schema=SCHEMA,
    )

    op.create_table(
        'ad_report_snapshots',
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), primary_key=True),
        sa.Column("tenant_id", sa.BigInteger(), nullable=False),
        sa.Column("account_id", sa.BigInteger(), nullable=False),
        sa.Column("shop_id", sa.BigInteger(), nullable=False),
        sa.Column("shop_listing_id", sa.BigInteger(), nullable=False),
        sa.Column("shop_listing_sku_id", sa.BigInteger(), nullable=True),
        sa.Column("product_id", sa.BigInteger(), nullable=False),
        sa.Column("campaign_id", sa.BigInteger(), nullable=False),
        sa.Column("asset_binding_id", sa.BigInteger(), nullable=True),
        sa.Column("granularity", postgresql.ENUM(name="enum_snapshot_granularity", create_type=False), nullable=False),
        sa.Column("window_start", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("window_end", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("attribution_mode", sa.String(64), nullable=False),
        sa.Column("report_version_key", sa.String(128), nullable=False),
        sa.Column("platform_updated_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("captured_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("spend", sa.BigInteger(), nullable=False, server_default='0'),
        sa.Column("gmv", sa.BigInteger(), nullable=False, server_default='0'),
        sa.Column("roi", sa.Numeric(), nullable=True),
        sa.Column("impressions", sa.Integer(), nullable=False, server_default='0'),
        sa.Column("clicks", sa.Integer(), nullable=False, server_default='0'),
        sa.Column("orders", sa.Integer(), nullable=False, server_default='0'),
        sa.Column("diagnosis", postgresql.ENUM(name="enum_snapshot_diag", create_type=False), nullable=False, server_default='unknown'),
        sa.Column("status", postgresql.ENUM(name="enum_snapshot_status", create_type=False), nullable=False, server_default='unknown'),
        sa.Column("raw_evidence_hash", sa.String(64), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["tenant_id"], ["app.tenants.id"]),
        schema=SCHEMA,
    )

    op.create_table(
        'roi_feedback_events',
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), primary_key=True),
        sa.Column("tenant_id", sa.BigInteger(), nullable=False),
        sa.Column("account_id", sa.BigInteger(), nullable=False),
        sa.Column("shop_id", sa.BigInteger(), nullable=False),
        sa.Column("shop_listing_id", sa.BigInteger(), nullable=False),
        sa.Column("shop_listing_sku_id", sa.BigInteger(), nullable=True),
        sa.Column("product_id", sa.BigInteger(), nullable=False),
        sa.Column("campaign_id", sa.BigInteger(), nullable=False),
        sa.Column("asset_binding_id", sa.BigInteger(), nullable=True),
        sa.Column("source_snapshot_id", sa.BigInteger(), nullable=False),
        sa.Column("window_start", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("window_end", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("attribution_mode", sa.String(64), nullable=False),
        sa.Column("feedback_type", postgresql.ENUM(name="enum_feedback_type", create_type=False), nullable=False),
        sa.Column("subject_type", postgresql.ENUM(name="enum_feedback_subject", create_type=False), nullable=False),
        sa.Column("subject_key", sa.String(128), nullable=False),
        sa.Column("value", sa.Numeric(), nullable=False),
        sa.Column("extra_explanation", postgresql.JSONB(), nullable=True),
        sa.Column("aggregation_version", sa.String(64), nullable=False),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["tenant_id"], ["app.tenants.id"]),
        sa.CheckConstraint("(feedback_type='product_score' AND subject_type='product') OR (feedback_type='category_score' AND subject_type='category') OR (feedback_type='material_score' AND subject_type='material') OR (feedback_type='sku_margin' AND subject_type='sku') OR (feedback_type='shop_strategy' AND subject_type='shop')", name='ck_feedback_subject_map'),
        sa.UniqueConstraint('tenant_id', 'idempotency_key'),
        sa.UniqueConstraint('source_snapshot_id', 'feedback_type', 'subject_type', 'subject_key', 'aggregation_version'),
        schema=SCHEMA,
    )


    # ================= W8 =================
    op.create_table(
        'manual_tasks',
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), primary_key=True),
        sa.Column("tenant_id", sa.BigInteger(), nullable=False),
        sa.Column("task_type", postgresql.ENUM(name="enum_task_type", create_type=False), nullable=False),
        sa.Column("ref_type", sa.String(64), nullable=False),
        sa.Column("ref_id", sa.BigInteger(), nullable=False),
        sa.Column("status", postgresql.ENUM(name="enum_task_status", create_type=False), nullable=False, server_default='pending'),
        sa.Column("reason", sa.String(512), nullable=True),
        sa.Column("assignee_actor_id", sa.Uuid(), nullable=True),
        sa.Column("approved_by_actor_id", sa.Uuid(), nullable=True),
        sa.Column("before_state", sa.String(64), nullable=True),
        sa.Column("after_state", sa.String(64), nullable=True),
        sa.Column("policy_version_id", sa.BigInteger(), nullable=True),
        sa.Column("evidence_ref", sa.String(256), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("resolved_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["tenant_id"], ["app.tenants.id"]),
        schema=SCHEMA,
    )

    op.create_table(
        'audit_events',
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), primary_key=True),
        sa.Column("tenant_id", sa.BigInteger(), nullable=False),
        sa.Column("actor_id", sa.Uuid(), nullable=False),
        sa.Column("action", sa.String(64), nullable=False),
        sa.Column("target_type", sa.String(64), nullable=False),
        sa.Column("target_public_id", sa.Uuid(), nullable=False),
        sa.Column("before", postgresql.JSONB(), nullable=True),
        sa.Column("after", postgresql.JSONB(), nullable=True),
        sa.Column("evidence_ref", sa.String(256), nullable=True),
        sa.Column("request_id", sa.String(128), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["tenant_id"], ["app.tenants.id"]),
        schema=SCHEMA,
    )

    op.create_table(
        'alert_events',
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), primary_key=True),
        sa.Column("public_id", sa.Uuid(), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", sa.BigInteger(), nullable=False),
        sa.Column("fingerprint", sa.String(128), nullable=False),
        sa.Column("severity", postgresql.ENUM(name="enum_alert_severity", create_type=False), nullable=False),
        sa.Column("category", postgresql.ENUM(name="enum_alert_category", create_type=False), nullable=False),
        sa.Column("title", sa.String(128), nullable=False),
        sa.Column("detail", sa.Text(), nullable=True),
        sa.Column("status", postgresql.ENUM(name="enum_alert_status", create_type=False), nullable=False, server_default='open'),
        sa.Column("first_seen_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("occurrence_count", sa.Integer(), nullable=False, server_default='1'),
        sa.Column("cooldown_until", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("acknowledged_by_actor_id", sa.Uuid(), nullable=True),
        sa.Column("acknowledged_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("resolved_by_actor_id", sa.Uuid(), nullable=True),
        sa.Column("resolved_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("row_version", sa.Integer(), nullable=False, server_default='1'),
        sa.ForeignKeyConstraint(["tenant_id"], ["app.tenants.id"]),
        sa.UniqueConstraint('public_id'),
        schema=SCHEMA,
    )

    op.create_table(
        'alert_deliveries',
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), primary_key=True),
        sa.Column("tenant_id", sa.BigInteger(), nullable=False),
        sa.Column("alert_event_id", sa.BigInteger(), nullable=False),
        sa.Column("channel", postgresql.ENUM(name="enum_delivery_channel", create_type=False), nullable=False),
        sa.Column("notification_type", postgresql.ENUM(name="enum_delivery_notif", create_type=False), nullable=False),
        sa.Column("status", postgresql.ENUM(name="enum_delivery_status", create_type=False), nullable=False, server_default='pending'),
        sa.Column("attempt", sa.Integer(), nullable=False, server_default='1'),
        sa.Column("error_detail", sa.String(256), nullable=True),
        sa.Column("sent_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["tenant_id"], ["app.tenants.id"]),
        sa.UniqueConstraint('alert_event_id', 'channel', 'notification_type', 'attempt'),
        schema=SCHEMA,
    )

    # ---- G4: 17 父候选键 UNIQUE(tenant_id, id) ----
    for t in PARENT_KEYS:
        op.create_unique_constraint("uq_" + t + "_tenant_id_id", t, ["tenant_id", "id"], schema=SCHEMA)

    # ---- G5: 58 组合 FK（命名 fk_<child>_<parent>，< 64 字符；11 条冻结 ON DELETE）----
    for child, parent, ccols, pcols, _nullable in COMPOSITE_FKS:
        op.create_foreign_key(
            "fk_" + child + "_" + parent,
            child, parent, ccols, pcols, source_schema=SCHEMA, referent_schema=SCHEMA,
            ondelete=FK_ACTIONS.get((child, parent)),
        )

    # ---- G6: 4 x UNIQUE NULLS NOT DISTINCT（索引名 uq_<table>_nullsdistinct < 63）----
    for table, cols in NULLS_UNIQUE:
        col_list = ', '.join('"%s"' % c for c in cols)
        op.execute('CREATE UNIQUE INDEX "uq_' + table + '_nullsdistinct" ON "' + SCHEMA + '"."' + table + '" (' + col_list + ') NULLS NOT DISTINCT')

    # ---- G8: 2 exclusion（btree_gist）----
    op.execute(
        f'ALTER TABLE "{SCHEMA}".pricing_decisions ADD CONSTRAINT ex_pricing_single_effective '
        f'EXCLUDE USING gist (shop_listing_sku_id WITH =, '
        f"tstzrange(effective_from, COALESCE(effective_to,'infinity'::timestamptz)) WITH &&) "
        f"WHERE (status='approved')"
    )
    op.execute(
        f'ALTER TABLE "{SCHEMA}".policy_versions ADD CONSTRAINT ex_policy_scope_effective '
        f'EXCLUDE USING gist (COALESCE(tenant_id,0) WITH =, policy_type WITH =, scope_type WITH =, '
        f"scope_key WITH =, tstzrange(effective_from, COALESCE(effective_to,'infinity'::timestamptz)) WITH &&)"
    )

    # ---- G9: 15 部分唯一 + 8 普通索引（index-registry.md）----
    for table, idx, cols, where in PARTIAL_UNIQUE:
        col_list = ', '.join('"%s"' % c for c in cols)
        op.execute('CREATE UNIQUE INDEX "' + idx + '" ON "' + SCHEMA + '"."' + table + '" (' + col_list + ') WHERE ' + where)

    for table, idx, cols in PLAIN_INDEXES:
        col_list = ', '.join('"%s"' % c for c in cols)
        op.execute('CREATE INDEX "' + idx + '" ON "' + SCHEMA + '"."' + table + '" (' + col_list + ')')


def downgrade() -> None:
    """严格逆序：索引 -> exclusion -> NULLS/唯一 -> FK -> 父键 -> 表。"""
    for table, idx, _cols in reversed(PLAIN_INDEXES):
        op.execute('DROP INDEX IF EXISTS "' + SCHEMA + '"."' + idx + '"')
    for table, idx, _cols, _w in reversed(PARTIAL_UNIQUE):
        op.execute('DROP INDEX IF EXISTS "' + SCHEMA + '"."' + idx + '"')
    op.execute('ALTER TABLE "' + SCHEMA + '".pricing_decisions DROP CONSTRAINT IF EXISTS ex_pricing_single_effective')
    op.execute('ALTER TABLE "' + SCHEMA + '".policy_versions DROP CONSTRAINT IF EXISTS ex_policy_scope_effective')
    for table, _cols in reversed(NULLS_UNIQUE):
        op.execute('DROP INDEX IF EXISTS "' + SCHEMA + '"."uq_' + table + '_nullsdistinct"')
    for child, parent, _ccols, _pcols, _nullable in reversed(COMPOSITE_FKS):
        op.drop_constraint("fk_" + child + "_" + parent, child, type_="foreignkey", schema=SCHEMA)
    for t in reversed(PARENT_KEYS):
        op.drop_constraint("uq_" + t + "_tenant_id_id", t, type_="unique", schema=SCHEMA)
    # 严格逆序：W8->W0 且每个 wave 内也逆序（R54-4）
    for w in reversed(WAVES):
        for t in reversed(w):
            op.drop_table(t, schema=SCHEMA)
