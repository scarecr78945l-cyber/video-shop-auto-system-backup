"""SQLAlchemy 2.0 引擎/会话管理。

默认 SQLite（开发零配置），生产通过 SOURCING_DB_URL 切 PostgreSQL。
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator, Optional

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from .config import SourcingConfig


class Database:
    """轻量封装：engine + session 工厂 + 建表。"""

    def __init__(self, config: SourcingConfig):
        self.config = config
        connect_args: dict = {}
        if config.db_url.startswith("sqlite"):
            connect_args["check_same_thread"] = False
        self.engine: Engine = create_engine(
            config.db_url, echo=False, future=True, connect_args=connect_args
        )
        self._session_factory = sessionmaker(
            bind=self.engine, expire_on_commit=False, future=True
        )

    def create_all(self) -> None:
        from . import tables  # noqa: F401  确保表已注册

        tables.Base.metadata.create_all(self.engine)

    @contextmanager
    def session(self) -> Iterator[Session]:
        session = self._session_factory()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def new_session(self) -> Session:
        return self._session_factory()


def default_database(config: Optional[SourcingConfig] = None) -> Database:
    if config is None:
        from .config import load_config

        config = load_config()
    return Database(config)
