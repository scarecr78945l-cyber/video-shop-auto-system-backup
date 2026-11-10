# -*- coding: utf-8 -*-
"""T4 生成器：数据驱动生成 17 个 trigger 的 Alembic migration（round-59 初版；round-61 R60 回修；round-63 R62 二次回修）。

数据来源：**生成器自带 manifest（本文件 MANIFEST 区）**。`trg_expected.py` 是独立验收快照，
断言执行 generator manifest ↔ expected ↔ migration/catalog 三向交叉（R62-3），
任何一侧录入错误都会被差异暴露，避免同源假通过。

round-61 回修（R60-1~R60-4）：G7 原序安装；cost/shopbind/snapshots 同源矩阵；supersede 事件勘误；
ZT001~ZT007 自定义 SQLSTATE；trg_expected 独立快照。
round-63 回修（R62-1~R62-3）：
- R62-1：cost_context 统一矩阵补 `listing.shop_id = NEW.shop_id`（同 tenant 同 product 不同 shop 拒绝）；
- R62-2：supersede 同时维护出边（NEW->parent）与入边（child->NEW），父 policy 更新破坏子链时拒绝；
- R62-3：生成器 manifest 与验收快照分离，断言三向比较。

用法：
  python scripts/gen_trg_migration.py          # 生成/覆盖 canonical 文件（漂移时拒绝）
  python scripts/gen_trg_migration.py --check  # 只校验，不写入
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VERSIONS = ROOT / "migrations" / "versions"

REV = "17trg000001"
DOWN = "31tbl000001"
CREATE_DATE = "2026-09-04T13:00:00+00:00"
CANONICAL_NAME = f"{REV}_17_triggers.py"
SCHEMA = "app"

# ---------------------------------------------------------------------------
# 生成器 manifest（round-63 起内嵌独立；与 trg_expected.py 独立验收快照交叉校验）
# ---------------------------------------------------------------------------
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

# 17 项 trigger（事件列按 v6 §8；supersede 含 round-61 勘误的 policy_type/scope_type/scope_id）
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

SQLSTATE_MAP = {
    "INVALID_POLICY_REF": "ZT001",
    "SKU_PRODUCT_MISMATCH": "ZT002",
    "CONTEXT_MISMATCH": "ZT003",
    "ACCOUNT_SHOP_MISMATCH": "ZT004",
    "SCOPE_MISMATCH": "ZT005",
    "DIMENSION_MISMATCH": "ZT006",
    "SUPERSEDE_MISMATCH": "ZT007",
}

# 函数体（PL/pgSQL，BEGIN...END 块内容；生成器自动包裹 BEGIN/END 与 RETURN NEW）。
# 变量风格：NEW.<col>；错误经 RAISE EXCEPTION '<CODE>: <detail>' USING ERRCODE='<SQLSTATE>'。
FUNC_BODIES = {
    # 1. policy 引用（同 tenant 或 global）
    "trg_shops_policy_ref": """
IF NEW.cid_policy_version_id IS NOT NULL AND NOT EXISTS (
    SELECT 1 FROM app.policy_versions p
    WHERE p.id = NEW.cid_policy_version_id
      AND (p.tenant_id IS NULL OR p.tenant_id = NEW.tenant_id)
) THEN
    RAISE EXCEPTION 'INVALID_POLICY_REF: shops.cid_policy_version_id'
        USING ERRCODE = 'ZT001';
END IF;
""",
    "trg_cost_policy_ref": """
IF NOT EXISTS (
    SELECT 1 FROM app.policy_versions p
    WHERE p.id = NEW.policy_version_id
      AND (p.tenant_id IS NULL OR p.tenant_id = NEW.tenant_id)
) THEN
    RAISE EXCEPTION 'INVALID_POLICY_REF: cost_snapshots.policy_version_id'
        USING ERRCODE = 'ZT001';
END IF;
""",
    "trg_selection_policy_ref": """
IF NEW.policy_version_id IS NOT NULL AND NOT EXISTS (
    SELECT 1 FROM app.policy_versions p
    WHERE p.id = NEW.policy_version_id
      AND (p.tenant_id IS NULL OR p.tenant_id = NEW.tenant_id)
) THEN
    RAISE EXCEPTION 'INVALID_POLICY_REF: selection_decisions.policy_version_id'
        USING ERRCODE = 'ZT001';
END IF;
""",
    "trg_pricing_policy_ref": """
IF NOT EXISTS (
    SELECT 1 FROM app.policy_versions p
    WHERE p.id = NEW.policy_version_id
      AND (p.tenant_id IS NULL OR p.tenant_id = NEW.tenant_id)
) THEN
    RAISE EXCEPTION 'INVALID_POLICY_REF: pricing_decisions.policy_version_id'
        USING ERRCODE = 'ZT001';
