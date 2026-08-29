"""REC-融合 P0-3：浏览器会话管理服务（M0 公共会话服务）。

旧系统 wechat_session/alibaba_session/session_watcher 迁移：
- 按来源注册 CDP 端口/profile（配置化）；
- 心跳探测登录态（探测回调可注入，fixtures 用 Mock）；
- 失效 → 来源置 waiting_login（AUTH_REQUIRED 语义，对齐 DA-008 码表）→ 阻塞该来源采集，
  其它来源不阻塞（失败隔离）；
- 人工登录后 resume → 来源恢复可采集（断点续跑）。

数据口径（REC-005/DA-001）：时间一律 UTC（ISO8601）。
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class SourceSession:
    """单个来源的会话状态（心跳探测 + 失效管理）。"""

    source: str
    cdp_port: int
    profile_dir: str = ""
    status: str = "unknown"  # logged_in | expired | unknown | waiting_login
    consecutive_failures: int = 0
    last_probed_at: str = ""
    waiting_since: str = ""
    # 探测回调（fixtures 注入 Mock；真实实现=CDP/页面探测）
    probe_fn: callable | None = None
    evidence: dict = field(default_factory=dict)

    def probe(self) -> str:
        """心跳探测登录态；返回并更新 status。"""
        if self.probe_fn is None:
            self.status = "unknown"
            return self.status
        self.last_probed_at = _utcnow_iso()
        ok = bool(self.probe_fn())
        if ok:
            self.status = "logged_in"
            self.consecutive_failures = 0
            self.waiting_since = ""
        else:
            self.consecutive_failures += 1
            if self.consecutive_failures >= 2:  # 连续 2 次失败 → 失效（对齐熔断语义）
                self.status = "expired"
                if not self.waiting_since:
                    self.waiting_since = _utcnow_iso()
            else:
                self.status = "unknown"
        self.evidence = {
            "consecutive_failures": self.consecutive_failures,
            "last_probed_at": self.last_probed_at,
        }
        return self.status


class SessionService:
    """M0 公共会话服务：注册来源 → 心跳探测 → 失效阻塞 → 人工恢复。"""

    def __init__(self) -> None:
        self._sessions: dict[str, SourceSession] = {}

    def register(
        self,
        source: str,
        cdp_port: int,
        profile_dir: str = "",
        probe_fn: callable | None = None,
    ) -> SourceSession:
        """注册来源（幂等：同 source 覆盖配置不重置状态）。"""
        session = self._sessions.get(source)
        if session is None:
            session = SourceSession(
                source=source, cdp_port=cdp_port,
                profile_dir=profile_dir, probe_fn=probe_fn,
            )
            self._sessions[source] = session
        else:
            session.cdp_port = cdp_port
            session.profile_dir = profile_dir
            session.probe_fn = probe_fn
        return session

    def probe_all(self) -> dict[str, str]:
        """全来源心跳探测；返回 {source: status}。"""
        return {s.source: s.probe() for s in self._sessions.values()}

    def is_ready(self, source: str) -> bool:
        """来源是否可采集（logged_in 或 unknown 且未进入 waiting_login）。"""
        session = self._sessions.get(source)
        if session is None:
            return True  # 未注册来源不阻塞（向后兼容）
        return session.status in ("logged_in", "unknown")

    def status_of(self, source: str) -> str:
        session = self._sessions.get(source)
        return session.status if session else "unknown"

    def block(self, source: str, reason: str = "") -> None:
        """人工/风控将来源置 waiting_login（阻塞该来源采集）。"""
        session = self._sessions.get(source)
        if session:
            session.status = "waiting_login"
            session.waiting_since = _utcnow_iso()
            session.evidence["block_reason"] = reason

    def resume(self, source: str) -> None:
        """人工登录完成 → 恢复（断点续跑）。"""
        session = self._sessions.get(source)
        if session:
            session.status = "logged_in"
            session.consecutive_failures = 0
            session.waiting_since = ""
            session.evidence["resumed_at"] = _utcnow_iso()

    def snapshot(self) -> list[dict]:
        """会话快照（脱敏，供看板/日志）。"""
        return [
            {
                "source": s.source,
                "cdp_port": s.cdp_port,
                "status": s.status,
                "waiting_since": s.waiting_since,
            }
            for s in self._sessions.values()
        ]

    def to_json(self) -> str:
        return json.dumps(self.snapshot(), ensure_ascii=False)
