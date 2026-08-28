"""M5 自动小店投放（商品托管）模块 CLI（`python -m ads ...`）。

用法示例：
  python -m ads init-db            # 建表（幂等，可重复执行；自动创建 data/db）
"""

from __future__ import annotations

import logging

import click

from .config import load_config


@click.group()
@click.option("--db-url", envvar="ADS_DB_URL", default=None, help="SQLAlchemy DSN，覆盖配置")
@click.option("--verbose", is_flag=True, help="DEBUG 日志")
@click.pass_context
def cli(ctx: click.Context, db_url: str | None, verbose: bool) -> None:
    overrides = {"db_url": db_url} if db_url else {}
    ctx.obj = load_config(**overrides)
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


@cli.command()
@click.pass_obj
def init_db(config) -> None:
    """建表（幂等，可重复执行；自动创建 data/db 父目录）。"""
    from .db import Database

    db = Database(config)
    db.create_all()
    click.echo(f"M5 投放库就绪: {config.db_url}")


if __name__ == "__main__":
    cli()