END IF;
""",
    "trg_campaigns_policy_ref": """
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
""",
    "trg_manual_policy_ref": """
IF NEW.policy_version_id IS NOT NULL AND NOT EXISTS (
    SELECT 1 FROM app.policy_versions p
    WHERE p.id = NEW.policy_version_id
      AND (p.tenant_id IS NULL OR p.tenant_id = NEW.tenant_id)
) THEN
    RAISE EXCEPTION 'INVALID_POLICY_REF: manual_tasks.policy_version_id'
        USING ERRCODE = 'ZT001';
END IF;
""",
    # 2. SKU/产品一致性
    "trg_offers_sku_product_consistency": """
IF NEW.sku_id IS NOT NULL AND NOT EXISTS (
    SELECT 1 FROM app.product_skus s
    WHERE s.id = NEW.sku_id AND s.product_id = NEW.product_id
) THEN
    RAISE EXCEPTION 'SKU_PRODUCT_MISMATCH: supplier_offers.sku_id/product_id'
        USING ERRCODE = 'ZT002';
END IF;
""",
    "trg_bindings_sku_product_consistency": """
IF NEW.product_sku_id IS NOT NULL AND NOT EXISTS (
    SELECT 1 FROM app.product_skus s
    WHERE s.id = NEW.product_sku_id AND s.product_id = NEW.product_id
) THEN
    RAISE EXCEPTION 'SKU_PRODUCT_MISMATCH: asset_product_bindings.product_sku_id/product_id'
        USING ERRCODE = 'ZT002';
END IF;
""",
    # 3. account/shop
    "trg_listings_account_shop_consistency": """
IF NOT EXISTS (
    SELECT 1 FROM app.shops s
    WHERE s.id = NEW.shop_id AND s.account_id = NEW.account_id
) THEN
    RAISE EXCEPTION 'ACCOUNT_SHOP_MISMATCH: shop_listings.shop_id/account_id'
        USING ERRCODE = 'ZT004';
END IF;
""",
    # 4. cost 上下文：按 decision_object_type 推导同源链（R60-2）
    #    函数体自带 DECLARE...BEGIN...END（含局部变量），生成器不再额外包裹 BEGIN/END
    "trg_cost_context_consistency": """
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
END;
""",
    # 5. shopbind 上下文：binding 的 product/asset + listing↔product/binding（R60-2）
    "trg_shopbind_context_consistency": """
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
""",
    # 6. pricing 上下文：listing_sku 属于 listing、listing 属于 shop
    "trg_pricing_context_consistency": """
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
""",
    # 7. campaign scope
    "trg_campaigns_scope_consistency": """
IF NOT EXISTS (
    SELECT 1 FROM app.shop_listings l
    WHERE l.id = NEW.shop_listing_id
      AND l.shop_id = NEW.shop_id
      AND l.account_id = NEW.account_id
) THEN
    RAISE EXCEPTION 'SCOPE_MISMATCH: ad_campaigns.shop_listing_id/shop_id/account_id'
        USING ERRCODE = 'ZT005';
