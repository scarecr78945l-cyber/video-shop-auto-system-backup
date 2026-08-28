"""M3 上传素材库 upload（v1.0 集成任务 3 · 子代理-F）测试。

覆盖 REC-002 双轨 UploadService（api|ui|semi）全部 fixtures/模拟路径：
1. 工厂 create_uploader：api/ui/semi 类型、config.upload.mode 默认、非法 mode 抛 ValueError；
2. ApiUploader mock：确定性 platform_material_id、落 opt_upload_records、
   AUTH_REQUIRED 不重试转人工 / RATE_LIMIT 180s 退避（sleep_fn 可测）/ PLATFORM_REJECT /
   TIMEOUT / UNEXPECTED 错误码正确且留证据；
3. UiUploader：PageOps 协议注入 + MockPageOps 调用留痕、page_changed 检测（P-003）、
   选择器配置化、错误分类；
4. SemiUploader：waiting_manual 状态 + 预填清单（file_path/预填字段/人工确认点）；
5. upload_batch：≤50/批、batch_no 递增、单条失败隔离（含 service 抛异常）、item_interval；
6. 无明文密钥、零真实网络（post/page_ops 全注入，源码无 requests/httpx/playwright）。

运行：cd backend && python -m pytest tests/test_optimization_upload.py -q --basetemp=".pytest-tmp-m3"
（P-001/P-011：必须本模块独立 basetemp，禁止共用 .pytest-tmp）
"""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError
from sqlalchemy import select

from optimization import tables
from optimization.config import UploadSpec, load_config
from optimization.db import Database
from optimization.upload import (
    ERR_AUTH_REQUIRED,
    ERR_NO_MATCH,
    ERR_PLATFORM_REJECT,
    ERR_RATE_LIMIT,
    ERR_TIMEOUT,
    ERR_UNEXPECTED,
    ApiUploader,
    MockPageOps,
    PageOps,
    SemiManifest,
    SemiUploader,
    UiUploader,
    UploadApiError,
    UploadRepo,
    UploadResult,
    UploadService,
    create_uploader,
    derive_target_id,
    deterministic_material_id,
    upload_batch,
)
from optimization.upload.ui import DEFAULT_SELECTORS

PACKAGE_DIR = Path(__file__).resolve().parent.parent / "optimization" / "upload"


# ---------------------------------------------------------------- fixtures


@pytest.fixture
def cfg(tmp_path):
    """内存库 + 临时 data_dir（P-011：不碰 .pytest-tmp 文件锁）。"""
    return load_config(db_url="sqlite:///:memory:", data_dir=tmp_path / "data")


@pytest.fixture
def db(cfg):
    database = Database(cfg)
    database.create_all()
    return database


@pytest.fixture(autouse=True)
def _offline_env(monkeypatch):
    """零密钥零网络：删除全部相关环境变量，保证 config/uploader 默认路径确定。"""
    for key in (
        "M3_UPLOAD_MODE", "M3_PLATFORM_TOKEN",
        "DEEPSEEK_API_KEY", "KIMI_API_KEY", "WAN_API_KEY",
    ):
        monkeypatch.delenv(key, raising=False)


def _record_rows(db) -> list:
    with db.session() as s:
        return list(s.execute(select(tables.OptUploadRecord)).scalars().all())


def _sleep_recorder():
    slept: list[float] = []
    return slept, lambda s: slept.append(float(s))


# ---------------------------------------------------------------- 工厂（验收 2）


def test_factory_returns_api():
    assert isinstance(create_uploader("api"), ApiUploader)


def test_factory_returns_ui():
    assert isinstance(create_uploader("ui"), UiUploader)


def test_factory_returns_semi():
    assert isinstance(create_uploader("semi"), SemiUploader)


def test_factory_mode_case_insensitive():
    assert isinstance(create_uploader("API"), ApiUploader)
    assert isinstance(create_uploader(" UI "), UiUploader)


def test_factory_default_mode_from_config():
    # 环境变量隔离后默认 config.upload.mode = api
    assert isinstance(create_uploader(), ApiUploader)
    # 显式覆盖 config → semi
    cfg_semi = load_config(upload=UploadSpec(mode="semi"))
    assert isinstance(create_uploader(config=cfg_semi), SemiUploader)


