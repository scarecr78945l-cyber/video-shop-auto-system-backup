# -*- coding: utf-8 -*-
"""P0-2 批次 1（B2）：SnapshotCollector(PG)（round-133；round-135 R134-3 加固）。

依据 round-132-cdx（F132-4 + §3.3）+ round-134-cdx R134-3：

- Collector 只调唯一 public 写入口 `SnapshotRepository.write_observation(obs)`
  （受信边界内完成 validate + 现场 hash + version key + draft 重验，R134-1）；
- run_once/collect_missing 对 observation 集合逐个执行，分别统计 created/reused/conflicted/rejected；
  单行 SAVEPOINT（begin_nested）隔离，失败不整批崩、保留外层事务可用性；
- **异常分类（R134-3）**：
    - ObservationValidationError / SnapshotContentConflict -> 业务结果（rejected/conflicted）；
    - 行级 PostgreSQL 约束/trigger SQLSTATE allowlist（ZT006 维度、23503 FK、23502 NOT NULL、
      23514 CHECK、23P01 exclusion）-> rejected（行级可隔离）；
    - OperationalError/InterfaceError/ProgrammingError/连接故障/未知异常 -> **原样向上抛出**
      （整批失败，不伪装成输入坏行）；
- collect_missing 只按 (S,V) 补缺，无 legacy recorded_at 游标。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, List, Optional

from sqlalchemy.engine import Connection
from sqlalchemy.exc import DBAPIError

from .repository import SnapshotContentConflict, SnapshotRepository
from .version import ObservationValidationError, ReportObservation

# 行级 PostgreSQL 约束/trigger SQLSTATE allowlist（R134-3）
ALLOWED_ROW_SQLSTATES = {
    "ZT006",   # 维度一致性（ad_report_snapshots / roi_feedback_events trigger）
    "23503",   # foreign_key_violation
    "23502",   # not_null_violation
    "23514",   # check_violation
    "23P01",   # exclusion_violation
}


@dataclass
class CollectResult:
    created: int = 0
    reused: int = 0
    conflicted: int = 0
    rejected: int = 0
    details: List[dict] = field(default_factory=list)  # [{row, outcome, reason}]

    def __post_init__(self) -> None:
        self.total = self.created + self.reused + self.conflicted + self.rejected

    def add(self, outcome: str, reason: str = "", row: Any = None) -> None:
        if outcome == "created":
            self.created += 1
        elif outcome == "reused":
            self.reused += 1
        elif outcome == "conflicted":
            self.conflicted += 1
        else:
            self.rejected += 1
        if reason or outcome in ("conflicted", "rejected"):
            self.details.append({"row": row, "outcome": outcome, "reason": reason})
        self.total = self.created + self.reused + self.conflicted + self.rejected


def _sqlstate_of(exc: DBAPIError) -> str:
    """从 DBAPI 异常提取 PostgreSQL SQLSTATE（psycopg2: exc.orig.pgcode）。"""
    orig = getattr(exc, "orig", None)
    if orig is not None:
        pgcode = getattr(orig, "pgcode", None)
        if pgcode:
            return str(pgcode)
        sqlstate = getattr(orig, "sqlstate", None)
        if sqlstate:
            return str(sqlstate)
    return ""


class SnapshotCollector:
    """PG 快照收集器：观测行 -> 唯一 public 写入口 -> append-only 入库，异常按 allowlist 分类。"""

    def __init__(self, conn: Connection, repository: Optional[SnapshotRepository] = None):
        self._conn = conn
        self._repo = repository or SnapshotRepository(conn)

    def _process_one(self, obs: ReportObservation, result: CollectResult, row: Any) -> None:
        """单行处理：SAVEPOINT 隔离；仅 allowlist 内异常转业务结果，其余原样抛出（R134-3）。"""
        try:
            with self._conn.begin_nested():
                res = self._repo.write_observation(obs)
            result.add("created" if res.created else "reused",
                       row=row, reason="" if res.created else f"reuse id={res.snapshot_id}")
        except SnapshotContentConflict as exc:
            result.add("conflicted", reason=str(exc), row=row)
        except ObservationValidationError as exc:
            result.add("rejected", reason=str(exc), row=row)
        except DBAPIError as exc:
            sqlstate = _sqlstate_of(exc)
            if sqlstate in ALLOWED_ROW_SQLSTATES:
                # 行级约束/trigger 拒绝：单行隔离，整批继续
                result.add("rejected",
                           reason=f"SQLSTATE {sqlstate}: {exc.orig}", row=row)
            else:
                # 连接故障/事务状态/编程错误/未知：原样抛出，整批失败
                raise
        # 其他非 DBAPI 未知异常：原样抛出（不伪装成 rejected）

    def run_once(self, observations: Iterable[ReportObservation]) -> CollectResult:
        """逐行 insert-or-select（append-only）。"""
        result = CollectResult()
        for i, obs in enumerate(observations):
            self._process_one(obs, result, i)
        return result

    def collect_missing(self, observations: Iterable[ReportObservation]) -> CollectResult:
        """断点补缺：只按 (S,V) 逐个 insert-or-select（无 legacy recorded_at 游标）。"""
        return self.run_once(observations)
