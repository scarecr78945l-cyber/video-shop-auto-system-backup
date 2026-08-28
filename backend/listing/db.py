"""M4 自动上架引擎/会话管理（SQLAlchemy 2.0）。

默认 SQLite（本模块独立库 data/db/m4-listing.db），生产通过
LISTING_DB_URL 切 PostgreSQL。一模块一库铁律：只操作本模块库。
文件型 SQLite 自动创建父目录（data/db）。
"""

from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, Optional

from sqlalchemy import create_engine, inspect
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from .config import ListingConfig


class ListingDatabase:
    """轻量封装：engine + session 工厂 + 建表（幂等）。"""

    def __init__(self, config: ListingConfig):
        self.config = config
        connect_args: dict = {}
        if config.db_url.startswith("sqlite"):
            connect_args["check_same_thread"] = False
            if config.db_url.startswith("sqlite:///"):
                # 文件型 SQLite：确保父目录存在（默认库 data/db/m4-listing.db，目录可能尚未创建）
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
        """幂等建表（7 张 listing_* 表）。"""
        from . import tables  # noqa: F401  确保表已注册

        tables.Base.metadata.create_all(self.engine)

    def table_names(self) -> list[str]:
        """已建表清单（init-db CLI 输出用）。"""
        return sorted(inspect(self.engine).get_table_names())

    def dispose(self) -> None:
        self.engine.dispose()

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


def default_database(config: Optional[ListingConfig] = None) -> ListingDatabase:
    if config is None:
        from .config import load_config

        config = load_config()
    return ListingDatabase(config)
