"""M4 上架流水线编排单元测试（端到端模拟：P1 mock adapter + P3 状态机 + P4 拒审，零网络）。

覆盖：happy path 全链状态迁移；gate 失败不入队；驳回分流（retry_candidate / manual）；
幂等；R22 负面（链接验证失败不迁移 listed）；requalify 全链/负路径；RATE_LIMIT
失败留痕（状态停合法位置）；op_log 脱敏摘要。

运行：cd backend && python -m pytest tests/test_listing_pipeline.py -q --basetemp=".pytest-tmp-m4"
"""

import json

import pytest

from adapters.wechat_openapi import (
    TokenBucket,
    WechatOpenApiAdapter,
    WechatOpenApiConfig,
)
from listing.pipeline import ListingPipeline
from listing.platform_rejection import RejectionHandler
from services.listing_gate import (
    ListingCandidate,
    ListingGate,
    PurchaseSettings,
    SkuInput,
)

TITLE_OK = "纯棉加厚家用擦手巾厨房清洁抹布吸水速干"  # 19 字符，无违禁词


# ---------------------------------------------------------------- fixtures


@pytest.fixture()
def gate():
    return ListingGate()


@pytest.fixture()
def adapter():
    return WechatOpenApiAdapter(WechatOpenApiConfig(mode="mock"))


@pytest.fixture()
def pipeline(repo_listing, machine_listing, gate, adapter):
    rejection = RejectionHandler(repo_listing, machine_listing, gate=gate)
    return ListingPipeline(
        gate=gate,
        adapter=adapter,
        repo=repo_listing,
        state_machine=machine_listing,
        rejection=rejection,
    )


# ---------------------------------------------------------------- 工具


def _make_images(tmp_path, n=5, prefix="main"):
    """生成 n 张互不相同的 1:1 PNG（R21 去重通过 + 宽高比通过）。"""
    from PIL import Image

    paths = []
    for i in range(n):
        p = tmp_path / f"{prefix}_{i}.png"
        Image.new("RGB", (100, 100), (10 + i * 40, 20 + i * 30, 30 + i * 20)).save(p)
        paths.append(str(p))
    return paths


