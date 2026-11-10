"""T4: 17 triggers (data-driven generator, from 15-数据字典.md v6 §8 + error-codes.yaml, round-61)

Revision ID: 17trg000001
Revises: 31tbl000001
Create Date: 2026-09-04T13:00:00+00:00
"""
from typing import Sequence, Union

from alembic import op


revision: str = '17trg000001'
down_revision: Union[str, Sequence[str], None] = '31tbl000001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


SCHEMA = 'app'

TRIGGERS = [
    ('trg_policy_supersede_scope', 'policy_versions', ('supersedes_id', 'tenant_id', 'policy_type', 'scope_type', 'scope_id'), 'SUPERSEDE_MISMATCH', 'ZT007'),
    ('trg_shops_policy_ref', 'shops', ('cid_policy_version_id', 'tenant_id'), 'INVALID_POLICY_REF', 'ZT001'),
    ('trg_cost_policy_ref', 'cost_snapshots', ('policy_version_id', 'tenant_id'), 'INVALID_POLICY_REF', 'ZT001'),
    ('trg_selection_policy_ref', 'selection_decisions', ('policy_version_id', 'tenant_id'), 'INVALID_POLICY_REF', 'ZT001'),
    ('trg_pricing_policy_ref', 'pricing_decisions', ('policy_version_id', 'tenant_id'), 'INVALID_POLICY_REF', 'ZT001'),
    ('trg_campaigns_policy_ref', 'ad_campaigns', ('budget_policy_version_id', 'cid_policy_version_id', 'tenant_id'), 'INVALID_POLICY_REF', 'ZT001'),
    ('trg_manual_policy_ref', 'manual_tasks', ('policy_version_id', 'tenant_id'), 'INVALID_POLICY_REF', 'ZT001'),
    ('trg_offers_sku_product_consistency', 'supplier_offers', ('sku_id', 'product_id', 'tenant_id'), 'SKU_PRODUCT_MISMATCH', 'ZT002'),
    ('trg_bindings_sku_product_consistency', 'asset_product_bindings', ('product_sku_id', 'product_id', 'tenant_id'), 'SKU_PRODUCT_MISMATCH', 'ZT002'),
    ('trg_listings_account_shop_consistency', 'shop_listings', ('account_id', 'shop_id', 'tenant_id'), 'ACCOUNT_SHOP_MISMATCH', 'ZT004'),
    ('trg_cost_context_consistency', 'cost_snapshots', None, 'CONTEXT_MISMATCH', 'ZT003'),
    ('trg_shopbind_context_consistency', 'asset_shop_bindings', None, 'CONTEXT_MISMATCH', 'ZT003'),
    ('trg_pricing_context_consistency', 'pricing_decisions', None, 'CONTEXT_MISMATCH', 'ZT003'),
    ('trg_campaigns_scope_consistency', 'ad_campaigns', ('account_id', 'shop_id', 'shop_listing_id', 'tenant_id'), 'SCOPE_MISMATCH', 'ZT005'),
    ('trg_campassets_same_scope', 'ad_campaign_assets', None, 'SCOPE_MISMATCH', 'ZT005'),
    ('trg_snapshots_dimension_consistency', 'ad_report_snapshots', None, 'DIMENSION_MISMATCH', 'ZT006'),
    ('trg_feedback_dimension_consistency', 'roi_feedback_events', None, 'DIMENSION_MISMATCH', 'ZT006'),
]