def test_factory_invalid_mode_raises():
    for bad in ("ftp", "batch", "xxx", "api2"):
        with pytest.raises(ValueError):
            create_uploader(bad)


def test_factory_invalid_config_mode_raises():
    cfg_bad = load_config(upload=UploadSpec(mode="ftp"))
    with pytest.raises(ValueError):
        create_uploader(config=cfg_bad)


def test_factory_injects_post_and_page_ops(cfg):
    post_called = {"n": 0}

    def post(url, payload, headers=None, timeout=None):
        post_called["n"] += 1
        return {"ok": True, "platform_material_id": "material_injected"}

    api = create_uploader("api", config=cfg, post=post)
    assert api.upload_video("a.mp4", {}).platform_material_id == "material_injected"
    assert post_called["n"] == 1

    ops = MockPageOps(material_id="material_ui")
    ui = create_uploader("ui", config=cfg, page_ops=ops)
    assert ui.upload_video("a.mp4", {}).platform_material_id == "material_ui"


# ---------------------------------------------------------------- ApiUploader（验收 3）


def test_api_success_deterministic_id(cfg):
    api = ApiUploader(cfg)
    r1 = api.upload_video("v/2025/v1.mp4", {"title": "陶瓷杯", "variant_id": "vv_1"})
    r2 = api.upload_video("v/2025/v1.mp4", {"title": "陶瓷杯", "variant_id": "vv_1"})
    assert r1.ok
    assert r1.platform_material_id.startswith("material_")
    assert len(r1.platform_material_id) == len("material_") + 8
    assert r1.platform_material_id == r2.platform_material_id  # 幂等确定


def test_api_success_different_meta_different_id(cfg):
    api = ApiUploader(cfg)
    a = api.upload_video("v1.mp4", {"title": "标题A"}).platform_material_id
    b = api.upload_video("v1.mp4", {"title": "标题B"}).platform_material_id
    assert a != b


def test_api_success_persists_record(cfg, db):
    api = ApiUploader(cfg, db=db)
    r = api.upload_video("v1.mp4", {"variant_id": "vv_9", "title": "陶瓷杯"})
    rows = _record_rows(db)
    assert len(rows) == 1
    row = rows[0]
    assert row.status == "success"
    assert row.mode == "api"
    assert row.batch_no == 1
    assert row.target_type == "video"
    assert row.target_id == "vv_9"
    assert row.platform_material_id == r.platform_material_id
    assert row.error_code == ""
    assert row.evidence_json["endpoint"].endswith("/material/upload")


def test_api_image_persists(cfg, db):
    api = ApiUploader(cfg, db=db)
    api.upload_image("img/main1.png", {"image_id": "img_1", "image_type": "main"})
    rows = _record_rows(db)
    assert rows[0].target_type == "image"
    assert rows[0].target_id == "img_1"


def test_api_auth_required_no_retry_manual(cfg, db):
    calls = {"n": 0}
    slept, sleep_fn = _sleep_recorder()

    def post(url, payload, headers=None, timeout=None):
        calls["n"] += 1
        return {"ok": False, "error_code": "AUTH_REQUIRED", "message": "登录态失效"}

    api = ApiUploader(cfg, db=db, post=post, sleep_fn=sleep_fn)
    r = api.upload_video("v1.mp4", {})
    assert not r.ok
    assert r.error_code == ERR_AUTH_REQUIRED
    assert calls["n"] == 1            # 不自动重试（P-002）
    assert slept == []                # 无退避等待
    assert r.evidence["manual_handoff"] is True
    assert r.evidence["retried"] is False
    row = _record_rows(db)[0]
    assert row.error_code == ERR_AUTH_REQUIRED
    assert row.status == "failed"


def test_api_rate_limit_backoff_then_success(cfg):
    calls = {"n": 0}
    slept, sleep_fn = _sleep_recorder()

    def post(url, payload, headers=None, timeout=None):
        calls["n"] += 1
        if calls["n"] == 1:
            return {"ok": False, "error_code": "RATE_LIMIT", "retry_after": 180}
        return {"ok": True, "platform_material_id": "material_ok"}

    api = ApiUploader(cfg, post=post, sleep_fn=sleep_fn, rate_limit_backoff_seconds=180.0)
    r = api.upload_video("v1.mp4", {})
    assert r.ok
    assert calls["n"] == 2
    assert slept == [180.0]           # 180s 退避一次
    assert r.evidence["attempts"] == 2
    assert r.evidence["retried"] is True


