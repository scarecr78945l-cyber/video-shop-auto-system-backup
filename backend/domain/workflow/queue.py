# -*- coding: utf-8 -*-
"""WorkflowQueue：workflow run/step 最小队列（P0-1 T8，round-105；round-107 R106-1~R106-3 定稿）。

契约（test-strategy.md §四 + 15-数据字典.md §6.1/§6.2 + idempotency.md §一/§三 + error-codes.yaml）：

- claim：`FOR UPDATE SKIP LOCKED` 两 worker 并发仅一方成功；返回 (id, attempt) fencing token；
  **首次 claim attempt 保持 1**（test-strategy §四.3）；重试/过期回收恰增 1；
- stale attempt：heartbeat/complete/fail/gate_retry 均条件更新 `WHERE id=? AND status='running' AND attempt=?`，
  受影响行数 != 1 拒绝写入（STALE_ATTEMPT_MSG）；
- 租约 45 分钟，heartbeat 延长 updated_at；heartbeat 周期上限 15 分钟；
- 不可领取状态矩阵：manual_review/done/failed 不可 claim；failed 为终态（不回收不重试）；
- 父 run 状态门禁：仅 run.status='running' 的 step 可 claim/recover（R106-3）；
- gate_retry 按 error-codes.yaml entries backoff_seconds（机器可读）+ retry_policies 熔断（R106-1）；
- 错误分流 handle_error：retryable→gate_retry / manual_takeover→manual_review / terminal→failed（R106-1）；
- 幂等键 = `<domain>:v1:<sha256(canonical_join(fields))>`（idempotency.md §一，R106-2 黄金向量）；
- ensure_run 并发同 key 返回原资源（R106-2，23505 不抛出）；
- 索引 N1 (status, updated_at) 覆盖 claim/recover 路径。
"""
from __future__ import annotations

import datetime
import hashlib
import json
import unicodedata
import uuid
from typing import Any, Optional

from sqlalchemy import text
from sqlalchemy.engine import Connection

# 冻结契约值（round-21）
LEASE_MINUTES = 45
HEARTBEAT_MAX_MINUTES = 15

# run/step 状态（v6 enum）
RUN_STATUSES = {"running", "waiting_manual", "paused", "done", "failed", "cancelled"}
STEP_STATUSES = {"pending", "running", "gate_retry", "manual_review", "done", "failed"}
RUN_ACTIVE = {"running"}  # 仅 running 的父 run 允许 claim/recover
RUN_TERMINAL = {"done", "failed", "cancelled"}

STALE_ATTEMPT_MSG = "stale attempt（status/attempt 不匹配）"

# error-codes.yaml entries（round-23 冻结；retryable/manual_takeover/backoff_seconds）
ERROR_ENTRIES = {
    "INVALID_POLICY_REF": {"retryable": False, "backoff_seconds": 0, "manual_takeover": True},
    "SKU_PRODUCT_MISMATCH": {"retryable": False, "backoff_seconds": 0, "manual_takeover": True},
    "CONTEXT_MISMATCH": {"retryable": False, "backoff_seconds": 0, "manual_takeover": True},
    "ACCOUNT_SHOP_MISMATCH": {"retryable": False, "backoff_seconds": 0, "manual_takeover": True},
    "SCOPE_MISMATCH": {"retryable": False, "backoff_seconds": 0, "manual_takeover": True},
    "DIMENSION_MISMATCH": {"retryable": False, "backoff_seconds": 0, "manual_takeover": True},
    "SUPERSEDE_MISMATCH": {"retryable": False, "backoff_seconds": 0, "manual_takeover": True},
    "VERIFICATION_REQUIRED": {"retryable": False, "backoff_seconds": 0, "manual_takeover": True},
    "AUTH_REQUIRED": {"retryable": False, "backoff_seconds": 0, "manual_takeover": True},
    "RATE_LIMIT": {"retryable": True, "backoff_seconds": 180, "manual_takeover": False},
    "TIMEOUT": {"retryable": True, "backoff_seconds": 60, "manual_takeover": False},
    "NO_MATCH": {"retryable": True, "backoff_seconds": 120, "manual_takeover": False},
    "PLATFORM_REJECT": {"retryable": False, "backoff_seconds": 0, "manual_takeover": True},
    "UNEXPECTED": {"retryable": True, "backoff_seconds": 60, "manual_takeover": False},
    "PAGE_CHANGED": {"retryable": False, "backoff_seconds": 0, "manual_takeover": True},
    "INSUFFICIENT_REFERENCES": {"retryable": True, "backoff_seconds": 120, "manual_takeover": False},
}

