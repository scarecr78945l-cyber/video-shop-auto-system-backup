"""M6 前端 v1.1 · 真实 API 冒烟（前端子代理⑦）

覆盖 5 项前端增强对应的后端契约真实链路：
  1. GET  /api/products?keyword=&page=&page_size=   服务端关键词 + 分页信封
  2. GET  /api/workbench/exceptions?page=&page_size= 异常中心分页信封（v1.1 迁移）
  3. POST /api/workbench/retry-batch                批量接管（单 job 失败不影响其余 / 空数组 422）
  4. GET  /api/assets/{id}/preview                  图片流（image 200 / video 400 / 不存在 404）
  5. GET  /api/ads/campaigns → product_name         商品名 join（命中 title / 缺失 null）

纪律：密码仅脚本进程内存（sha256 hex 仅子进程环境变量，不落任何文件）；
P-019：单条 http.client 持久连接；临时目录/子进程用完清理；不运行 git。
"""
from __future__ import annotations

import hashlib
import http.client
import json
import os
import secrets
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2] / "backend"
sys.path.insert(0, str(BACKEND))

PORT = 8123
HOST = "127.0.0.1"

PASSED: list[str] = []
FAILED: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    if cond:
        PASSED.append(name)
        print(f"  ✅ {name}{('  ' + detail) if detail else ''}")
    else:
        FAILED.append(name)
        print(f"  ❌ {name}{('  ' + detail) if detail else ''}")


