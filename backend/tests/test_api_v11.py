"""API 层测试 · v1.1 增强（test_api_v11.py）。

覆盖（总控派发 5 项）：
1. products keyword 服务端过滤（命中/未命中/组合/大小写不敏感）+ page/page_size 信封迁移；
2. jobs keyword（product_id 字符串/error_message）+ limit 硬上限；
3. POST /api/workbench/retry-batch 批量接管（混合成功/409/404、空数组 422、超 100 422、
   幂等、单 job 失败不影响其他、审计留痕、未登录 401）；
4. GET /api/assets/{id}/preview 图片预览媒体端点（image 200 流 + Content-Type、video 400、
   不存在 404、路径穿越防护、无存储配置 503）；
5. ads/campaigns product_name 跨库 join（有商品/无商品→null/M1 库不可用→全 null）；
6. 分页信封一致性抽查（≥3 端点 {total,page,page_size,items} + ads/report 例外登记）。
"""

from __future__ import annotations

import pytest

from tests.api_testing import login, make_client, seed_all, seed_m2, seed_m5


@pytest.fixture()
def ctx(tmp_path):
    client, services, creds, viewer_creds = make_client(tmp_path)
    with client:
        assert login(client, creds).status_code == 200
        seed_all(services)
        yield client, services, creds


# ================================================================ 1. products keyword


def test_products_keyword_hit_and_miss(ctx):
    c, services, creds = ctx
    resp = c.get("/api/products", params={"keyword": "喂食器"})
    body = resp.json()
    assert body["total"] == 1
    assert "猫咪自动喂食器" in body["items"][0]["title"]
    resp2 = c.get("/api/products", params={"keyword": "不存在的关键词xyz"})
    assert resp2.json()["total"] == 0


def test_products_keyword_combined_filters(ctx):
    c, services, creds = ctx
    # keyword + category 组合（命中/不命中）
    resp = c.get("/api/products", params={"keyword": "置物架", "category": "收纳整理"})
    assert resp.json()["total"] == 1
    resp2 = c.get("/api/products", params={"keyword": "置物架", "category": "宠物用品"})
    assert resp2.json()["total"] == 0
    # keyword + score 区间
    resp3 = c.get("/api/products", params={"keyword": "喂食器", "min_score": 70, "max_score": 80})
    assert resp3.json()["total"] == 1
    resp4 = c.get("/api/products", params={"keyword": "喂食器", "min_score": 80, "max_score": 90})
    assert resp4.json()["total"] == 0
    # keyword + state
    resp5 = c.get("/api/products", params={"keyword": "置物架", "state": "pool"})
    assert resp5.json()["total"] == 1


def test_products_page_page_size_envelope(ctx):
    c, services, creds = ctx
    resp = c.get("/api/products", params={"page": 1, "page_size": 2})
    assert resp.status_code == 200
    body = resp.json()
    assert set(body.keys()) >= {"total", "page", "page_size", "items"}
    assert body["page"] == 1 and body["page_size"] == 2
    assert len(body["items"]) == 2
    # 第二页
    resp2 = c.get("/api/products", params={"page": 2, "page_size": 2})
    body2 = resp2.json()
    assert body2["total"] == 3 and body2["page"] == 2 and len(body2["items"]) == 1
    assert {i["id"] for i in body["items"]}.isdisjoint({i["id"] for i in body2["items"]})
    # 非法分页 → 422
    assert c.get("/api/products", params={"page": 0}).status_code == 422
    assert c.get("/api/products", params={"page_size": 101}).status_code == 422


# ================================================================ 2. jobs keyword/limit


def test_jobs_keyword_product_id(ctx):
    c, services, creds = ctx
    # product_id 数字字符串模糊匹配：seed_m0 的 job product_id 为 101/102/103
    resp = c.get("/api/jobs", params={"keyword": "101"})
    body = resp.json()
    assert body["total"] == 1
    assert body["items"][0]["product_id"] == 101
    resp2 = c.get("/api/jobs", params={"keyword": "10"})
    assert resp2.json()["total"] == 3
    resp3 = c.get("/api/jobs", params={"keyword": "999"})
    assert resp3.json()["total"] == 0


