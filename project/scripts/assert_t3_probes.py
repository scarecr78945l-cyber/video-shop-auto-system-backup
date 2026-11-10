# -*- coding: utf-8 -*-
"""T3: 约束行为正反例探针（round-55 R54-3b 回修版；外层事务结束 ROLLBACK，不留数据）。

用 SAVEPOINT（begin_nested）隔离每个负例；所有 id 用 RETURNING 捕获（identity 序列不回滚）。
round-55 修正/新增（Codex round-54 R54-3 §5.3）：
  - P2 改为**真实组合 FK 正例**：asset_product_bindings(tenant_id, asset_id)->assets(tenant_id,id)
  - 新增 FK action 行为探针：
      P6  CASCADE 正例：删除 platform_accounts 行 -> account_runtime_profiles 级联删除
      N4  RESTRICT 负例：删除有 supplier_offers 的 suppliers 行 -> 违反
  - 新增 P7 public_id 默认正例：省略 public_id 插入 -> 自动 gen_random_uuid()
探针清单：
  P1  基础 FK 正向（shops.tenant_id 有效）
  N1  基础 FK 负向（shops.tenant_id=999）
  P2  组合 FK 正向（asset_product_bindings (tenant_id,asset_id) 匹配）
  N2  组合 FK 负向（shops (tenant_id=t2, account_id=a1) 组合不匹配）
  P3  NULLS NOT DISTINCT 负向（两行 sku=NULL 同键）
  P4  部分唯一（软删同名+新建成功；未删同名违反）
  P5  exclusion（同 SKU approved 区间重叠违反；不重叠成功）
  P6  CASCADE 正例（删 platform_accounts -> profiles 级联删）
  N4  RESTRICT 负例（删有 offers 的 suppliers -> 违反）
  P7  public_id 默认（省略 public_id 插入成功）
  N3  CHECK 负向（roi_feedback feedback_type/subject 不匹配）
用法：python scripts/assert_t3_probes.py（需 DATABASE_URL；事务回滚无残留）
"""
import os
import sys

from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError

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


def expect_violation(conn, label, sql, params=None):
    try:
        with conn.begin_nested():
            conn.execute(text(sql), params or {})
    except IntegrityError:
        check(label, True)
        return
    check(label, False, "未报错")


def ins(conn, sql, params):
    return conn.execute(text(sql), params).scalar()


eng = create_engine(URL, isolation_level="SERIALIZABLE")
conn = eng.connect()
tx = conn.begin()

