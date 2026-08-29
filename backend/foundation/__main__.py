"""M0 基座 CLI：init-db（幂等建表+种子）与 scheduler（调度器进程）。

用法：
  python -m foundation init-db                     # 建五表 + 错误码种子（幂等）
  python -m foundation scheduler --once            # 单轮调度
  python -m foundation scheduler --loop --interval 30   # 常驻调度（独立进程）
"""

from __future__ import annotations

import argparse
import logging
import sys

from .config import load_config
from .db import default_database
from .repo import WorkflowQueue
from .scheduler import LoggingWorker, WorkflowScheduler


def _setup_logging(level: str) -> None:
    logging.basicConfig(level=getattr(logging, level.upper(), logging.INFO), format="%(asctime)s %(levelname)s %(name)s %(message)s")


def cmd_init_db(args: argparse.Namespace) -> int:
    overrides = {"db_url": args.db_url} if args.db_url else {}
    cfg = load_config(**overrides)
    database = default_database(cfg)
    database.create_all()
    added = database.seed()
    print(f"建表完成（五表）：{cfg.db_url}")
    print(f"错误码种子：新增 {added} 条（幂等）")
    return 0


def cmd_scheduler(args: argparse.Namespace) -> int:
    overrides = {"db_url": args.db_url} if args.db_url else {}
    cfg = load_config(**overrides)
    database = default_database(cfg)
    database.create_all()
    database.seed()
    queue = WorkflowQueue(database)
    worker = LoggingWorker()  # 演示/占位；业务 worker 由各模块集成时注入
    scheduler = WorkflowScheduler(queue, worker, config=cfg.scheduler)
    if args.once:
        stats = scheduler.run_once()
        print(f"单轮调度完成：{stats}")
        return 0
    scheduler.run_forever(interval=args.interval)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="foundation", description="M0 基座与数据治理 CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    p_init = sub.add_parser("init-db", help="幂等建五表 + 错误码种子")
    p_init.add_argument("--db-url", default=None, help="覆盖数据库 DSN（默认读 M0_DB_URL）")
    p_init.set_defaults(func=cmd_init_db)

    p_sched = sub.add_parser("scheduler", help="队列调度器（独立进程）")
    p_sched.add_argument("--db-url", default=None, help="覆盖数据库 DSN（默认读 M0_DB_URL）")
    p_sched.add_argument("--once", action="store_true", help="只跑一轮")
    p_sched.add_argument("--interval", type=float, default=None, help="轮询间隔秒（--loop 用）")
    p_sched.set_defaults(func=cmd_scheduler)

    parser.add_argument("--log-level", default="INFO", help="日志级别")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    _setup_logging(args.log_level)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
