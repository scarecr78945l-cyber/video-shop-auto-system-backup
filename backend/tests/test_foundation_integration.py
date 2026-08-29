"""A7 跨模块集成冒烟（M0 基座骨架 · mock/fixtures 模式）。

闭环（M1 → M0 → M4 → M5 → 回写 M1）：
  M1 商品池（sourcing.products，fixtures 造数）
  → M0 队列（workflow_jobs 入队/claim/complete 编排，listing_upload stage）
  → M4 上架（ListingPipeline：gate + WechatOpenApiAdapter(mock) → listed + R22 链接证据）
  → M5 候选池（CandidatePool.get_sale_candidates 只读读出销售中商品）
  → M0 风控（RiskEngine 预算三重/余额）+ 脱敏（security，P-004）
  → M5 回写（feedback C-2 JSON 聚合/写出）
  → M1 导入（ad_backfill.load_exchange/apply_exchange → m1 cache 落库）

零真实平台/浏览器（mock/fixtures）；全部临时库（不碰真实 .db，一模块一库语义）。
运行：python -m pytest tests/test_foundation_integration.py -q --basetemp=".pytest-tmp-m0"
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

# ---- M0 基座
from foundation.config import FoundationConfig
from foundation.db import Database
from foundation.repo import WorkflowQueue
from foundation.risk import RiskEngine, check_budget_triple, kill_switch_enabled
from foundation.scheduler import LoggingWorker, WorkflowScheduler
from foundation.security import redact_text

# ---- M1 选品
from sourcing.db import Database as SourcingDatabase
from sourcing.tables import M1AdConversionCache, Product

# ---- M4 上架
from adapters.wechat_openapi import WechatOpenApiAdapter, WechatOpenApiConfig
from listing.candidate_pool import CandidatePool
from listing.pipeline import ListingPipeline
from listing.platform_rejection import RejectionHandler
from services.listing_gate import (
    ListingCandidate,
    ListingGate,
    PurchaseSettings,
    SkuInput,
)

# ---- M5 投放
from ads import feedback as m5_feedback
from sourcing import ad_backfill as m1_backfill

TITLE_OK = "纯棉加厚家用擦手巾厨房清洁抹布吸水速干"  # 19 字符无违禁词


def _make_images(tmp_path: Path, n: int = 5, prefix: str = "main") -> list[str]:
    """生成 n 张互不相同的 1:1 PNG（R21 去重 + 宽高比通过）。"""
    from PIL import Image

    paths = []
    for i in range(n):
        p = tmp_path / f"{prefix}_{i}.png"
        Image.new("RGB", (100, 100), (10 + i * 40, 20 + i * 30, 30 + i * 20)).save(p)
        paths.append(str(p))
    return paths


def _make_candidate(tmp_path: Path, product_id: int, category_name: str = "收纳整理") -> ListingCandidate:
    return ListingCandidate(
        product_id=product_id,
        title=TITLE_OK,
        category_id=2001,
        category_name=category_name,
        qualification={"qualification_id": "QL-001", "expires_at": "2026-12-31"},
        main_images=_make_images(tmp_path),
        detail_images=_make_images(tmp_path, n=1, prefix="detail"),
        skus=[SkuInput(code="SKU-001", cost_cents=1500, price_cents=2990)],
        purchase_settings=PurchaseSettings(
            purchase_limit={"per_user": 2, "period": "month"},
            freight_template_id="1",
            after_sale="支持7天无理由退换货",
        ),
    )


# ---------------------------------------------------------------- fixtures


@pytest.fixture()
def fdb() -> Database:
    """M0 基座内存库（五表 + 错误码种子）。"""
    cfg = FoundationConfig(db_url="sqlite:///:memory:", lease_minutes=45, data_dir=Path("."))
    database = Database(cfg)
    database.create_all()
    database.seed()
    return database


@pytest.fixture()
def queue(fdb: Database) -> WorkflowQueue:
    return WorkflowQueue(fdb)


@pytest.fixture()
def sdb() -> SourcingDatabase:
    """M1 选品内存库（products/m1_ad_conversion_cache 表）。"""
    from sourcing.config import SourcingConfig

    cfg = SourcingConfig(db_url="sqlite:///:memory:", data_dir=Path("."))
    database = SourcingDatabase(cfg)
    database.create_all()
    return database


@pytest.fixture()
def m1_products(sdb: SourcingDatabase) -> list[int]:
    """M1 商品池 fixtures 造数：2 个白名单类目商品（state=pool）。"""
    with sdb.session() as session:
        p1 = Product(
            fingerprint="a" * 64, title=TITLE_OK, category="收纳整理",
            platform_price=1990, state="pool", compliance_state="candidate",
        )
        p2 = Product(
            fingerprint="b" * 64, title="宠物梳毛器", category="宠物用品",
            platform_price=2990, state="pool", compliance_state="candidate",
        )
        session.add_all([p1, p2])
        session.flush()
        ids = [p1.id, p2.id]
    return ids


@pytest.fixture()
def gate() -> ListingGate:
    return ListingGate()


@pytest.fixture()
def adapter() -> WechatOpenApiAdapter:
    return WechatOpenApiAdapter(WechatOpenApiConfig(mode="mock"))


@pytest.fixture()
def pipeline(repo_listing, machine_listing, gate, adapter) -> ListingPipeline:
    rejection = RejectionHandler(repo_listing, machine_listing, gate=gate)
    return ListingPipeline(
        gate=gate,
        adapter=adapter,
        repo=repo_listing,
        state_machine=machine_listing,
        rejection=rejection,
    )


# ---------------------------------------------------------------- 闭环冒烟


def test_a7_full_loop_m1_m0_m4_m5_backfill(
    tmp_path, fdb, queue, sdb, m1_products, pipeline, repo_listing
) -> None:
    """完整闭环：M1 商品池 → M0 队列 → M4 上架（listed+R22）→ M5 候选池 → 回写 M1。"""
    product_id = m1_products[0]

    # ---- ① M0 队列编排：listing_upload job 入队 → 调度器领取 → worker 执行 → complete
    job = queue.enqueue(product_id=product_id, stage="listing_upload", payload={"title": TITLE_OK})
    sched = WorkflowScheduler(queue, LoggingWorker(), worker_id="a7-smoke")
    stats = sched.run_once()
    assert stats["claimed"] == 1 and stats["succeeded"] == 1
    assert queue.get(job.id).status == "success"

    # ---- ② M4 上架：gate + mock adapter 全链 → listed（R22 链接证据）
    result = pipeline.submit(_make_candidate(tmp_path, product_id=product_id, category_name="收纳整理"))
    assert result["ok"] is True, result
    assert result["stage"] == "listed", result
    assert result.get("product_link"), "R22：listed 必须带真实链接证据"
    assert result["evidence"]["link_verified_at"], "R22：链接验证时间证据"

    # ---- ③ M5 候选池：只读读出销售中商品（DA-009 已修复：M4 SPU/SKU 幂等落库 → 断言收紧）
    pool = CandidatePool(repo_listing)
    candidates = pool.get_sale_candidates()
    assert len(candidates) == 1
    cand = candidates[0]
    assert cand["product_id"] == product_id
    assert cand["product_link"]
    assert cand["title"] == TITLE_OK            # 关联 listing_spus（DA-009 修复后非 None）
    assert cand["category_id"] == 2001          # 类目 ID 正确
    assert cand["price_min_cents"] == 2990 and cand["price_max_cents"] == 2990  # 金额分 int（DA-001）

    # ---- ④ M0 风控：预算三重/余额充足 → 不 halt；全停开启 → halt_all
    engine = RiskEngine()
    budget_ok = check_budget_triple(3000, 5000, 9000, 5000, 10000, 20000)
    assert not budget_ok.over_limit
    risk_ok = engine.evaluate(campaign=cand, snapshots=[], account_balance_fen=999999, budget=budget_ok)
    assert risk_ok.halt_all is False
    assert kill_switch_enabled(False, "off") is False
    risk_stop = engine.evaluate(campaign=cand, snapshots=[], account_balance_fen=999999, kill_switch=True)
    assert risk_stop.halt_all is True

    # ---- ⑤ M0 脱敏：含 token 的链接/证据脱敏后无明文（P-004）
    redacted = redact_text(f"上传成功 {cand['product_link']}?token=SECRETTOK123 附证据")
    assert "SECRETTOK123" not in redacted
    assert "***" in redacted

    # ---- ⑥ M5 回写：类目聚合（C-2）→ 交换 JSON → M1 导入
    agg = m5_feedback.aggregate_by_category(
        [{"product_id": product_id, "gmv_fen": 900000, "spend_fen": 300000, "sample_count": 9}],
        {product_id: "收纳整理"},
    )
    assert "收纳整理" in agg["data"], agg
    exchange = m5_feedback.build_exchange_file(
        agg["data"], period_start="2026-08-01", period_end="2026-08-31",
        generated_at=datetime.now(timezone.utc),
    )
    assert exchange["schema_version"] == 1
    path = tmp_path / "m5-ad-conversion.json"
    m5_feedback.write_exchange_file(exchange, path)

    ex = m1_backfill.load_exchange(path)
    assert ex is not None
    stats_b = m1_backfill.apply_exchange(sdb, ex, str(path))
    assert stats_b["inserted"] == 1
    with sdb.session() as session:
        row = session.query(M1AdConversionCache).filter_by(category="收纳整理").one_or_none()
    assert row is not None
    assert row.sales_amount == 900000  # 金额分 int（DA-001）


def test_a7_m0_scheduler_isolates_failures(fdb, queue) -> None:
    """M0 调度器失败隔离：一个 job 人工接管，另一个正常完成（A2 语义在闭环中生效）。"""
    from foundation.scheduler import Worker
    from foundation.tables import WorkflowJob

    class FlakyWorker(Worker):
        def __init__(self):
            self.count = 0

        def execute(self, job: WorkflowJob) -> dict:
            self.count += 1
            if job.product_id == 1:
                return {"ok": False, "error_code": "VERIFICATION_REQUIRED", "evidence": {"reason": "验证码"}}
            return {"ok": True, "error_code": None, "evidence": {"done": True}}

    queue.enqueue(product_id=1, stage="source_collect")
    queue.enqueue(product_id=2, stage="source_collect")
    sched = WorkflowScheduler(queue, FlakyWorker(), worker_id="a7-isolate")
    stats = sched.run_once()
    assert stats["claimed"] == 2
    assert stats["failed"] == 1 and stats["succeeded"] == 1
    assert queue.get(1).status == "waiting_verification"  # 人工接管单任务暂停
    assert queue.get(2).status == "success"               # 失败隔离不阻塞


def test_a7_risk_budget_triple_hard_stop() -> None:
    """M0 风控：预算三重任一超限即停（S7 硬约束，与 M5 引用基座同口径）。"""
    bv = check_budget_triple(6000, 5000, 5000, budget_single_fen=5000, budget_daily_fen=10000, budget_plan_fen=20000)
    assert bv.over_limit and bv.rule == "single"
    result = RiskEngine().evaluate(campaign={}, snapshots=[], account_balance_fen=999999, budget=bv)
    assert any(v.rule_id == "S7" for v in result.verdicts)