try:
    # ============ 基线（id 全部 RETURNING 捕获）============
    tid1 = ins(conn,
               "INSERT INTO app.tenants (public_id, name, scope) VALUES "
               "('00000000-0000-0000-0000-000000000001','t1','internal') RETURNING id", {})
    tid2 = ins(conn,
               "INSERT INTO app.tenants (public_id, name, scope) VALUES "
               "('00000000-0000-0000-0000-000000000004','t2','internal') RETURNING id", {})
    aid1 = ins(conn,
               "INSERT INTO app.platform_accounts (public_id, tenant_id, platform, account_key) VALUES "
               "('00000000-0000-0000-0000-000000000002',:t,'wechat_channels','acc1') RETURNING id",
               {"t": tid1})
    conn.execute(text(
        "INSERT INTO app.actor_registry (actor_id, actor_kind, name) VALUES "
        "('00000000-0000-0000-0000-000000000003','system','seed')"))
    # R118-2：head 策略引用触发器需 policy_versions fixture（探针后段硬编码 policy_version_id=1，
    # 空库首次插入 id=1）；复用 assert_triggers_probes 的 mkpolicy 本地做法（不依赖 seed）
    pol1 = ins(conn,
               "INSERT INTO app.policy_versions (public_id, tenant_id, policy_type, version, scope_type, "
               "scope_id, content, content_hash, effective_from, effective_to, approved_by_actor_id) VALUES "
               "('00000000-0000-0000-0000-000000000030',:t,'cid_breakeven','v5','global',NULL,'{}','h',now(),NULL,"
               "'00000000-0000-0000-0000-000000000003') RETURNING id", {"t": tid1})
    # R118-2：探针后段引用动态捕获的 pol1（不硬编码 id=1——共享库 policy_versions 可能非空）
    pid1 = ins(conn,
               "INSERT INTO app.products (public_id, tenant_id, title_base, category_id) VALUES "
               "('00000000-0000-0000-0000-000000000020',:t,'P1','cat1') RETURNING id", {"t": tid1})

    # ============ P1 基础 FK 正向 ============
    sid1 = ins(conn,
               "INSERT INTO app.shops (public_id, tenant_id, account_id, platform_shop_id, name) VALUES "
               "('00000000-0000-0000-0000-000000000010',:t,:a,'shop1','s1') RETURNING id",
               {"t": tid1, "a": aid1})
    check("P1 基础 FK shops.tenant_id 有效 -> 成功", True)

    # ============ N1 基础 FK 负向 ============
    expect_violation(conn, "N1 基础 FK shops.tenant_id=999 -> 违反",
                     "INSERT INTO app.shops (public_id, tenant_id, account_id, platform_shop_id, name) VALUES "
                     "('00000000-0000-0000-0000-000000000011',999,:a,'shop2','s2')",
                     {"a": aid1})

    # ============ P2 组合 FK 正向（真实双列组合 FK）============
    ast1 = ins(conn,
               "INSERT INTO app.assets (public_id, tenant_id, content_sha256, file_ref, mime_type, size_bytes, "
               "source_type, evidence_hash, captured_at, mode) VALUES "
               "('00000000-0000-0000-0000-000000000021',:t,repeat('a',64),'f1','image/png',100,"
               "'self_created',repeat('b',64),now(),'real') RETURNING id", {"t": tid1})
    ins(conn,
        "INSERT INTO app.asset_product_bindings (tenant_id, asset_id, product_id, product_sku_id, purpose) VALUES "
        "(:t,:a,:p,NULL,'main_image') RETURNING id",
        {"t": tid1, "a": ast1, "p": pid1})
    check("P2 组合 FK 正向 asset_product_bindings(tenant_id,asset_id) -> 成功", True)

    # ============ N2 组合 FK 负向（tenant 存在但账号属其他 tenant）============
    expect_violation(conn, "N2 组合 FK shops(tenant_id=t2, account_id=a1) -> 违反",
                     "INSERT INTO app.shops (public_id, tenant_id, account_id, platform_shop_id, name) VALUES "
                     "('00000000-0000-0000-0000-000000000013',:t,:a,'shop3','s3')",
                     {"t": tid2, "a": aid1})

    # ============ P3 NULLS NOT DISTINCT 负向 ============
    # P2 已插入第一行 (asset,product,sku=NULL,purpose='main_image')；再插同键行应违反
    expect_violation(conn, "P3 NULLS NOT DISTINCT 两行 sku=NULL 相同键 -> 违反",
                     "INSERT INTO app.asset_product_bindings (tenant_id, asset_id, product_id, product_sku_id, purpose) "
                     "VALUES (:t,:a,:p,NULL,'main_image')",
                     {"t": tid1, "a": ast1, "p": pid1})

    # ============ P4 部分唯一 ============
    ins(conn,
        "INSERT INTO app.tenants (public_id, name, scope, deleted_at) VALUES "
        "('00000000-0000-0000-0000-000000000030','dup','internal',now()) RETURNING id", {})
    ins(conn,
        "INSERT INTO app.tenants (public_id, name, scope) VALUES "
        "('00000000-0000-0000-0000-000000000031','dup','internal') RETURNING id", {})
    check("P4 部分唯一 软删+新建同名 -> 成功", True)
    expect_violation(conn, "P4 部分唯一 未删同名 -> 违反",
                     "INSERT INTO app.tenants (public_id, name, scope) VALUES "
                     "('00000000-0000-0000-0000-000000000032','dup','internal')")

    # ============ P6 CASCADE 正例（R54-2 行为验证）============
    # 独立账号做级联测试：不建 shops（shops->platform_accounts 为 NO ACTION 会阻断删除）
    aid_del = ins(conn,
                  "INSERT INTO app.platform_accounts (public_id, tenant_id, platform, account_key) VALUES "
                  "('00000000-0000-0000-0000-000000000090',:t,'douyin','acc-del') RETURNING id",
                  {"t": tid1})
    prof1 = ins(conn,
                "INSERT INTO app.account_runtime_profiles (tenant_id, account_id, purpose) "
                "VALUES (:t,:a,'default') RETURNING id", {"t": tid1, "a": aid_del})
    conn.execute(text("DELETE FROM app.platform_accounts WHERE id=:a"), {"a": aid_del})
    gone = conn.execute(text(
        "SELECT count(*) FROM app.account_runtime_profiles WHERE id=:p"), {"p": prof1}).scalar()
    check("P6 CASCADE 删 platform_accounts -> profile 级联删除", gone == 0, f"remaining={gone}")

    # ============ N4 RESTRICT 负例（R54-2 行为验证）============
    sup1 = ins(conn,
               "INSERT INTO app.suppliers (public_id, tenant_id, supplier_code, name, source_platform, source, mode) "
               "VALUES ('00000000-0000-0000-0000-000000000012',:t,'SUP1','sup','self','manual','real') RETURNING id",
               {"t": tid1})
    offer1 = ins(conn,
                 "INSERT INTO app.supplier_offers (tenant_id, supplier_id, supplier_sku_id, offer_id, price, "
                 "observed_at, expires_at, source, mode, idempotency_key) VALUES "
                 "(:t,:s,'SS1','OF1',10.0,now(),now()+interval '1 day','supplier_catalog','real','ik1') RETURNING id",
                 {"t": tid1, "s": sup1})
    expect_violation(conn, "N4 RESTRICT 删有 offers 的 suppliers -> 违反",
                     "DELETE FROM app.suppliers WHERE id=:s", {"s": sup1})
    # 删除 offer 后可删 supplier（验证 RESTRICT 确实由 offer 触发）
    conn.execute(text("DELETE FROM app.supplier_offers WHERE id=:o"), {"o": offer1})
    conn.execute(text("DELETE FROM app.suppliers WHERE id=:s"), {"s": sup1})
    check("N4 RESTRICT 删 offer 后 supplier 可删", True)

    # ============ P7 public_id 默认正例（R54-1 §3.3 行为验证）============
    new_id = ins(conn,
                 "INSERT INTO app.tenants (name, scope) VALUES ('p7t','internal') RETURNING id", {})
    pid_val = conn.execute(text(
        "SELECT public_id FROM app.tenants WHERE id=:i"), {"i": new_id}).scalar()
    check("P7 public_id 默认 gen_random_uuid()（省略插入）", pid_val is not None and pid_val !=
          "00000000-0000-0000-0000-000000000001", f"public_id={pid_val}")

    # ============ P5 exclusion ============
    sku1 = ins(conn,
               "INSERT INTO app.product_skus (tenant_id, product_id, attributes) "
               "VALUES (:t,:p,'{}') RETURNING id", {"t": tid1, "p": pid1})
    l1 = ins(conn,
             "INSERT INTO app.shop_listings (public_id, tenant_id, account_id, shop_id, product_id, "
             "title_effective, idempotency_key) VALUES "
             "('00000000-0000-0000-0000-000000000040',:t,:a,:s,:p,'L1','lk1') RETURNING id",
             {"t": tid1, "a": aid1, "s": sid1, "p": pid1})
    lsku1 = ins(conn,
                "INSERT INTO app.shop_listing_skus (tenant_id, shop_listing_id, sku_id, shop_price) "
                "VALUES (:t,:l,:sk,100) RETURNING id", {"t": tid1, "l": l1, "sk": sku1})
    cs1 = ins(conn,
              "INSERT INTO app.cost_snapshots (public_id, tenant_id, decision_object_type, decision_object_id, "
              "policy_version_id, k_price, ad_pre_margin, idempotency_key, snapshot_at) VALUES "
              "('00000000-0000-0000-0000-000000000041',:t,'shop_listing_sku',:o,:pv,10.0,3.0,'c1',now()) RETURNING id",
              {"t": tid1, "o": lsku1, "pv": pol1})
    ins(conn,
        "INSERT INTO app.pricing_decisions (public_id, tenant_id, shop_id, shop_listing_id, shop_listing_sku_id, "
        "cost_snapshot_id, policy_version_id, decision_type, cost_floor_price, suggested_price, floor_price, "
        "cid_inputs, cid_results, status, effective_from, effective_to, idempotency_key) VALUES "
        "('00000000-0000-0000-0000-000000000050',:t,:s,:l,:ls,:c,:pv,'initial',5,10,4,'{}','{}','approved',"
        "'2026-01-01','2026-02-01','pk1') RETURNING id",
        {"t": tid1, "s": sid1, "l": l1, "ls": lsku1, "c": cs1, "pv": pol1})
    expect_violation(conn, "P5 exclusion 同 SKU 区间重叠 approved -> 违反",
                     "INSERT INTO app.pricing_decisions (public_id, tenant_id, shop_id, shop_listing_id, "
                     "shop_listing_sku_id, cost_snapshot_id, policy_version_id, decision_type, cost_floor_price, "
                     "suggested_price, floor_price, cid_inputs, cid_results, status, effective_from, effective_to, "
                     "idempotency_key) VALUES "
                     "('00000000-0000-0000-0000-000000000051',:t,:s,:l,:ls,:c,:pv,'initial',5,10,4,'{}','{}','approved',"
                     "'2026-01-15','2026-03-01','pk2')",
                     {"t": tid1, "s": sid1, "l": l1, "ls": lsku1, "c": cs1, "pv": pol1})
    ins(conn,
        "INSERT INTO app.pricing_decisions (public_id, tenant_id, shop_id, shop_listing_id, shop_listing_sku_id, "
        "cost_snapshot_id, policy_version_id, decision_type, cost_floor_price, suggested_price, floor_price, "
        "cid_inputs, cid_results, status, effective_from, effective_to, idempotency_key) VALUES "
        "('00000000-0000-0000-0000-000000000052',:t,:s,:l,:ls,:c,:pv,'initial',5,10,4,'{}','{}','approved',"
        "'2026-03-01','2026-04-01','pk3') RETURNING id",
        {"t": tid1, "s": sid1, "l": l1, "ls": lsku1, "c": cs1, "pv": pol1})
    check("P5 exclusion 同 SKU 区间不重叠 -> 成功", True)

    # ============ N3 CHECK 负向 ============
    camp1 = ins(conn,
                "INSERT INTO app.ad_campaigns (public_id, tenant_id, account_id, shop_id, shop_listing_id, "
                "idempotency_key, approved_budget, approved_daily_budget, approved_target_roi, approved_stop_loss, "
                "current_budget, current_daily_budget, current_target_roi, current_stop_loss, "
                "feedback_coefficient, budget_policy_version_id, cid_policy_version_id) VALUES "
                "('00000000-0000-0000-0000-000000000060',:t,:a,:s,:l,'ak1',1000,100,2.0,0.5,1000,100,2.0,0.5,1.0,:pv,:pv) "
                "RETURNING id",
                {"t": tid1, "a": aid1, "s": sid1, "l": l1, "pv": pol1})
    snap1 = ins(conn,
                "INSERT INTO app.ad_report_snapshots (tenant_id, account_id, shop_id, shop_listing_id, product_id, "
                "campaign_id, granularity, window_start, window_end, attribution_mode, report_version_key, "
                "captured_at, raw_evidence_hash) VALUES "
                "(:t,:a,:s,:l,:p,:c,'campaign','2026-01-01','2026-01-02','last_click','rv1',now(),repeat('x',64)) "
                "RETURNING id",
                {"t": tid1, "a": aid1, "s": sid1, "l": l1, "p": pid1, "c": camp1})
    expect_violation(conn, "N3 CHECK feedback product_score/subject=shop -> 违反",
                     "INSERT INTO app.roi_feedback_events (tenant_id, account_id, shop_id, shop_listing_id, "
                     "product_id, campaign_id, source_snapshot_id, window_start, window_end, attribution_mode, "
                     "feedback_type, subject_type, subject_key, value, aggregation_version, idempotency_key) VALUES "
                     "(:t,:a,:s,:l,:p,:c,:sn,'2026-01-01','2026-01-02','last_click','product_score','shop','SK',1.0,"
                     "'av1','rf1')",
                     {"t": tid1, "a": aid1, "s": sid1, "l": l1, "p": pid1, "c": camp1, "sn": snap1})

except Exception as exc:  # noqa: BLE001
    check("探针执行异常", False, f"{type(exc).__name__}: {exc}")
finally:
    if tx.is_active:
        tx.rollback()
    conn.close()
    eng.dispose()

print("T3-PROBES:", "PASS" if ok else "FAIL")
sys.exit(0 if ok else 1)