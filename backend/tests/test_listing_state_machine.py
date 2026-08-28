"""M4 自动上架：ListingStateMachine 9 态迁移单测（R22 铁律断言 + 租约断点续跑 + 证据留痕）。

纪律：本模块独立 basetemp `--basetemp=".pytest-tmp-m4"`（P-001/P-011）；
全部用例用 tmp_path 临时 SQLite，零网络零真实平台（listed 链接验证由
调用方 evidence 模拟，绝不发真实 HTTP 请求）。
"""

import hashlib
import json

import pytest
from sqlalchemy import update

from listing.models import ListingTask
from listing.state_machine import (
    IllegalTransitionError,
    ListedLinkVerificationError,
)
from listing.tables import ListingTaskRow

LINK_URL = "https://channels.weixin.qq.com/shop/goods/12345"


def make_task(product_id: int = 1001, task_id: str | None = None, generation_version: str = "g1") -> ListingTask:
    return ListingTask(
        task_id=task_id or f"T-{product_id}",
        product_id=product_id,
        generation_version=generation_version,
    )


def link_evidence(url: str = LINK_URL, verified: bool = True) -> dict:
    return {"link_url": url, "verified": verified}


def to_platform_auditing(repo, machine, task_id: str | None = None) -> ListingTask:
    """快速推进到 platform_auditing（合法迁移链）。"""
    task = repo.create_task(make_task(task_id=task_id) if task_id else make_task())
    for s in ("creating", "draft", "platform_auditing"):
        task = machine.transition(task, s)
    return task


# ---------------------------------------------------------------- 合法迁移链


def test_happy_path_to_listed(repo_listing, machine_listing):
    """合法迁移链 pending→creating→draft→platform_auditing→listed（带 link_verified 证据）。"""
    task = repo_listing.create_task(make_task())
    assert task.status == "pending"
    for s in ("creating", "draft", "platform_auditing"):
        task = machine_listing.transition(task, s)
        assert task.status == s
    task = machine_listing.transition(task, "listed", evidence=link_evidence())
    assert task.status == "listed"
    assert task.product_link == LINK_URL
    assert task.link_verified_at is not None
    assert machine_listing.is_terminal(task.status)


def test_platform_auditing_to_rejected(repo_listing, machine_listing):
    """platform_auditing→rejected（驳回），reject_reason_code 随证据落库。"""
    task = to_platform_auditing(repo_listing, machine_listing)
    task = machine_listing.transition(
        task, "rejected", evidence={"reject_reason_code": "image"}
    )
    assert task.status == "rejected"
    assert task.reject_reason_code == "image"


def test_rejected_to_retry_candidate_then_creating(repo_listing, machine_listing):
    """rejected→retry_candidate→creating（二次门禁通过重走创建流程）。"""
    task = to_platform_auditing(repo_listing, machine_listing)
    task = machine_listing.transition(task, "rejected", evidence={"reject_reason_code": "price"})
    task = machine_listing.transition(task, "retry_candidate")
    assert task.status == "retry_candidate"
    task = machine_listing.transition(task, "creating")
    assert task.status == "creating"


def test_rejected_to_manual(repo_listing, machine_listing):
    """rejected→manual（自动修复不可行转人工）。"""
    task = to_platform_auditing(repo_listing, machine_listing)
    task = machine_listing.transition(task, "rejected")
    task = machine_listing.transition(task, "manual")
    assert task.status == "manual"
    assert machine_listing.is_terminal(task.status)


def test_creating_to_failed(repo_listing, machine_listing):
    """creating→failed（创建失败终态，保留证据）。"""
    task = repo_listing.create_task(make_task())
    task = machine_listing.transition(task, "creating")
    task = machine_listing.transition(task, "failed")
    assert task.status == "failed"
    assert machine_listing.is_terminal(task.status)


# ---------------------------------------------------------------- 非法迁移


def test_illegal_transition_pending_to_listed(repo_listing, machine_listing):
    """pending→listed 非法（跳过全部中间态）抛 IllegalTransitionError。"""
    task = repo_listing.create_task(make_task())
    with pytest.raises(IllegalTransitionError) as ei:
        machine_listing.transition(task, "listed", evidence=link_evidence())
    assert ei.value.task_id == task.task_id
    assert ei.value.from_status == "pending"
    assert ei.value.to_status == "listed"


def test_illegal_transition_draft_to_listed(repo_listing, machine_listing):
    """draft→listed 非法（未过平台审核不可标已上架）。"""
    task = repo_listing.create_task(make_task())
    task = machine_listing.transition(task, "creating")
    task = machine_listing.transition(task, "draft")
    with pytest.raises(IllegalTransitionError):
        machine_listing.transition(task, "listed", evidence=link_evidence())


def test_terminal_state_has_no_outgoing_transition(repo_listing, machine_listing):
    """终态 listed 无出边：listed→creating 抛 IllegalTransitionError。"""
    task = to_platform_auditing(repo_listing, machine_listing)
    task = machine_listing.transition(task, "listed", evidence=link_evidence())
    with pytest.raises(IllegalTransitionError):
        machine_listing.transition(task, "creating")


# ---------------------------------------------------------------- R22 铁律断言


def test_listed_requires_link_verification_evidence(repo_listing, machine_listing):
    """R22：platform_auditing→listed 无 link_verified 证据 → 抛错（不得标已上架）。"""
    task = to_platform_auditing(repo_listing, machine_listing)
    with pytest.raises(ListedLinkVerificationError):
        machine_listing.transition(task, "listed")


def test_listed_requires_verified_true(repo_listing, machine_listing):
    """R22：verified=False 的证据不通过。"""
    task = to_platform_auditing(repo_listing, machine_listing)
    with pytest.raises(ListedLinkVerificationError):
        machine_listing.transition(task, "listed", evidence=link_evidence(verified=False))