# error-codes.yaml retry_policies（round-23 A2 冻结：熔断/预算）
RETRY_POLICIES = {
    "RATE_LIMIT": {"max_attempts": 3, "circuit_open_after": 2, "circuit_open_seconds": 300},
    "TIMEOUT": {"max_attempts": 3},
    "NO_MATCH": {"max_attempts": 2},
    "INSUFFICIENT_REFERENCES": {"max_attempts": 2},
    "UNEXPECTED": {"max_attempts": 3},
}


class WorkflowQueueError(Exception):
    """流程队列契约错误。"""


# ---------------------------------------------------------------------------
# 幂等键公式（idempotency.md §一；R106-2 黄金向量；R108-1 UUID/时间规范化）
# ---------------------------------------------------------------------------
def _norm_uuid(value: Any) -> str:
    """已知 UUID 位置的等价表示 -> 小写规范形（idempotency.md §二：UUID 小写）。"""
    s = unicodedata.normalize("NFC", str(value))
    try:
        return str(uuid.UUID(s)).lower()
    except (ValueError, AttributeError):
        return s


def _norm_time(value: Any) -> str:
    """时间型字段 -> UTC ISO-8601（idempotency.md §二：时间 UTC ISO-8601）。

    解析为 datetime 后转 UTC；无法解析的 token（如业务窗口 'w1'）原样保留（R108-1 明确类型边界）。
    """
    s = unicodedata.normalize("NFC", str(value))
    try:
        dt = datetime.datetime.fromisoformat(s.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=datetime.timezone.utc)
        return dt.astimezone(datetime.timezone.utc).isoformat()
    except (ValueError, AttributeError):
        return s


def _canonical_join(fields: list[Any]) -> str:
    """canonical_join：NFC 归一、UTF-8、转义（先反斜杠后竖线）、| 连接、None→nil。"""
    out = []
    for f in fields:
        if f is None:
            out.append("nil")
            continue
        s = unicodedata.normalize("NFC", str(f))
        s = s.replace("\\", "\\\\")
        s = s.replace("|", "\\|")
        out.append(s)
    return "|".join(out)


def _hash_key(domain: str, fields: list[Any]) -> str:
    canon = _canonical_join(fields)
    digest = hashlib.sha256(canon.encode("utf-8")).hexdigest()
    return f"{domain}:v1:{digest}"


def compute_step_action_key(
    tenant_public_id: str,
    run_public_id: str,
    step_type: str,
    logical_action_slot: str,
    target_public_id_or_nil: Optional[str] = None,
) -> str:
    """idempotency.md §三 键 11：`step` 域；UUID 字段小写规范化（R108-1）；
    黄金向量 step:v1:5e4786... 保持（向量 UUID 全数字，lower 不变）。"""
    return _hash_key("step", [
        _norm_uuid(tenant_public_id),
        _norm_uuid(run_public_id),
        step_type,
        logical_action_slot,
        _norm_uuid(target_public_id_or_nil) if target_public_id_or_nil else None,
    ])


def compute_run_key(
    tenant_public_id: str,
    trigger_type: str,
    trigger_public_id: str,
    schedule_window: str,
    policy_version_id: str,
) -> str:
    """idempotency.md §三 键 10：`run` 域，输入序 trigger_type|trigger_public_id|schedule_window|
    policy_version_id（不含 tenant_public_id——R106-2 修正）；UUID/时间字段规范化（R108-1）。"""
    return _hash_key("run", [
        trigger_type,
        _norm_uuid(trigger_public_id),
        _norm_time(schedule_window),
        policy_version_id,
    ])


