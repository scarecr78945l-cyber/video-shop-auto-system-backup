# -*- coding: utf-8 -*-
"""T4: 17 trigger 行为正反例探针（round-59；外层事务结束 ROLLBACK，不留数据）。

test-strategy §六：17 项各至少一个正例 + 一个反例；反例覆盖 7 个错误码；
断言稳定错误码（SQLSTATE + 消息前缀），不依赖自然语言错误文本。

基线（按依赖序插入，全 RETURNING 捕获 id）：
  tenants t1/t2；policies（global/t1/t2）；platform_accounts；suppliers；products；
  product_skus；supplier_offers；assets；asset_product_bindings；shops；shop_listings；
  shop_listing_skus；asset_shop_bindings；cost_snapshots；pricing_decisions；ad_campaigns；
  ad_campaign_assets；ad_report_snapshots；roi_feedback_events；workflow_runs；
  manual_tasks；selection_decisions
用法：python scripts/assert_triggers_probes.py（需 DATABASE_URL；事务回滚无残留）
"""
import os
import sys

from sqlalchemy import create_engine, text
from sqlalchemy.exc import DBAPIError, IntegrityError

URL = os.environ.get("DATABASE_URL", "").strip()
if not URL:
    print("[FAIL] 缺少 DATABASE_URL", file=sys.stderr)
    sys.exit(1)

ok = True


def check(name, cond, detail=""):
    global ok
    print(f"[{'PASS' if cond else 'FAIL'}] {name}" + (f"  {detail}" if detail else ""))
    if not cond:
        ok = False


def expect_state(label, sql, params, code, state):
    """在 SAVEPOINT 内执行应触发错误码的 SQL；断言 SQLSTATE == state 且消息含错误码 code。"""
    try:
        with conn.begin_nested():
            conn.execute(text(sql), params)
    except DBAPIError as exc:
        orig = exc.orig
        pgcode = getattr(orig, "pgcode", "")
        pgerror = str(getattr(orig, "pgerror", "") or exc)
        code_ok = pgcode == state and code in pgerror
        check(label, code_ok, f"pgcode={pgcode} msg={pgerror[:120]}")
        return
    check(label, False, "未报错")


def ins(conn, sql, params):
    return conn.execute(text(sql), params).scalar()


eng = create_engine(URL, isolation_level="SERIALIZABLE")
conn = eng.connect()
tx = conn.begin()