def test_listed_requires_nonempty_link_url(repo_listing, machine_listing):
    """R22：link_url 为空不通过。"""
    task = to_platform_auditing(repo_listing, machine_listing)
    with pytest.raises(ListedLinkVerificationError):
        machine_listing.transition(task, "listed", evidence=link_evidence(url=""))


# ---------------------------------------------------------------- 终态判定


def test_terminal_states(repo_listing, machine_listing):
    """listed/manual/failed 为终态；其余为非终态。"""
    for s in ("listed", "manual", "failed"):
        assert machine_listing.is_terminal(s)
    for s in ("pending", "creating", "draft", "platform_auditing", "rejected", "retry_candidate"):
        assert not machine_listing.is_terminal(s)


# ---------------------------------------------------------------- 证据留痕


def test_transition_writes_op_log_evidence(repo_listing, machine_listing):
    """每次迁移写 listing_op_logs 一条（api=state_machine, direction=transition）。"""
    task = repo_listing.create_task(make_task())
    task = machine_listing.transition(task, "creating")
    logs = repo_listing.list_op_logs(task.task_id)
    assert len(logs) == 1
    assert logs[0].api == "state_machine"
    assert logs[0].direction == "transition"
    ev = json.loads(logs[0].evidence_json)
    assert ev["from"] == "pending"
    assert ev["to"] == "creating"
    assert "at" in ev


def test_append_op_log_evidence_sanitized(repo_listing):
    """证据留痕可回查；payload_digest/evidence_json 不含敏感明文值。"""
    secret = "WECHAT_SECRET-super-secret"
    repo_listing.create_task(make_task(product_id=9, task_id="T-9"))
    repo_listing.append_op_log(
        task_id="T-9",
        request_id="T-9:submit_audit:1",
        api="submit_audit",
        direction="request",
        # 脱敏摘要：仅 SHA256 摘要，绝不落明文 token/密钥
        payload_digest=hashlib.sha256(
            json.dumps({"token": secret, "title": "x"}, sort_keys=True).encode()
        ).hexdigest(),
        status_code=200,
        error_code=None,
        platform_code="0",
        evidence_json=json.dumps({"audit_id": "A-1"}),
    )
    logs = repo_listing.list_op_logs("T-9")
    assert len(logs) == 1
    assert logs[0].request_id == "T-9:submit_audit:1"
    assert logs[0].api == "submit_audit"
    assert logs[0].status_code == 200
    assert secret not in logs[0].payload_digest
    assert secret not in logs[0].evidence_json


# ---------------------------------------------------------------- 租约（断点续跑）


def test_claim_task_lease_and_expiry_recovery(repo_listing):
    """领取后他人不可再领；手动将 lease_expires_at 改为过去 → 过期回收可重新领取。"""
    repo_listing.create_task(make_task(product_id=7, task_id="T-7"))
    claimed = repo_listing.claim_task("worker-A")
    assert claimed is not None
    assert claimed.lease_owner == "worker-A"
    assert claimed.lease_expires_at is not None
    assert repo_listing.claim_task("worker-B") is None  # 租约未过期

    # 模拟进程中断 45min+：把租约过期时间改为过去 → 回收重新领取（断点续跑）
    with repo_listing.database.session() as session:
        session.execute(
            update(ListingTaskRow)
            .where(ListingTaskRow.task_id == "T-7")
            .values(lease_expires_at="2000-01-01T00:00:00+00:00")
        )
    re_claimed = repo_listing.claim_task("worker-B")
    assert re_claimed is not None
    assert re_claimed.lease_owner == "worker-B"
    assert re_claimed.lease_expires_at is not None


def test_claim_task_specific_id(repo_listing):
    """按 task_id 领取指定任务。"""
    repo_listing.create_task(make_task(product_id=11, task_id="T-11"))
    repo_listing.create_task(make_task(product_id=12, task_id="T-12"))
    claimed = repo_listing.claim_task("worker-A", task_id="T-12")
    assert claimed is not None
    assert claimed.task_id == "T-12"
    assert claimed.lease_owner == "worker-A"


def test_claim_task_only_non_terminal(repo_listing, machine_listing):
    """终态任务不可被领取（failed/manual/listed 无租约）。"""
    repo_listing.create_task(make_task(product_id=8, task_id="T-8"))
    task = repo_listing.get_task("T-8")
    task = machine_listing.transition(task, "creating")
    task = machine_listing.transition(task, "failed")
    assert repo_listing.claim_task("worker-A") is None


def test_release_task_clears_lease(repo_listing):
    """release_task 清空租约，任务立即可被其他 worker 领取。"""
    repo_listing.create_task(make_task(product_id=13, task_id="T-13"))
    claimed = repo_listing.claim_task("worker-A")
    assert claimed.lease_owner == "worker-A"
    repo_listing.release_task("T-13")
    released = repo_listing.get_task("T-13")
    assert released.lease_owner is None
    assert released.lease_expires_at is None
    re_claimed = repo_listing.claim_task("worker-B")
    assert re_claimed is not None and re_claimed.lease_owner == "worker-B"


# ---------------------------------------------------------------- 状态落地


def test_update_status_updates_updated_at(repo_listing):
    """update_status 更新 status + 附加字段 + updated_at。"""
    task = repo_listing.create_task(make_task(product_id=10, task_id="T-10"))
    before = task.updated_at
    updated = repo_listing.update_status(
        "T-10", "creating", platform_spu_id="SPU-1"
    )
    assert updated.status == "creating"
    assert updated.platform_spu_id == "SPU-1"
    assert updated.updated_at >= before
    fetched = repo_listing.get_task("T-10")
    assert fetched.status == "creating"
