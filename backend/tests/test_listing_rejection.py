"""M4 自动上架：平台拒审处理（platform_rejection）单测。

覆盖：驳回原因七分类关键词映射（含优先级）、修复候选生成（title/image 主图/详情图
分支/price/qualification/无候选）、handle 全流程（rejected→retry_candidate|manual +
listing_audit_records 落库）、二次门禁 requalify（合规放行/违规拒绝且任务状态不变/
仅 retry_candidate 可重提）、state_machine transition 证据含 reject_reason_code。

纪律：本模块独立 basetemp `--basetemp=".pytest-tmp-m4"`（P-001/P-011）；
全部用例 tmp_path 临时 SQLite，复用 conftest 的 cfg_listing/db_listing/repo_listing/
machine_listing fixtures，零网络零真实平台调用；requalify 用 Pillow 在 tmp 生成图片
（与 test_listing_gate 同口径）。
"""

import json

import pytest
from PIL import Image
from sqlalchemy import select

from listing.models import ListingTask
from listing.platform_rejection import (
    RejectionHandler,
    _build_fix_candidates,
    classify_reject_reason,
)
from listing.tables import ListingAuditRecordRow
from services.listing_gate import ListingCandidate, PurchaseSettings, SkuInput

VALID_TITLE = "免打孔卫生间置物架 浴室收纳架"  # 15 字符（与 listing_gate 测试同口径）


# ---------------------------------------------------------------- 工具


def make_task(
    product_id: int = 1001,
    task_id: str | None = None,
    generation_version: str = "g1",
    platform_spu_id: str | None = None,
) -> ListingTask:
    return ListingTask(
        task_id=task_id or f"T-{product_id}",
        product_id=product_id,
        generation_version=generation_version,
        platform_spu_id=platform_spu_id,
    )


def to_rejected(repo, machine, task_id=None, product_id=1001, platform_spu_id=None):
    """合法迁移链 pending→creating→draft→platform_auditing→rejected（模拟平台驳回）。"""
    task = repo.create_task(
        make_task(
            product_id=product_id,
            task_id=task_id,
            platform_spu_id=platform_spu_id,
        )
    )
    for s in ("creating", "draft", "platform_auditing"):
        task = machine.transition(task, s)
    task = machine.transition(task, "rejected")
    return task


def audit_records(repo, task_id: str) -> list[ListingAuditRecordRow]:
    with repo.database.session() as session:
        rows = (
            session.execute(
                select(ListingAuditRecordRow).where(
                    ListingAuditRecordRow.task_id == task_id
                )
            )
            .scalars()
            .all()
        )
        return list(rows)


def make_image(path, size=(100, 100), color=(200, 30, 30)):
    img = Image.new("RGB", size, color)
    img.save(path)
    return str(path)


def make_main_images(tmp_path, n: int) -> list[str]:
    paths = []
    for i in range(n):
        color = ((i * 40) % 256, (i * 61) % 256, (i * 83) % 256)
        paths.append(make_image(tmp_path / f"main_{i}.png", color=color))
    return paths


def valid_candidate(tmp_path, **overrides) -> ListingCandidate:
    """合规上架候选（六项硬门禁全过，与 test_listing_gate.valid_candidate 同口径）。"""
    main_images = overrides.pop("main_images", None)
    detail_images = overrides.pop("detail_images", None)
    data = dict(
        product_id=1001,
        title=VALID_TITLE,
        category_id=1,
        category_name="家居日用",
        qualification={"qualification_id": "Q-001", "expires_at": "2027-12-31"},
        main_images=(
            make_main_images(tmp_path, 5) if main_images is None else main_images
        ),
        detail_images=(
            [make_image(tmp_path / "detail_0.png")]
            if detail_images is None
            else detail_images
        ),
        skus=[SkuInput(code="SKU-A", cost_cents=300, price_cents=990)],
        purchase_settings=PurchaseSettings(
            purchase_limit={"per_user": 2, "period": "month"},
            freight_template_id="FT-001",
            after_sale="7 天无理由退货",
        ),
    )
    data.update(overrides)
    return ListingCandidate(**data)


# ---------------------------------------------------------------- 分类映射


@pytest.mark.parametrize(
    "reason,expected",
    [
        ("标题含违禁词，请修改", "title"),
        ("商品类目选择错误", "category"),
        ("请补充品牌授权资质证件", "qualification"),
        ("主图不清晰，重新上传", "image"),
        ("商品售价过低", "price"),
        ("功效夸大宣传，涉嫌虚假", "content_compliance"),
        ("其他未知系统错误", "other"),
    ],
)
def test_classify_reject_reason(reason, expected):
    """关键词表命中即分类：七分类各取一条原文样本。"""
    assert classify_reject_reason(reason) == expected


