"""M2 素材库基座 CLI（`python -m materials ...`）。

用法示例：
  python -m materials init-db            # 建表（幂等，可重复执行；自动创建 data/db）
  python -m materials pool --limit 20    # 列素材（人工验收用；空库输出空列表不报错）
  python -m materials download --once    # 下载中台单轮（子代理 F）
  python -m materials download --serve --port 8787   # 启动多实例下载中台 HTTP API
"""

from __future__ import annotations

import logging

import click

from .config import load_config


@click.group()
@click.option("--db-url", envvar="MATERIALS_DB_URL", default=None, help="SQLAlchemy DSN，覆盖配置")
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
    """建表（幂等，可重复执行）。"""
    from .db import Database

    db = Database(config)
    db.create_all()
    click.echo(f"素材库就绪: {config.db_url}")


@cli.command()
@click.option("--limit", type=int, default=20)
@click.pass_obj
def pool(config, limit) -> None:
    """列素材（按 id 倒序；空库输出空列表不报错）。"""
    from .db import Database
    from .repo import AssetRepo

    db = Database(config)
    repo = AssetRepo(db)
    assets = repo.list_assets(limit=limit)
    if not assets:
        click.echo("（素材库为空）")
        return
    click.echo(f"{'id':>4} {'类型':<6} {'平台':<10} {'上传':<9} {'合规':<8} {'md5':<10} 来源")
    for a in assets:
        click.echo(
            f"{a['id']:>4} {a['asset_type']:<6} {a['source_platform']:<10} "
            f"{a['upload_status']:<9} {a['compliance_status']:<8} "
            f"{a['md5'][:10]} {a['source_url'][:40]}"
        )


@cli.command()
@click.option("--once", is_flag=True, help="只跑一轮（领至多 --max-jobs 个任务）")
@click.option("--loop", is_flag=True, help="常驻循环（--interval 控制轮询间隔）")
@click.option("--serve", is_flag=True, help="启动多实例 HTTP API（--host/--port）")
@click.option("--host", default="127.0.0.1", show_default=True, help="API 绑定地址")
@click.option("--port", type=int, default=8788, show_default=True, help="API 端口（默认 8788：8787 已被工作区 captcha-vision-gateway 占用，见 pitfall-log P-008）")
@click.option("--interval", type=float, default=1.0, show_default=True, help="循环轮询间隔（秒）")
@click.option("--max-jobs", type=int, default=None, help="单轮最多处理任务数（默认取配置 concurrency）")
@click.option(
    "--repo", "repo_mode", type=click.Choice(["auto", "memory"]), default="auto", show_default=True,
    help="auto=SqlAlchemyDownloadJobRepo（需子代理 D 的 repo/表就绪）；memory=内存 fake（演示/自测）",
)
@click.option("--worker-id", default=None, help="实例标识（默认 WORKER_ID env 或 hostname-随机后缀）")
@click.pass_obj
def download(config, once, loop, serve, host, port, interval, max_jobs, repo_mode, worker_id) -> None:
    """素材下载中台：领任务→断点续传下载→存存储→退避/熔断记账；或启动多实例 HTTP API。

    R-M2-06/R-M2-21：失败按错误码退避（RATE_LIMIT 180s/TIMEOUT 60s/NO_MATCH 120s，节流 0~4 级）；
    同平台连续失败 ≥2 熔断暂停（asset_sources.risk_control=1，冷却后探针恢复）。
    """
    import json as _json
    import time as _time

    from .downloader import DownloaderService, InMemoryDownloadJobRepo, SqlAlchemyDownloadJobRepo
    from .downloader_api import serve_forever

    if repo_mode == "memory":
        repo = InMemoryDownloadJobRepo()
    else:
        repo = SqlAlchemyDownloadJobRepo(db_url=config.db_url)
    service = DownloaderService(repo, config=config)
    if worker_id:
        service.worker.worker_id = worker_id
    if serve:
        service.start_worker_loop(interval_seconds=interval)
        serve_forever(service, host=host, port=port)
        return
    if once:
        click.echo(_json.dumps(service.run_once(max_jobs=max_jobs), ensure_ascii=False, indent=2))
        return
    # --loop（默认）
    click.echo(f"worker_id={service.worker.worker_id}，开始循环（Ctrl+C 停止）")
    try:
        while True:
            stats = service.run_once(max_jobs=max_jobs)
            click.echo(_json.dumps(stats, ensure_ascii=False))
            _time.sleep(interval)
    except KeyboardInterrupt:
        click.echo("已停止")


