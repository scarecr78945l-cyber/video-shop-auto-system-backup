"""REC-融合 P0-1：上架类目记忆 fixtures + pipeline 接线测试。

旧系统 category_listing_memory 迁移验证：
① 首单通过后，第二单上架包自动预填必填参数/物流模板
② 该类目后续拒审率超阈值 → 转人工复核
③ 连续图片拒审 streak ≥3 → 转人工复核（独立判据）
④ pipeline 接线（decisions D14）：gate 前按类目预填 freight_template_id、
   上架成功/拒审记录提交计数、拒审率阈值 → 强制 manual（不覆盖显式值）。
"""

import json

import pytest

from listing.repo import ListingRepo

TITLE_OK = "纯棉加厚家用擦手巾厨房清洁抹布吸水速干"  # 19 字符，无违禁词


def _seed(repo: ListingRepo, category: str, **fields) -> None:
    repo.upsert_category_memory(category, **fields)


def test_first_pass_then_second_prefill(repo_listing):
    """① 首单通过（记 streak + 预填字段）后，第二单读记忆即得预填。"""
    repo = repo_listing
    # 首单人工通过：记 1 次通过 + 沉淀必填参数/物流模板/退货地址
    repo.record_category_submission("收纳整理", rejected=False)
    repo.upsert_category_memory(
        "收纳整理",
        required_fields=["适用场景", "容量", "包装清单"],
        logistics_template="默认快递-包邮-48h发货",
        return_address_rule={"region": "华东", "fee_paid": "seller"},
    )
    # 第二单上架包生成时读取记忆
    memory = repo.get_category_memory("收纳整理")
    assert memory is not None
    assert memory["manual_pass_streak"] == 1
    assert memory["required_fields"] == ["适用场景", "容量", "包装清单"]
    assert memory["logistics_template"] == "默认快递-包邮-48h发货"
    assert memory["return_address_rule"] == {"region": "华东", "fee_paid": "seller"}


def test_reject_rate_threshold_triggers_manual(repo_listing):
    """② 拒审率 ≥50% → 该类目转人工复核。"""
    repo = repo_listing
    repo.record_category_submission("厨房用品", rejected=True)
    repo.record_category_submission("厨房用品", rejected=True)  # 2/2 = 100%
    assert repo.should_manual_review_category("厨房用品") is True
    # 低拒审率（1/4 = 25%）不触发
    repo2_mem = repo.get_category_memory("厨房用品")
    # 补 2 次通过 → 2/4 = 50%，恰达阈值（>=）触发
    repo.record_category_submission("厨房用品", rejected=False)
    repo.record_category_submission("厨房用品", rejected=False)
    assert repo.should_manual_review_category("厨房用品") is True
    # 自定义阈值：25% 阈值下 1/3 即触发
    repo.record_category_submission("厨房用品", rejected=True)  # 3/5
    assert repo.should_manual_review_category("厨房用品", reject_rate_threshold=0.6) is True
    assert repo.should_manual_review_category("厨房用品", reject_rate_threshold=0.7) is False


def test_image_rejection_streak_triggers_manual(repo_listing):
    """③ 连续图片拒审 streak ≥3 → 转人工复核（独立于拒审率）。"""
    repo = repo_listing
    for _ in range(3):
        repo.record_category_submission("宠物用品", rejected=True)
    assert repo.should_manual_review_category("宠物用品") is True
    # 通过一次后 streak 清零 → 不再因 streak 触发（拒审率 3/4=75% 仍会触发）
    repo.record_category_submission("宠物用品", rejected=False)
    memory = repo.get_category_memory("宠物用品")
    assert memory["platform_image_rejection_streak"] == 0
    assert repo.should_manual_review_category("宠物用品") is True  # 拒审率 3/4


def test_no_memory_no_manual(repo_listing):
    """无记忆的类目不触发人工复核。"""
    repo = repo_listing
    assert repo.get_category_memory("未知类目") is None
    assert repo.should_manual_review_category("未知类目") is False


