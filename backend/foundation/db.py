"""M0 基座引擎/会话管理（参照 backend/sourcing/db.py 风格）。

默认 SQLite（开发零配置），生产通过 M0_DB_URL 切 PostgreSQL。
测试可用内存库：sqlite:///:memory:（StaticPool 保证跨 session 共享同一连接）。
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator, Optional

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from .config import FoundationConfig, load_config


class Database:
    """轻量封装：engine + session 工厂 + 建表 + 错误码种子。"""

    def __init__(self, config: FoundationConfig):
        self.config = config
        connect_args: dict = {}
        poolclass = None
        if config.db_url.startswith("sqlite"):
            connect_args["check_same_thread"] = False
            if config.db_url == "sqlite:///:memory:":
                # 内存库：固定单连接，保证建表/写入/读取跨 session 可见
                poolclass = StaticPool
        self.engine: Engine = create_engine(
            config.db_url,
            echo=False,
            future=True,
            connect_args=connect_args,
            poolclass=poolclass,
        )
        self._session_factory = sessionmaker(
            bind=self.engine, expire_on_commit=False, future=True
        )

    def create_all(self) -> None:
        """建共享五表（幂等：CREATE TABLE IF NOT EXISTS 语义）。"""
        from . import tables  # noqa: F401  确保表已注册

        tables.Base.metadata.create_all(self.engine)

    def seed(self) -> int:
        """幂等写入 error_codes 种子数据（已存在的 code 跳过），返回新增条数。"""
        from .tables import seed_error_codes

        with self.session() as session:
            return seed_error_codes(session)

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


def default_database(config: Optional[FoundationConfig] = None) -> Database:
    if config is None:
        config = load_config()
    return Database(config)