def test_jobs_keyword_error_message(ctx):
    c, services, creds = ctx
    resp = c.get("/api/jobs", params={"keyword": "验证码"})
    body = resp.json()
    assert body["total"] == 1
    assert body["items"][0]["error_message"] == "需要验证码"
    resp2 = c.get("/api/jobs", params={"keyword": "平台驳回"})
    assert resp2.json()["total"] == 1
    # 与既有过滤组合：keyword + status
    resp3 = c.get("/api/jobs", params={"keyword": "验证码", "status": "blocked"})
    assert resp3.json()["total"] == 0


def test_jobs_limit_param(ctx):
    c, services, creds = ctx
    resp = c.get("/api/jobs", params={"limit": 1})
    body = resp.json()
    assert len(body["items"]) <= 1
    assert body["total"] == 3
    assert body["page"] == 1 and body["page_size"] == 20
    # limit 上限内不截断（≥ job 数）
    resp2 = c.get("/api/jobs", params={"limit": 500})
    assert len(resp2.json()["items"]) == 3
    # 非法 limit → 422
    assert c.get("/api/jobs", params={"limit": 0}).status_code == 422
    assert c.get("/api/jobs", params={"limit": 501}).status_code == 422


# ================================================================ 3. retry-batch


def _job_id_by_status(c, status: str) -> int:
    return c.get("/api/jobs", params={"status": status}).json()["items"][0]["id"]


def test_retry_batch_mixed_results(ctx):
    """混合：成功(ok) + 已恢复 409(INVALID_STATE) + 不存在 404(NO_MATCH)，整体 200。"""
    c, services, creds = ctx
    wv = _job_id_by_status(c, "waiting_verification")
    ok_job = _job_id_by_status(c, "success")
    resp = c.post("/api/workbench/retry-batch", json={"job_ids": [wv, ok_job, 999999]})
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert body["total"] == 3 and body["success_count"] == 1
    by_id = {r["job_id"]: r for r in body["results"]}
    assert by_id[wv]["ok"] is True and by_id[wv]["status"] == "pending"
    assert by_id[ok_job]["ok"] is False
    assert by_id[ok_job]["error"]["code"] == "INVALID_STATE"
    assert by_id[999999]["ok"] is False
    assert by_id[999999]["error"]["code"] == "NO_MATCH"
    # 单 job 失败不影响其他：wv 已成功恢复，不再出现在异常中心
    assert c.get("/api/workbench/exceptions", params={"status": "waiting_verification"}).json()["total"] == 0
    # 成功 job 走既有审计留痕
    logs = c.get("/api/logs").json()["items"]
    assert any("人工接管后重试" in item["message"] for item in logs)


def test_retry_batch_blocked_retryable(ctx):
    c, services, creds = ctx
    blocked = _job_id_by_status(c, "blocked")
    resp = c.post("/api/workbench/retry-batch", json={"job_ids": [blocked]})
    assert resp.status_code == 200
    result = resp.json()["results"][0]
    assert result["ok"] is True and result["status"] == "pending"


def test_retry_batch_empty_422(ctx):
    c, services, creds = ctx
    resp = c.post("/api/workbench/retry-batch", json={"job_ids": []})
    assert resp.status_code == 422
    assert resp.json()["code"] == "VALIDATION_ERROR"


def test_retry_batch_over_100_422(ctx):
    c, services, creds = ctx
    resp = c.post("/api/workbench/retry-batch", json={"job_ids": list(range(1, 102))})
    assert resp.status_code == 422
    assert resp.json()["code"] == "VALIDATION_ERROR"


def test_retry_batch_idempotent(ctx):
    """幂等：批量中已恢复的 job → ok:false + INVALID_STATE，整体仍 200。"""
    c, services, creds = ctx
    wv = _job_id_by_status(c, "waiting_verification")
    resp1 = c.post("/api/workbench/retry-batch", json={"job_ids": [wv]})
    assert resp1.json()["results"][0]["ok"] is True
    # 再次批量（含已恢复 job + 另一个仍可重试的 blocked job）
    blocked = _job_id_by_status(c, "blocked")
    resp2 = c.post("/api/workbench/retry-batch", json={"job_ids": [wv, blocked]})
    assert resp2.status_code == 200
    by_id = {r["job_id"]: r for r in resp2.json()["results"]}
    assert by_id[wv]["ok"] is False and by_id[wv]["error"]["code"] == "INVALID_STATE"
    assert by_id[blocked]["ok"] is True