try:
    # ================= 基线 =================
    t1 = ins(conn, "INSERT INTO app.tenants (public_id, name, scope) VALUES ('00000000-0000-0000-0000-000000000001','t1','internal') RETURNING id", {})
    t2 = ins(conn, "INSERT INTO app.tenants (public_id, name, scope) VALUES ('00000000-0000-0000-0000-000000000004','t2','internal') RETURNING id", {})

    # policies：global / t1 / t2（effective_to 有限，避免同 scope exclusion 区间重叠）
    def mkpolicy(suffix, tenant, eff_to_sql):
        # eff_to_sql 为受控 SQL 片段（'NULL' 或 "now() + interval '30 days'"），直接嵌入
        return ins(conn,
                   "INSERT INTO app.policy_versions (public_id, tenant_id, policy_type, version, scope_type, "
                   "scope_id, content, content_hash, effective_from, effective_to, approved_by_actor_id) VALUES "
                   "(:p,:t,'cid_breakeven','v5','global',NULL,'{}','h',now()," + eff_to_sql + ","
                   "'00000000-0000-0000-0000-000000000003') RETURNING id",
                   {"p": f"00000000-0000-0000-0000-{suffix:012d}", "t": tenant})

    pg_global = mkpolicy(100, None, "NULL")
    pg_t1 = mkpolicy(101, t1, "now() + interval '30 days'")
    pg_t2 = mkpolicy(102, t2, "now() + interval '30 days'")

    acc1 = ins(conn,
               "INSERT INTO app.platform_accounts (public_id, tenant_id, platform, account_key) VALUES "
               "('00000000-0000-0000-0000-000000000002',:t,'wechat_channels','acc1') RETURNING id", {"t": t1})
    acc2 = ins(conn,
               "INSERT INTO app.platform_accounts (public_id, tenant_id, platform, account_key) VALUES "
               "('00000000-0000-0000-0000-000000000005',:t,'wechat_channels','acc2') RETURNING id", {"t": t2})

    sup1 = ins(conn,
               "INSERT INTO app.suppliers (public_id, tenant_id, supplier_code, name, source_platform, source, mode) "
               "VALUES ('00000000-0000-0000-0000-000000000012',:t,'SUP1','sup','self','manual','real') RETURNING id",
               {"t": t1})
    prod1 = ins(conn,
                "INSERT INTO app.products (public_id, tenant_id, title_base, category_id) VALUES "
                "('00000000-0000-0000-0000-000000000020',:t,'P1','cat1') RETURNING id", {"t": t1})
    prod2 = ins(conn,
                "INSERT INTO app.products (public_id, tenant_id, title_base, category_id) VALUES "
                "('00000000-0000-0000-0000-000000000021',:t,'P2','cat1') RETURNING id", {"t": t1})
    sku1 = ins(conn,
               "INSERT INTO app.product_skus (tenant_id, product_id, attributes) VALUES (:t,:p,'{}') RETURNING id",
               {"t": t1, "p": prod1})
    sku2 = ins(conn,
               "INSERT INTO app.product_skus (tenant_id, product_id, attributes) VALUES (:t,:p,'{}') RETURNING id",
               {"t": t1, "p": prod2})

    # 基线 supplier_offer（sku1 属于 prod1 -> 一致性成立）
    of1 = ins(conn,
              "INSERT INTO app.supplier_offers (tenant_id, supplier_id, product_id, sku_id, supplier_sku_id, "
              "offer_id, price, observed_at, expires_at, source, mode, idempotency_key) VALUES "
              "(:t,:s,:p,:k,'SS1','OF1',10.0,now(),now()+interval '1 day','supplier_catalog','real','ik1') RETURNING id",
              {"t": t1, "s": sup1, "p": prod1, "k": sku1})

    ast1 = ins(conn,
               "INSERT INTO app.assets (public_id, tenant_id, content_sha256, file_ref, mime_type, size_bytes, "
               "source_type, evidence_hash, captured_at, mode) VALUES "
               "('00000000-0000-0000-0000-000000000030',:t,repeat('a',64),'f1','image/png',100,"
               "'self_created',repeat('b',64),now(),'real') RETURNING id", {"t": t1})

    # 基线 asset_product_binding（sku1->prod1 一致）
    apb1 = ins(conn,
               "INSERT INTO app.asset_product_bindings (tenant_id, asset_id, product_id, product_sku_id, purpose) "
               "VALUES (:t,:a,:p,:k,'main_image') RETURNING id", {"t": t1, "a": ast1, "p": prod1, "k": sku1})

    # shops：先无 cid_policy（policy 引用 trigger 只在非空时触发）
    shop1 = ins(conn,
                "INSERT INTO app.shops (public_id, tenant_id, account_id, platform_shop_id, name) VALUES "
                "('00000000-0000-0000-0000-000000000010',:t,:a,'shop1','s1') RETURNING id",
                {"t": t1, "a": acc1})
    shop2 = ins(conn,
                "INSERT INTO app.shops (public_id, tenant_id, account_id, platform_shop_id, name) VALUES "
                "('00000000-0000-0000-0000-000000000011',:t,:a,'shop2','s2') RETURNING id",
                {"t": t2, "a": acc2})

    l1 = ins(conn,
             "INSERT INTO app.shop_listings (public_id, tenant_id, account_id, shop_id, product_id, "
             "title_effective, idempotency_key) VALUES "
             "('00000000-0000-0000-0000-000000000040',:t,:a,:s,:p,'L1','lk1') RETURNING id",
             {"t": t1, "a": acc1, "s": shop1, "p": prod1})
    lsku1 = ins(conn,
                "INSERT INTO app.shop_listing_skus (tenant_id, shop_listing_id, sku_id, shop_price) "
                "VALUES (:t,:l,:k,100) RETURNING id", {"t": t1, "l": l1, "k": sku1})

    asb1 = ins(conn,
               "INSERT INTO app.asset_shop_bindings (tenant_id, asset_id, shop_id, purpose) "
               "VALUES (:t,:a,:s,'ad_image') RETURNING id", {"t": t1, "a": ast1, "s": shop1})

    cs1 = ins(conn,
              "INSERT INTO app.cost_snapshots (public_id, tenant_id, decision_object_type, decision_object_id, "
              "shop_id, shop_listing_id, offer_id, policy_version_id, k_price, ad_pre_margin, idempotency_key, "
              "snapshot_at) VALUES "
              "('00000000-0000-0000-0000-000000000050',:t,'shop_listing_sku',:o,:s,:l,:of,:p,10.0,3.0,'c1',now()) "
              "RETURNING id",
              {"t": t1, "o": lsku1, "s": shop1, "l": l1, "of": of1, "p": pg_t1})

    pd1 = ins(conn,
              "INSERT INTO app.pricing_decisions (public_id, tenant_id, shop_id, shop_listing_id, "
              "shop_listing_sku_id, cost_snapshot_id, policy_version_id, decision_type, cost_floor_price, "
              "suggested_price, floor_price, cid_inputs, cid_results, effective_from, idempotency_key) VALUES "
              "('00000000-0000-0000-0000-000000000051',:t,:s,:l,:ls,:c,:p,'initial',5,10,4,'{}','{}',now(),'pk1') "
              "RETURNING id",
              {"t": t1, "s": shop1, "l": l1, "ls": lsku1, "c": cs1, "p": pg_t1})

    camp1 = ins(conn,
                "INSERT INTO app.ad_campaigns (public_id, tenant_id, account_id, shop_id, shop_listing_id, "
                "idempotency_key, approved_budget, approved_daily_budget, approved_target_roi, approved_stop_loss, "
                "current_budget, current_daily_budget, current_target_roi, current_stop_loss, feedback_coefficient, "
                "budget_policy_version_id, cid_policy_version_id) VALUES "
                "('00000000-0000-0000-0000-000000000060',:t,:a,:s,:l,'ak1',1000,100,2.0,0.5,1000,100,2.0,0.5,1.0,"
                ":bp,:cp) RETURNING id",
                {"t": t1, "a": acc1, "s": shop1, "l": l1, "bp": pg_t1, "cp": pg_t1})

    aca1 = ins(conn,
               "INSERT INTO app.ad_campaign_assets (tenant_id, campaign_id, asset_shop_binding_id) "
               "VALUES (:t,:c,:b) RETURNING id", {"t": t1, "c": camp1, "b": asb1})

    snap1 = ins(conn,
                "INSERT INTO app.ad_report_snapshots (tenant_id, account_id, shop_id, shop_listing_id, "
                "shop_listing_sku_id, product_id, campaign_id, asset_binding_id, granularity, window_start, "
                "window_end, attribution_mode, report_version_key, captured_at, raw_evidence_hash) VALUES "
                "(:t,:a,:s,:l,:ls,:p,:c,:b,'campaign','2026-01-01','2026-01-02','last_click','rv1',now(),"
                "repeat('x',64)) RETURNING id",
                {"t": t1, "a": acc1, "s": shop1, "l": l1, "ls": lsku1, "p": prod1, "c": camp1, "b": asb1})

    fb1 = ins(conn,
              "INSERT INTO app.roi_feedback_events (tenant_id, account_id, shop_id, shop_listing_id, "
              "shop_listing_sku_id, product_id, campaign_id, asset_binding_id, source_snapshot_id, window_start, "
              "window_end, attribution_mode, feedback_type, subject_type, subject_key, value, aggregation_version, "
              "idempotency_key) VALUES "
              "(:t,:a,:s,:l,:ls,:p,:c,:b,:sn,'2026-01-01','2026-01-02','last_click','product_score','product','PK',"
              "1.0,'av1','rf1') RETURNING id",
              {"t": t1, "a": acc1, "s": shop1, "l": l1, "ls": lsku1, "p": prod1, "c": camp1, "b": asb1, "sn": snap1})

    wr1 = ins(conn,
              "INSERT INTO app.workflow_runs (public_id, tenant_id, run_type, idempotency_key) VALUES "
              "('00000000-0000-0000-0000-000000000070',:t,'listing_flow','wr1') RETURNING id", {"t": t1})
    ws1 = ins(conn,
              "INSERT INTO app.workflow_steps (tenant_id, run_id, step_type, action_idempotency_key) "
              "VALUES (:t,:r,'gate','awk1') RETURNING id", {"t": t1, "r": wr1})

    mt1 = ins(conn,
              "INSERT INTO app.manual_tasks (tenant_id, task_type, ref_type, ref_id, policy_version_id) "
              "VALUES (:t,'listing_confirm','shop_listing',:r,:p) RETURNING id",
              {"t": t1, "r": l1, "p": pg_t1})
    sd1 = ins(conn,
              "INSERT INTO app.selection_decisions (public_id, tenant_id, product_id, source, compliance_result, "
              "observed_at, selection_batch_key, policy_version_id) VALUES "
              "('00000000-0000-0000-0000-000000000080',:t,:p,'board_snapshot','candidate',now(),'sb1',:pv) "
              "RETURNING id",
              {"t": t1, "p": prod1, "pv": pg_t1})

    # ================= 17 项 正例 + 反例 =================

    # 1. trg_policy_supersede_scope（SUPERSEDE_MISMATCH）
    #    正例：新 v6 接续 pg_t1 的区间（effective_from=+30d，effective_to=+90d，半开区间不重叠避开 exclusion）
    pv_sup = ins(conn,
                 "INSERT INTO app.policy_versions (public_id, tenant_id, policy_type, version, scope_type, "
                 "scope_id, content, content_hash, effective_from, effective_to, approved_by_actor_id, "
                 "supersedes_id) VALUES "
                 "('00000000-0000-0000-0000-000000000103',:t,'cid_breakeven','v6','global',NULL,'{}','h',"
                 "now()+interval '30 days',now()+interval '90 days','00000000-0000-0000-0000-000000000003',:sup) "
                 "RETURNING id",
                 {"t": t1, "sup": pg_t1})
    check("T1 正例 trg_policy_supersede_scope 同 tenant 同 scope 同 type -> 成功", True)
    expect_state("T1 反例 trg_policy_supersede_scope 跨 tenant supersede -> SUPERSEDE_MISMATCH", "INSERT INTO app.policy_versions (public_id, tenant_id, policy_type, version, scope_type, "
                 "scope_id, content, content_hash, effective_from, effective_to, approved_by_actor_id, "
                 "supersedes_id) VALUES "
                 "('00000000-0000-0000-0000-000000000104',:t,'cid_breakeven','v6','global',NULL,'{}','h',"
                 "now()+interval '60 days',NULL,'00000000-0000-0000-0000-000000000003',:sup)",
                 {"t": t2, "sup": pg_t1}, 'SUPERSEDE_MISMATCH', "ZT007")

    # 2. trg_shops_policy_ref（INVALID_POLICY_REF）
    conn.execute(text("UPDATE app.shops SET cid_policy_version_id=:p WHERE id=:i"), {"p": pg_t1, "i": shop1})
    check("T2 正例 trg_shops_policy_ref 同 tenant policy -> 成功", True)
    expect_state("T2 反例 trg_shops_policy_ref 跨 tenant policy -> INVALID_POLICY_REF", "UPDATE app.shops SET cid_policy_version_id=:p WHERE id=:i",
                 {"p": pg_t2, "i": shop1}, 'INVALID_POLICY_REF', "ZT001")

    # 3. trg_cost_policy_ref（INVALID_POLICY_REF）
    conn.execute(text("UPDATE app.cost_snapshots SET policy_version_id=:p WHERE id=:i"), {"p": pg_global, "i": cs1})
    check("T3 正例 trg_cost_policy_ref global policy -> 成功", True)
    expect_state("T3 反例 trg_cost_policy_ref 跨 tenant policy -> INVALID_POLICY_REF", "UPDATE app.cost_snapshots SET policy_version_id=:p WHERE id=:i",
                 {"p": pg_t2, "i": cs1}, 'INVALID_POLICY_REF', "ZT001")

    # 4. trg_selection_policy_ref（INVALID_POLICY_REF）
    conn.execute(text("UPDATE app.selection_decisions SET policy_version_id=:p WHERE id=:i"), {"p": pg_global, "i": sd1})
    check("T4 正例 trg_selection_policy_ref global policy -> 成功", True)
    expect_state("T4 反例 trg_selection_policy_ref 跨 tenant policy -> INVALID_POLICY_REF", "UPDATE app.selection_decisions SET policy_version_id=:p WHERE id=:i",
                 {"p": pg_t2, "i": sd1}, 'INVALID_POLICY_REF', "ZT001")

    # 5. trg_pricing_policy_ref（INVALID_POLICY_REF）
    conn.execute(text("UPDATE app.pricing_decisions SET policy_version_id=:p WHERE id=:i"), {"p": pg_global, "i": pd1})
    check("T5 正例 trg_pricing_policy_ref global policy -> 成功", True)
    expect_state("T5 反例 trg_pricing_policy_ref 跨 tenant policy -> INVALID_POLICY_REF", "UPDATE app.pricing_decisions SET policy_version_id=:p WHERE id=:i",
                 {"p": pg_t2, "i": pd1}, 'INVALID_POLICY_REF', "ZT001")

    # 6. trg_campaigns_policy_ref（INVALID_POLICY_REF）
    conn.execute(text("UPDATE app.ad_campaigns SET budget_policy_version_id=:p WHERE id=:i"), {"p": pg_global, "i": camp1})
    check("T6 正例 trg_campaigns_policy_ref global budget policy -> 成功", True)
    expect_state("T6 反例 trg_campaigns_policy_ref 跨 tenant cid policy -> INVALID_POLICY_REF", "UPDATE app.ad_campaigns SET cid_policy_version_id=:p WHERE id=:i",
                 {"p": pg_t2, "i": camp1}, 'INVALID_POLICY_REF', "ZT001")

    # 7. trg_manual_policy_ref（INVALID_POLICY_REF）
    conn.execute(text("UPDATE app.manual_tasks SET policy_version_id=:p WHERE id=:i"), {"p": pg_global, "i": mt1})
    check("T7 正例 trg_manual_policy_ref global policy -> 成功", True)
    expect_state("T7 反例 trg_manual_policy_ref 跨 tenant policy -> INVALID_POLICY_REF", "UPDATE app.manual_tasks SET policy_version_id=:p WHERE id=:i",
                 {"p": pg_t2, "i": mt1}, 'INVALID_POLICY_REF', "ZT001")

    # 8. trg_offers_sku_product_consistency（SKU_PRODUCT_MISMATCH）
    ins(conn,
        "INSERT INTO app.supplier_offers (tenant_id, supplier_id, product_id, sku_id, supplier_sku_id, offer_id, "
        "price, observed_at, expires_at, source, mode, idempotency_key) VALUES "
        "(:t,:s,:p,:k,'SS2','OF2',10.0,now(),now()+interval '1 day','supplier_catalog','real','ik2') RETURNING id",
        {"t": t1, "s": sup1, "p": prod1, "k": sku1})
    check("T8 正例 trg_offers_sku_product_consistency sku 属于 product -> 成功", True)
    expect_state("T8 反例 trg_offers_sku_product_consistency sku 不属于 product -> SKU_PRODUCT_MISMATCH", "INSERT INTO app.supplier_offers (tenant_id, supplier_id, product_id, sku_id, supplier_sku_id, "
                 "offer_id, price, observed_at, expires_at, source, mode, idempotency_key) VALUES "
                 "(:t,:s,:p,:k,'SS3','OF3',10.0,now(),now()+interval '1 day','supplier_catalog','real','ik3')",
                 {"t": t1, "s": sup1, "p": prod2, "k": sku1}, 'SKU_PRODUCT_MISMATCH', "ZT002")

    # 9. trg_bindings_sku_product_consistency（SKU_PRODUCT_MISMATCH）
    ins(conn,
        "INSERT INTO app.asset_product_bindings (tenant_id, asset_id, product_id, product_sku_id, purpose) "
        "VALUES (:t,:a,:p,:k,'detail_image') RETURNING id",
        {"t": t1, "a": ast1, "p": prod1, "k": sku1})
    check("T9 正例 trg_bindings_sku_product_consistency sku 属于 product -> 成功", True)
    expect_state("T9 反例 trg_bindings_sku_product_consistency sku 不属于 product -> SKU_PRODUCT_MISMATCH", "INSERT INTO app.asset_product_bindings (tenant_id, asset_id, product_id, product_sku_id, purpose) "
                 "VALUES (:t,:a,:p,:k,'detail_image')",
                 {"t": t1, "a": ast1, "p": prod2, "k": sku1}, 'SKU_PRODUCT_MISMATCH', "ZT002")

    # 10. trg_listings_account_shop_consistency（ACCOUNT_SHOP_MISMATCH）
    #     正例需与基线 (shop1,prod1) 不同的组合（px_listings_shop_product 部分唯一）
    prod3 = ins(conn,
                "INSERT INTO app.products (public_id, tenant_id, title_base, category_id) VALUES "
                "('00000000-0000-0000-0000-000000000022',:t,'P3','cat1') RETURNING id", {"t": t1})
    ins(conn,
        "INSERT INTO app.shop_listings (public_id, tenant_id, account_id, shop_id, product_id, title_effective, "
        "idempotency_key) VALUES ('00000000-0000-0000-0000-000000000041',:t,:a,:s,:p,'L2','lk2') RETURNING id",
        {"t": t1, "a": acc1, "s": shop1, "p": prod3})
    check("T10 正例 trg_listings_account_shop_consistency shop 属于 account -> 成功", True)
    expect_state("T10 反例 trg_listings_account_shop_consistency shop 不属于 account -> ACCOUNT_SHOP_MISMATCH", "INSERT INTO app.shop_listings (public_id, tenant_id, account_id, shop_id, product_id, "
                 "title_effective, idempotency_key) VALUES "
                 "('00000000-0000-0000-0000-000000000042',:t,:a,:s,:p,'L3','lk3')",
                 {"t": t1, "a": acc2, "s": shop1, "p": prod1}, 'ACCOUNT_SHOP_MISMATCH', "ZT004")

    # 11. trg_cost_context_consistency（CONTEXT_MISMATCH）
    conn.execute(text("UPDATE app.cost_snapshots SET decision_object_id=:o WHERE id=:i"), {"o": lsku1, "i": cs1})
    check("T11 正例 trg_cost_context_consistency decision_object 有效 -> 成功", True)
    expect_state("T11 反例 trg_cost_context_consistency decision_object 不存在 -> CONTEXT_MISMATCH", "INSERT INTO app.cost_snapshots (public_id, tenant_id, decision_object_type, decision_object_id, "
                 "shop_id, shop_listing_id, offer_id, policy_version_id, k_price, ad_pre_margin, idempotency_key, "
                 "snapshot_at) VALUES "
                 "('00000000-0000-0000-0000-000000000052',:t,'shop_listing_sku',999,:s,:l,:of,:p,10.0,3.0,'c2',now())",
                 {"t": t1, "s": shop1, "l": l1, "of": of1, "p": pg_t1}, 'CONTEXT_MISMATCH', "ZT003")

    # 12. trg_shopbind_context_consistency（CONTEXT_MISMATCH）
    ins(conn,
        "INSERT INTO app.asset_shop_bindings (tenant_id, asset_id, shop_id, asset_product_binding_id, "
        "product_id, purpose) VALUES (:t,:a,:s,:b,:p,'main_image') RETURNING id",
        {"t": t1, "a": ast1, "s": shop1, "b": apb1, "p": prod1})
    check("T12 正例 trg_shopbind_context_consistency binding 的 product/asset 一致 -> 成功", True)
    expect_state("T12 反例 trg_shopbind_context_consistency binding 的 product 不一致 -> CONTEXT_MISMATCH", "INSERT INTO app.asset_shop_bindings (tenant_id, asset_id, shop_id, asset_product_binding_id, "
                 "product_id, purpose) VALUES (:t,:a,:s,:b,:p,'main_image')",
                 {"t": t1, "a": ast1, "s": shop1, "b": apb1, "p": prod2}, 'CONTEXT_MISMATCH', "ZT003")

    # 13. trg_pricing_context_consistency（CONTEXT_MISMATCH）
    conn.execute(text("UPDATE app.pricing_decisions SET daily_price=9.0 WHERE id=:i"), {"i": pd1})
    check("T13 正例 trg_pricing_context_consistency 上下文未变 -> 成功", True)
    expect_state("T13 反例 trg_pricing_context_consistency listing_sku 不属于 listing -> CONTEXT_MISMATCH", "INSERT INTO app.pricing_decisions (public_id, tenant_id, shop_id, shop_listing_id, "
                 "shop_listing_sku_id, cost_snapshot_id, policy_version_id, decision_type, cost_floor_price, "
                 "suggested_price, floor_price, cid_inputs, cid_results, effective_from, idempotency_key) VALUES "
                 "('00000000-0000-0000-0000-000000000053',:t,:s,:l,999,:c,:p,'initial',5,10,4,'{}','{}',now(),'pk2')",
                 {"t": t1, "s": shop1, "l": l1, "c": cs1, "p": pg_t1}, 'CONTEXT_MISMATCH', "ZT003")

    # 14. trg_campaigns_scope_consistency（SCOPE_MISMATCH）
    conn.execute(text("UPDATE app.ad_campaigns SET current_budget=2000 WHERE id=:i"), {"i": camp1})
    check("T14 正例 trg_campaigns_scope_consistency 非 scope 列更新 -> 成功", True)
    expect_state("T14 反例 trg_campaigns_scope_consistency listing 的 shop 不一致 -> SCOPE_MISMATCH", "INSERT INTO app.ad_campaigns (public_id, tenant_id, account_id, shop_id, shop_listing_id, "
                 "idempotency_key, approved_budget, approved_daily_budget, approved_target_roi, approved_stop_loss, "
                 "current_budget, current_daily_budget, current_target_roi, current_stop_loss, feedback_coefficient, "
                 "budget_policy_version_id, cid_policy_version_id) VALUES "
                 "('00000000-0000-0000-0000-000000000061',:t,:a,:s,:l,'ak2',1000,100,2.0,0.5,1000,100,2.0,0.5,1.0,"
                 ":bp,:cp)",
                 {"t": t1, "a": acc1, "s": shop2, "l": l1, "bp": pg_t1, "cp": pg_t1}, 'SCOPE_MISMATCH', "ZT005")

    # 15. trg_campassets_same_scope（SCOPE_MISMATCH）
    #     正例需新 binding（ad_campaign_assets 有 UNIQUE(campaign_id, asset_shop_binding_id)；
    #     asset_shop_bindings NULLS NOT DISTINCT 需不同 purpose 避免与 asb1 冲突）
    asb2 = ins(conn,
               "INSERT INTO app.asset_shop_bindings (tenant_id, asset_id, shop_id, purpose) "
               "VALUES (:t,:a,:s,'main_image') RETURNING id", {"t": t1, "a": ast1, "s": shop1})
    ins(conn,
        "INSERT INTO app.ad_campaign_assets (tenant_id, campaign_id, asset_shop_binding_id) "
        "VALUES (:t,:c,:b) RETURNING id", {"t": t1, "c": camp1, "b": asb2})
    check("T15 正例 trg_campassets_same_scope campaign 与 binding 同 shop -> 成功", True)
    # 构造 shop3 的 binding 再引用 -> campaign(shop1) 与 binding(shop3) 不一致
    shop3 = ins(conn,
                "INSERT INTO app.shops (public_id, tenant_id, account_id, platform_shop_id, name) VALUES "
                "('00000000-0000-0000-0000-000000000012',:t,:a,'shop3','s3') RETURNING id",
                {"t": t1, "a": acc1})
    asb3 = ins(conn,
               "INSERT INTO app.asset_shop_bindings (tenant_id, asset_id, shop_id, purpose) "
               "VALUES (:t,:a,:s,'ad_image') RETURNING id", {"t": t1, "a": ast1, "s": shop3})
    expect_state("T15 反例 trg_campassets_same_scope binding 属另一 shop -> SCOPE_MISMATCH", "INSERT INTO app.ad_campaign_assets (tenant_id, campaign_id, asset_shop_binding_id) "
                 "VALUES (:t,:c,:b)",
                 {"t": t1, "c": camp1, "b": asb3}, 'SCOPE_MISMATCH', "ZT005")

    # 16. trg_snapshots_dimension_consistency（DIMENSION_MISMATCH）
    ins(conn,
        "INSERT INTO app.ad_report_snapshots (tenant_id, account_id, shop_id, shop_listing_id, "
        "shop_listing_sku_id, product_id, campaign_id, asset_binding_id, granularity, window_start, window_end, "
        "attribution_mode, report_version_key, captured_at, raw_evidence_hash) VALUES "
        "(:t,:a,:s,:l,:ls,:p,:c,:b,'campaign','2026-02-01','2026-02-02','last_click','rv2',now(),repeat('y',64)) "
        "RETURNING id",
        {"t": t1, "a": acc1, "s": shop1, "l": l1, "ls": lsku1, "p": prod1, "c": camp1, "b": asb1})
    check("T16 正例 trg_snapshots_dimension_consistency 维度同源 -> 成功", True)
    expect_state("T16 反例 trg_snapshots_dimension_consistency listing 的 shop 不一致 -> DIMENSION_MISMATCH", "INSERT INTO app.ad_report_snapshots (tenant_id, account_id, shop_id, shop_listing_id, "
                 "shop_listing_sku_id, product_id, campaign_id, asset_binding_id, granularity, window_start, "
                 "window_end, attribution_mode, report_version_key, captured_at, raw_evidence_hash) VALUES "
                 "(:t,:a,:s,:l,:ls,:p,:c,:b,'campaign','2026-02-01','2026-02-02','last_click','rv3',now(),"
                 "repeat('z',64))",
                 {"t": t1, "a": acc1, "s": shop2, "l": l1, "ls": lsku1, "p": prod1, "c": camp1, "b": asb1}, 'DIMENSION_MISMATCH', "ZT006")

    # 17. trg_feedback_dimension_consistency（DIMENSION_MISMATCH）
    ins(conn,
        "INSERT INTO app.roi_feedback_events (tenant_id, account_id, shop_id, shop_listing_id, "
        "shop_listing_sku_id, product_id, campaign_id, asset_binding_id, source_snapshot_id, window_start, "
        "window_end, attribution_mode, feedback_type, subject_type, subject_key, value, aggregation_version, "
        "idempotency_key) VALUES "
        "(:t,:a,:s,:l,:ls,:p,:c,:b,:sn,'2026-01-01','2026-01-02','last_click','category_score','category','CAT',"
        "1.0,'av2','rf2') RETURNING id",
        {"t": t1, "a": acc1, "s": shop1, "l": l1, "ls": lsku1, "p": prod1, "c": camp1, "b": asb1, "sn": snap1})
    check("T17 正例 trg_feedback_dimension_consistency 冗余维度与 source_snapshot 一致 -> 成功", True)
    expect_state("T17 反例 trg_feedback_dimension_consistency shop 与 source_snapshot 不一致 -> DIMENSION_MISMATCH", "INSERT INTO app.roi_feedback_events (tenant_id, account_id, shop_id, shop_listing_id, "
                 "shop_listing_sku_id, product_id, campaign_id, asset_binding_id, source_snapshot_id, window_start, "
                 "window_end, attribution_mode, feedback_type, subject_type, subject_key, value, aggregation_version, "
                 "idempotency_key) VALUES "
                 "(:t,:a,:s,:l,:ls,:p,:c,:b,:sn,'2026-01-01','2026-01-02','last_click','product_score','product','PK',"
                 "1.0,'av3','rf3')",
                 {"t": t1, "a": acc1, "s": shop2, "l": l1, "ls": lsku1, "p": prod1, "c": camp1, "b": asb1, "sn": snap1}, 'DIMENSION_MISMATCH', "ZT006")


    # ================= R60-2 新增：同源关系错配反例（对象存在/同 tenant 但关系错误）=================

    # R60-2a trg_cost_context_consistency：decision_object=product1 + listing(product2) + offer(product1)
    #        对象均存在且同 tenant，但 listing 与对象 product 不同源 -> CONTEXT_MISMATCH
    l_mismatch = ins(conn,
                     "INSERT INTO app.shop_listings (public_id, tenant_id, account_id, shop_id, product_id, "
                     "title_effective, idempotency_key) VALUES "
                     "('00000000-0000-0000-0000-000000000043',:t,:a,:s,:p,'Lmis','lk_mis') RETURNING id",
                     {"t": t1, "a": acc1, "s": shop1, "p": prod2})
    expect_state("R60-2a 反例 trg_cost_context_consistency object=product1 + listing(product2) -> CONTEXT_MISMATCH",
                 "INSERT INTO app.cost_snapshots (public_id, tenant_id, decision_object_type, decision_object_id, "
                 "shop_id, shop_listing_id, offer_id, policy_version_id, k_price, ad_pre_margin, idempotency_key, "
                 "snapshot_at) VALUES "
                 "('00000000-0000-0000-0000-000000000054',:t,'product',:o,:s,:l,:of,:p,10.0,3.0,'c_r60_2a',now())",
                 {"t": t1, "o": prod1, "s": shop1, "l": l_mismatch, "of": of1, "p": pg_t1},
                 'CONTEXT_MISMATCH', "ZT003")

    # R60-2b trg_shopbind_context_consistency：binding(product1) + listing(product2) 同 shop
    #        binding 与 listing 的 product 不同源 -> CONTEXT_MISMATCH
    expect_state("R60-2b 反例 trg_shopbind_context_consistency binding(product1)+listing(product2) -> CONTEXT_MISMATCH",
                 "INSERT INTO app.asset_shop_bindings (tenant_id, asset_id, shop_id, asset_product_binding_id, "
                 "product_id, shop_listing_id, purpose) VALUES "
                 "(:t,:a,:s,:b,:p,:l,'main_image')",
                 {"t": t1, "a": ast1, "s": shop1, "b": apb1, "p": prod1, "l": l_mismatch},
                 'CONTEXT_MISMATCH', "ZT003")

    # R60-2c trg_policy_supersede_scope：事件列含 policy_type/scope_type/scope_id（R60-2 勘误），
    #        更新已建 supersede 的 policy_type 应触发 SUPERSEDE_MISMATCH（旧实现可绕过）
    expect_state("R60-2c 反例 trg_policy_supersede_scope 更新 policy_type 绕过 -> SUPERSEDE_MISMATCH",
                 "UPDATE app.policy_versions SET policy_type='pricing' WHERE id=:i",
                 {"i": pv_sup}, 'SUPERSEDE_MISMATCH', "ZT007")

    # R60-2d trg_snapshots_dimension_consistency：asset_binding(product2) 与 snapshot(product1) 不同源
    #        先建 product=prod2 的 binding（无 listing，避免 shopbind 拦截），再以 product=prod1 建 snapshot
    asb_r60 = ins(conn,
                  "INSERT INTO app.asset_shop_bindings (tenant_id, asset_id, shop_id, product_id, purpose) "
                  "VALUES (:t,:a,:s,:p,'ad_image') RETURNING id",
                  {"t": t1, "a": ast1, "s": shop1, "p": prod2})
    expect_state("R60-2d 反例 trg_snapshots_dimension_consistency asset_binding product 不一致 -> DIMENSION_MISMATCH",
                 "INSERT INTO app.ad_report_snapshots (tenant_id, account_id, shop_id, shop_listing_id, "
                 "shop_listing_sku_id, product_id, campaign_id, asset_binding_id, granularity, window_start, "
                 "window_end, attribution_mode, report_version_key, captured_at, raw_evidence_hash) VALUES "
                 "(:t,:a,:s,:l,:ls,:p,:c,:b,'campaign','2026-03-01','2026-03-02','last_click','rv_r60',now(),"
                 "repeat('q',64))",
                 {"t": t1, "a": acc1, "s": shop1, "l": l1, "ls": lsku1, "p": prod1, "c": camp1, "b": asb_r60},
                 'DIMENSION_MISMATCH', "ZT006")

    # ================= R62-1：cost_context shop↔listing 同源（同 tenant 同 product 不同 shop）=================
    # 构造属于 shop3 的 listing（product=prod1），再以 shop_id=shop1 建 cost_snapshot -> 应 CONTEXT_MISMATCH
    l_shop3 = ins(conn,
                  "INSERT INTO app.shop_listings (public_id, tenant_id, account_id, shop_id, product_id, "
                  "title_effective, idempotency_key) VALUES "
                  "('00000000-0000-0000-0000-000000000044',:t,:a,:s,:p,'Lshop3','lk_s3') RETURNING id",
                  {"t": t1, "a": acc1, "s": shop3, "p": prod1})
    expect_state("R62-1 反例 trg_cost_context_consistency listing(shop3) + shop_id=shop1 -> CONTEXT_MISMATCH",
                 "INSERT INTO app.cost_snapshots (public_id, tenant_id, decision_object_type, decision_object_id, "
                 "shop_id, shop_listing_id, offer_id, policy_version_id, k_price, ad_pre_margin, idempotency_key, "
                 "snapshot_at) VALUES "
                 "('00000000-0000-0000-0000-000000000055',:t,'product',:o,:s,:l,:of,:p,10.0,3.0,'c_r62_1',now())",
                 {"t": t1, "o": prod1, "s": shop1, "l": l_shop3, "of": of1, "p": pg_t1},
                 'CONTEXT_MISMATCH', "ZT003")

    # ================= R62-2：supersede 父侧更新破坏子链（入边校验）=================
    # 建 parent -> child 链（同 tenant 同 scope：scope_type=shop/scope_id=S1；version 错开避开
    # uq_policy_versions_nullsdistinct；区间错开 [+90d,+120d)/[+120d,inf) 避开 exclusion）
    pv_parent = ins(conn,
                    "INSERT INTO app.policy_versions (public_id, tenant_id, policy_type, version, scope_type, "
                    "scope_id, content, content_hash, effective_from, effective_to, approved_by_actor_id) VALUES "
                    "('00000000-0000-0000-0000-000000000105',:t,'cid_breakeven','v1','shop','S1','{}','h',"
                    "now()+interval '90 days',now()+interval '120 days','00000000-0000-0000-0000-000000000003') "
                    "RETURNING id",
                    {"t": t1})
    pv_child = ins(conn,
                   "INSERT INTO app.policy_versions (public_id, tenant_id, policy_type, version, scope_type, "
                   "scope_id, content, content_hash, effective_from, effective_to, approved_by_actor_id, "
                   "supersedes_id) VALUES "
                   "('00000000-0000-0000-0000-000000000106',:t,'cid_breakeven','v2','shop','S1','{}','h',"
                   "now()+interval '120 days',NULL,'00000000-0000-0000-0000-000000000003',:sup) RETURNING id",
                   {"t": t1, "sup": pv_parent})
    expect_state("R62-2 反例 trg_policy_supersede_scope 父 policy_type 更新破坏子链 -> SUPERSEDE_MISMATCH",
                 "UPDATE app.policy_versions SET policy_type='pricing' WHERE id=:i",
                 {"i": pv_parent}, 'SUPERSEDE_MISMATCH', "ZT007")
    # 子链正常时父更新同 type 字段不破坏（如 version）应成功（入边仅校验 tenant/type/scope）
    conn.execute(text("UPDATE app.policy_versions SET version='v7' WHERE id=:i"), {"i": pv_parent})
    check("R62-2 正例 supersede 父 version 更新不破坏子链 -> 成功", True)

except Exception as exc:  # noqa: BLE001
    check("探针执行异常", False, f"{type(exc).__name__}: {exc}")
finally:
    if tx.is_active:
        tx.rollback()
    conn.close()
    eng.dispose()

print("T4-TRIGGER-PROBES:", "PASS" if ok else "FAIL")
sys.exit(0 if ok else 1)