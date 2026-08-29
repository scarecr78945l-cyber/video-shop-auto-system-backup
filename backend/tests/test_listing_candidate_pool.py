"""M4 → M5 衔接候选池测试（P6）：CandidatePool 只读视图 + 错峰窗口。

- 复用 conftest fixtures：cfg_listing/db_listing/repo_listing/machine_listing；
- 全部 tmp_path SQLite 零建库；
- 测试命令（P-001/P-011 纪律，本模块独立 basetemp）：
  cd backend && python -m pytest tests/test_listing_candidate_pool.py -q --basetemp=".pytest-tmp-m4"
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import update

from listing.candidate_pool import CandidatePool, CandidatePoolConfig
from listing.models import ListingTask, utcnow_iso
from listing.tables import ListingSkuRow, ListingSpuRow, ListingTaskRow

LISTED = "https://channels.weixin.qq.com/shop/"


# ---------------------------------------------------------------- 造数工具


def _run_to_listed(repo, machine, product_id: int, gen: str = "v1", link_url: str | None = None):
    """走 P3 state_machine 合法迁移链到 listed（R22 必带 link_url+verified=True 证据）。"""
    task = ListingTask(
        task_id=f"task-{product_id}-{gen}", product_id=product_id, generation_version=gen
    )
    repo.create_task(task)
    t = machine.transition(task, "creating")
    t = machine.transition(t, "draft")
    t = machine.transition(t, "platform_auditing")
    url = link_url or f"{LISTED}p{product_id}"
    return machine.transition(t, "listed", evidence={"link_url": url, "verified": True})


def _run_to_status(repo, machine, product_id: int, status: str, gen: str = "v1"):
    """迁移到指定非终态（draft/platform_auditing/rejected/retry_candidate/manual）。"""
    task = ListingTask(
        task_id=f"task-{product_id}-{gen}", product_id=product_id, generation_version=gen
    )
    repo.create_task(task)
    t = machine.transition(task, "creating")
    t = machine.transition(t, "draft")
    if status == "draft":
        return t
    t = machine.transition(t, "platform_auditing")
    if status == "platform_auditing":
        return t
    t = machine.transition(
        t, "rejected", evidence={"reject_reason_code": "title"}
    )
    if status == "rejected":
        return t
    return machine.transition(t, status)  # retry_candidate | manual


def _add_spu(db, task_id: str, spu_id: str, title: str, category_id: int):
    with db.session() as s:
        s.add(
            ListingSpuRow(
                spu_id=spu_id,
                task_id=task_id,
                title=title,
                category_id=category_id,
                status="listed",
                created_at=utcnow_iso(),
                updated_at=utcnow_iso(),
            )
        )


def _add_sku(db, spu_id: str, sku_id: str, price_cents: int, cost_cents: int = 100):
    with db.session() as s:
        s.add(
            ListingSkuRow(
                sku_id=sku_id,
                spu_id=spu_id,
                product_sku_code=f"code-{sku_id}",
                price_cents=price_cents,
                cost_cents=cost_cents,
                stock=10000,
                status="on_sale",
            )
        )


def _force_link_verified(db, task_id: str, link_verified_at: str):
    """直接 UPDATE 固化 link_verified_at（排序确定性）。"""
    with db.session() as s:
        s.execute(
            update(ListingTaskRow)
            .where(ListingTaskRow.task_id == task_id)
            .values(link_verified_at=link_verified_at)
        )


# ---------------------------------------------------------------- 候选池口径


def test_only_listed_with_verified_link_returned(repo_listing, machine_listing, db_listing):
    """只返回 listed 且链接验证过的任务；异常数据（listed 但链接/验证时间被清空、
    空串链接）一律不出现。"""
    t1 = _run_to_listed(repo_listing, machine_listing, 101, link_url=f"{LISTED}101")
    t2 = _run_to_listed(repo_listing, machine_listing, 102, link_url=f"{LISTED}102")
    # 异常数据 1：listed 但 link_verified_at / product_link 被清空（直接 UPDATE 模拟）
    t_bad_null = _run_to_listed(repo_listing, machine_listing, 103, link_url=f"{LISTED}103")
    # 异常数据 2：listed 但 product_link 为空串（非空过滤应排除）
    t_bad_empty = _run_to_listed(repo_listing, machine_listing, 104, link_url=f"{LISTED}104")
    with db_listing.session() as s:
        s.execute(
            update(ListingTaskRow)
            .where(ListingTaskRow.task_id == t_bad_null.task_id)
            .values(link_verified_at=None, product_link=None)
        )
        s.execute(
            update(ListingTaskRow)
            .where(ListingTaskRow.task_id == t_bad_empty.task_id)
            .values(product_link="")
        )

    pool = CandidatePool(repo_listing)
    results = pool.get_sale_candidates()
    task_ids = {r["task_id"] for r in results}
    assert task_ids == {t1.task_id, t2.task_id}
    assert t_bad_null.task_id not in task_ids
    assert t_bad_empty.task_id not in task_ids


def test_relevance_ready_filter(repo_listing, machine_listing, db_listing):
    """REC-迁移-03（C3）：候选池相关性过滤——仅返回素材相关性已过（passed）
    的商品；未在集合内的商品被排除（不直读 M2 库，由编排层传入集合）。"""
    t1 = _run_to_listed(repo_listing, machine_listing, 201, link_url=f"{LISTED}201")
    t2 = _run_to_listed(repo_listing, machine_listing, 202, link_url=f"{LISTED}202")
    t3 = _run_to_listed(repo_listing, machine_listing, 203, link_url=f"{LISTED}203")

    pool = CandidatePool(repo_listing)
    # 不传过滤 → 全部返回（向后兼容）
    assert len(pool.get_sale_candidates()) == 3
    # 只放行 201/203（202 素材相关性未过）；product_id 为 int
    results = pool.get_sale_candidates(relevance_ready_ids={201, 203})
    task_ids = {r["task_id"] for r in results}
    assert task_ids == {t1.task_id, t3.task_id}
    assert t2.task_id not in task_ids
    # 证据记录过滤数量
    assert pool.last_evidence.get("relevance_filtered") == 1


def test_non_listed_statuses_excluded(repo_listing, machine_listing):
    """草稿/审核中/驳回/人工/待重提一律不出现（仅销售中商品，07 文档六节）。"""
    for pid, status in [
        (201, "draft"),
        (202, "platform_auditing"),
        (203, "rejected"),
        (204, "manual"),
        (205, "retry_candidate"),
    ]:
        _run_to_status(repo_listing, machine_listing, pid, status)
    t_ok = _run_to_listed(repo_listing, machine_listing, 206, link_url=f"{LISTED}206")

    results = CandidatePool(repo_listing).get_sale_candidates()
    assert [r["task_id"] for r in results] == [t_ok.task_id]


def test_field_completeness(repo_listing, machine_listing, db_listing):
    """返回字段完整性：product_id/task_id/title/category_id/product_link/
    link_verified_at/price_min_cents/price_max_cents。"""
    t = _run_to_listed(repo_listing, machine_listing, 301, link_url=f"{LISTED}301")
    _add_spu(db_listing, t.task_id, "spu-301", "测试商品标题", 1001)
    _add_sku(db_listing, "spu-301", "sku-301a", 1990)
    _add_sku(db_listing, "spu-301", "sku-301b", 2990)
    _force_link_verified(db_listing, t.task_id, "2026-01-01T00:00:00+00:00")

    (r,) = CandidatePool(repo_listing).get_sale_candidates()
    assert r == {
        "product_id": 301,
        "task_id": t.task_id,
        "title": "测试商品标题",
        "category_id": 1001,
        "product_link": f"{LISTED}301",
        "link_verified_at": "2026-01-01T00:00:00+00:00",
        "price_min_cents": 1990,
        "price_max_cents": 2990,
    }


def test_price_aggregation_min_max_and_no_sku(repo_listing, machine_listing, db_listing):
    """多 SKU 聚合 min/max 正确（单位分）；无 SKU 置 None；无 SPU 时 title/
    category_id 置 None。"""
    t1 = _run_to_listed(repo_listing, machine_listing, 401, link_url=f"{LISTED}401")
    _add_spu(db_listing, t1.task_id, "spu-401", "多 SKU 商品", 2001)
    _add_sku(db_listing, "spu-401", "sku-401a", 990)
    _add_sku(db_listing, "spu-401", "sku-401b", 1990)
    _add_sku(db_listing, "spu-401", "sku-401c", 1290)
    _force_link_verified(db_listing, t1.task_id, "2026-01-01T00:00:00+00:00")

    t2 = _run_to_listed(repo_listing, machine_listing, 402, link_url=f"{LISTED}402")
    _add_spu(db_listing, t2.task_id, "spu-402", "无 SKU 商品", 2002)
    _force_link_verified(db_listing, t2.task_id, "2026-01-01T00:00:01+00:00")

    t3 = _run_to_listed(repo_listing, machine_listing, 403, link_url=f"{LISTED}403")
    _force_link_verified(db_listing, t3.task_id, "2026-01-01T00:00:02+00:00")

    by_task = {r["task_id"]: r for r in CandidatePool(repo_listing).get_sale_candidates()}
    assert by_task[t1.task_id]["price_min_cents"] == 990
    assert by_task[t1.task_id]["price_max_cents"] == 1990
    assert by_task[t2.task_id]["price_min_cents"] is None
    assert by_task[t2.task_id]["price_max_cents"] is None
    assert by_task[t3.task_id]["title"] is None
    assert by_task[t3.task_id]["category_id"] is None
    assert by_task[t3.task_id]["price_min_cents"] is None


def test_ordered_by_link_verified_at_asc(repo_listing, machine_listing, db_listing):
    """按 link_verified_at 升序（先上架先出）。"""
    t_late = _run_to_listed(repo_listing, machine_listing, 501, link_url=f"{LISTED}501")
    t_early = _run_to_listed(repo_listing, machine_listing, 502, link_url=f"{LISTED}502")
    _force_link_verified(db_listing, t_late.task_id, "2026-02-01T00:00:00+00:00")
    _force_link_verified(db_listing, t_early.task_id, "2026-01-01T00:00:00+00:00")

    results = CandidatePool(repo_listing).get_sale_candidates()
    assert [r["task_id"] for r in results] == [t_early.task_id, t_late.task_id]


def test_limit_and_batch_max_truncation(repo_listing, machine_listing, db_listing):
    """limit 生效且不超过 candidate_batch_max（超出截断并附 evidence 提示）。"""
    ids = []
    for pid in (601, 602, 603):
        t = _run_to_listed(repo_listing, machine_listing, pid, link_url=f"{LISTED}{pid}")
        _force_link_verified(db_listing, t.task_id, f"2026-01-01T00:00:0{pid % 10}+00:00")
        ids.append(t.task_id)

    pool = CandidatePool(
        repo_listing, config=CandidatePoolConfig(candidate_batch_max=2)
    )

    # 无 limit → 默认 candidate_batch_max=2，截断 + evidence
    results = pool.get_sale_candidates()
    assert len(results) == 2
    assert pool.last_evidence == {
        "truncated": True,
        "requested": None,
        "applied": 2,
        "total_matched": 3,
    }

    # 显式 limit=1 → 1 条
    results = pool.get_sale_candidates(limit=1)
    assert len(results) == 1
    assert pool.last_evidence["applied"] == 1

    # 显式 limit=10 超过 batch_max → 仍截断到 2 并提示
    results = pool.get_sale_candidates(limit=10)
    assert len(results) == 2
    assert pool.last_evidence["truncated"] is True
    assert pool.last_evidence["requested"] == 10
    assert pool.last_evidence["applied"] == 2


def test_empty_db_returns_empty_list(repo_listing):
    """空库返回空列表（不报错，幂等）。"""
    pool = CandidatePool(repo_listing)
    assert pool.get_sale_candidates() == []
    assert pool.get_sale_candidates() == []  # 幂等：重复调用一致
    assert pool.last_evidence == {
        "truncated": False,
        "requested": None,
        "applied": 50,
        "total_matched": 0,
    }


# ---------------------------------------------------------------- 错峰窗口


def test_in_peak_avoid_window_default_boundaries():
    """默认窗口 10:00–12:00：窗口内 True、窗口外 False、end 边界不含（左闭右开）。"""
    pool = CandidatePool.__new__(CandidatePool)  # 仅测窗口逻辑，不连库
    pool.config = CandidatePoolConfig()
    pool._window_start, pool._window_end = CandidatePool._parse_window(
        pool.config.peak_avoid_window
    )

    assert pool.in_peak_avoid_window(datetime(2026, 1, 1, 10, 0)) is True    # start 含
    assert pool.in_peak_avoid_window(datetime(2026, 1, 1, 11, 59)) is True   # 窗口内
    assert pool.in_peak_avoid_window(datetime(2026, 1, 1, 12, 0)) is False   # end 不含
    assert pool.in_peak_avoid_window(datetime(2026, 1, 1, 9, 59)) is False   # 窗口外
    assert pool.in_peak_avoid_window(datetime(2026, 1, 1, 13, 0)) is False   # 窗口外
    # 粒度为 HH:MM：10:00:30 → 10:00 窗口内；12:00:30 → 12:00 已出窗
    assert pool.in_peak_avoid_window(datetime(2026, 1, 1, 10, 0, 30)) is True
    assert pool.in_peak_avoid_window(datetime(2026, 1, 1, 12, 0, 30)) is False


def test_in_peak_avoid_window_cross_day():
    """跨天窗口 22:00→02:00 按环形处理：22:00 含、02:00 不含、白天 False。"""
    pool = CandidatePool.__new__(CandidatePool)
    pool.config = CandidatePoolConfig(
        peak_avoid_window={"start": "22:00", "end": "02:00"}
    )
    pool._window_start, pool._window_end = CandidatePool._parse_window(
        pool.config.peak_avoid_window
    )

    assert pool.in_peak_avoid_window(datetime(2026, 1, 1, 22, 0)) is True    # start 含
    assert pool.in_peak_avoid_window(datetime(2026, 1, 1, 23, 30)) is True   # 跨天前段
    assert pool.in_peak_avoid_window(datetime(2026, 1, 2, 1, 30)) is True    # 跨天后段
    assert pool.in_peak_avoid_window(datetime(2026, 1, 2, 2, 0)) is False    # end 不含
    assert pool.in_peak_avoid_window(datetime(2026, 1, 1, 12, 0)) is False   # 白天非互斥


def test_in_peak_avoid_window_config_error(repo_listing):
    """窗口配置缺键/非法格式 → CandidatePool 构造时清晰报错（fail fast）。"""
    import pytest

    with pytest.raises(ValueError):
        CandidatePool(
            repo_listing,
            config=CandidatePoolConfig(peak_avoid_window={"start": "10:00"}),
        )
    with pytest.raises(ValueError):
        CandidatePool(
            repo_listing,
            config=CandidatePoolConfig(
                peak_avoid_window={"start": "25:00", "end": "12:00"}
            ),
        )


def test_end_to_end_pipeline_feeds_candidate_pool(repo_listing, machine_listing, tmp_path):
    """DA-009 集成修复：pipeline 上架成功后 SPU/SKU 自动落库 → 候选池返回完整字段。

    回归保护：title/category_id/价格不再恒为 None（M0 A7 集成冒烟发现的缺口）。
    """
    from adapters.wechat_openapi import WechatOpenApiAdapter, WechatOpenApiConfig
    from listing.pipeline import ListingPipeline
    from listing.platform_rejection import RejectionHandler
    from services.listing_gate import (
        ListingCandidate,
        ListingGate,
        PurchaseSettings,
        SkuInput,
    )

    def _images(n: int, prefix: str) -> list[str]:
        from PIL import Image

        paths = []
        for i in range(n):
            p = tmp_path / f"{prefix}_{i}.png"
            Image.new("RGB", (100, 100), (10 + i * 40, 20, 30)).save(p)
            paths.append(str(p))
        return paths

    gate = ListingGate()
    adapter = WechatOpenApiAdapter(WechatOpenApiConfig(mode="mock"))
    rejection = RejectionHandler(repo_listing, machine_listing, gate=gate)
    pipeline = ListingPipeline(
        gate=gate,
        adapter=adapter,
        repo=repo_listing,
        state_machine=machine_listing,
        rejection=rejection,
    )
    candidate = ListingCandidate(
        product_id=9001,
        title="纯棉加厚家用擦手巾厨房清洁抹布吸水速干",
        category_id=2001,
        category_name="厨房用品",
        qualification={"qualification_id": "QL-001", "expires_at": "2026-12-31"},
        main_images=_images(5, "main"),
        detail_images=_images(1, "detail"),
        skus=[SkuInput(code="SKU-9001", cost_cents=1500, price_cents=2990)],
        purchase_settings=PurchaseSettings(
            purchase_limit={"per_user": 2, "period": "month"},
            freight_template_id="1",
            after_sale="支持7天无理由退换货",
        ),
    )
    result = pipeline.submit(candidate, generation_version="v1")
    assert result["ok"] is True and result["stage"] == "listed"

    rows = CandidatePool(repo_listing).get_sale_candidates()
    assert len(rows) == 1
    row = rows[0]
    assert row["title"] == candidate.title          # DA-009：不再为 None
    assert row["category_id"] == 2001
    assert row["price_min_cents"] == 2990
    assert row["price_max_cents"] == 2990