def test_api_rate_limit_retry_after_custom(cfg):
    calls = {"n": 0}
    slept, sleep_fn = _sleep_recorder()

    def post(url, payload, headers=None, timeout=None):
        calls["n"] += 1
        if calls["n"] == 1:
            return {"ok": False, "error_code": "RATE_LIMIT", "retry_after": 45}
        return {"ok": True}

    api = ApiUploader(cfg, post=post, sleep_fn=sleep_fn)
    r = api.upload_video("v1.mp4", {})
    assert r.ok
    assert slept == [45.0]            # 优先取平台 retry_after


def test_api_rate_limit_exhausted(cfg, db):
    calls = {"n": 0}
    slept, sleep_fn = _sleep_recorder()

    def post(url, payload, headers=None, timeout=None):
        calls["n"] += 1
        return {"ok": False, "error_code": "RATE_LIMIT"}

    api = ApiUploader(cfg, db=db, post=post, sleep_fn=sleep_fn, max_retries=2)
    r = api.upload_video("v1.mp4", {})
    assert not r.ok
    assert r.error_code == ERR_RATE_LIMIT
    assert calls["n"] == 3            # 初始 + 2 次重试
    assert slept == [180.0, 180.0]    # 每次退避 180s（默认）
    assert r.evidence["attempts"] == 3
    row = _record_rows(db)[0]
    assert row.error_code == ERR_RATE_LIMIT


def test_api_rate_limit_no_retry_when_max_retries_zero(cfg):
    calls = {"n": 0}
    slept, sleep_fn = _sleep_recorder()

    def post(url, payload, headers=None, timeout=None):
        calls["n"] += 1
        return {"ok": False, "error_code": "RATE_LIMIT"}

    api = ApiUploader(cfg, post=post, sleep_fn=sleep_fn, max_retries=0)
    r = api.upload_video("v1.mp4", {})
    assert r.error_code == ERR_RATE_LIMIT
    assert calls["n"] == 1
    assert slept == []


def test_api_platform_reject(cfg, db):
    def post(url, payload, headers=None, timeout=None):
        return {"ok": False, "error_code": "PLATFORM_REJECT", "message": "素材审核不通过",
                "reasons": ["画面模糊", "字幕含供应链词"]}

    api = ApiUploader(cfg, db=db, post=post)
    r = api.upload_video("v1.mp4", {})
    assert not r.ok
    assert r.error_code == ERR_PLATFORM_REJECT
    assert r.evidence["response"]["reasons"] == ["画面模糊", "字幕含供应链词"]
    assert r.evidence["manual_handoff"] is False  # 拒审不转人工自动重试，留证据待处理（P-007）
    assert _record_rows(db)[0].error_code == ERR_PLATFORM_REJECT


def test_api_timeout_via_raise(cfg):
    def post(url, payload, headers=None, timeout=None):
        raise UploadApiError(ERR_TIMEOUT, "平台响应超时")

    api = ApiUploader(cfg, post=post)
    r = api.upload_video("v1.mp4", {})
    assert r.error_code == ERR_TIMEOUT
    assert "超时" in r.evidence["response"]["message"]


def test_api_unexpected_exception(cfg, db):
    def post(url, payload, headers=None, timeout=None):
        raise RuntimeError("boom")

    api = ApiUploader(cfg, db=db, post=post)
    r = api.upload_video("v1.mp4", {})
    assert not r.ok
    assert r.error_code == ERR_UNEXPECTED
    assert "boom" in r.evidence["response"]["message"]
    assert _record_rows(db)[0].status == "failed"


def test_api_request_log_evidence(cfg):
    api = ApiUploader(cfg)
    api.upload_video("v1.mp4", {"title": "陶瓷杯", "variant_id": "vv_1"})
    assert len(api.request_log) == 1
    req = api.last_request
    assert req["method"] == "POST"
    assert req["payload"]["file_path"] == "v1.mp4"
    assert req["payload"]["material"]["title"] == "陶瓷杯"
    assert "variant_id" not in req["payload"]["material"]  # 身份字段不进物料载荷
    assert "headers" not in req                      # 请求记录不含 header（防令牌泄漏）
    assert "Authorization" not in str(api.last_response)


