"""M3 自动素材优化模块 · SQLAlchemy 2.0 引擎/会话管理。

默认 SQLite（本模块独立库 data/db/m3-optimization.db），生产通过 M3_DB_URL 切 PostgreSQL。
一模块一库铁律：只操作本模块库。
"""

from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, Optional

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from .config import M3Config


class Database:
    """轻量封装：engine + session 工厂 + 建表。"""

    def __init__(self, config: M3Config):
        self.config = config
        connect_args: dict = {}
        if config.db_url.startswith("sqlite"):
            connect_args["check_same_thread"] = False
            if config.db_url.startswith("sqlite:///"):
                # 文件型 SQLite：确保父目录存在
                db_path = Path(config.db_url.replace("sqlite:///", ""))
                if db_path.parent and not db_path.parent.exists():
                    db_path.parent.mkdir(parents=True, exist_ok=True)
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


def default_database(config: Optional[M3Config] = None) -> Database:
    if config is None:
        from .config import load_config

        config = load_config()
    return Database(config)
