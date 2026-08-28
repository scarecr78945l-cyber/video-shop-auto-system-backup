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


# ---------------------------------------------------------------- M2 materials
# 素材库基座 fixtures：临时 SQLite + 临时存储目录（不动 sourcing fixtures）。
# 内部 import：materials 包异常时不连带拖垮既有 sourcing 测试。


@pytest.fixture()
def cfg_materials(tmp_path):
    """M2 素材库隔离配置（临时 SQLite）。"""
    from materials.config import load_config

    return load_config(
        db_url=f"sqlite:///{tmp_path / 'materials-test.db'}",
        data_dir=tmp_path / "data",
        fixtures_dir=Path(__file__).parent.parent / "fixtures",
        storage_dir=tmp_path / "storage",
    )


@pytest.fixture()
def db_materials(cfg_materials):
    """M2 素材库 Database（建好 7 张 asset_* 表）。"""
    from materials.db import Database

    database = Database(cfg_materials)
    database.create_all()
    return database