class WorkflowQueue:
    """workflow run/step 最小队列（真实 PG 事务，worker 并行安全）。"""

    def __init__(self, conn: Connection):
        self._conn = conn

    # ---------------------------------------------------------------- run
    def ensure_run(
        self,
        *,
        tenant_id: int,
        tenant_public_id: str,
        run_type: str,
        idempotency_key: str,
        trigger_type: str,
        trigger_public_id: str,
        schedule_window: str,
        policy_version_id: str,
        input_ref: Optional[str] = None,
    ) -> tuple[int, bool]:
        """幂等创建 run：并发同 key 用 `ON CONFLICT DO NOTHING` 原子幂等（无 savepoint 需求，
        R106-2）；冲突时返回既有 run (id, False)；首次创建 (id, True)。"""
        row = self._conn.execute(text(
            "SELECT id FROM app.workflow_runs WHERE tenant_id=:t AND idempotency_key=:k"),
            {"t": tenant_id, "k": idempotency_key}).first()
        if row is not None:
            return int(row[0]), False
        run_id = self._conn.execute(text(
            "INSERT INTO app.workflow_runs (public_id, tenant_id, run_type, idempotency_key, "
            " status, input_ref, created_at, updated_at) "
            "VALUES (gen_random_uuid(), :t, :rt, :k, 'running', :i, now(), now()) "
            "ON CONFLICT (tenant_id, idempotency_key) DO NOTHING RETURNING id"),
            {"t": tenant_id, "rt": run_type, "k": idempotency_key, "i": input_ref}).scalar()
        if run_id is not None:
            return int(run_id), True
        row = self._conn.execute(text(
            "SELECT id FROM app.workflow_runs WHERE tenant_id=:t AND idempotency_key=:k"),
            {"t": tenant_id, "k": idempotency_key}).first()
        if row is not None:
            return int(row[0]), False
        raise WorkflowQueueError(f"run 唯一冲突但 idempotency_key 未找到: {idempotency_key}")

    def set_run_status(
        self,
        *,
        run_id: int,
        status: str,
        state: Optional[str] = None,
        output_ref: Optional[str] = None,
    ) -> None:
        """R106-3：run 生命周期控制（pause/resume/cancel/finalize/manual）——更新 status + state/output_ref。"""
        if status not in RUN_STATUSES:
            raise WorkflowQueueError(f"非法 run 状态: {status}")
        upd = self._conn.execute(text(
            "UPDATE app.workflow_runs SET status=:s, state=:st, output_ref=:o, updated_at=now() "
            "WHERE id=:r"),
            {"s": status, "st": state, "o": output_ref, "r": run_id})
        if upd.rowcount != 1:
            raise WorkflowQueueError(f"run 不存在: {run_id}")

    def run_status(self, *, run_id: int) -> Optional[str]:
        return self._conn.execute(text(
            "SELECT status FROM app.workflow_runs WHERE id=:r"), {"r": run_id}).scalar()

    def enqueue_step(
        self,
        *,
        tenant_id: int,
        run_id: int,
        step_type: str,
        action_idempotency_key: str,
        gate_result: Optional[dict[str, Any]] = None,
    ) -> int:
        """入队 step（pending, attempt=1）。action key 唯一约束防重复入队（幂等）。"""
        try:
            nested = self._conn.begin_nested()
            try:
                step_id = self._conn.execute(text(
                    "INSERT INTO app.workflow_steps (tenant_id, run_id, step_type, status, attempt, "
                    " action_idempotency_key, gate_result, created_at, updated_at) "
                    "VALUES (:t, :r, :st, 'pending', 1, :k, CAST(:g AS jsonb), now(), now()) "
                    "RETURNING id"),
                    {"t": tenant_id, "r": run_id, "st": step_type, "k": action_idempotency_key,
                     "g": _json_dumps(gate_result)}).scalar()
                nested.commit()
                return int(step_id)
            except Exception as exc:  # noqa: BLE001
                nested.rollback()
                pgcode = getattr(getattr(exc, "orig", None), "pgcode", None)
                if pgcode != "23505":
                    raise
                constraint = getattr(getattr(exc, "orig", None), "diag", None) and \
                    getattr(getattr(exc.orig, "diag", None), "constraint_name", None)
                # 两约束可能同时冲突，PG 报其一：都查一次确定动作身份
                row = self._conn.execute(text(
                    "SELECT id FROM app.workflow_steps "
                    "WHERE tenant_id=:t AND action_idempotency_key=:k"),
                    {"t": tenant_id, "k": action_idempotency_key}).first()
                if row is not None:
                    # 同 action key 重放：幂等返回原资源（无论报哪个约束名）
                    return int(row[0])
                # 不同 action key 同 run 同 step_type：显式拒绝（R108-1），禁止合并
                raise WorkflowQueueError(
                    f"同 run 同 step_type 已有 step（不同 action key 冲突，拒绝合并）: "
                    f"run={run_id} step_type={step_type} key={action_idempotency_key}")
        except WorkflowQueueError:
            raise

    # ---------------------------------------------------------------- claim
    def claim(self, *, run_id: int) -> Optional[tuple[int, int]]:
        """领取一个可执行 step（SKIP LOCKED 并发安全）；返回 (step_id, attempt) fencing token。

        **首次 claim attempt 保持 1**（test-strategy §四.3）；仅父 run status='running' 可领
        （R106-3）；gate_retry 需 backoff 到期（gate_result.retry_at <= now）才可领取。
        """
        row = self._conn.execute(text(
            "SELECT s.id, s.attempt, s.gate_result FROM app.workflow_steps s "
            "JOIN app.workflow_runs r ON r.id = s.run_id "
            "WHERE s.run_id=:r AND r.status='running' AND s.status='pending' "
            "ORDER BY s.id FOR UPDATE SKIP LOCKED LIMIT 1"),
            {"r": run_id}).first()
        if row is None:
            row = self._conn.execute(text(
                "SELECT s.id, s.attempt, s.gate_result FROM app.workflow_steps s "
                "JOIN app.workflow_runs r ON r.id = s.run_id "
                "WHERE s.run_id=:r AND r.status='running' AND s.status='gate_retry' AND "
                "      (s.gate_result IS NULL OR "
                "       COALESCE((s.gate_result->>'retry_at')::timestamptz, '2000-01-01') <= now()) "
                "ORDER BY s.id FOR UPDATE SKIP LOCKED LIMIT 1"),
                {"r": run_id}).first()
        if row is None:
            return None
        step_id, attempt = int(row[0]), int(row[1])
        # 升级 running；**attempt 保持原值**（gate_retry 已在重试时递增；recover 在回收时递增）
        upd = self._conn.execute(text(
            "UPDATE app.workflow_steps SET status='running', updated_at=now() "
            "WHERE id=:s AND status IN ('pending','gate_retry') AND attempt=:a"),
            {"s": step_id, "a": attempt})
        if upd.rowcount != 1:
            raise WorkflowQueueError("claim 竞态：step 状态/attempt 已变化")
        return step_id, attempt

    # ------------------------------------------------- stale attempt 门禁
    def _stale_guarded_update(self, step_id: int, attempt: int, sql: str, params: dict) -> None:
        upd = self._conn.execute(text(sql), {**params, "s": step_id, "a": attempt})
        if upd.rowcount != 1:
            raise WorkflowQueueError(STALE_ATTEMPT_MSG)

    def heartbeat(self, *, step_id: int, attempt: int) -> None:
        self._stale_guarded_update(step_id, attempt,
            "UPDATE app.workflow_steps SET updated_at=now() "
            "WHERE id=:s AND status='running' AND attempt=:a", {})

    def complete(self, *, step_id: int, attempt: int, evidence_ref: Optional[str] = None) -> None:
        self._stale_guarded_update(step_id, attempt,
            "UPDATE app.workflow_steps SET status='done', evidence_ref=:e, updated_at=now() "
            "WHERE id=:s AND status='running' AND attempt=:a",
            {"e": evidence_ref})

    def fail(self, *, step_id: int, attempt: int, error_code: Optional[str] = None) -> None:
        """错误处理入口：按 error-codes.yaml 注册表分流（R106-1.3）——
        manual_takeover=true 的码转 manual_review（人工接管，不终止 execution）；
        其余强制 failed（terminal 语义）。"""
        if error_code and ERROR_ENTRIES.get(error_code, {}).get("manual_takeover"):
            self._stale_guarded_update(step_id, attempt,
                "UPDATE app.workflow_steps SET status='manual_review', error_code=:e, "
                "updated_at=now() "
                "WHERE id=:s AND status='running' AND attempt=:a", {"e": error_code})
            return
        self._stale_guarded_update(step_id, attempt,
            "UPDATE app.workflow_steps SET status='failed', error_code=:e, updated_at=now() "
            "WHERE id=:s AND status='running' AND attempt=:a",
            {"e": error_code})

    # ------------------------------------------------------------ 错误分流
    def handle_error(
        self,
        *,
        step_id: int,
        attempt: int,
        error_code: str,
        gate_result: Optional[dict[str, Any]] = None,
    ) -> str:
        """R106-1：消费 error-codes.yaml 注册表的错误分流：
        - retryable=true -> gate_retry（backoff 到期可重领；预算耗尽 -> failed）
        - manual_takeover=true -> manual_review（转人工，不终止 execution）
        - 其它（无注册表/terminal）-> failed
        返回目标状态。
        """
        entry = ERROR_ENTRIES.get(error_code)
        if entry is None:
            self.fail(step_id=step_id, attempt=attempt, error_code=error_code)
            return "failed"
        if entry["retryable"]:
            # R108-2：返回 gate_retry 实际持久化的目标状态（预算耗尽 -> failed）
            return self.gate_retry(step_id=step_id, attempt=attempt, error_code=error_code,
                                   gate_result=gate_result)
        if entry["manual_takeover"]:
            self._stale_guarded_update(step_id, attempt,
                "UPDATE app.workflow_steps SET status='manual_review', error_code=:e, "
                "updated_at=now() "
                "WHERE id=:s AND status='running' AND attempt=:a", {"e": error_code})
            return "manual_review"
        self.fail(step_id=step_id, attempt=attempt, error_code=error_code)
        return "failed"

    def gate_retry(
        self,
        *,
        step_id: int,
        attempt: int,
        error_code: str,
        gate_result: Optional[dict[str, Any]] = None,
    ) -> str:
        """R106-1/R108-2：按 entries backoff_seconds + retry_policies 熔断进入 gate_retry
        （attempt 恰增 1）；预算耗尽 -> failed 终态。**返回实际持久化状态**（gate_retry/failed）。"""
        policy = RETRY_POLICIES.get(error_code)
        if policy is None:
            raise WorkflowQueueError(f"error_code 无 retry policy（机器可读失败）: {error_code}")
        max_attempts = int(policy["max_attempts"])
        # 本轮执行 attempt 已 >= max_attempts -> 预算耗尽，终态 failed（不回收不重试）
        if attempt >= max_attempts:
            self._stale_guarded_update(step_id, attempt,
                "UPDATE app.workflow_steps SET status='failed', error_code=:e, updated_at=now() "
                "WHERE id=:s AND status='running' AND attempt=:a", {"e": error_code})
            return "failed"
        # backoff：entries backoff_seconds；RATE_LIMIT 熔断覆盖最短等待
        entry = ERROR_ENTRIES.get(error_code, {})
        backoff = int(entry.get("backoff_seconds", 0) or 0)
        if error_code == "RATE_LIMIT":
            circuit_after = int(policy.get("circuit_open_after", 2))
            if attempt >= circuit_after:
                backoff = int(policy.get("circuit_open_seconds", 300))
        merged = dict(gate_result or {})
        merged["error_code"] = error_code
        if backoff > 0:
            merged["retry_at"] = _now_iso_plus(backoff)
        else:
            merged.pop("retry_at", None)
        # 新 attempt 恰增 1（R106-1.1：重试递增；claim 时保持）
        self._stale_guarded_update(step_id, attempt,
            "UPDATE app.workflow_steps SET status='gate_retry', error_code=:e, gate_result=:g, "
            "attempt=attempt+1, updated_at=now() "
            "WHERE id=:s AND status='running' AND attempt=:a",
            {"e": error_code, "g": _json_dumps(merged)})
        return "gate_retry"

    # ----------------------------------------------------------- recover
    def recover_stale_attempts(self) -> int:
        """R108-3：recover 与 set_run_status 建立共同并发协议——先锁定过期 step 所属父 run 行
        （FOR UPDATE OF runs），锁后按**当前** run 状态决定是否回收（不依赖 UPDATE FROM 旧快照）；
        仅父 run='running' 的 45 分钟无 heartbeat running step -> pending（新 attempt 恰增 1）。"""
        rows = self._conn.execute(text(
            "SELECT DISTINCT s.run_id FROM app.workflow_steps s "
            "WHERE s.status='running' AND "
            "      s.updated_at < now() - make_interval(mins => :m)"),
            {"m": LEASE_MINUTES}).all()
        recovered = 0
        for (run_id,) in rows:
            # 与 set_run_status 串行化：锁父 run 行后再判当前状态
            st = self._conn.execute(text(
                "SELECT status FROM app.workflow_runs WHERE id=:r FOR UPDATE"),
                {"r": run_id}).scalar()
            if st != "running":
                continue
            upd = self._conn.execute(text(
                "UPDATE app.workflow_steps SET status='pending', attempt=attempt+1, updated_at=now() "
                "WHERE run_id=:r AND status='running' AND "
                "      updated_at < now() - make_interval(mins => :m)"),
                {"r": run_id, "m": LEASE_MINUTES})
            recovered += int(upd.rowcount)
        return recovered

    def list_pending(self, *, run_id: int) -> list[dict[str, Any]]:
        rows = self._conn.execute(text(
            "SELECT id, step_type, status, attempt, error_code, gate_result, "
            " action_idempotency_key, updated_at FROM app.workflow_steps "
            "WHERE run_id=:r ORDER BY id"), {"r": run_id}).mappings().all()
        return [dict(r) for r in rows]


def _json_dumps(value: Optional[dict[str, Any]]) -> Optional[str]:
    if value is None:
        return None
    return json.dumps(value, ensure_ascii=True)


def _now_iso_plus(seconds: int) -> str:
    return (datetime.datetime.now(datetime.timezone.utc)
            + datetime.timedelta(seconds=seconds)).isoformat()