def test_upload_result_error_code_validation():
    assert UploadResult(error_code="AUTH_REQUIRED").error_code == "AUTH_REQUIRED"
    assert UploadResult().error_code == ""
    with pytest.raises(ValidationError):
        UploadResult(error_code="BAD_CODE")
    with pytest.raises(ValidationError):
        UploadResult(status="bogus")


# ---------------------------------------------------------------- UiUploader（验收 4）


def test_ui_success_records_calls(cfg, db):
    ops = MockPageOps(material_id="material_ui_123")
    api = UiUploader(cfg, db=db, page_ops=ops)
    r = api.upload_video("v1.mp4", {"title": "陶瓷杯"})
    assert r.ok
    assert r.platform_material_id == "material_ui_123"
    ops_list = [c["op"] for c in ops.calls]
    assert "goto" in ops_list
    assert "fill" in ops_list
    assert "click" in ops_list
    fills = [c for c in ops.calls if c["op"] == "fill"]
    assert fills[0]["selector"] == DEFAULT_SELECTORS["file_input"]
    assert fills[0]["value"] == "v1.mp4"
    assert fills[1]["selector"] == DEFAULT_SELECTORS["title_input"]
    assert fills[1]["value"] == "陶瓷杯"
    row = _record_rows(db)[0]
    assert row.mode == "ui"
    assert row.status == "success"
    assert "ops_calls" in r.evidence


def test_ui_success_deterministic_fallback(cfg):
    ops = MockPageOps()  # 页面未返回素材 ID
    api = UiUploader(cfg, page_ops=ops)
    r = api.upload_video("v1.mp4", {"title": "陶瓷杯"})
    assert r.ok
    assert r.platform_material_id == deterministic_material_id("v1.mp4", {"title": "陶瓷杯"})
    assert r.evidence["material_id_source"] == "deterministic"


def test_ui_page_changed_detection(cfg, db):
    anchor = DEFAULT_SELECTORS["page_anchors"][0]
    ops = MockPageOps(missing_selectors=[anchor])
    api = UiUploader(cfg, db=db, page_ops=ops)
    r = api.upload_video("v1.mp4", {})
    assert not r.ok
    assert r.error_code == ERR_NO_MATCH              # page_changed → NO_MATCH（P-003）
    assert r.evidence["page_changed"] is True
    assert r.evidence["missing"] == [anchor]
    assert r.evidence["screenshot_path"].endswith("page_changed.png")
    assert any(c["op"] == "screenshot" for c in ops.calls)   # 截图留证
    row = _record_rows(db)[0]
    assert row.error_code == ERR_NO_MATCH


def test_ui_auth_required_manual(cfg):
    ops = MockPageOps(fail_code=ERR_AUTH_REQUIRED)
    api = UiUploader(cfg, page_ops=ops)
    r = api.upload_video("v1.mp4", {})
    assert r.error_code == ERR_AUTH_REQUIRED
    assert r.evidence["manual_handoff"] is True
    assert "登录" in r.evidence["error_text"]


def test_ui_platform_reject(cfg):
    ops = MockPageOps(fail_code=ERR_PLATFORM_REJECT)
    api = UiUploader(cfg, page_ops=ops)
    r = api.upload_video("v1.mp4", {})
    assert r.error_code == ERR_PLATFORM_REJECT
    assert "审核" in r.evidence["error_text"]


def test_ui_rate_limit_no_auto_retry(cfg):
    ops = MockPageOps(fail_code=ERR_RATE_LIMIT)
    api = UiUploader(cfg, page_ops=ops)
    r = api.upload_video("v1.mp4", {})
    assert r.error_code == ERR_RATE_LIMIT
    assert r.evidence["retried"] is False  # UI 兜底不自动重试（节流由编排层承担）


def test_ui_timeout(cfg):
    ops = MockPageOps(timeout_selectors=[DEFAULT_SELECTORS["file_input"]])
    api = UiUploader(cfg, page_ops=ops)
    r = api.upload_video("v1.mp4", {})
    assert r.error_code == ERR_TIMEOUT
    assert r.evidence["timeout_selector"] == DEFAULT_SELECTORS["file_input"]