def make_candidate(tmp_path, product_id=1001, title=TITLE_OK, **overrides):
    data = dict(
        product_id=product_id,
        title=title,
        category_id=2001,
        category_name="厨房用品",  # 白名单类目
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
    data.update(overrides)
    return ListingCandidate(**data)


def _reject_query(audit_id, task_id=""):
    return {"audit_status": "reject", "reject_reason": "标题含违禁词，请修改后重新提交"}


# ---------------------------------------------------------------- 用例


def test_submit_happy_path_end_to_end(pipeline, repo_listing, tmp_path):
    result = pipeline.submit(make_candidate(tmp_path), generation_version="v1")

    assert result["ok"] is True
    assert result["stage"] == "listed"
    assert result["task_id"]
    assert result["product_link"].startswith("https://channels.weixin.qq.com/shop/goods/")

    task = repo_listing.get_task(result["task_id"])
    assert task.status == "listed"
    assert task.platform_spu_id
    assert task.product_link == result["product_link"]
    assert task.link_verified_at  # R22：链接验证通过时间落库

    # DA-009：SPU/SKU 已落库（listing_spus/listing_skus）——M5 候选池数据源
    spu = repo_listing.get_spu(task.platform_spu_id)
    assert spu is not None
    assert spu["title"] == TITLE_OK
    assert spu["category_id"] == 2001
    assert spu["audit_id"]  # 提交审核后回填 audit_id
    skus = repo_listing.get_skus(task.platform_spu_id)
    assert len(skus) == 1
    assert skus[0]["product_sku_code"] == "SKU-001"
    assert skus[0]["price_cents"] == 2990
    assert skus[0]["cost_cents"] == 1500

    # op_log 证据齐全：状态机迁移 4 条 + adapter 调用留痕
    logs = repo_listing.list_op_logs(result["task_id"])
    transitions = [l for l in logs if l.api == "state_machine"]
    to_statuses = {json.loads(l.evidence_json)["to"] for l in transitions}
    assert {"creating", "draft", "platform_auditing", "listed"} <= to_statuses
    api_calls = {l.api for l in logs if l.direction == "response"}
    assert {"create_spu", "create_skus", "upload_image", "submit_audit",
            "query_audit_status", "get_product_link"} <= api_calls


def test_gate_failure_no_enqueue(pipeline, repo_listing, tmp_path):
    candidate = make_candidate(tmp_path, title="短")  # 标题过短 → 门禁拒绝
    result = pipeline.submit(candidate, generation_version="v1")

    assert result["ok"] is False
    assert result["stage"] == "gate"
    assert result["gate_result"]["passed"] is False
    codes = [i["reason_code"] for i in result["gate_result"]["items"] if not i["passed"]]
    assert "title_length" in codes
    assert repo_listing.get_task_by_product(candidate.product_id, "v1") is None  # 不入队


def test_reject_path_retry_candidate(pipeline, adapter, repo_listing, tmp_path, monkeypatch):
    monkeypatch.setattr(adapter, "query_audit_status", _reject_query)
    result = pipeline.submit(make_candidate(tmp_path), generation_version="v1")

    assert result["ok"] is True
    assert result["stage"] == "retry_candidate"
    assert result["evidence"]["category"] == "title"  # 拒审分类：标题
    task = repo_listing.get_task(result["task_id"])
    assert task.status == "retry_candidate"
    assert task.reject_reason_code == "title"


def test_reject_path_manual(pipeline, adapter, repo_listing, tmp_path, monkeypatch):
    def fake_query(audit_id, task_id=""):
        return {"audit_status": "reject", "reject_reason": "其他原因未说明"}

    monkeypatch.setattr(adapter, "query_audit_status", fake_query)
    result = pipeline.submit(make_candidate(tmp_path), generation_version="v1")

    assert result["ok"] is True
    assert result["stage"] == "manual"  # 无修复候选 → 人工介入
    assert result["evidence"]["category"] == "other"
    task = repo_listing.get_task(result["task_id"])
    assert task.status == "manual"


def test_idempotent_second_submit(pipeline, tmp_path):
    candidate = make_candidate(tmp_path)
    first = pipeline.submit(candidate, generation_version="v1")
    second = pipeline.submit(candidate, generation_version="v1")

    assert second["ok"] is True
    assert second["existing"] is True
    assert second["task_id"] == first["task_id"]
    assert second["status"] == "listed"


def test_r22_link_verifier_false_stays_auditing(
    repo_listing, machine_listing, gate, adapter, tmp_path
):
    rejection = RejectionHandler(repo_listing, machine_listing, gate=gate)
    pipeline = ListingPipeline(
        gate=gate,
        adapter=adapter,
        repo=repo_listing,
        state_machine=machine_listing,
        rejection=rejection,
        link_verifier=lambda url: False,  # 链接验证失败
    )
    result = pipeline.submit(make_candidate(tmp_path), generation_version="v1")

    assert result["ok"] is False
    assert result["stage"] == "link_verify"
    assert result["error_code"] == "UNEXPECTED"
    task = repo_listing.get_task(result["task_id"])
    assert task.status == "platform_auditing"  # 不迁移 listed
    assert task.product_link is None


def test_requalify_and_resubmit_full_chain(
    pipeline, adapter, repo_listing, tmp_path, monkeypatch
):
    monkeypatch.setattr(adapter, "query_audit_status", _reject_query)
    candidate = make_candidate(tmp_path)
    submit_result = pipeline.submit(candidate, generation_version="v1")
    assert submit_result["stage"] == "retry_candidate"
    task_id = submit_result["task_id"]

    monkeypatch.delattr(adapter, "query_audit_status")  # 恢复 mock 默认（pass）
    # 限流窗口重置（重提发生在下一风控周期；mock 每接口令牌桶 capacity=10）
    adapter._buckets["upload_image"] = TokenBucket(
        capacity=10, refill_rate=1.0, tokens=10.0
    )
    requalify_result = pipeline.requalify_and_resubmit(task_id, candidate)

    assert requalify_result["ok"] is True
    assert requalify_result["stage"] == "listed"
    assert requalify_result["task_id"] == task_id  # 复用原任务
    assert requalify_result["product_link"]
    task = repo_listing.get_task(task_id)
    assert task.status == "listed"
    assert task.link_verified_at


def test_requalify_not_retry_candidate(pipeline, tmp_path):
    candidate = make_candidate(tmp_path)
    submit_result = pipeline.submit(candidate, generation_version="v1")
    assert submit_result["stage"] == "listed"

    result = pipeline.requalify_and_resubmit(submit_result["task_id"], candidate)
    assert result["ok"] is False
    assert result["stage"] == "requalify"
    assert result["evidence"]["status"] == "listed"  # 仅 retry_candidate 可重提


def test_requalify_gate_fail(
    pipeline, adapter, repo_listing, tmp_path, monkeypatch
):
    monkeypatch.setattr(adapter, "query_audit_status", _reject_query)
    candidate = make_candidate(tmp_path)
    submit_result = pipeline.submit(candidate, generation_version="v1")
    assert submit_result["stage"] == "retry_candidate"

    bad_candidate = make_candidate(tmp_path, title="短")  # 二次门禁不过
    result = pipeline.requalify_and_resubmit(submit_result["task_id"], bad_candidate)
    assert result["ok"] is False
    assert result["stage"] == "requalify"
    assert result["gate_result"]["passed"] is False
    task = repo_listing.get_task(submit_result["task_id"])
    assert task.status == "retry_candidate"  # 门禁不过不迁移


def test_rate_limit_failure_stays_legal_state(
    pipeline, adapter, repo_listing, tmp_path, monkeypatch
):
    # mock 模式跳过令牌桶限流（P0-1 预填集成后）；用 monkeypatch 模拟
    # live 模式的 RATE_LIMIT 失败，验证 pipeline 停靠在最近合法状态
    def boom(*args, **kwargs):
        from adapters.wechat_openapi import WechatApiError
        raise WechatApiError("RATE_LIMIT", message="模拟限流", evidence={"api": "create_spu"})

    monkeypatch.setattr(adapter, "create_spu", boom)
    result = pipeline.submit(make_candidate(tmp_path), generation_version="v1")

    assert result["ok"] is False
    assert result["error_code"] == "RATE_LIMIT"
    assert result["stage"] == "creating"
    task = repo_listing.get_task(result["task_id"])
    assert task.status == "creating"  # 停在最近合法状态（断点续跑，不伪造状态）


def test_op_log_payload_digest_redacted(pipeline, repo_listing, tmp_path):
    result = pipeline.submit(make_candidate(tmp_path), generation_version="v1")

    logs = repo_listing.list_op_logs(result["task_id"])
    request_logs = [l for l in logs if l.api == "create_spu" and l.direction == "request"]
    assert request_logs
    digest = request_logs[0].payload_digest
    assert digest and len(digest) == 16  # 脱敏摘要，非原文
    assert request_logs[0].evidence_json is None  # 请求体不落明文证据
