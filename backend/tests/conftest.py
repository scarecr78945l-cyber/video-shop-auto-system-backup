"""pytest 全局配置：保证 sourcing 包可导入 + 共享 fixtures 路径。"""

import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parent
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

import pytest  # noqa: E402

from sourcing.config import SourcingConfig  # noqa: E402


@pytest.fixture()
def cfg(tmp_path):
    """隔离配置：临时 SQLite + 指向仓库内 fixtures。"""
    return SourcingConfig(
        db_url=f"sqlite:///{tmp_path/'test.db'}",
        fixtures_dir=Path(__file__).parent.parent / "fixtures",
        data_dir=tmp_path / "data",
    )


@pytest.fixture()
def db(cfg):
    from sourcing.db import Database

    database = Database(cfg)
    database.create_all()
    return database
