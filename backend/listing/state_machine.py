"""M4 上架状态机：9 态迁移合法校验 + R22 铁律断言 + 迁移证据留痕。

状态（context/README.md 第二节）：pending / creating / draft /
platform_auditing / listed / rejected / retry_candidate / manual / failed。

铁律（R22）：禁止以内部状态/本地猜测标记 listed；listed 唯一判据 =
query_audit_status=通过 且 get_product_link 返回 且 链接 HTTP 可达 →
由调用方传入 link_verified 证据（link_url 非空且 verified=True），
否则 transition 抛 ListedLinkVerificationError —— 断言固化在本文件。
"""

from __future__ import annotations

import json
import uuid
from typing import Any, Optional

from .models import ListingTask, utcnow_iso
from .repo import ListingRepo


class IllegalTransitionError(Exception):
    """非法状态迁移（不在 ALLOWED_TRANSITIONS 内）。"""

    def __init__(self, task_id: str, from_status: str, to_status: str):
        self.task_id = task_id
        self.from_status = from_status
        self.to_status = to_status
        super().__init__(f"非法状态迁移: task={task_id} {from_status} -> {to_status}")


class ListedLinkVerificationError(Exception):
    """R22 铁律：listed 必须携带 link_verified 证据（link_url 非空且 verified=True）。"""

    def __init__(self, task_id: str):
        self.task_id = task_id
        super().__init__(
            f"禁止标记 listed: task={task_id} 缺少 link_verified 证据 "
            f"(要求 link_url 非空且 verified=True，R22 铁律)"
        )


class ListingStateMachine:
    """上架状态机（9 态；终态 listed/manual/failed 无出边）。"""

    STATUSES = frozenset(
        {
            "pending",
            "creating",
            "draft",
            "platform_auditing",
            "listed",
            "rejected",
            "retry_candidate",
            "manual",
            "failed",
        }
    )

    # 迁移条件见 context/README.md 第二节：
    #   pending→creating（入队）；creating→draft（SPU/SKU/图全部成功）| failed；
    #   draft→platform_auditing（submit_audit 成功）| failed；
    #   platform_auditing→listed（R22 唯一判据）| rejected（驳回）；
    #   rejected→retry_candidate（修复候选）| manual；retry_candidate→creating（二次门禁）| manual。
    ALLOWED_TRANSITIONS: dict[str, frozenset[str]] = {
        "pending": frozenset({"creating"}),
        "creating": frozenset({"draft", "failed"}),
        "draft": frozenset({"platform_auditing", "failed"}),
        "platform_auditing": frozenset({"listed", "rejected"}),
        "rejected": frozenset({"retry_candidate", "manual"}),
        "retry_candidate": frozenset({"creating", "manual"}),
        "listed": frozenset(),
        "manual": frozenset(),
        "failed": frozenset(),
    }

    TERMINAL_STATUSES = frozenset({"listed", "manual", "failed"})

    def __init__(self, repo: ListingRepo):
        self.repo = repo

    def is_terminal(self, status: str) -> bool:
        """listed / manual / failed 为终态。"""
        return status in self.TERMINAL_STATUSES

    def transition(
        self,
        task: ListingTask,
        new_status: str,
        evidence: Optional[dict[str, Any]] = None,
    ) -> ListingTask:
        """校验迁移合法 → 落地状态 → 写 listing_op_logs 一条迁移证据 → 返回更新后任务。

        - 非法迁移（不在 ALLOWED_TRANSITIONS）抛 IllegalTransitionError；
        - 迁移到 listed 必须携带 link_verified 证据（link_url 非空且 verified=True），
          否则抛 ListedLinkVerificationError（R22 断言固化）；
        - rejected 迁移可带 evidence["reject_reason_code"] 落 reject_reason_code。
        """
        task_id = task.task_id
        if new_status not in self.ALLOWED_TRANSITIONS.get(task.status, frozenset()):
            raise IllegalTransitionError(task_id, task.status, new_status)

        evidence = evidence or {}
        fields: dict[str, Any] = {}
        if new_status == "listed":
            link_url = evidence.get("link_url")
            verified = evidence.get("verified")
            if not link_url or verified is not True:
                raise ListedLinkVerificationError(task_id)
            fields["product_link"] = str(link_url)
            fields["link_verified_at"] = utcnow_iso()
        elif new_status == "rejected":
            code = evidence.get("reject_reason_code")
            if code:
                fields["reject_reason_code"] = str(code)

        updated = self.repo.update_status(task_id, new_status, **fields)

        self.repo.append_op_log(
            task_id=task_id,
            request_id=f"state_machine:{task_id}:{uuid.uuid4().hex[:12]}",
            api="state_machine",
            direction="transition",
            payload_digest="",  # 迁移证据不涉及请求体，无敏感值
            evidence_json=json.dumps(
                {
                    "from": task.status,
                    "to": new_status,
                    "at": utcnow_iso(),
                    "evidence": evidence,
                },
                ensure_ascii=False,
            ),
        )
        return updated