@cli.command()
@click.option("--input", "input_path", required=True, type=click.Path(), help="输入素材路径")
@click.option(
    "--output", "output_path", default=None, type=click.Path(),
    help="输出路径（默认：输入同目录 `原名.normalized.mp4`）",
)
@click.pass_obj
def normalize(config, input_path, output_path) -> None:
    """素材标准化：probe 预检 → ffmpeg 转码 → 转码后复检硬规格（双校验 R-M2-12）。

    ffmpeg/ffprobe 缺失时打印清晰错误（含安装指引）并以非 0 退出（R-M2-15 不静默）；
    复检未通过同样非 0 退出并逐项说明失败原因（P-007 防复发）。
    """
    import json as _json

    from .normalizer import FFmpegProcessRunner, Normalizer, NormalizerError

    ncfg = config.normalize
    runner = FFmpegProcessRunner(
        ffmpeg_path=ncfg.ffmpeg_path,
        ffprobe_path=ncfg.ffprobe_path,
        timeout_seconds=ncfg.transcode_timeout_seconds,
    )
    # 先探测 ffmpeg/ffprobe（R-M2-15）：缺失立即给清晰错误，不等到转码阶段
    try:
        runner._resolve_ffmpeg()
        runner._resolve_ffprobe()
    except NormalizerError as exc:
        click.echo(f"错误：{exc}", err=True)
        raise SystemExit(1)

    if not Path(input_path).exists():
        click.echo(f"错误：输入文件不存在: {input_path}", err=True)
        raise SystemExit(2)

    normalizer = Normalizer(runner, config=config)
    try:
        result = normalizer.normalize(input_path, output_path=output_path)
    except NormalizerError as exc:
        click.echo(f"标准化失败：{exc}", err=True)
        raise SystemExit(1)

    click.echo(_json.dumps(result, ensure_ascii=False, indent=2, default=str))
    if not result["passed"]:
        click.echo("复检未通过（硬规格不达标，见上方 failures）", err=True)
        raise SystemExit(1)


@cli.command()
@click.option("--file", "file_path", type=click.Path(exists=True), required=True, help="素材文件路径")
@click.option(
    "--type", "asset_type", type=click.Choice(["image", "video"]), default="image",
    show_default=True, help="素材类型（video 需本机 ffmpeg，缺失报清晰错误）",
)
@click.pass_obj
def dedup_check(config, file_path, asset_type) -> None:
    """双去重人工验收：对单个素材文件跑 MD5 + phash 检查（只查不注册）。"""
    import json as _json

    from .db import Database
    from .dedup import DedupService, FrameExtractionError, FFmpegNotFoundError

    db = Database(config)
    svc = DedupService(db)
    try:
        result = (
            svc.check_image(file_path) if asset_type == "image" else svc.check_video(file_path)
        )
    except (FFmpegNotFoundError, FrameExtractionError) as exc:
        click.echo(f"去重检查失败：{exc}", err=True)
        raise SystemExit(1)
    click.echo(_json.dumps(result, ensure_ascii=False, indent=2))


@cli.command()
@click.option("--keyword", default=None, help="搜索关键词（与 --author-url 二选一）")
@click.option("--author-url", "author_url", default=None, help="达人主页 URL 或达人 ID（与 --keyword 二选一）")
@click.option("--count", type=int, default=10, show_default=True, help="下载数量上限")
@click.option("--output-dir", "output_dir", default=None, type=click.Path(), help="输出目录（默认 config.tiktok.default_output_dir）")
@click.option("--json", "as_json", is_flag=True, help="以 JSON 输出结果列表")
@click.pass_obj
def tiktok_download(config, keyword, author_url, count, output_dir, as_json) -> None:
    """TikTokDownloader 采集（抖音/快手/小红书；视频号不在本封装范围，R-M2-05）。

    外部 CLI 子进程 + 超时 + 输出解析 + 错误分类（对齐 downloader.py 码表）；
    binary 缺失时打印清晰错误（含安装指引）并以非 0 退出（不静默）；
    版本锁定与安装说明见 collectors/README.md；开发/CI 可用 fake CLI fixtures（R-M2-17）。
    """
    import json as _json

    from .collectors.tiktok_wrapper import TikTokDownloaderCLI, TikTokDownloaderError

    if not keyword and not author_url:
        click.echo("错误：--keyword 与 --author-url 必须二选一", err=True)
        raise SystemExit(2)
    if keyword and author_url:
        click.echo("错误：--keyword 与 --author-url 只能二选一", err=True)
        raise SystemExit(2)

    cli = TikTokDownloaderCLI(output_dir=output_dir, config=config)
    avail = cli.check_available()
    if not avail["available"]:
        click.echo(f"错误：{avail['error']}", err=True)
        raise SystemExit(1)
    try:
        if keyword:
            results = cli.search_download(keyword, count=count)
        else:
            results = cli.author_download(author_url, count=count)
    except TikTokDownloaderError as exc:
        click.echo(f"采集失败 [{exc.error_code}]：{exc.message}", err=True)
        raise SystemExit(1)

    if as_json:
        click.echo(_json.dumps(results, ensure_ascii=False, indent=2, default=str))
    else:
        for r in results:
            click.echo(
                f"{r['platform'] or '未知'}\t{r['title'][:24] or '（无标题）'}\t"
                f"{r['file_path'] or '（未落盘）'}"
            )
        click.echo(f"共 {len(results)} 个作品")


if __name__ == "__main__":
    cli()