def upgrade() -> None:
    """按 ddl-order §六 G7 原序：每项 CREATE FUNCTION -> CREATE TRIGGER（普通 BEFORE ROW）。"""

    # ---- trg_policy_supersede_scope（SUPERSEDE_MISMATCH）----
    op.execute(
        """
CREATE OR REPLACE FUNCTION app.fn_policy_supersede_scope() RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
-- 出边：NEW.supersedes_id -> parent 必须与 NEW 的 tenant/type/scope 一致
IF NEW.supersedes_id IS NOT NULL AND NOT EXISTS (
    SELECT 1 FROM app.policy_versions p
    WHERE p.id = NEW.supersedes_id
      AND p.tenant_id IS NOT DISTINCT FROM NEW.tenant_id
      AND p.policy_type = NEW.policy_type
      AND p.scope_type = NEW.scope_type
      AND p.scope_key = CASE WHEN NEW.scope_id IS NULL THEN '<global>' ELSE NEW.scope_id END
) THEN
    RAISE EXCEPTION 'SUPERSEDE_MISMATCH: policy_versions.supersedes_id'
        USING ERRCODE = 'ZT007';
END IF;
-- 入边：NEW 作为父节点，所有 child.supersedes_id = NEW.id 必须与 NEW 保持一致
--      （INSERT 时 NEW.id 为 NULL -> 无子行匹配；UPDATE 父行 type/scope 时拦截既有子链破坏）
IF EXISTS (
    SELECT 1 FROM app.policy_versions c
    WHERE c.supersedes_id = NEW.id
      AND (c.tenant_id IS DISTINCT FROM NEW.tenant_id
           OR c.policy_type <> NEW.policy_type
           OR c.scope_type <> NEW.scope_type
           OR c.scope_key <> CASE WHEN NEW.scope_id IS NULL THEN '<global>' ELSE NEW.scope_id END)
) THEN
    RAISE EXCEPTION 'SUPERSEDE_MISMATCH: policy_versions supersede children'
        USING ERRCODE = 'ZT007';
END IF;
        RETURN NEW;
        END;
        $$
        """
    )
    op.execute(
        f"""CREATE TRIGGER trg_policy_supersede_scope BEFORE INSERT OR UPDATE OF supersedes_id, tenant_id, policy_type, scope_type, scope_id ON app.policy_versions FOR EACH ROW EXECUTE FUNCTION app.fn_policy_supersede_scope()"""
    )

    # ---- trg_shops_policy_ref（INVALID_POLICY_REF）----
    op.execute(
        """
CREATE OR REPLACE FUNCTION app.fn_shops_policy_ref() RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
IF NEW.cid_policy_version_id IS NOT NULL AND NOT EXISTS (
    SELECT 1 FROM app.policy_versions p
    WHERE p.id = NEW.cid_policy_version_id
      AND (p.tenant_id IS NULL OR p.tenant_id = NEW.tenant_id)
) THEN
    RAISE EXCEPTION 'INVALID_POLICY_REF: shops.cid_policy_version_id'
        USING ERRCODE = 'ZT001';
END IF;
        RETURN NEW;
        END;
        $$
        """
    )
    op.execute(
        f"""CREATE TRIGGER trg_shops_policy_ref BEFORE INSERT OR UPDATE OF cid_policy_version_id, tenant_id ON app.shops FOR EACH ROW EXECUTE FUNCTION app.fn_shops_policy_ref()"""
    )

    # ---- trg_cost_policy_ref（INVALID_POLICY_REF）----
    op.execute(
        """
CREATE OR REPLACE FUNCTION app.fn_cost_policy_ref() RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
IF NOT EXISTS (
    SELECT 1 FROM app.policy_versions p
    WHERE p.id = NEW.policy_version_id
      AND (p.tenant_id IS NULL OR p.tenant_id = NEW.tenant_id)
) THEN
    RAISE EXCEPTION 'INVALID_POLICY_REF: cost_snapshots.policy_version_id'
        USING ERRCODE = 'ZT001';
END IF;
        RETURN NEW;
        END;
        $$
        """
    )
    op.execute(
        f"""CREATE TRIGGER trg_cost_policy_ref BEFORE INSERT OR UPDATE OF policy_version_id, tenant_id ON app.cost_snapshots FOR EACH ROW EXECUTE FUNCTION app.fn_cost_policy_ref()"""
    )

    # ---- trg_selection_policy_ref（INVALID_POLICY_REF）----
    op.execute(
        """
CREATE OR REPLACE FUNCTION app.fn_selection_policy_ref() RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
IF NEW.policy_version_id IS NOT NULL AND NOT EXISTS (
    SELECT 1 FROM app.policy_versions p
    WHERE p.id = NEW.policy_version_id
      AND (p.tenant_id IS NULL OR p.tenant_id = NEW.tenant_id)
) THEN
    RAISE EXCEPTION 'INVALID_POLICY_REF: selection_decisions.policy_version_id'
        USING ERRCODE = 'ZT001';
END IF;
        RETURN NEW;
        END;
        $$
        """
    )
    op.execute(
        f"""CREATE TRIGGER trg_selection_policy_ref BEFORE INSERT OR UPDATE OF policy_version_id, tenant_id ON app.selection_decisions FOR EACH ROW EXECUTE FUNCTION app.fn_selection_policy_ref()"""
    )

    # ---- trg_pricing_policy_ref（INVALID_POLICY_REF）----
    op.execute(
        """
CREATE OR REPLACE FUNCTION app.fn_pricing_policy_ref() RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
IF NOT EXISTS (
    SELECT 1 FROM app.policy_versions p
    WHERE p.id = NEW.policy_version_id
      AND (p.tenant_id IS NULL OR p.tenant_id = NEW.tenant_id)
) THEN
    RAISE EXCEPTION 'INVALID_POLICY_REF: pricing_decisions.policy_version_id'
        USING ERRCODE = 'ZT001';
END IF;
        RETURN NEW;
        END;
        $$
        """
    )
    op.execute(
        f"""CREATE TRIGGER trg_pricing_policy_ref BEFORE INSERT OR UPDATE OF policy_version_id, tenant_id ON app.pricing_decisions FOR EACH ROW EXECUTE FUNCTION app.fn_pricing_policy_ref()"""
    )

    # ---- trg_campaigns_policy_ref（INVALID_POLICY_REF）----
    op.execute(
        """
CREATE OR REPLACE FUNCTION app.fn_campaigns_policy_ref() RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
IF NOT EXISTS (
    SELECT 1 FROM app.policy_versions p
    WHERE p.id = NEW.budget_policy_version_id
      AND (p.tenant_id IS NULL OR p.tenant_id = NEW.tenant_id)
) THEN
    RAISE EXCEPTION 'INVALID_POLICY_REF: ad_campaigns.budget_policy_version_id'
        USING ERRCODE = 'ZT001';
END IF;
IF NOT EXISTS (
    SELECT 1 FROM app.policy_versions p
    WHERE p.id = NEW.cid_policy_version_id
      AND (p.tenant_id IS NULL OR p.tenant_id = NEW.tenant_id)
) THEN
    RAISE EXCEPTION 'INVALID_POLICY_REF: ad_campaigns.cid_policy_version_id'
        USING ERRCODE = 'ZT001';
END IF;
        RETURN NEW;
        END;
        $$
        """
    )
    op.execute(
        f"""CREATE TRIGGER trg_campaigns_policy_ref BEFORE INSERT OR UPDATE OF budget_policy_version_id, cid_policy_version_id, tenant_id ON app.ad_campaigns FOR EACH ROW EXECUTE FUNCTION app.fn_campaigns_policy_ref()"""
    )

    # ---- trg_manual_policy_ref（INVALID_POLICY_REF）----
    op.execute(
        """
CREATE OR REPLACE FUNCTION app.fn_manual_policy_ref() RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
IF NEW.policy_version_id IS NOT NULL AND NOT EXISTS (
    SELECT 1 FROM app.policy_versions p
    WHERE p.id = NEW.policy_version_id
      AND (p.tenant_id IS NULL OR p.tenant_id = NEW.tenant_id)
) THEN
    RAISE EXCEPTION 'INVALID_POLICY_REF: manual_tasks.policy_version_id'
        USING ERRCODE = 'ZT001';
END IF;
        RETURN NEW;
        END;
        $$
        """
    )
    op.execute(
        f"""CREATE TRIGGER trg_manual_policy_ref BEFORE INSERT OR UPDATE OF policy_version_id, tenant_id ON app.manual_tasks FOR EACH ROW EXECUTE FUNCTION app.fn_manual_policy_ref()"""
    )

    # ---- trg_offers_sku_product_consistency（SKU_PRODUCT_MISMATCH）----
    op.execute(
        """
CREATE OR REPLACE FUNCTION app.fn_offers_sku_product_consistency() RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
IF NEW.sku_id IS NOT NULL AND NOT EXISTS (
    SELECT 1 FROM app.product_skus s
    WHERE s.id = NEW.sku_id AND s.product_id = NEW.product_id
) THEN
    RAISE EXCEPTION 'SKU_PRODUCT_MISMATCH: supplier_offers.sku_id/product_id'
        USING ERRCODE = 'ZT002';
END IF;
        RETURN NEW;
        END;
        $$
        """
    )
    op.execute(
        f"""CREATE TRIGGER trg_offers_sku_product_consistency BEFORE INSERT OR UPDATE OF sku_id, product_id, tenant_id ON app.supplier_offers FOR EACH ROW EXECUTE FUNCTION app.fn_offers_sku_product_consistency()"""
    )

    # ---- trg_bindings_sku_product_consistency（SKU_PRODUCT_MISMATCH）----
    op.execute(
        """
CREATE OR REPLACE FUNCTION app.fn_bindings_sku_product_consistency() RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
IF NEW.product_sku_id IS NOT NULL AND NOT EXISTS (
    SELECT 1 FROM app.product_skus s
    WHERE s.id = NEW.product_sku_id AND s.product_id = NEW.product_id
) THEN
    RAISE EXCEPTION 'SKU_PRODUCT_MISMATCH: asset_product_bindings.product_sku_id/product_id'
        USING ERRCODE = 'ZT002';
END IF;
        RETURN NEW;
        END;
        $$
        """
    )
    op.execute(
        f"""CREATE TRIGGER trg_bindings_sku_product_consistency BEFORE INSERT OR UPDATE OF product_sku_id, product_id, tenant_id ON app.asset_product_bindings FOR EACH ROW EXECUTE FUNCTION app.fn_bindings_sku_product_consistency()"""
    )

    # ---- trg_listings_account_shop_consistency（ACCOUNT_SHOP_MISMATCH）----
    op.execute(
        """
CREATE OR REPLACE FUNCTION app.fn_listings_account_shop_consistency() RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
IF NOT EXISTS (
    SELECT 1 FROM app.shops s
    WHERE s.id = NEW.shop_id AND s.account_id = NEW.account_id
) THEN
    RAISE EXCEPTION 'ACCOUNT_SHOP_MISMATCH: shop_listings.shop_id/account_id'
        USING ERRCODE = 'ZT004';
END IF;
        RETURN NEW;
        END;
        $$
        """
    )
    op.execute(
        f"""CREATE TRIGGER trg_listings_account_shop_consistency BEFORE INSERT OR UPDATE OF account_id, shop_id, tenant_id ON app.shop_listings FOR EACH ROW EXECUTE FUNCTION app.fn_listings_account_shop_consistency()"""
    )

    # ---- trg_cost_context_consistency（CONTEXT_MISMATCH）----
    op.execute(
        """
CREATE OR REPLACE FUNCTION app.fn_cost_context_consistency() RETURNS trigger
        LANGUAGE plpgsql
        AS $$
DECLARE
    d_product bigint := NULL;
    d_shop bigint := NULL;
    d_listing bigint := NULL;
BEGIN
    IF NEW.decision_object_type = 'product' THEN
        IF NOT EXISTS (SELECT 1 FROM app.products p WHERE p.id = NEW.decision_object_id AND p.tenant_id = NEW.tenant_id) THEN
            RAISE EXCEPTION 'CONTEXT_MISMATCH: cost_snapshots.decision_object product'
                USING ERRCODE = 'ZT003';
        END IF;
        d_product := NEW.decision_object_id;
    ELSIF NEW.decision_object_type = 'sku' THEN
        SELECT product_id INTO d_product FROM app.product_skus s
        WHERE s.id = NEW.decision_object_id AND s.tenant_id = NEW.tenant_id;
        IF d_product IS NULL THEN
            RAISE EXCEPTION 'CONTEXT_MISMATCH: cost_snapshots.decision_object sku'
                USING ERRCODE = 'ZT003';
        END IF;
    ELSIF NEW.decision_object_type = 'shop_listing' THEN
        SELECT l.product_id, l.shop_id, l.id INTO d_product, d_shop, d_listing
        FROM app.shop_listings l WHERE l.id = NEW.decision_object_id AND l.tenant_id = NEW.tenant_id;
        IF d_listing IS NULL THEN
            RAISE EXCEPTION 'CONTEXT_MISMATCH: cost_snapshots.decision_object shop_listing'
                USING ERRCODE = 'ZT003';
        END IF;
    ELSIF NEW.decision_object_type = 'shop_listing_sku' THEN
        SELECT ls.shop_listing_id INTO d_listing FROM app.shop_listing_skus ls
        WHERE ls.id = NEW.decision_object_id AND ls.tenant_id = NEW.tenant_id;
        IF d_listing IS NULL THEN
            RAISE EXCEPTION 'CONTEXT_MISMATCH: cost_snapshots.decision_object shop_listing_sku'
                USING ERRCODE = 'ZT003';
        END IF;
        SELECT l.product_id, l.shop_id INTO d_product, d_shop FROM app.shop_listings l WHERE l.id = d_listing;
        IF d_product IS NULL THEN
            RAISE EXCEPTION 'CONTEXT_MISMATCH: cost_snapshots.decision_object shop_listing_sku chain'
                USING ERRCODE = 'ZT003';
        END IF;
    ELSE
        RAISE EXCEPTION 'CONTEXT_MISMATCH: cost_snapshots.decision_object_type unknown'
            USING ERRCODE = 'ZT003';
    END IF;

    IF NEW.shop_id IS NOT NULL THEN
        IF d_shop IS NOT NULL AND NEW.shop_id <> d_shop THEN
            RAISE EXCEPTION 'CONTEXT_MISMATCH: cost_snapshots.shop_id'
                USING ERRCODE = 'ZT003';
        END IF;
        -- R62-1：shop_id 与 shop_listing_id 同时非空时，listing 必须属于 NEW.shop_id
        IF NEW.shop_listing_id IS NOT NULL AND NOT EXISTS (
            SELECT 1 FROM app.shop_listings l
            WHERE l.id = NEW.shop_listing_id AND l.shop_id = NEW.shop_id
        ) THEN
            RAISE EXCEPTION 'CONTEXT_MISMATCH: cost_snapshots.shop_listing_id/shop_id'
                USING ERRCODE = 'ZT003';
        END IF;
        IF NOT EXISTS (SELECT 1 FROM app.shops s WHERE s.id = NEW.shop_id AND s.tenant_id = NEW.tenant_id) THEN
            RAISE EXCEPTION 'CONTEXT_MISMATCH: cost_snapshots.shop_id'
                USING ERRCODE = 'ZT003';
        END IF;
    END IF;

    IF NEW.shop_listing_id IS NOT NULL THEN
        IF d_listing IS NOT NULL AND NEW.shop_listing_id <> d_listing THEN
            RAISE EXCEPTION 'CONTEXT_MISMATCH: cost_snapshots.shop_listing_id'
                USING ERRCODE = 'ZT003';
        END IF;
        IF d_listing IS NULL AND NOT EXISTS (
            SELECT 1 FROM app.shop_listings l
            WHERE l.id = NEW.shop_listing_id AND l.tenant_id = NEW.tenant_id AND l.product_id = d_product
        ) THEN
            RAISE EXCEPTION 'CONTEXT_MISMATCH: cost_snapshots.shop_listing_id/product'
                USING ERRCODE = 'ZT003';
        END IF;
    END IF;

    IF NEW.offer_id IS NOT NULL THEN
        IF NOT EXISTS (
            SELECT 1 FROM app.supplier_offers o
            WHERE o.id = NEW.offer_id AND o.tenant_id = NEW.tenant_id
              AND (o.product_id = d_product OR EXISTS (
                  SELECT 1 FROM app.product_skus s
                  WHERE s.id = o.sku_id AND s.product_id = d_product))
        ) THEN
            RAISE EXCEPTION 'CONTEXT_MISMATCH: cost_snapshots.offer_id/product'
                USING ERRCODE = 'ZT003';
        END IF;
    END IF;
        RETURN NEW;
END;
        $$
        """
    )
    op.execute(
        f"""CREATE TRIGGER trg_cost_context_consistency BEFORE INSERT OR UPDATE ON app.cost_snapshots FOR EACH ROW EXECUTE FUNCTION app.fn_cost_context_consistency()"""
    )

    # ---- trg_shopbind_context_consistency（CONTEXT_MISMATCH）----
    op.execute(
        """
CREATE OR REPLACE FUNCTION app.fn_shopbind_context_consistency() RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
IF NEW.asset_product_binding_id IS NOT NULL AND NOT EXISTS (
    SELECT 1 FROM app.asset_product_bindings b
    WHERE b.id = NEW.asset_product_binding_id
      AND b.asset_id = NEW.asset_id
      AND b.product_id = NEW.product_id
) THEN
    RAISE EXCEPTION 'CONTEXT_MISMATCH: asset_shop_bindings.asset_product_binding_id'
        USING ERRCODE = 'ZT003';
END IF;
IF NEW.shop_listing_id IS NOT NULL AND NOT EXISTS (
    SELECT 1 FROM app.shop_listings l
    WHERE l.id = NEW.shop_listing_id
      AND l.shop_id = NEW.shop_id
      AND (NEW.product_id IS NULL OR l.product_id = NEW.product_id)
) THEN
    RAISE EXCEPTION 'CONTEXT_MISMATCH: asset_shop_bindings.shop_listing_id/shop_id/product_id'
        USING ERRCODE = 'ZT003';
END IF;
        RETURN NEW;
        END;
        $$
        """
    )
    op.execute(
        f"""CREATE TRIGGER trg_shopbind_context_consistency BEFORE INSERT OR UPDATE ON app.asset_shop_bindings FOR EACH ROW EXECUTE FUNCTION app.fn_shopbind_context_consistency()"""
    )

    # ---- trg_pricing_context_consistency（CONTEXT_MISMATCH）----
    op.execute(
        """
CREATE OR REPLACE FUNCTION app.fn_pricing_context_consistency() RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
IF NOT EXISTS (
    SELECT 1 FROM app.shop_listing_skus ls
    WHERE ls.id = NEW.shop_listing_sku_id AND ls.shop_listing_id = NEW.shop_listing_id
) THEN
    RAISE EXCEPTION 'CONTEXT_MISMATCH: pricing_decisions.shop_listing_sku_id/shop_listing_id'
        USING ERRCODE = 'ZT003';
END IF;
IF NOT EXISTS (
    SELECT 1 FROM app.shop_listings l
    WHERE l.id = NEW.shop_listing_id AND l.shop_id = NEW.shop_id
) THEN
    RAISE EXCEPTION 'CONTEXT_MISMATCH: pricing_decisions.shop_listing_id/shop_id'
        USING ERRCODE = 'ZT003';
END IF;
        RETURN NEW;
        END;
        $$
        """
    )
    op.execute(
        f"""CREATE TRIGGER trg_pricing_context_consistency BEFORE INSERT OR UPDATE ON app.pricing_decisions FOR EACH ROW EXECUTE FUNCTION app.fn_pricing_context_consistency()"""
    )

    # ---- trg_campaigns_scope_consistency（SCOPE_MISMATCH）----
    op.execute(
        """
CREATE OR REPLACE FUNCTION app.fn_campaigns_scope_consistency() RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
IF NOT EXISTS (
    SELECT 1 FROM app.shop_listings l
    WHERE l.id = NEW.shop_listing_id
      AND l.shop_id = NEW.shop_id
      AND l.account_id = NEW.account_id
) THEN
    RAISE EXCEPTION 'SCOPE_MISMATCH: ad_campaigns.shop_listing_id/shop_id/account_id'
        USING ERRCODE = 'ZT005';
END IF;
        RETURN NEW;
        END;
        $$
        """
    )
    op.execute(
        f"""CREATE TRIGGER trg_campaigns_scope_consistency BEFORE INSERT OR UPDATE OF account_id, shop_id, shop_listing_id, tenant_id ON app.ad_campaigns FOR EACH ROW EXECUTE FUNCTION app.fn_campaigns_scope_consistency()"""
    )

    # ---- trg_campassets_same_scope（SCOPE_MISMATCH）----
    op.execute(
        """
CREATE OR REPLACE FUNCTION app.fn_campassets_same_scope() RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
IF NOT EXISTS (
    SELECT 1 FROM app.ad_campaigns c
    JOIN app.asset_shop_bindings b ON b.id = NEW.asset_shop_binding_id
    WHERE c.id = NEW.campaign_id
      AND c.tenant_id = NEW.tenant_id
      AND c.shop_id = b.shop_id
) THEN
    RAISE EXCEPTION 'SCOPE_MISMATCH: ad_campaign_assets.campaign_id/asset_shop_binding_id'
        USING ERRCODE = 'ZT005';
END IF;
        RETURN NEW;
        END;
        $$
        """
    )
    op.execute(
        f"""CREATE TRIGGER trg_campassets_same_scope BEFORE INSERT OR UPDATE ON app.ad_campaign_assets FOR EACH ROW EXECUTE FUNCTION app.fn_campassets_same_scope()"""
    )

    # ---- trg_snapshots_dimension_consistency（DIMENSION_MISMATCH）----
    op.execute(
        """
CREATE OR REPLACE FUNCTION app.fn_snapshots_dimension_consistency() RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
IF NOT EXISTS (
    SELECT 1 FROM app.shops s WHERE s.id = NEW.shop_id AND s.account_id = NEW.account_id
) THEN
    RAISE EXCEPTION 'DIMENSION_MISMATCH: ad_report_snapshots.shop_id/account_id'
        USING ERRCODE = 'ZT006';
END IF;
IF NOT EXISTS (
    SELECT 1 FROM app.shop_listings l
    WHERE l.id = NEW.shop_listing_id
      AND l.shop_id = NEW.shop_id
      AND l.product_id = NEW.product_id
) THEN
    RAISE EXCEPTION 'DIMENSION_MISMATCH: ad_report_snapshots.shop_listing_id/shop_id/product_id'
        USING ERRCODE = 'ZT006';
END IF;
IF NEW.shop_listing_sku_id IS NOT NULL AND NOT EXISTS (
    SELECT 1 FROM app.shop_listing_skus ls
    WHERE ls.id = NEW.shop_listing_sku_id AND ls.shop_listing_id = NEW.shop_listing_id
) THEN
    RAISE EXCEPTION 'DIMENSION_MISMATCH: ad_report_snapshots.shop_listing_sku_id'
        USING ERRCODE = 'ZT006';
END IF;
IF NOT EXISTS (
    SELECT 1 FROM app.ad_campaigns c
    WHERE c.id = NEW.campaign_id AND c.shop_listing_id = NEW.shop_listing_id
) THEN
    RAISE EXCEPTION 'DIMENSION_MISMATCH: ad_report_snapshots.campaign_id/shop_listing_id'
        USING ERRCODE = 'ZT006';
END IF;
IF NEW.asset_binding_id IS NOT NULL AND NOT EXISTS (
    SELECT 1 FROM app.asset_shop_bindings b
    WHERE b.id = NEW.asset_binding_id
      AND b.shop_id = NEW.shop_id
      AND (b.product_id IS NULL OR b.product_id = NEW.product_id)
      AND (b.shop_listing_id IS NULL OR b.shop_listing_id = NEW.shop_listing_id)
) THEN
    RAISE EXCEPTION 'DIMENSION_MISMATCH: ad_report_snapshots.asset_binding_id/shop/product/listing'
        USING ERRCODE = 'ZT006';
END IF;
        RETURN NEW;
        END;
        $$
        """
    )
    op.execute(
        f"""CREATE TRIGGER trg_snapshots_dimension_consistency BEFORE INSERT OR UPDATE ON app.ad_report_snapshots FOR EACH ROW EXECUTE FUNCTION app.fn_snapshots_dimension_consistency()"""
    )

    # ---- trg_feedback_dimension_consistency（DIMENSION_MISMATCH）----
    op.execute(
        """
CREATE OR REPLACE FUNCTION app.fn_feedback_dimension_consistency() RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
IF NOT EXISTS (
    SELECT 1 FROM app.ad_report_snapshots s
    WHERE s.id = NEW.source_snapshot_id
      AND s.tenant_id = NEW.tenant_id
      AND s.account_id = NEW.account_id
      AND s.shop_id = NEW.shop_id
      AND s.shop_listing_id = NEW.shop_listing_id
      AND s.product_id = NEW.product_id
      AND s.campaign_id = NEW.campaign_id
      AND s.shop_listing_sku_id IS NOT DISTINCT FROM NEW.shop_listing_sku_id
      AND s.asset_binding_id IS NOT DISTINCT FROM NEW.asset_binding_id
) THEN
    RAISE EXCEPTION 'DIMENSION_MISMATCH: roi_feedback_events.source_snapshot_id'
        USING ERRCODE = 'ZT006';
END IF;
        RETURN NEW;
        END;
        $$
        """
    )
    op.execute(
        f"""CREATE TRIGGER trg_feedback_dimension_consistency BEFORE INSERT OR UPDATE ON app.roi_feedback_events FOR EACH ROW EXECUTE FUNCTION app.fn_feedback_dimension_consistency()"""
    )