def test_retry_batch_requires_login(ctx):
    c, services, creds = ctx
    c.cookies.clear()
    resp = c.post("/api/workbench/retry-batch", json={"job_ids": [1]})
    assert resp.status_code == 401
    assert resp.json()["code"] == "AUTH_REQUIRED"


# ================================================================ 4. preview 媒体端点


def _preview_client(tmp_path, monkeypatch, storage_name: str | None = "m2storage"):
    """构造带（或不带）MATERIALS_STORAGE_DIR 注入的客户端（环境变量须在造库前设置）。"""
    storage = None
    if storage_name:
        storage = tmp_path / storage_name
        monkeypatch.setenv("MATERIALS_STORAGE_DIR", str(storage))
        storage.mkdir(parents=True, exist_ok=True)
    client, services, creds, _ = make_client(tmp_path)
    return client, services, creds, storage


def _new_image_asset(services, file_path: str, md5: str, phash: str) -> int:
    return services.materials_repo.create_asset(
        asset_type="image",
        source_platform="测试",
        source_url="https://example.com/preview.png",
        md5=md5,
        phash=phash,
        file_path=file_path,
        size=100,
    )


def test_asset_preview_image_stream(tmp_path, monkeypatch):
    client, services, creds, storage = _preview_client(tmp_path, monkeypatch)
    with client:
        assert login(client, creds).status_code == 200
        ids = seed_m2(services)
        img_bytes = b"\x89PNG\r\n\x1a\n" + b"fake-png-payload"
        target = storage / "images" / "p.jpg"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(img_bytes)
        resp = client.get(f"/api/assets/{ids['image']}/preview")
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "image/jpeg"  # 扩展名 .jpg
        assert resp.content == img_bytes
        # 脱敏：响应体不含绝对路径
        assert str(storage) not in resp.content.decode("latin1", errors="ignore")


def test_asset_preview_video_400(tmp_path, monkeypatch):
    client, services, creds, _ = _preview_client(tmp_path, monkeypatch)
    with client:
        assert login(client, creds).status_code == 200
        ids = seed_m2(services)
        resp = client.get(f"/api/assets/{ids['video']}/preview")
        assert resp.status_code == 400
        assert resp.json()["code"] == "INVALID_STATE"
        assert "仅图片素材可预览" in resp.json()["message"]


def test_asset_preview_asset_not_found_404(tmp_path, monkeypatch):
    client, services, creds, _ = _preview_client(tmp_path, monkeypatch)
    with client:
        assert login(client, creds).status_code == 200
        resp = client.get("/api/assets/999999/preview")
        assert resp.status_code == 404
        assert resp.json()["code"] == "NO_MATCH"


def test_asset_preview_missing_file_404(tmp_path, monkeypatch):
    client, services, creds, storage = _preview_client(tmp_path, monkeypatch)
    with client:
        assert login(client, creds).status_code == 200
        aid = _new_image_asset(services, "images/ghost.png", "e" * 32, "f" * 16)
        resp = client.get(f"/api/assets/{aid}/preview")
        assert resp.status_code == 404
        assert resp.json()["code"] == "NO_MATCH"


def test_asset_preview_path_traversal_404(tmp_path, monkeypatch):
    """路径穿越防护：越界键（../、绝对路径、盘符）→ 404，不泄露文件。"""
    client, services, creds, storage = _preview_client(tmp_path, monkeypatch)
    with client:
        assert login(client, creds).status_code == 200
        evil_file = storage / "evil.txt"
        evil_file.write_text("SECRET_CONTENT")
        # ① ../ 越界键
        aid1 = _new_image_asset(services, "../../evil.txt", "a1" * 16, "b1" * 8)
        resp = client.get(f"/api/assets/{aid1}/preview")
        assert resp.status_code == 404
        assert resp.json()["code"] == "NO_MATCH"
        # ② 绝对路径键（POSIX 风格）
        aid2 = _new_image_asset(services, "/etc/passwd", "a2" * 16, "b2" * 8)
        resp2 = client.get(f"/api/assets/{aid2}/preview")
        assert resp2.status_code == 404
        # ③ 盘符键（Windows 风格）
        aid3 = _new_image_asset(services, "C:/Windows/win.ini", "a3" * 16, "b3" * 8)
        resp3 = client.get(f"/api/assets/{aid3}/preview")
        assert resp3.status_code == 404


