"""M0 基座 CLI：init-db（幂等建表+种子）、scheduler（调度器进程）与 manifest（SHA-256 清单）。

用法：
  python -m foundation init-db                     # 建五表 + 错误码种子（幂等）
  python -m foundation scheduler --once            # 单轮调度
  python -m foundation scheduler --loop --interval 30   # 常驻调度（独立进程）
  python -m foundation manifest build -o MANIFEST.json --base-dir . file1 file2   # 生成 SHA-256 清单（P2-4）
  python -m foundation manifest verify -m MANIFEST.json --base-dir .              # 校验清单（退出码 0=全通过）
"""

from __future__ import annotations

import argparse
import logging
import sys

from .config import load_config
from .db import default_database
from .manifest import build_manifest, save_manifest, verify_manifest
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


def cmd_manifest_build(args: argparse.Namespace) -> int:
    """生成 MANIFEST.json（P2-4：关键交付物 SHA-256 清单，对齐旧系统机制）。"""
    meta: dict[str, str] = {}
    for kv in args.meta or []:
        key, _, value = kv.partition("=")
        if not key.strip():
            print(f"忽略无效 --meta：{kv}")
            continue
        meta[key.strip()] = value.strip()
    manifest = build_manifest(
        args.files, base_dir=args.base_dir, title=args.title, meta=meta
    )
    save_manifest(manifest, args.output)
    print(
        f"MANIFEST 已生成：{args.output}（{len(manifest['files'])} 个文件，"
        f"SHA-256，格式 {manifest['format']}）"
    )
    return 0


def cmd_manifest_verify(args: argparse.Namespace) -> int:
    """校验 MANIFEST.json：存在性 + SHA-256（退出码 0=全通过，1=有缺失/不一致）。"""
    result = verify_manifest(args.manifest, base_dir=args.base_dir)
    print(
        f"校验完成：total={result.total} matched={result.matched} "
        f"missing={result.missing} mismatched={result.mismatched}"
    )
    for err in result.errors:
        print(f"  - {err}")
    return 0 if result.ok else 1


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

    p_manifest = sub.add_parser("manifest", help="备份协议：SHA-256 清单（P2-4）")
    msub = p_manifest.add_subparsers(dest="manifest_command", required=True)

    p_build = msub.add_parser("build", help="生成 MANIFEST.json")
    p_build.add_argument("files", nargs="+", help="待校验文件（相对 --base-dir 解析）")
    p_build.add_argument("-o", "--output", required=True, help="输出清单路径")
    p_build.add_argument("--base-dir", default=".", help="相对路径基准（默认当前目录）")
    p_build.add_argument("--title", default="", help="清单标题（业务说明）")
    p_build.add_argument(
        "--meta", action="append", default=None,
        help="业务说明 key=value（可重复，对齐旧系统 policy/gate 扩展点）",
    )
    p_build.set_defaults(func=cmd_manifest_build)

    p_verify = msub.add_parser("verify", help="校验 MANIFEST.json")
    p_verify.add_argument("-m", "--manifest", required=True, help="清单路径")
    p_verify.add_argument("--base-dir", default=".", help="文件基准目录（默认当前目录）")
    p_verify.set_defaults(func=cmd_manifest_verify)

    parser.add_argument("--log-level", default="INFO", help="日志级别")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    _setup_logging(args.log_level)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