def test_classify_priority_order():
    """分类按优先级：先命中的分类优先（title>category>…>content_compliance）。"""
    assert classify_reject_reason("标题类目错误，请修改") == "title"  # 类目在后，标题优先
    assert classify_reject_reason("品牌授权已过期") == "qualification"  # 品牌授权优先于品牌
    assert classify_reject_reason("品牌夸大宣传") == "content_compliance"  # 无品牌授权 → 品牌命中
    assert classify_reject_reason("图片详情图均不合规") == "image"


# ---------------------------------------------------------------- 修复候选生成


@pytest.mark.parametrize(
    "category,reason,expected_actions",
    [
        ("title", "标题违规", ["改标题"]),
        ("image", "主图不合规", ["重传主图"]),
        ("image", "详情图缺失", ["重传详情图"]),
        ("image", "图片素材不合规", ["重传主图", "重传详情图"]),
        ("image", "图片不合规", ["重传主图", "重传详情图"]),
        ("price", "价格异常", ["改价"]),
        ("qualification", "缺少资质", ["补资质"]),
        ("category", "类目错误", []),
        ("content_compliance", "夸大宣传", []),
        ("other", "未知错误", []),
    ],
)
def test_build_fix_candidates(category, reason, expected_actions):
    """修复候选按分类生成；image 按 reason 细分主图/详情图；无候选分类返回空。"""
    candidates = _build_fix_candidates(category, reason)
    assert [c.action for c in candidates] == expected_actions


@pytest.mark.parametrize(
    "category,reason,expected_gate",
    [
        ("title", "标题违规", True),
        ("image", "主图不合规", True),
        ("price", "价格异常", True),
        ("qualification", "缺少资质", False),
    ],
)
def test_fix_candidate_gate_required(category, reason, expected_gate):
    """title/image/price 候选需二次门禁；qualification 补资质候选 gate_required=False。"""
    candidates = _build_fix_candidates(category, reason)
    assert candidates
    assert all(c.gate_required is expected_gate for c in candidates)


@pytest.mark.parametrize(
    "reason,expected_category,expected_auto_fixable,expected_resubmit",
    [
        ("标题含违禁词", "title", True, True),
        ("缺少经营资质证件", "qualification", False, True),  # 有候选走重提，但需人工证件
        ("功效夸大宣传", "content_compliance", False, False),
    ],
)
def test_analyze(reason, expected_category, expected_auto_fixable, expected_resubmit, repo_listing, machine_listing):
    """analyze：分类 + 候选 + auto_fixable + resubmit_required 语义正确。"""
    handler = RejectionHandler(repo_listing, machine_listing)
    analysis = handler.analyze(reason)
    assert analysis.category == expected_category
    assert analysis.reject_reason == reason
    assert analysis.auto_fixable is expected_auto_fixable
    assert analysis.resubmit_required is expected_resubmit


# ---------------------------------------------------------------- handle 全流程


def test_handle_title_to_retry_candidate(repo_listing, machine_listing):
    """title 拒审：有修复候选 → 迁移 retry_candidate，action=retry_candidate。"""
    task = to_rejected(repo_listing, machine_listing)
    handler = RejectionHandler(repo_listing, machine_listing)
    result = handler.handle(task, "标题含违禁词")
    assert result.task_id == task.task_id
    assert result.category == "title"
    assert result.action == "retry_candidate"
    assert [c.action for c in result.analysis.fix_candidates] == ["改标题"]
    assert repo_listing.get_task(task.task_id).status == "retry_candidate"


def test_handle_qualification_to_retry_candidate(repo_listing, machine_listing):
    """qualification 拒审：action 仍 retry_candidate，但 auto_fixable=False（补资质需人工证件）。"""
    task = to_rejected(repo_listing, machine_listing)
    handler = RejectionHandler(repo_listing, machine_listing)
    result = handler.handle(task, "缺少经营资质证件")
    assert result.category == "qualification"
    assert result.action == "retry_candidate"
    assert result.analysis.auto_fixable is False
    assert result.analysis.resubmit_required is True
    assert [c.action for c in result.analysis.fix_candidates] == ["补资质"]
    assert repo_listing.get_task(task.task_id).status == "retry_candidate"


def test_handle_content_compliance_to_manual(repo_listing, machine_listing):
    """content_compliance 拒审：无修复候选 → 迁移 manual（人工介入）。"""
    task = to_rejected(repo_listing, machine_listing)
    handler = RejectionHandler(repo_listing, machine_listing)
    result = handler.handle(task, "功效夸大宣传，涉嫌虚假")
    assert result.category == "content_compliance"
    assert result.action == "manual"
    assert result.analysis.fix_candidates == []
    assert repo_listing.get_task(task.task_id).status == "manual"
    assert machine_listing.is_terminal(repo_listing.get_task(task.task_id).status)