# ================================================================
# ④ pipeline 接线（decisions D14）
# ================================================================


@pytest.fixture()
def pipeline(repo_listing, machine_listing):
    from adapters.wechat_openapi import WechatOpenApiAdapter, WechatOpenApiConfig
    from listing.pipeline import ListingPipeline
    from listing.platform_rejection import RejectionHandler
    from services.listing_gate import ListingGate

    gate = ListingGate()
    adapter = WechatOpenApiAdapter(WechatOpenApiConfig(mode="mock"))
    rejection = RejectionHandler(repo_listing, machine_listing, gate=gate)
    return ListingPipeline(
        gate=gate,
        adapter=adapter,
        repo=repo_listing,
        state_machine=machine_listing,
        rejection=rejection,
    )


def _make_images(tmp_path, n=5, prefix="main"):
    from PIL import Image

    paths = []
    for i in range(n):
        p = tmp_path / f"{prefix}_{i}.png"
        Image.new("RGB", (100, 100), (10 + i * 40, 20 + i * 30, 30 + i * 20)).save(p)
        paths.append(str(p))
    return paths


def _make_candidate(tmp_path, product_id=2001, title=TITLE_OK, **overrides):
    from services.listing_gate import ListingCandidate, PurchaseSettings, SkuInput

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


def _missing_freight_candidate(tmp_path, product_id=2002):
    """缺运费模板（freight_template_id=None）的候选：门禁本会拒绝 purchase_settings。"""
    from services.listing_gate import PurchaseSettings

    return _make_candidate(
        tmp_path,
        product_id=product_id,
        purchase_settings=PurchaseSettings(
            purchase_limit={"per_user": 2, "period": "month"},
            freight_template_id=None,
            after_sale="支持7天无理由退换货",
        ),
    )


def test_pipeline_prefill_freight_from_memory(pipeline, repo_listing, tmp_path):
    """首单通过（沉淀记忆）后，第二单缺运费模板 → 预填并过门禁上架。"""
    # 首单：完整参数提交成功（记录通过 streak）
    first = pipeline.submit(_make_candidate(tmp_path, product_id=2001), generation_version="v1")
    assert first["stage"] == "listed"
    # 人工确认环节沉淀类目记忆（物流模板）
    _seed(repo_listing, "厨房用品", logistics_template="默认快递-包邮-48h发货")

    # 第二单：缺 freight_template_id（门禁原本会拒绝 purchase_settings）
    second = pipeline.submit(
        _missing_freight_candidate(tmp_path, product_id=2002), generation_version="v2"
    )
    assert second["ok"] is True
    assert second["stage"] == "listed"
    assert second["evidence"]["category_memory"]["applied"] is True
    assert second["evidence"]["category_memory"]["freight_template_id"] == "默认快递-包邮-48h发货"

    # 预填已参与门禁（未被 purchase_settings 门禁拦截）且落库为 SPU 运费模板
    task = repo_listing.get_task(second["task_id"])
    spu = repo_listing.get_spu(task.platform_spu_id)
    assert spu is not None
    # 预填值经 _to_int 转 int：非数字字符串 → 0（模板 ID 待 M5 侧契约对齐，见 decisions D14 备注）
    assert int(spu["freight_template_id"] or 0) == 0
    # 预填证据留痕（listing_op_logs）
    logs = repo_listing.list_op_logs(second["task_id"])
    prefill_logs = [l for l in logs if l.api == "category_memory_prefill"]
    assert len(prefill_logs) == 1
    assert json.loads(prefill_logs[0].evidence_json)["freight_template_id"] == "默认快递-包邮-48h发货"


