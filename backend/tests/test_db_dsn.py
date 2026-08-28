"""S1a：默认 DSN 与 SQLite 父目录自动创建（REC-007 基线改造）。

覆盖两点：
1. 默认 load_config() 的 db_url 指向 data/db/m1-sourcing.db（唯一正式开发库）；
2. Database 对「父目录不存在的文件型 SQLite」自动 mkdir，构造与 create_all 不抛异常。
"""

from sqlalchemy import inspect

from sourcing.config import load_config
from sourcing.db import Database


def test_default_db_url_points_to_m1_dev_db():
    cfg = load_config()
    assert "data/db/m1-sourcing.db" in cfg.db_url


def test_create_all_auto_creates_missing_parent_dir(tmp_path):
    db_file = tmp_path / "a" / "b" / "test.db"
    cfg = load_config(db_url=f"sqlite:///{db_file}")
    db = Database(cfg)  # 父目录不存在时构造不抛异常（内部已 mkdir）
    db.create_all()
    assert db_file.exists()
    table_names = inspect(db.engine).get_table_names()
    assert len(table_names) > 0