def test_handle_audit_record_persisted(repo_listing, machine_listing):
    """handle 写 listing_audit_records：reject_category/fix_candidate/resubmit_required 落库正确。"""
    task = to_rejected(repo_listing, machine_listing)
    handler = RejectionHandler(repo_listing, machine_listing)
    handler.handle(task, "标题含违禁词")
    recs = audit_records(repo_listing, task.task_id)
    assert len(recs) == 1
    r = recs[0]
    assert r.task_id == task.task_id
    assert r.reject_reason == "标题含违禁词"
    assert r.reject_category == "title"
    assert r.resubmit_required == 1
    fix = json.loads(r.fix_candidate)
    assert [c["action"] for c in fix] == ["改标题"]
    assert fix[0]["gate_required"] is True
    ev = json.loads(r.evidence)
    assert ev["reject_reason_code"] == "title"
    assert ev["action"] == "retry_candidate"


def test_handle_manual_audit_record_no_resubmit(repo_listing, machine_listing):
    """manual 拒审：审核记录 resubmit_required=0、无修复候选（fix_candidate 为空）。"""
    task = to_rejected(repo_listing, machine_listing)
    handler = RejectionHandler(repo_listing, machine_listing)
    handler.handle(task, "类目选择错误")
    recs = audit_records(repo_listing, task.task_id)
    assert len(recs) == 1
    r = recs[0]
    assert r.reject_category == "category"
    assert r.resubmit_required == 0
    assert r.fix_candidate is None
    ev = json.loads(r.evidence)
    assert ev["reject_reason_code"] == "category"
    assert ev["action"] == "manual"


def test_audit_id_derived_from_platform_spu_id(repo_listing, machine_listing):
    """audit_id 从 platform_spu_id 派生（无则回退 task_id），保证唯一性前缀。"""
    task = to_rejected(
        repo_listing, machine_listing, platform_spu_id="SPU-123"
    )
    handler = RejectionHandler(repo_listing, machine_listing)
    handler.handle(task, "主图不清晰")
    recs = audit_records(repo_listing, task.task_id)
    assert len(recs) == 1
    assert recs[0].audit_id.startswith("REJ:SPU-123:")


def test_handle_transition_op_log_evidence_contains_reject_code(
    repo_listing, machine_listing
):
    """state_machine.transition 的 op_log 证据含 reject_reason_code（迁移留痕）。"""
    task = to_rejected(repo_listing, machine_listing)
    handler = RejectionHandler(repo_listing, machine_listing)
    handler.handle(task, "标题含违禁词")
    logs = repo_listing.list_op_logs(task.task_id)
    transitions = [
        l for l in logs if l.api == "state_machine" and l.direction == "transition"
    ]
    last = transitions[-1]
    ev = json.loads(last.evidence_json)
    assert ev["from"] == "rejected"
    assert ev["to"] == "retry_candidate"
    assert ev["evidence"]["reject_reason_code"] == "title"


# ---------------------------------------------------------------- 二次门禁 requalify


def test_requalify_passes_compliant_candidate(tmp_path, repo_listing, machine_listing):
    """合规候选 → 二次门禁通过 True；requalify 只评估，不迁移任务状态。"""
    task = to_rejected(repo_listing, machine_listing)
    handler = RejectionHandler(repo_listing, machine_listing)
    handler.handle(task, "标题含违禁词")
    current = repo_listing.get_task(task.task_id)
    assert current.status == "retry_candidate"
    assert handler.requalify(current, valid_candidate(tmp_path)) is True
    after = repo_listing.get_task(task.task_id)
    assert after.status == "retry_candidate"  # 迁移动作由调用方执行（retry_candidate→creating）


def test_requalify_rejects_noncompliant_status_unchanged(
    tmp_path, repo_listing, machine_listing
):
    """含违规项候选（标题超长 36 字符）→ False，且任务状态保持不变（不迁移）。"""
    task = to_rejected(repo_listing, machine_listing)
    handler = RejectionHandler(repo_listing, machine_listing)
    handler.handle(task, "标题含违禁词")
    current = repo_listing.get_task(task.task_id)
    bad = valid_candidate(tmp_path, title="长" * 36)
    assert handler.requalify(current, bad) is False
    after = repo_listing.get_task(task.task_id)
    assert after.status == "retry_candidate"
    assert after.reject_reason_code is None  # 未迁移 → 无新 reject 落库


@pytest.mark.parametrize("to_status", ["rejected", "manual"])
def test_requalify_only_retry_candidate(
    tmp_path, repo_listing, machine_listing, to_status
):
    """二次门禁仅对 retry_candidate 任务开放：rejected/manual 一律 False。"""
    task = to_rejected(repo_listing, machine_listing)
    handler = RejectionHandler(repo_listing, machine_listing)
    if to_status == "manual":
        handler.handle(task, "功效夸大宣传")  # manual 终态
        current = repo_listing.get_task(task.task_id)
    else:
        current = task  # 仍处 rejected（拒审决策前不可重提）
    assert current.status == to_status
    assert handler.requalify(current, valid_candidate(tmp_path)) is False
