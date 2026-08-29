"""M6 API 层测试共享工具（非 conftest，独立模块避免污染既有测试）。

提供：
- `make_services(tmp_path)`：构造隔离 Services（6 个 tmp SQLite 库，零外网零真实库）；
  内置账号 admin（role=admin，密码运行时随机生成——不落任何明文，P-004）；
- `make_client(tmp_path)`：TestClient + Services + 登录凭据；
- 各模块造数辅助（直接调用各模块 repo 幂等函数/ORM，不修改模块源码）。

测试命令（P-001/P-011/P-017）：`python -X utf8 -m pytest tests/test_api_*.py -q
--basetemp=".pytest-tmp-m6"`。
"""

from __future__ import annotations

import secrets
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

BACKEND = Path(__file__).resolve().parent.parent
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from api.auth import FixturesAuthStore  # noqa: E402
from api.config import M6Config  # noqa: E402
from api.services import Services  # noqa: E402

ADMIN_USERNAME = "admin"


def random_password() -> str:
    """运行时随机密码（测试登录用；不落任何文件）。"""
    return secrets.token_urlsafe(16)


def make_services(tmp_path, password: Optional[str] = None):
    """构造隔离 Services（6 个 tmp SQLite 库）+ admin/viewer 账号。

    返回 (services, admin_creds, viewer_creds)；密码运行时随机生成，不落任何文件。
    """
    password = password or random_password()
    viewer_password = random_password()
    store = FixturesAuthStore(admin_username=ADMIN_USERNAME, admin_password_hash="")
    store.seed_user_plain(ADMIN_USERNAME, password, role="admin")
    store.seed_user_plain("viewer", viewer_password, role="viewer")
    settings = M6Config(
        api_auth_mode="fixtures",
        m0_db_url=f"sqlite:///{tmp_path / 'm0.db'}",
        sourcing_db_url=f"sqlite:///{tmp_path / 'm1.db'}",
        materials_db_url=f"sqlite:///{tmp_path / 'm2.db'}",
        m3_db_url=f"sqlite:///{tmp_path / 'm3.db'}",
        m4_db_url=f"sqlite:///{tmp_path / 'm4.db'}",
        m5_db_url=f"sqlite:///{tmp_path / 'm5.db'}",
    )
    services = Services(settings, auth_store=store)
    return (
        services,
        {"username": ADMIN_USERNAME, "password": password},
        {"username": "viewer", "password": viewer_password},
    )


def make_client(tmp_path, password: Optional[str] = None):
    """构造 TestClient（with 生命周期已启动）+ Services + 登录凭据。"""
    from fastapi.testclient import TestClient

    from api.app import create_app

    services, creds, viewer_creds = make_services(tmp_path, password=password)
    app = create_app(services=services)
    client = TestClient(app)
    return client, services, creds, viewer_creds


def login(client, creds: dict[str, str]) -> Any:
    """登录并返回响应（成功应含 Set-Cookie）。"""
    return client.post("/api/auth/login", json=creds)


def auth_headers(client, creds: dict[str, str]) -> dict[str, str]:
    """登录后取 cookie 作为后续请求头（TestClient 自动管理 cookie，通常无需手拼）。"""
    resp = login(client, creds)
    assert resp.status_code == 200, resp.text
    return {"Cookie": "; ".join(f"{k}={v}" for k, v in client.cookies.items())}


# ================================================================ 造数辅助


def seed_m0(services: Services) -> None:
    """M0：入队若干 workflow_jobs（含 waiting_verification / blocked / success）。"""
    from foundation.tables import WorkflowJob

    queue = services.m0_queue
    jobs = []
    jobs.append(queue.enqueue(product_id=101, stage="source_collect", payload={"mode": "fixtures"}))
    jobs.append(queue.enqueue(product_id=102, stage="listing_upload", payload={"mode": "fixtures"}))
    jobs.append(queue.enqueue(product_id=103, stage="shop_ads_run", payload={"mode": "fixtures"}))
    with services.m0_db.session() as session:
        # ① success
        j = session.get(WorkflowJob, jobs[0].id)
        j.status = "success"
        j.evidence_json = {"items": 3, "url": "https://example.com/a?token=SECRET"}
        # ② waiting_verification（人工接管）
        j2 = session.get(WorkflowJob, jobs[1].id)
        j2.status = "waiting_verification"
        j2.error_code = "VERIFICATION_REQUIRED"
        j2.error_message = "需要验证码"
        # ③ blocked
        j3 = session.get(WorkflowJob, jobs[2].id)
        j3.status = "blocked"
        j3.error_code = "PLATFORM_REJECT"
        j3.error_message = "平台驳回"
    return jobs