def test_ui_custom_selectors(cfg):
    ops = MockPageOps(material_id="material_custom")
    selectors = {
        "page_anchors": [],                       # 无锚点 → 签名校验跳过
        "file_input": "#custom-file",
        "title_input": "#custom-title",
        "submit": "#custom-submit",
        "result_id": "#custom-result",
        "error_box": ".custom-error",
    }
    api = UiUploader(cfg, page_ops=ops, selectors=selectors)
    r = api.upload_video("v1.mp4", {"title": "T"})
    assert r.ok and r.platform_material_id == "material_custom"
    fills = [c for c in ops.calls if c["op"] == "fill"]
    assert fills[0]["selector"] == "#custom-file"
    assert any(c["op"] == "click" and c["selector"] == "#custom-submit" for c in ops.calls)


def test_ui_page_ops_protocol_runtime():
    assert isinstance(MockPageOps(), PageOps)      # runtime_checkable 协议


def test_ui_image_flow(cfg, db):
    ops = MockPageOps(material_id="material_img")
    api = UiUploader(cfg, db=db, page_ops=ops)
    r = api.upload_image("img/main1.png", {"image_id": "img_1"})
    assert r.ok
    assert r.platform_material_id == "material_img"
    assert _record_rows(db)[0].target_type == "image"


# ---------------------------------------------------------------- SemiUploader（验收 5）


def test_semi_waiting_manual_result(cfg, db):
    semi = SemiUploader(cfg, db=db)
    r = semi.upload_video("v1.mp4", {"title": "陶瓷杯", "variant_id": "vv_1"})
    assert r.status == "waiting_manual"
    assert not r.ok
    assert r.error_code == ""
    assert r.evidence["pending_manual"] is True
    assert len(r.evidence["confirm_points"]) >= 3   # 人工确认点非空
    assert r.evidence["manifest_entry"]["file_path"] == "v1.mp4"
    assert r.evidence["manifest_entry"]["prefilled"]["title"] == "陶瓷杯"
    row = _record_rows(db)[0]
    assert row.status == "waiting_manual"
    assert row.mode == "semi"
    assert row.platform_material_id == ""
    assert row.target_id == "vv_1"


def test_semi_upload_image(cfg, db):
    semi = SemiUploader(cfg, db=db)
    r = semi.upload_image("img/main1.png", {"image_id": "img_1"})
    assert r.status == "waiting_manual"
    assert _record_rows(db)[0].target_type == "image"
    assert _record_rows(db)[0].target_id == "img_1"


def test_semi_build_manifest(cfg):
    semi = SemiUploader(cfg)
    manifest = semi.build_manifest(
        [
            {"file_path": "v1.mp4", "target_type": "video", "meta": {"title": "陶瓷杯", "category": "家居日用"}},
            {"file_path": "img/main1.png", "target_type": "image", "meta": {"image_type": "main"}},
        ],
        batch_no=3,
    )
    assert isinstance(manifest, SemiManifest)
    assert manifest.mode == "semi"
    assert manifest.batch_no == 3
    assert len(manifest.entries) == 2
    e0 = manifest.entries[0]
    assert e0.file_path == "v1.mp4"
    assert e0.target_type == "video"
    assert e0.prefilled["title"] == "陶瓷杯"
    assert e0.prefilled["category"] == "家居日用"
    assert e0.prefilled["file_name"] == "v1.mp4"
    assert len(e0.confirm_points) >= 3
    assert manifest.entries[1].target_type == "image"
    assert "main1.png" in manifest.entries[1].prefilled["file_name"]


def test_semi_confirm_points_configurable(cfg):
    points = ["确认A", "确认B"]
    semi = SemiUploader(cfg, confirm_points=points)
    r = semi.upload_video("v1.mp4", {})
    assert r.evidence["confirm_points"] == points


# ---------------------------------------------------------------- upload_batch（验收 6）