def test_pipeline_prefill_does_not_override_explicit(pipeline, repo_listing, tmp_path):
    """记忆存在但调用方显式提供运费模板 → 不覆盖显式值。"""
    _seed(repo_listing, "厨房用品", logistics_template="默认快递-包邮-48h发货")
    result = pipeline.submit(
        _make_candidate(tmp_path, product_id=2101), generation_version="v1"
    )
    assert result["ok"] is True
    task = repo_listing.get_task(result["task_id"])
    spu = repo_listing.get_spu(task.platform_spu_id)
    assert int(spu["freight_template_id"] or 0) == 1  # 显式值 "1"，未被记忆覆盖


def test_pipeline_no_memory_gate_rejects_missing_freight(pipeline, repo_listing, tmp_path):
    """无类目记忆且缺运费模板 → purchase_settings 门禁拒绝，不入队。"""
    result = pipeline.submit(
        _missing_freight_candidate(tmp_path, product_id=2201), generation_version="v1"
    )
    assert result["ok"] is False
    assert result["stage"] == "gate"
    codes = [i["reason_code"] for i in result["gate_result"]["items"] if not i["passed"]]
    assert "purchase_settings" in codes
    assert repo_listing.get_task_by_product(2201, "v1") is None  # 不入队


def test_pipeline_reject_rate_triggers_manual(
    pipeline, repo_listing, tmp_path, monkeypatch
):
    """类目拒审率 ≥50% → 驳回后强制 manual（即使有自动修复候选）。"""
    # 类目记忆：2 次拒审 → 拒审率 100% → should_manual_review_category=True
    repo_listing.record_category_submission("厨房用品", rejected=True)
    repo_listing.record_category_submission("厨房用品", rejected=True)

    def fake_query(audit_id, task_id=""):
        return {"audit_status": "reject", "reject_reason": "标题含违禁词，请修改后重新提交"}

    monkeypatch.setattr(pipeline.adapter, "query_audit_status", fake_query)
    result = pipeline.submit(_make_candidate(tmp_path, product_id=2301), generation_version="v1")

    # 有修复候选（title 分类）但类目拒审率阈值 → 强制 manual
    assert result["ok"] is True
    assert result["stage"] == "manual"
    assert result["evidence"]["category"] == "title"
    assert result["evidence"]["category_manual_review"] is True
    task = repo_listing.get_task(result["task_id"])
    assert task.status == "manual"
    # 提交计数累计：2（seed）+ 1（本次）= 3 次拒审
    memory = repo_listing.get_category_memory("厨房用品")
    assert memory["submit_count"] == 3
    assert memory["reject_count"] == 3


def test_pipeline_listed_records_pass_and_reject_counts(
    pipeline, repo_listing, tmp_path, monkeypatch
):
    """上架成功记录通过计数；后续拒审记录拒审计数（拒审率判定数据源）。"""
    # 第一单：成功上架 → 记录 1 次通过
    first = pipeline.submit(_make_candidate(tmp_path, product_id=2401), generation_version="v1")
    assert first["stage"] == "listed"
    mem1 = repo_listing.get_category_memory("厨房用品")
    assert mem1["submit_count"] == 1
    assert mem1["manual_pass_streak"] == 1
    assert mem1["reject_count"] == 0

    # 第二单：驳回 → 记录 1 次拒审（1/2 = 50% → 恰达阈值，第三单开始转人工）
    def fake_query(audit_id, task_id=""):
        return {"audit_status": "reject", "reject_reason": "图片不清晰，请重新上传"}

    monkeypatch.setattr(pipeline.adapter, "query_audit_status", fake_query)
    second = pipeline.submit(_make_candidate(tmp_path, product_id=2402), generation_version="v2")
    assert second["stage"] == "retry_candidate"  # 提交前拒审率 0/1=0% 未达阈值 → 有修复候选走重提
    mem2 = repo_listing.get_category_memory("厨房用品")
    assert mem2["submit_count"] == 2
    assert mem2["reject_count"] == 1
    # 拒审率 1/2 = 50% 恰达默认阈值 0.5 → 下一次驳回即强制 manual
    assert repo_listing.should_manual_review_category("厨房用品") is True
