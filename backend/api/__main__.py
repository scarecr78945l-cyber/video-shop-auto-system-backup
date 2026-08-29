"""允许 `python -m api` 启动 API 服务（backend/ 目录）。

用法：`python -X utf8 -m api [--host HOST] [--port PORT]`
环境变量：M6_API_HOST / M6_API_PORT（默认 127.0.0.1:8000）。
"""

from __future__ import annotations

import argparse
import logging
import sys


def main(argv: list[str] | None = None) -> int:
    from .config import load_config
    from .app import create_app

    cfg = load_config()
    parser = argparse.ArgumentParser(prog="python -m api", description="M6 控制台 API 服务")
    parser.add_argument("--host", default=None, help=f"监听地址（默认 M6_API_HOST 或 {cfg.api_host}）")
    parser.add_argument("--port", type=int, default=None, help=f"监听端口（默认 M6_API_PORT 或 {cfg.api_port}）")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=getattr(logging, cfg.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    import uvicorn

    app = create_app()
    uvicorn.run(
        app,
        host=args.host or cfg.api_host,
        port=args.port or cfg.api_port,
        log_level=cfg.log_level.lower(),
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