def downgrade() -> None:
    """严格逆序（G7 逆序）：先 DROP TRIGGER，后 DROP FUNCTION。"""
    op.execute(f"DROP TRIGGER IF EXISTS trg_feedback_dimension_consistency ON app.roi_feedback_events")
    op.execute(f"DROP FUNCTION IF EXISTS app.fn_feedback_dimension_consistency()")
    op.execute(f"DROP TRIGGER IF EXISTS trg_snapshots_dimension_consistency ON app.ad_report_snapshots")
    op.execute(f"DROP FUNCTION IF EXISTS app.fn_snapshots_dimension_consistency()")
    op.execute(f"DROP TRIGGER IF EXISTS trg_campassets_same_scope ON app.ad_campaign_assets")
    op.execute(f"DROP FUNCTION IF EXISTS app.fn_campassets_same_scope()")
    op.execute(f"DROP TRIGGER IF EXISTS trg_campaigns_scope_consistency ON app.ad_campaigns")
    op.execute(f"DROP FUNCTION IF EXISTS app.fn_campaigns_scope_consistency()")
    op.execute(f"DROP TRIGGER IF EXISTS trg_pricing_context_consistency ON app.pricing_decisions")
    op.execute(f"DROP FUNCTION IF EXISTS app.fn_pricing_context_consistency()")
    op.execute(f"DROP TRIGGER IF EXISTS trg_shopbind_context_consistency ON app.asset_shop_bindings")
    op.execute(f"DROP FUNCTION IF EXISTS app.fn_shopbind_context_consistency()")
    op.execute(f"DROP TRIGGER IF EXISTS trg_cost_context_consistency ON app.cost_snapshots")
    op.execute(f"DROP FUNCTION IF EXISTS app.fn_cost_context_consistency()")
    op.execute(f"DROP TRIGGER IF EXISTS trg_listings_account_shop_consistency ON app.shop_listings")
    op.execute(f"DROP FUNCTION IF EXISTS app.fn_listings_account_shop_consistency()")
    op.execute(f"DROP TRIGGER IF EXISTS trg_bindings_sku_product_consistency ON app.asset_product_bindings")
    op.execute(f"DROP FUNCTION IF EXISTS app.fn_bindings_sku_product_consistency()")
    op.execute(f"DROP TRIGGER IF EXISTS trg_offers_sku_product_consistency ON app.supplier_offers")
    op.execute(f"DROP FUNCTION IF EXISTS app.fn_offers_sku_product_consistency()")
    op.execute(f"DROP TRIGGER IF EXISTS trg_manual_policy_ref ON app.manual_tasks")
    op.execute(f"DROP FUNCTION IF EXISTS app.fn_manual_policy_ref()")
    op.execute(f"DROP TRIGGER IF EXISTS trg_campaigns_policy_ref ON app.ad_campaigns")
    op.execute(f"DROP FUNCTION IF EXISTS app.fn_campaigns_policy_ref()")
    op.execute(f"DROP TRIGGER IF EXISTS trg_pricing_policy_ref ON app.pricing_decisions")
    op.execute(f"DROP FUNCTION IF EXISTS app.fn_pricing_policy_ref()")
    op.execute(f"DROP TRIGGER IF EXISTS trg_selection_policy_ref ON app.selection_decisions")
    op.execute(f"DROP FUNCTION IF EXISTS app.fn_selection_policy_ref()")
    op.execute(f"DROP TRIGGER IF EXISTS trg_cost_policy_ref ON app.cost_snapshots")
    op.execute(f"DROP FUNCTION IF EXISTS app.fn_cost_policy_ref()")
    op.execute(f"DROP TRIGGER IF EXISTS trg_shops_policy_ref ON app.shops")
    op.execute(f"DROP FUNCTION IF EXISTS app.fn_shops_policy_ref()")
    op.execute(f"DROP TRIGGER IF EXISTS trg_policy_supersede_scope ON app.policy_versions")
    op.execute(f"DROP FUNCTION IF EXISTS app.fn_policy_supersede_scope()")