def seed_m1(services: Services) -> dict[int, int]:
    """M1：造 3 个商品（2 pool + 1 manual_review），含打分/询价/来源证据。"""
    from sourcing.tables import Product, ProductSourceEvidence, Sku

    rows = [
        ("免打孔卫生间置物架 浴室收纳架", "收纳整理", "pool", "candidate", 82.5, 29.9, 8.5, 19.9),
        ("猫咪自动喂食器 宠物定时喂食碗", "宠物用品", "pool", "candidate", 74.0, 79.0, 22.0, 49.9),
        ("便携榨汁杯 无线充电 家用小型果汁机", "数码配件", "manual_review", "manual_review", 66.0, 89.0, 30.0, 59.9),
    ]
    product_ids: list[int] = []
    with services.sourcing_db.session() as session:
        for i, (title, category, state, comp_state, score, price, cost, suggest) in enumerate(rows):
            p = Product(
                fingerprint=f"fp-m1-{i:03d}",
                image_phash=f"ph{i:016d}",
                title=title,
                sanitized_title=title,
                category=category,
                platform_price=price,
                real_cost=cost,
                suggested_price=suggest,
                profit_margin=round((suggest - cost) / suggest, 2),
                sales=1000 + i * 100,
                rank_best=i + 1,
                board_count=2,
                score=score,
                score_breakdown={
                    "total": score,
                    "note": "",
                    "dimensions": {
                        "trend": {"key": "trend", "label": "热度趋势", "raw": 30, "weight": 0.35, "weighted": round(score * 0.35, 1), "active": True, "reasons": ["榜单热度高"]},
                        "profit": {"key": "profit", "label": "利润率", "raw": 25, "weight": 0.3, "weighted": round(score * 0.3, 1), "active": True, "reasons": ["成本可控"]},
                    },
                },
                compliance_state=comp_state,
                compliance_reasons=[] if comp_state == "candidate" else ["待人工复核"],
                state=state,
                supplier_count=2,
                ad_conversion={},
            )
            session.add(p)
            session.flush()
            product_ids.append(p.id)
            session.add(
                Sku(
                    product_id=p.id,
                    supplier_name="供应商A",
                    sku_name=f"SKU-{p.id}",
                    unit_cost=cost,
                    min_order=10,
                    freight=0.0,
                    raw_url="https://detail.1688.com/offer/123456.html",
                )
            )
            # 类目投放转化（M5 C-2 口径：sales_amount 单位分，API 层须换算为元）
            ad_conversion = (
                {"roi": 3.2, "sales_amount": 128000, "sample_count": 34}
                if i == 0
                else {}
            )
            session.add(
                ProductSourceEvidence(
                    product_id=p.id,
                    source="youmi",
                    board="商品榜",
                    platform_item_id=f"ym-{p.id}",
                    title=title,
                    price=price,
                    sales=1000,
                    rank=1,
                    image_urls=["https://img.example.com/p.jpg"],
                    raw_json={"source_product_url": "https://example.com/p?token=SHOULD_BE_REDACTED"},
                )
            )
            # 回填 ad_conversion（repo.upsert_product 语义：直接写 JSON 列）
            p.ad_conversion = ad_conversion
    return {r[0]: pid for r, pid in zip(rows, product_ids)}


def seed_m2(services: Services) -> dict[str, int]:
    """M2：造 2 个素材（video/image）+ 相关性门状态 + 上传记录。"""
    repo = services.materials_repo
    aid1 = repo.create_asset(
        asset_type="video",
        source_platform="抖音",
        source_url="https://example.com/v.mp4?token=REDACT_ME",
        md5="a" * 32,
        phash="b" * 16,
        file_path="videos/a.mp4",
        size=1024 * 1024,
        duration=30,
        resolution="720x1280",
        compliance_status="passed",
        relevance_status="manual_review",
        heat_score=88.0,
    )
    aid2 = repo.create_asset(
        asset_type="image",
        source_platform="淘宝",
        source_url="https://img.example.com/p.jpg",
        md5="c" * 32,
        phash="d" * 16,
        file_path="images/p.jpg",
        size=2048,
        compliance_status="passed",
        relevance_status="passed",
    )
    repo.mark_uploaded(aid1, "mat-upload-001")
    return {"video": aid1, "image": aid2}


def seed_m3(services: Services) -> dict[str, str]:
    """M3：造 1 个生图批次（2 张图，1 待审）+ 1 条文案。"""
    from optimization.models import CopywriteDraft

    img_repo = services.m3_image_repo
    copy_repo = services.m3_copywrite_repo
    img_repo.create_batch(
        batch_id="batch-001",
        product_id="101",
        image_type="main",
        plan={"strategy": "白色背景主图"},
        target_count=5,
    )
    img_id1 = img_repo.upsert_image(
        {
            "batch_id": "batch-001",
            "product_id": "101",
            "image_type": "main",
            "variant_no": 1,
            "file_path": "images/g1.png",
            "phash": "phash-1",
            "width": 800,
            "height": 800,
            "quality_json": {"score": 90, "issues": []},
            "quality_ok": True,
        }
    )
    img_repo.upsert_image(
        {
            "batch_id": "batch-001",
            "product_id": "101",
            "image_type": "main",
            "variant_no": 2,
            "file_path": "images/g2.png",
            "phash": "phash-2",
            "width": 800,
            "height": 800,
            "quality_json": {"score": 85, "issues": []},
            "quality_ok": True,
        }
    )
    copy_repo.upsert(
        CopywriteDraft(
            product_id="101",
            copy_type="title",
            content="免打孔卫生间置物架浴室收纳架",
            variant_no=1,
            char_len=16,
            passed=True,
        )
    )
    copy_repo.upsert(
        CopywriteDraft(
            product_id="101",
            copy_type="ad",
            content="多场景收纳 免打孔安装",
            variant_no=1,
            char_len=12,
            passed=True,
        )
    )
    return {"batch_id": "batch-001", "image_id": img_id1}