def seed(workdir: Path, storage: Path):
    """造数：M0 4 任务 / M1 3 商品 / M2 图片+视频素材（落真实 PNG 文件）/ M5 2 托管计划。"""
    from api.auth import FixturesAuthStore
    from api.config import M6Config
    from api.services import Services

    db = workdir / "dbs"
    db.mkdir(parents=True, exist_ok=True)
    storage.mkdir(parents=True, exist_ok=True)

    settings = M6Config(
        api_auth_mode="fixtures",
        m0_db_url=f"sqlite:///{db / 'm0.db'}",
        sourcing_db_url=f"sqlite:///{db / 'm1.db'}",
        materials_db_url=f"sqlite:///{db / 'm2.db'}",
        m3_db_url=f"sqlite:///{db / 'm3.db'}",
        m4_db_url=f"sqlite:///{db / 'm4.db'}",
        m5_db_url=f"sqlite:///{db / 'm5.db'}",
    )
    services = Services(settings, auth_store=FixturesAuthStore(admin_username="", admin_password_hash=""))

    # ---- M0：waiting_verification / blocked / success / waiting_login ----
    from foundation.tables import WorkflowJob

    queue = services.m0_queue
    j_verify = queue.enqueue(product_id=101, stage="listing_upload", payload={"mode": "smoke"})
    j_blocked = queue.enqueue(product_id=102, stage="shop_ads_run", payload={"mode": "smoke"})
    j_success = queue.enqueue(product_id=103, stage="source_collect", payload={"mode": "smoke"})
    j_login = queue.enqueue(product_id=104, stage="shop_ads_report", payload={"mode": "smoke"})
    with services.m0_db.session() as session:
        v = session.get(WorkflowJob, j_verify.id)
        v.status = "waiting_verification"
        v.error_code = "VERIFICATION_REQUIRED"
        v.error_message = "需要验证码"
        b = session.get(WorkflowJob, j_blocked.id)
        b.status = "blocked"
        b.error_code = "PLATFORM_REJECT"
        b.error_message = "平台驳回"
        s = session.get(WorkflowJob, j_success.id)
        s.status = "success"
        l = session.get(WorkflowJob, j_login.id)
        l.status = "waiting_login"
        l.error_code = "AUTH_REQUIRED"
        l.error_message = "登录失效"
        session.commit()

    # ---- M1：3 商品（keyword 命中/未命中 + join 用）----
    from sqlalchemy import select

    from sourcing.tables import Product

    products = [
        ("猫咪自动喂食器 宠物定时喂食碗", "宠物用品", "pool", "candidate", 74.0, 79.0),
        ("便携榨汁杯 无线充电 家用小型果汁机", "数码配件", "pool", "candidate", 66.0, 89.0),
        ("免打孔卫生间置物架 浴室收纳架", "收纳整理", "pool", "candidate", 82.5, 29.9),
    ]
    with services.sourcing_db.session() as session:
        for i, (title, category, state, comp, score, price) in enumerate(products):
            p = Product(
                fingerprint=f"fp-v11-{i:03d}",
                image_phash=f"ph{i:016d}",
                title=title,
                sanitized_title=title,
                category=category,
                platform_price=price,
                real_cost=price * 0.4,
                suggested_price=price * 1.5,
                profit_margin=0.4,
                sales=1000 + i * 100,
                rank_best=i + 1,
                board_count=2,
                score=score,
                score_breakdown={"total": score, "dimensions": {}, "note": ""},
                compliance_state=comp,
                state=state,
            )
            session.add(p)
        session.commit()
        rows = list(session.scalars(select(Product).order_by(Product.id)).all())
        product_ids = {row.title: row.id for row in rows}

    # ---- M2：image（落真实 PNG）+ video ----
    repo = services.materials_repo
    image_id = repo.create_asset(
        asset_type="image",
        source_platform="淘宝",
        source_url="https://img.example.com/p.png",
        md5="c" * 32,
        phash="d" * 16,
        file_path="images/smoke.png",
        size=68,
        compliance_status="passed",
        relevance_status="passed",
    )
    video_id = repo.create_asset(
        asset_type="video",
        source_platform="抖音",
        source_url="https://example.com/v.mp4",
        md5="a" * 32,
        phash="b" * 16,
        file_path="videos/a.mp4",
        size=1024,
        duration=30,
        resolution="720x1280",
        compliance_status="passed",
        relevance_status="manual_review",
    )
    # 1x1 合法 PNG（最小字节）
    png_bytes = bytes.fromhex(
        "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
        "0000000a49444154789c63000100000500010d0a2db40000000049454e44ae426082"
    )
    (storage / "images").mkdir(parents=True, exist_ok=True)
    (storage / "images" / "smoke.png").write_bytes(png_bytes)

    # ---- M5：campaign（product_id=1 命中 M1 join；product_id=999 缺失 → null）----
    import ads.repo as ads_repo

    with services.m5_db.session() as session:
        cid_join = ads_repo.create_campaign(
            session, product_id=product_ids["免打孔卫生间置物架 浴室收纳架"],
            target_type="roi", target_roi=2.0, material_ids=["mat-001"],
            status="active", diagnosis="excellent",
        )
        cid_null = ads_repo.create_campaign(
            session, product_id=999, target_type="net_roi", target_roi=3.0,
            material_ids=[], status="paused", diagnosis="good",
        )
        ads_repo.upsert_account_state(session, balance=50000, status="active", throttle_level=0)
        ads_repo.upsert_material(
            session, material_id="mat-001", asset_id=1, file_path="videos/a.mp4",
            duration=30.0, resolution="720x1280", evaluation="efficient", upload_status="approved",
        )
        session.commit()

    return {
        "job_verify": j_verify.id,
        "job_blocked": j_blocked.id,
        "job_success": j_success.id,
        "job_login": j_login.id,
        "image_id": image_id,
        "video_id": video_id,
        "campaign_join": cid_join,
        "campaign_null": cid_null,
    }


def wait_health(conn: http.client.HTTPConnection, tries: int = 40) -> bool:
    for _ in range(tries):
        try:
            conn.request("GET", "/api/health")
            resp = conn.getresponse()
            resp.read()
            if resp.status == 200:
                return True
        except Exception:
            pass
        time.sleep(0.5)
    return False