def test_batch_serial_success(cfg, db):
    api = ApiUploader(cfg, db=db)
    items = [
        {"file_path": "v1.mp4", "meta": {"variant_id": "vv_1", "title": "T1"}},
        {"file_path": "v2.mp4", "meta": {"variant_id": "vv_2", "title": "T2"}},
        {"file_path": "v3.mp4", "meta": {"variant_id": "vv_3", "title": "T3"}},
    ]
    out = upload_batch(api, items)
    assert out["mode"] == "api"
    assert out["total"] == 3
    assert out["success"] == 3 and out["failed"] == 0
    assert len(out["batch_ids"]) == 1
    rows = _record_rows(db)
    assert [r.batch_no for r in rows] == [1, 2, 3]      # batch_no 递增
    assert [r.target_id for r in rows] == ["vv_1", "vv_2", "vv_3"]
    assert all(r.status == "success" for r in rows)


def test_batch_chunking_55_items(cfg, db):
    api = ApiUploader(cfg, db=db)
    items = [{"file_path": f"v{i:02d}.mp4", "meta": {"variant_id": f"vv_{i}"}} for i in range(55)]
    out = upload_batch(api, items)
    assert out["success"] == 55
    assert len(out["batch_ids"]) == 2                    # 50 + 5 两批
    assert out["batch_size"] == 50
    rows = _record_rows(db)
    assert len(rows) == 55
    batch_nos = [r.batch_no for r in rows]
    assert max(batch_nos) == 50                          # batch_no ≤ batch_size
    assert set(batch_nos) == set(range(1, 51)) | set(range(1, 6))
    db_batch_ids = {r.evidence_json.get("batch_id") for r in rows}
    assert db_batch_ids == set(out["batch_ids"])         # 批次身份留痕


def test_batch_failure_isolation(cfg, db):
    def post(url, payload, headers=None, timeout=None):
        if "bad" in str(payload.get("file_path") or ""):
            return {"ok": False, "error_code": "PLATFORM_REJECT", "message": "拒审"}
        return {"ok": True, "platform_material_id": "material_ok"}

    api = ApiUploader(cfg, db=db, post=post)
    items = [
        {"file_path": "ok1.mp4", "meta": {"variant_id": "vv_1"}},
        {"file_path": "bad.mp4", "meta": {"variant_id": "vv_2"}},
        {"file_path": "ok2.mp4", "meta": {"variant_id": "vv_3"}},
    ]
    out = upload_batch(api, items)
    assert out["success"] == 2 and out["failed"] == 1    # 单条失败不阻塞整批
    rows = _record_rows(db)
    assert len(rows) == 3
    bad_row = next(r for r in rows if r.target_id == "vv_2")
    assert bad_row.status == "failed"
    assert bad_row.error_code == ERR_PLATFORM_REJECT


def test_batch_service_raise_is_isolated(cfg, db):
    class _ExplodingUploader(ApiUploader):
        def upload_video(self, file_path, meta, **kw):
            if "explode" in str(file_path):
                raise RuntimeError("boom")
            return super().upload_video(file_path, meta, **kw)

    api = _ExplodingUploader(cfg, db=db)
    items = [
        {"file_path": "ok1.mp4", "meta": {"variant_id": "vv_1"}},
        {"file_path": "explode.mp4", "meta": {"variant_id": "vv_2"}},
        {"file_path": "ok2.mp4", "meta": {"variant_id": "vv_3"}},
    ]
    out = upload_batch(api, items)
    assert out["success"] == 2 and out["failed"] == 1
    rows = _record_rows(db)
    bad_row = next(r for r in rows if r.target_id == "vv_2")
    assert bad_row.error_code == ERR_UNEXPECTED
    assert bad_row.evidence_json.get("isolated") is True
    assert bad_row.batch_no == 2                      # 失败项仍在批内占位编号


def test_batch_batch_size_validation(cfg):
    api = ApiUploader(cfg)
    items = [{"file_path": "v1.mp4", "meta": {}}]
    with pytest.raises(ValueError):
        upload_batch(api, items, batch_size=0)
    with pytest.raises(ValueError):
        upload_batch(api, items, batch_size=51)          # P-006 ≤50/批
    upload_batch(api, items, batch_size=50)              # 边界合法


def test_batch_item_interval_sleep(cfg):
    slept, sleep_fn = _sleep_recorder()
    api = ApiUploader(cfg)
    items = [{"file_path": f"v{i}.mp4", "meta": {}} for i in range(3)]
    upload_batch(api, items, sleep_fn=sleep_fn, item_interval_s=0.5)
    assert slept == [0.5, 0.5]                           # 3 项 → 2 次节流间隔