def seed_m4(services: Services) -> dict[str, str]:
    """M4：造 3 个上架任务（pending / listed（已验链接）/ retry_candidate）。"""
    from listing.models import ListingTask, utcnow_iso

    repo = services.m4_repo
    pending = ListingTask(
        task_id="task-pending-001",
        product_id=101,
        generation_version="v1",
        status="pending",
        gate_result={"item": {"passed": True, "reason": ""}},
    )
    repo.create_task(pending)
    repo.upsert_spu(
        spu_id="spu-001",
        task_id="task-pending-001",
        title="免打孔卫生间置物架",
        category_id=1,
        status="draft",
    )
    repo.upsert_skus(
        "spu-001",
        [{"sku_id": "sku-001", "product_sku_code": "c1", "price_cents": 1290, "cost_cents": 850}],
    )
    repo.append_op_log(
        task_id="task-pending-001",
        api="state_machine",
        direction="transition",
        evidence_json='{"from":"pending","to":"creating"}',
    )
    repo.append_op_log(
        task_id="task-pending-001",
        api="create_spu",
        direction="response",
        status_code=200,
        evidence_json='{"spu_id":"spu-001"}',
    )

    listed = ListingTask(
        task_id="task-listed-001",
        product_id=102,
        generation_version="v1",
        status="listed",
        platform_spu_id="spu-002",
        product_link="https://channels.weixin.qq.com/shop/abc",
        link_verified_at=utcnow_iso(),
        attempts=1,
    )
    repo.create_task(listed)
    repo.upsert_spu(spu_id="spu-002", task_id="task-listed-001", title="猫咪自动喂食器", category_id=2, status="listed")
    repo.upsert_skus(
        "spu-002",
        [{"sku_id": "sku-002", "product_sku_code": "c2", "price_cents": 4990, "cost_cents": 2200}],
    )

    retry = ListingTask(
        task_id="task-retry-001",
        product_id=103,
        generation_version="v1",
        status="retry_candidate",
        reject_reason_code="image",
        attempts=2,
    )
    repo.create_task(retry)
    return {"pending": "task-pending-001", "listed": "task-listed-001", "retry": "task-retry-001"}


def seed_m5(services: Services) -> dict[str, int]:
    """M5：造 2 个托管计划 + 快照 + 账户状态 + 素材。"""
    import ads.repo as ads_repo

    with services.m5_db.session() as session:
        cid1 = ads_repo.create_campaign(
            session,
            product_id=101,
            target_type="roi",
            target_roi=2.0,
            material_ids=["mat-001"],
            status="active",
            diagnosis="excellent",
        )
        cid2 = ads_repo.create_campaign(
            session,
            product_id=102,
            target_type="net_roi",
            target_roi=3.0,
            material_ids=[],
            status="paused",
            diagnosis="good",
        )
        now = datetime.now(timezone.utc)
        ads_repo.upsert_snapshot(
            session,
            campaign_id=cid1,
            recorded_at=now,
            impressions=10000,
            spend=1290,          # 12.9 元
            gmv=2580,            # 25.8 元
            platform_subsidy=100,  # 1.0 元
            diagnosis="excellent",
            status="active",
        )
        ads_repo.upsert_snapshot(
            session,
            campaign_id=cid2,
            recorded_at=now,
            impressions=5000,
            spend=990,
            gmv=0,
            platform_subsidy=0,
            diagnosis="good",
            status="paused",
        )
        ads_repo.upsert_account_state(session, balance=50000, status="active", throttle_level=0)
        ads_repo.upsert_material(
            session,
            material_id="mat-001",
            asset_id=1,
            file_path="videos/a.mp4",
            duration=30.0,
            resolution="720x1280",
            evaluation="efficient",
            upload_status="approved",
        )
    return {"active": cid1, "paused": cid2}


def seed_all(services: Services) -> dict[str, Any]:
    """一次性造全模块数据（各测试按需调用）。"""
    return {
        "m0": seed_m0(services),
        "m1": seed_m1(services),
        "m2": seed_m2(services),
        "m3": seed_m3(services),
        "m4": seed_m4(services),
        "m5": seed_m5(services),
    }