def main() -> int:
    workdir = Path(__file__).resolve().parent / ".smoke-v11"
    storage = workdir / "storage"
    if workdir.exists():
        shutil.rmtree(workdir)
    workdir.mkdir(parents=True, exist_ok=True)

    ids = seed(workdir, storage)

    # 随机账号：明文仅内存；hash 仅子进程环境变量
    password = secrets.token_urlsafe(16)
    password_hash = hashlib.sha256(password.encode()).hexdigest()
    env = dict(os.environ)
    env.update(
        {
            "M6_API_AUTH_MODE": "fixtures",
            "M6_ADMIN_USERNAME": "admin",
            "M6_ADMIN_PASSWORD_HASH": password_hash,
            "M6_M0_DB_URL": f"sqlite:///{workdir / 'dbs' / 'm0.db'}",
            "M6_SOURCING_DB_URL": f"sqlite:///{workdir / 'dbs' / 'm1.db'}",
            "M6_MATERIALS_DB_URL": f"sqlite:///{workdir / 'dbs' / 'm2.db'}",
            "M6_M3_DB_URL": f"sqlite:///{workdir / 'dbs' / 'm3.db'}",
            "M6_M4_DB_URL": f"sqlite:///{workdir / 'dbs' / 'm4.db'}",
            "M6_M5_DB_URL": f"sqlite:///{workdir / 'dbs' / 'm5.db'}",
            "MATERIALS_STORAGE_DIR": str(storage),
            "M6_CORS_ORIGINS": "http://127.0.0.1:3000,http://localhost:3000",
            "PYTHONUTF8": "1",
        }
    )

    server = subprocess.Popen(
        [sys.executable, "-X", "utf8", "-m", "api", "--host", HOST, "--port", str(PORT)],
        cwd=str(BACKEND),
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        conn = http.client.HTTPConnection(HOST, PORT, timeout=15)
        if not wait_health(conn):
            print("服务未就绪")
            return 2

        # 登录（单条持久连接，P-019）
        body = json.dumps({"username": "admin", "password": password})
        conn.request("POST", "/api/auth/login", body=body, headers={"Content-Type": "application/json"})
        resp = conn.getresponse()
        login_body = resp.read()
        check("login 200", resp.status == 200, f"status={resp.status}")
        cookie = resp.getheader("Set-Cookie", "").split(";")[0]

        def req(method: str, path: str, payload=None):
            headers = {"Cookie": cookie} if cookie else {}
            if payload is not None:
                headers["Content-Type"] = "application/json"
                body_bytes = json.dumps(payload).encode()
            else:
                body_bytes = None
            conn.request(method, path, body=body_bytes, headers=headers)
            r = conn.getresponse()
            data = r.read()
            return r, data

        # ---- 1. products keyword + page/page_size ----
        r, data = req("GET", "/api/products?keyword=%E5%96%82%E9%A3%9F%E5%99%A8&page=1&page_size=20")
        prod = json.loads(data)
        check("products keyword 命中 1 条", r.status == 200 and prod["total"] == 1 and len(prod["items"]) == 1,
              f"total={prod.get('total')} title={prod['items'][0]['title'] if prod.get('items') else None}")
        check("products 信封 {total,page,page_size,items} 无 limit/offset",
              set(prod.keys()) >= {"total", "page", "page_size", "items"} and "limit" not in prod and "offset" not in prod,
              f"keys={sorted(prod.keys())}")
        r, data = req("GET", "/api/products?keyword=zzz&page=1&page_size=20")
        check("products keyword 未命中 → total=0", json.loads(data)["total"] == 0)
        r, data = req("GET", "/api/products?page=1&page_size=2")
        prod2 = json.loads(data)
        check("products 分页 page_size=2 → items=2 / total=3", prod2["total"] == 3 and len(prod2["items"]) == 2 and prod2["page_size"] == 2)

        # ---- 2. exceptions page/page_size 信封 ----
        r, data = req("GET", "/api/workbench/exceptions?page=1&page_size=20")
        exc = json.loads(data)
        check("exceptions 信封 {total,page,page_size,items}", set(exc.keys()) >= {"total", "page", "page_size", "items"},
              f"keys={sorted(exc.keys())} total={exc.get('total')}")
        r, data = req("GET", "/api/workbench/exceptions?status=waiting_verification")
        check("exceptions status 筛选", json.loads(data)["total"] == 1)

        # ---- 3. retry-batch ----
        payload = {"job_ids": [ids["job_verify"], ids["job_blocked"], ids["job_login"], ids["job_success"], 999999]}
        r, data = req("POST", "/api/workbench/retry-batch", payload)
        rb = json.loads(data)
        results = rb.get("results", [])
        by_id = {x["job_id"]: x for x in results}
        ok_ids = [x["job_id"] for x in results if x["ok"]]
        check("retry-batch 整体 200 + results 长度 5", r.status == 200 and len(results) == 5, f"len={len(results)}")
        check("retry-batch 3 成功（verify/blocked/login）", set(ok_ids) == {ids["job_verify"], ids["job_blocked"], ids["job_login"]},
              f"ok={ok_ids}")
        check("retry-batch success 项 → INVALID_STATE 不影响其余",
              by_id[ids["job_success"]]["ok"] is False and by_id[ids["job_success"]]["error"]["code"] == "INVALID_STATE")
        check("retry-batch 不存在 → NO_MATCH + error{code,message}",
              by_id[999999]["ok"] is False and by_id[999999]["error"]["code"] == "NO_MATCH" and isinstance(by_id[999999]["error"]["message"], str))
        check("retry-batch 附加键 success_count=3", rb.get("success_count") == 3 and rb.get("total") == 5)
        # 幂等：再批量一次，verify 已恢复 → INVALID_STATE
        r, data = req("POST", "/api/workbench/retry-batch", {"job_ids": [ids["job_verify"]]})
        rb2 = json.loads(data)
        check("retry-batch 幂等（已恢复 → INVALID_STATE）", rb2["results"][0]["ok"] is False and rb2["results"][0]["error"]["code"] == "INVALID_STATE")
        r, data = req("POST", "/api/workbench/retry-batch", {"job_ids": []})
        check("retry-batch 空数组 → 422 VALIDATION_ERROR", r.status == 422 and json.loads(data).get("code") == "VALIDATION_ERROR", f"status={r.status}")
        r, data = req("GET", "/api/workbench/exceptions?page=1&page_size=20")
        exc_after = json.loads(data)
        check("retry-batch 后异常清单 3→0（三个异常任务均已批量恢复）", exc_after["total"] == 0, f"total={exc_after['total']}")

        # ---- 4. preview ----
        r, data = req("GET", f"/api/assets/{ids['image_id']}/preview")
        png = bytes.fromhex(
            "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
            "0000000a49444154789c63000100000500010d0a2db40000000049454e44ae426082"
        )
        check("preview image → 200 + image/png + 内容一致",
              r.status == 200 and r.getheader("Content-Type", "").startswith("image/png") and data == png,
              f"status={r.status} ct={r.getheader('Content-Type')} len={len(data)}")
        r, data = req("GET", f"/api/assets/{ids['video_id']}/preview")
        check("preview video → 400 INVALID_STATE", r.status == 400 and json.loads(data).get("code") == "INVALID_STATE", f"status={r.status}")
        r, data = req("GET", "/api/assets/99999/preview")
        check("preview 不存在 → 404", r.status == 404, f"status={r.status}")

        # ---- 5. campaigns product_name ----
        r, data = req("GET", "/api/ads/campaigns?page=1&page_size=20")
        cams = json.loads(data)["items"]
        by_cid = {c["id"]: c for c in cams}
        join_cam = by_cid[ids["campaign_join"]]
        null_cam = by_cid[ids["campaign_null"]]
        check("campaigns 每项含 product_name 键", "product_name" in join_cam and "product_name" in null_cam)
        check("campaigns join 命中 → M1 title", join_cam["product_name"] == "免打孔卫生间置物架 浴室收纳架",
              f"product_name={join_cam['product_name']!r}")
        check("campaigns 商品缺失 → product_name=null", null_cam["product_name"] is None)

        print(f"\n结果：{len(PASSED)} passed / {len(FAILED)} failed")
        return 0 if not FAILED else 1
    finally:
        try:
            conn.close()
        except Exception:
            pass
        server.terminate()
        try:
            server.wait(timeout=10)
        except subprocess.TimeoutExpired:
            server.kill()
        shutil.rmtree(workdir, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
