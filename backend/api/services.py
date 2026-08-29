"""M6 后端 API 层 · 服务容器（Services）。

聚合 M0~M5 模块 Database/repo 的单例容器，供路由依赖注入使用：
- 每个模块库可经 M6 配置的 db_url 覆盖（测试用 tmp 库，生产用各模块默认库）；
- 零修改各模块源码：只构造其 config/Database，调用其 repo 函数；
- 提供 kill-switch（对齐 M0 `M0_KILL_SWITCH` / app_config `risk.kill_switch`）
  与操作审计（写 M0 logs 表，脱敏留痕）能力。
"""

from __future__ import annotations

import logging
import threading
from typing import Any, Optional

from .auth import AuthStore, AuthStoreConfigError, FixturesAuthStore, M0AuthStore
from .config import AUTH_MODE_FIXTURES, AUTH_MODE_M0, M6Config
from .errors import redact_text

logger = logging.getLogger(__name__)

KILL_SWITCH_CONFIG_KEY = "risk.kill_switch"


class Services:
    """聚合服务容器：惰性构造各模块 Database 与业务对象。"""

    def __init__(
        self,
        settings: Optional[M6Config] = None,
        *,
        auth_store: Optional[AuthStore] = None,
    ):
        self.settings = settings or M6Config()
        self._auth_store = auth_store
        self._dbs: dict[str, Any] = {}
        self._repos: dict[str, Any] = {}
        self._lock = threading.Lock()
        self._kill_switch_memory: Optional[bool] = None  # M0 库不可用时的内存兜底
        self._kill_switch_loaded = False

    # ------------------------------------------------------------ 鉴权
    @property
    def auth_store(self) -> AuthStore:
        if self._auth_store is not None:
            return self._auth_store
        cfg = self.settings
        if cfg.api_auth_mode == AUTH_MODE_M0:
            try:
                self._auth_store = M0AuthStore(
                    self.m0_db,
                    session_ttl_hours=cfg.session_ttl_hours,
                )
            except AuthStoreConfigError:
                raise
        else:
            self._auth_store = FixturesAuthStore(
                admin_username=cfg.admin_username,
                admin_password_hash=cfg.admin_password_hash,
                session_ttl_hours=cfg.session_ttl_hours,
            )
        return self._auth_store

    # ------------------------------------------------------------ 模块库（惰性）
    def _module_db(self, key: str, url_attr: str, builder) -> Any:
        with self._lock:
            if key in self._dbs:
                return self._dbs[key]
            url = getattr(self.settings, url_attr) or None
            overrides = {"db_url": url} if url else {}
            config = builder(overrides)
            database = config["database_class"](config["config"])
            database.create_all()
            if config.get("seed"):
                config["seed"](database)
            self._dbs[key] = database
            return database

    # ---- M0 foundation ----
    @property
    def m0_db(self):
        return self._module_db(
            "m0",
            "m0_db_url",
            lambda overrides: _build("foundation", overrides),
        )

    # ---- M1 sourcing ----
    @property
    def sourcing_db(self):
        return self._module_db(
            "sourcing",
            "sourcing_db_url",
            lambda overrides: _build("sourcing", overrides),
        )

    # ---- M2 materials ----
    @property
    def materials_db(self):
        return self._module_db(
            "materials",
            "materials_db_url",
            lambda overrides: _build("materials", overrides),
        )

    # ---- M3 optimization ----
    @property
    def m3_db(self):
        return self._module_db(
            "m3",
            "m3_db_url",
            lambda overrides: _build("optimization", overrides),
        )

    # ---- M4 listing ----
    @property
    def m4_db(self):
        return self._module_db(
            "m4",
            "m4_db_url",
            lambda overrides: _build("listing", overrides),
        )

    # ---- M5 ads ----
    @property
    def m5_db(self):
        return self._module_db(
            "m5",
            "m5_db_url",
            lambda overrides: _build("ads", overrides),
        )

    # ------------------------------------------------------------ 业务对象
    @property
    def m0_queue(self):
        """M0 WorkflowQueue（任务队列）。"""
        if "m0_queue" not in self._repos:
            from foundation.repo import WorkflowQueue

            self._repos["m0_queue"] = WorkflowQueue(self.m0_db)
        return self._repos["m0_queue"]

    @property
    def materials_repo(self):
        if "materials_repo" not in self._repos:
            from materials.repo import AssetRepo

            self._repos["materials_repo"] = AssetRepo(self.materials_db)
        return self._repos["materials_repo"]

    @property
    def relevance_gate_service(self):
        if "relevance_gate" not in self._repos:
            from materials.integration import RelevanceGateService

            self._repos["relevance_gate"] = RelevanceGateService(self.materials_repo)
        return self._repos["relevance_gate"]

    @property
    def m3_image_repo(self):
        if "m3_image_repo" not in self._repos:
            from optimization.repo import ImageRepo

            self._repos["m3_image_repo"] = ImageRepo(self.m3_db)
        return self._repos["m3_image_repo"]

    @property
    def m3_copywrite_repo(self):
        if "m3_copywrite_repo" not in self._repos:
            from optimization.repo import CopywriteRepo

            self._repos["m3_copywrite_repo"] = CopywriteRepo(self.m3_db)
        return self._repos["m3_copywrite_repo"]

    @property
    def m3_review_repo(self):
        """M3 审核记录仓储（opt_review_records，审核判定留痕用）。"""
        if "m3_review_repo" not in self._repos:
            from optimization.review.gate import ReviewRecordRepo

            self._repos["m3_review_repo"] = ReviewRecordRepo(self.m3_db)
        return self._repos["m3_review_repo"]

    @property
    def m4_repo(self):
        if "m4_repo" not in self._repos:
            from listing.repo import ListingRepo

            self._repos["m4_repo"] = ListingRepo(self.m4_db)
        return self._repos["m4_repo"]

    @property
    def m4_state_machine(self):
        if "m4_state_machine" not in self._repos:
            from listing.state_machine import ListingStateMachine

            self._repos["m4_state_machine"] = ListingStateMachine(self.m4_repo)
        return self._repos["m4_state_machine"]

    @property
    def m4_candidate_pool(self):
        if "m4_candidate_pool" not in self._repos:
            from listing.candidate_pool import CandidatePool

            self._repos["m4_candidate_pool"] = CandidatePool(self.m4_repo)
        return self._repos["m4_candidate_pool"]

    # ------------------------------------------------------------ kill-switch（S8）
    def kill_switch_get(self) -> bool:
        """读取一键全停状态：优先 M0 app_config `risk.kill_switch`，兜底内存。"""
        if not self._kill_switch_loaded:
            self._kill_switch_loaded = True
            try:
                from foundation.tables import AppConfigRow

                with self.m0_db.session() as session:
                    row = session.get(AppConfigRow, KILL_SWITCH_CONFIG_KEY)
                if row is not None:
                    value = row.value or {}
                    self._kill_switch_memory = bool(value.get("enabled", False))
            except Exception:  # noqa: BLE001 —— M0 库不可用时静默走内存兜底
                logger.warning("kill-switch 读取 M0 app_config 失败，使用内存兜底")
        return bool(self._kill_switch_memory)

    def kill_switch_set(self, enabled: bool) -> dict[str, Any]:
        """设置一键全停：写 M0 app_config `risk.kill_switch`（对齐 `M0_KILL_SWITCH`）。"""
        self._kill_switch_memory = bool(enabled)
        self._kill_switch_loaded = True
        try:
            from foundation.tables import AppConfigRow

            with self.m0_db.session() as session:
                row = session.get(AppConfigRow, KILL_SWITCH_CONFIG_KEY)
                if row is None:
                    session.add(
                        AppConfigRow(
                            key=KILL_SWITCH_CONFIG_KEY,
                            value={"enabled": bool(enabled)},
                            description="一键全停总开关（S8，最高优先级）",
                        )
                    )
                else:
                    row.value = {"enabled": bool(enabled)}
        except Exception:  # noqa: BLE001 —— M0 库不可用仅内存生效
            logger.warning("kill-switch 写 M0 app_config 失败，仅内存生效")
        return {"key": KILL_SWITCH_CONFIG_KEY, "enabled": bool(enabled)}

    # ------------------------------------------------------------ 操作审计
    def audit(
        self,
        event: str,
        message: str = "",
        evidence: Any = None,
        operator: str = "",
        module: str = "m6",
        level: str = "INFO",
    ) -> None:
        """写 M0 logs 表操作留痕（证据经脱敏；best-effort 不抛错）。"""
        try:
            from foundation.tables import LogEntry

            with self.m0_db.session() as session:
                session.add(
                    LogEntry(
                        module=module,
                        level=level,
                        event=event,
                        message=redact_text(message, 500),
                        evidence=redact_text(str(evidence or {}), 1000),
                    )
                )
        except Exception:  # noqa: BLE001
            logger.warning("审计日志写入失败 event=%s", event)


# ---------------------------------------------------------------- 构造工具


def _build(module: str, overrides: dict[str, str]) -> dict[str, Any]:
    """构造模块 config + database_class + 可选 seed，返回 dict。"""
    if module == "foundation":
        from foundation.config import load_config
        from foundation.db import Database

        cfg = load_config(**overrides)
        return {
            "config": cfg,
            "database_class": Database,
            "seed": lambda db: db.seed(),
        }
    if module == "sourcing":
        from sourcing.config import load_config
        from sourcing.db import Database

        return {"config": load_config(**overrides), "database_class": Database, "seed": None}
    if module == "materials":
        from materials.config import load_config
        from materials.db import Database

        return {"config": load_config(**overrides), "database_class": Database, "seed": None}
    if module == "optimization":
        from optimization.config import load_config
        from optimization.db import Database

        return {"config": load_config(**overrides), "database_class": Database, "seed": None}
    if module == "listing":
        from listing.config import load_config
        from listing.db import ListingDatabase

        return {"config": load_config(**overrides), "database_class": ListingDatabase, "seed": None}
    if module == "ads":
        from ads.config import load_config
        from ads.db import Database

        return {"config": load_config(**overrides), "database_class": Database, "seed": None}
    raise ValueError(f"unknown module: {module}")