def test_asset_preview_no_storage_config_503(tmp_path):
    """存储配置缺失 → 503 明确错误（测试注入：storage_dir 置空）。"""
    client, services, creds, _ = make_client(tmp_path)
    with client:
        assert login(client, creds).status_code == 200
        ids = seed_m2(services)
        services.materials_db.config.storage_dir = None
        resp = client.get(f"/api/assets/{ids['image']}/preview")
        assert resp.status_code == 503
        assert resp.json()["code"] == "UNEXPECTED"
        assert "存储目录未配置" in resp.json()["message"]


def test_asset_preview_requires_login(tmp_path, monkeypatch):
    client, services, creds, _ = _preview_client(tmp_path, monkeypatch)
    with client:
        ids = seed_m2(services)
        resp = client.get(f"/api/assets/{ids['image']}/preview")
        assert resp.status_code == 401
        assert resp.json()["code"] == "AUTH_REQUIRED"


# ================================================================ 5. campaigns product_name


def test_campaigns_product_name_join(tmp_path):
    """跨库 join：M5 ad_campaigns.product_id → M1 products.title；无商品 → null。"""
    from sourcing.tables import Product

    client, services, creds, _ = make_client(tmp_path)
    with client:
        assert login(client, creds).status_code == 200
        ids = seed_m5(services)  # campaigns: product_id 101(active) / 102(paused)
        with services.sourcing_db.session() as session:
            session.add(
                Product(
                    id=101,
                    fingerprint="fp-cam-101",
                    title="托管测试商品A",
                    sanitized_title="托管测试商品A",
                    category="测试",
                    state="pool",
                    compliance_state="candidate",
                    compliance_reasons=[],
                    score=50.0,
                )
            )
        resp = client.get("/api/ads/campaigns")
        assert resp.status_code == 200
        items = {item["id"]: item for item in resp.json()["items"]}
        assert items[ids["active"]]["product_name"] == "托管测试商品A"
        # product 102 在 M1 库不存在 → null
        assert items[ids["paused"]]["product_name"] is None
        # 既有字段不改变
        assert items[ids["active"]]["target_type"] == "roi"
        assert items[ids["active"]]["latest_snapshot"]["spend_yuan"] == 12.9


def test_campaigns_product_name_m1_db_unavailable(tmp_path, monkeypatch):
    """M1 库不可用 → product_name 全 null（不阻塞看板，整体 200）。"""
    client, services, creds, _ = make_client(tmp_path)
    with client:
        assert login(client, creds).status_code == 200
        seed_m5(services)

        def _boom():
            raise RuntimeError("m1 db down")

        monkeypatch.setattr(services.sourcing_db, "session", _boom)
        resp = client.get("/api/ads/campaigns")
        assert resp.status_code == 200
        for item in resp.json()["items"]:
            assert item["product_name"] is None


# ================================================================ 6. 信封一致性抽查


@pytest.mark.parametrize(
    "path",
    [
        "/api/jobs",
        "/api/products",
        "/api/assets",
        "/api/assets/uploads",
        "/api/optimization/batches",
        "/api/listing/tasks",
        "/api/listing/ready",
        "/api/ads/campaigns",
        "/api/workbench/exceptions",
    ],
)
def test_list_envelope_consistency(ctx, path):
    """分页信封一致性：{total, page, page_size, items}（≥3 端点抽查）。"""
    c, services, creds = ctx
    resp = c.get(path)
    assert resp.status_code == 200, f"{path} -> {resp.status_code}"
    body = resp.json()
    assert set(body.keys()) >= {"total", "page", "page_size", "items"}, f"{path} 信封不一致"
    assert body["page"] == 1 and body["page_size"] == 20


def test_ads_report_envelope_exception(ctx):
    """例外登记：ads/report 为 days 聚合信封 {days, total, items}。"""
    c, services, creds = ctx
    resp = c.get("/api/ads/report", params={"days": 7})
    assert resp.status_code == 200
    body = resp.json()
    assert set(body.keys()) >= {"days", "total", "items"}
    assert "page" not in body and "page_size" not in body