def test_batch_mixed_target_types(cfg, db):
    api = ApiUploader(cfg, db=db)
    items = [
        {"file_path": "v1.mp4", "target_type": "video", "meta": {"variant_id": "vv_1"}},
        {"file_path": "img/main1.png", "target_type": "image", "meta": {"image_id": "img_1"}},
    ]
    out = upload_batch(api, items)
    assert out["success"] == 2
    rows = _record_rows(db)
    assert {r.target_type for r in rows} == {"video", "image"}


def test_batch_no_db_still_runs(cfg):
    api = ApiUploader(cfg)                                # 无 db/repo：纯计算模式
    items = [{"file_path": "v1.mp4", "meta": {}}, {"file_path": "v2.mp4", "meta": {}}]
    out = upload_batch(api, items)
    assert out["success"] == 2 and out["total"] == 2


def test_batch_invalid_item(cfg):
    api = ApiUploader(cfg)
    with pytest.raises(ValueError):
        upload_batch(api, [{"meta": {}}])                 # 缺 file_path
    with pytest.raises(ValueError):
        upload_batch(api, [{"file_path": "x", "target_type": "audio"}])  # 非法类型


def test_batch_semi_waiting_manual_count(cfg, db):
    semi = SemiUploader(cfg, db=db)
    items = [{"file_path": f"v{i}.mp4", "meta": {"variant_id": f"vv_{i}"}} for i in range(3)]
    out = upload_batch(semi, items)
    assert out["waiting_manual"] == 3 and out["success"] == 0
    assert all(r.status == "waiting_manual" for r in _record_rows(db))


# ---------------------------------------------------------------- 落库与纪律（验收 1/7）


def test_upload_repo_record_and_list(db):
    repo = UploadRepo(db)
    r1 = UploadResult(status="success", platform_material_id="material_a",
                      evidence={"note": "ok"})
    r2 = UploadResult(status="failed", error_code="TIMEOUT", evidence={"note": "x"})
    repo.record(target_type="video", target_id="vv_1", result=r1, batch_no=1, mode="api")
    repo.record(target_type="image", target_id="img_1", result=r2, batch_no=2, mode="ui")
    assert repo.count() == 2
    assert repo.count(mode="api") == 1
    recent = repo.list_recent(limit=10)
    assert len(recent) == 2
    by_target = {d["target_id"]: d for d in recent}
    assert by_target["vv_1"]["status"] == "success"
    assert by_target["vv_1"]["platform_material_id"] == "material_a"
    assert by_target["vv_1"]["evidence_json"]["note"] == "ok"
    assert by_target["img_1"]["error_code"] == "TIMEOUT"
    assert by_target["img_1"]["batch_no"] == 2


def test_upload_package_exports():
    from optimization import upload

    for name in (
        "UploadService", "UploadResult", "ApiUploader", "UiUploader", "SemiUploader",
        "create_uploader", "upload_batch", "PageOps", "MockPageOps", "PageChangedError",
        "SemiManifest", "UploadRepo", "ERR_AUTH_REQUIRED", "ERR_RATE_LIMIT",
        "ERR_TIMEOUT", "ERR_PLATFORM_REJECT", "ERR_UNEXPECTED", "ERR_NO_MATCH",
    ):
        assert hasattr(upload, name), name


def test_no_network_imports_and_no_plaintext_key():
    """零真实网络 + 无明文密钥（P-004）：源码不得 import 网络/浏览器库，不得含密钥样。"""
    sources = "\n".join(
        p.read_text(encoding="utf-8") for p in sorted(PACKAGE_DIR.glob("*.py"))
    )
    for banned in ("import requests", "import httpx", "import urllib",
                   "import playwright", "from playwright", "import aiohttp"):
        assert banned not in sources, banned
    import re

    assert not re.search(r"\b(sk-[A-Za-z0-9]{16,}|[0-9a-fA-F]{32,})\b", sources)
    api_src = (PACKAGE_DIR / "api.py").read_text(encoding="utf-8")
    assert "M3_PLATFORM_TOKEN" in api_src               # 密钥只出现环境变量名
    assert "os.environ.get" in api_src                  # 值经环境变量读取，不硬编码