END IF;
""",
    "trg_campassets_same_scope": """
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
""",
    # 8. 报表维度同源（R60-2：补 asset_binding 的 product/listing）
    "trg_snapshots_dimension_consistency": """
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
""",
    # 9. feedback 冗余维度与 source_snapshot 一致
    "trg_feedback_dimension_consistency": """
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
""",
    # 10. supersede 双向维护：出边（NEW->parent）与入边（child->NEW）（R62-2）
    #     事件含 policy_type/scope_type/scope_id（round-61 勘误）；scope_key 用生成表达式等价形式。
    "trg_policy_supersede_scope": """
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
""",
}


def _validate() -> None:
    assert len(TRIGGERS) == 17, f"TRIGGERS == {len(TRIGGERS)} != 17"
    names = [t[0] for t in TRIGGERS]
    assert len(set(names)) == 17, "trigger 名重复"
    # R60-1：安装顺序 == G7 冻结顺序
    assert names == INSTALL_ORDER, f"安装顺序 != G7:\n  actual={names}\n  expect={INSTALL_ORDER}"
    # R60-3：SQLSTATE 全部为 ZT 自定义类且不落在 PL/pgSQL 已登记 P0001~P0004
    for code, state in SQLSTATE_MAP.items():
        assert state.startswith("ZT"), f"{code} SQLSTATE 非自定义类: {state}"
        assert state in ("ZT001", "ZT002", "ZT003", "ZT004", "ZT005", "ZT006", "ZT007"), state
    assert set(t[3] for t in TRIGGERS) == set(BUSINESS_CODES), "业务错误码集合不一致"
    assert set(SQLSTATE_MAP) == set(BUSINESS_CODES), "SQLSTATE_MAP 与业务码不一致"
    # 每个 trigger 有函数体；每个函数体只使用其自身错误码的 SQLSTATE
    missing = [n for n, *_ in TRIGGERS if n not in FUNC_BODIES]
    assert not missing, f"缺函数体: {missing}"
    for name, _t, _ev, code, state in TRIGGERS:
        body = FUNC_BODIES[name]
        assert state in body, f"{name} 函数体缺 {state}"
        for other, other_state in SQLSTATE_MAP.items():
            if other_state in body and other != code:
                raise AssertionError(f"{name} 函数体出现 {other} 的 SQLSTATE {other_state}")
    # 事件列字段存在性
    tables = {t for _n, t, *_ in TRIGGERS}
    for name, table, cols, _code, _state in TRIGGERS:
        assert table in tables


def build_content() -> str:
    L = []
    L.append('"""T4: 17 triggers (data-driven generator, from 15-数据字典.md v6 §8 + error-codes.yaml, round-61)')
    L.append("")
    L.append(f"Revision ID: {REV}")
    L.append(f"Revises: {DOWN}")
    L.append(f"Create Date: {CREATE_DATE}")
    L.append('"""')
    L.append("from typing import Sequence, Union")
    L.append("")
    L.append("from alembic import op")
    L.append("")
    L.append("")
    L.append(f"revision: str = {REV!r}")
    L.append(f"down_revision: Union[str, Sequence[str], None] = {DOWN!r}")
    L.append("branch_labels: Union[str, Sequence[str], None] = None")
    L.append("depends_on: Union[str, Sequence[str], None] = None")
    L.append("")
    L.append("")
    L.append(f"SCHEMA = {SCHEMA!r}")
    L.append("")
    L.append("TRIGGERS = [")
    for name, table, ev, code, state in TRIGGERS:
        L.append("    (%r, %r, %r, %r, %r)," % (name, table, ev, code, state))
    L.append("]")
    L.append("")

    L.append("")
    L.append("def upgrade() -> None:")
    L.append('    """按 ddl-order §六 G7 原序：每项 CREATE FUNCTION -> CREATE TRIGGER（普通 BEFORE ROW）。"""')
    for name, table, ev, code, _state in TRIGGERS:
        fn = "fn_" + name[len("trg_"):]
        events = f"BEFORE INSERT OR UPDATE" + (f" OF {', '.join(ev)}" if ev else "")
        body = FUNC_BODIES[name]
        self_contained = body.strip().startswith("DECLARE") and body.strip().rstrip().endswith("END;")
        L.append("")
        L.append("    # ---- %s（%s）----" % (name, code))
        L.append("    op.execute(")
        L.append("        \"\"\"")
        L.append(f"CREATE OR REPLACE FUNCTION {SCHEMA}.{fn}() RETURNS trigger")
        L.append("        LANGUAGE plpgsql")
        L.append("        AS $$")
        if not self_contained:
            L.append("        BEGIN")
        body_lines = body.strip("\n").split("\n")
        if self_contained:
            # 在最后的 END; 前插入 RETURN NEW;（块内）
            for i in range(len(body_lines) - 1, -1, -1):
                if body_lines[i].strip() == "END;":
                    body_lines.insert(i, "        RETURN NEW;")
                    break
        for line in body_lines:
            L.append(line)
        if not self_contained:
            L.append("        RETURN NEW;")
            L.append("        END;")
        L.append("        $$")
        L.append('        """')
        L.append("    )")
        L.append("    op.execute(")
        L.append(f"        f\"\"\"CREATE TRIGGER {name} {events} ON {SCHEMA}.{table} FOR EACH ROW EXECUTE FUNCTION {SCHEMA}.{fn}()\"\"\"")
        L.append("    )")
    L.append("")

    L.append("")
    L.append("")
    L.append("def downgrade() -> None:")
    L.append('    """严格逆序（G7 逆序）：先 DROP TRIGGER，后 DROP FUNCTION。"""')
    for name, table, _ev, _code, _state in reversed(TRIGGERS):
        fn = "fn_" + name[len("trg_"):]
        L.append(f"    op.execute(f\"DROP TRIGGER IF EXISTS {name} ON {SCHEMA}.{table}\")")
        L.append(f"    op.execute(f\"DROP FUNCTION IF EXISTS {SCHEMA}.{fn}()\")")
    L.append("")
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
    print(f"[OK] generated {out} ({len(TRIGGERS)} triggers)")


if __name__ == "__main__":
    main()