"""M4 自动上架 CLI。

用法：
    python -m listing init-db
        # 幂等建 7 张 listing_* 表并打印建表清单（LISTING_DB_URL 可覆盖库路径）
"""

from __future__ import annotations

import argparse
import sys
from typing import Optional, Sequence


def cmd_init_db(args: argparse.Namespace) -> int:
    from .config import load_config
    from .db import default_database

    config = load_config()
    database = default_database(config)
    database.create_all()
    tables = database.table_names()
    print(f"[init-db] db_url={config.db_url}")
    print(f"[init-db] 建表完成（幂等），共 {len(tables)} 张表：")
    for name in tables:
        print(f"  - {name}")
    database.dispose()
    return 0


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m listing", description="M4 自动上架模块 CLI"
    )
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("init-db", help="幂等建 7 张 listing_* 表并打印建表清单").set_defaults(
        handler=cmd_init_db
    )
    args = parser.parse_args(argv)
    return args.handler(args)


if __name__ == "__main__":
    sys.exit(main())
