# -*- coding: utf-8 -*-
"""backend.domain.workflow：流程 run/step + 最小队列（P0-1 T8，round-105；round-107 R106 定稿）。

依据：15-数据字典.md v6 §6.1/§6.2（workflow_runs/workflow_steps）、docs/contracts/test-strategy.md §四
（隐式租约断言）、idempotency.md §一/§三 键 10/11（R106-2 canonical/hash 公式）、error-codes.yaml
（R106-1 错误注册表）、index-registry N1/N2。
"""
from .queue import (  # noqa: F401
    ERROR_ENTRIES,
    HEARTBEAT_MAX_MINUTES,
    LEASE_MINUTES,
    RETRY_POLICIES,
    RUN_ACTIVE,
    RUN_TERMINAL,
    STALE_ATTEMPT_MSG,
    WorkflowQueue,
    WorkflowQueueError,
    _canonical_join,
    _hash_key,
    compute_run_key,
    compute_step_action_key,
)

__all__ = [
    "ERROR_ENTRIES",
    "HEARTBEAT_MAX_MINUTES",
    "LEASE_MINUTES",
    "RETRY_POLICIES",
    "RUN_ACTIVE",
    "RUN_TERMINAL",
    "STALE_ATTEMPT_MSG",
    "WorkflowQueue",
    "WorkflowQueueError",
    "_canonical_join",
    "_hash_key",
    "compute_run_key",
    "compute_step_action_key",
]
