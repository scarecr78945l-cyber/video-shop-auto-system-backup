"""选品模块 CLI。

用法示例：
  python -m sourcing init-db
  python -m sourcing launch-browsers           # 为各来源启动独立浏览器（登录态隔离）
  python -m sourcing zombie-clean --port 9223  # P-016：清理僵尸标签页（保留采集目标页，不碰登录态）
  python -m sourcing run-pipeline --mode auto  # 真实数据采集（需先启动浏览器并登录）
  python -m sourcing run-pipeline --mode fixtures --top-n 20   # 离线样本
  python -m sourcing collect --source doudian --board 商品榜 --mode auto
  python -m sourcing scheduler --loop --interval 60
  python -m sourcing pool --limit 20
  python -m sourcing score --product-id 3
  python -m sourcing gate-relax                    # S5 闸门放松 dry-run：只报告不放行
  python -m sourcing gate-relax --apply            # 实际放行达标类目 manual_review 商品
  python -m sourcing ad-sync --file ../_management/data-exchange/m5-ad-conversion.json
  python -m sourcing report-daily --days 7 [--json-out report.json]  # S4 日有效候选度量
  python -m sourcing config-show
"""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

import click

from .config import load_config


@click.group()
@click.option("--db-url", envvar="SOURCING_DB_URL", default=None, help="SQLAlchemy DSN，覆盖配置")
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
    """建表（SQLite 默认，生产走 SOURCING_DB_URL）。"""
    from .db import Database

    db = Database(config)
    db.create_all()
    click.echo(f"数据库就绪: {config.db_url}")


def _find_chrome() -> str:
    import shutil

    candidates = [
        "C:/Program Files/Google/Chrome/Application/chrome.exe",
        "C:/Program Files (x86)/Google/Chrome/Application/chrome.exe",
        "C:/Users/Administrator/AppData/Local/Google/Chrome/Application/chrome.exe",
    ]
    for c in candidates:
        if Path(c).exists():
            return c
    return shutil.which("chrome") or shutil.which("google-chrome") or shutil.which("msedge") or ""


def _port_open(port: int) -> bool:
    import socket

    s = socket.socket()
    s.settimeout(1)
    try:
        s.connect(("127.0.0.1", port))
        return True
    except Exception:
        return False
    finally:
        s.close()


@cli.command()
@click.option("--chrome", default=None, help="Chrome 可执行文件路径，覆盖配置")
@click.pass_obj
def launch_browsers(config, chrome) -> None:
    """为缺失的浏览器启动独立实例；已存在（用户已开）的跳过。

    端口占用检测：有米云(9555)/商机中心(9333)/抖店罗盘(9226) 通常已由用户独立浏览器占用，
    本命令只补启动 1688/淘宝 的共享浏览器（9222）。
    """
    import subprocess

    chrome_path = chrome or config.chrome_path or _find_chrome()
    if not chrome_path or not Path(chrome_path).exists():
        click.echo(f"未找到 Chrome：{chrome_path or '(空)'}")
        click.echo("请用 --chrome 指定，或设置 SOURCING_CHROME_PATH 环境变量")
        sys.exit(1)

    # 按 cdp_port 去重，合并同端口来源
    instances: dict[int, tuple[str, str]] = {}  # port -> (profile, label)
    for name, label in [
        ("opportunities", "视频号商机中心"),
        ("youmi", "有米云"),
        ("doudian", "抖店电商罗盘"),
        ("alibaba", "1688"),
        ("taobao", "淘宝"),
    ]:
        spec = getattr(config, name)
        if not spec.enabled:
            continue
        profile = spec.profile_dir or "shared"
        instances.setdefault(spec.cdp_port, (profile, label))

    data_dir = config.data_dir
    data_dir.mkdir(parents=True, exist_ok=True)
    for port, (profile, label) in instances.items():
        if _port_open(port):
            click.echo(f"浏览器已存在（跳过启动）：{label} → CDP :{port}")
            continue
        udd = (data_dir / "chrome-profiles" / profile).resolve()
        udd.mkdir(parents=True, exist_ok=True)
        cmd = [
            chrome_path,
            f"--remote-debugging-port={port}",
            f"--user-data-dir={udd}",
            "--no-first-run",
            "--no-default-browser-check",
        ]
        subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        click.echo(f"已启动浏览器：{label} → CDP :{port}  profile={udd}")

    click.echo("\n下一步：确认各浏览器已登录对应平台（python -m sourcing probe-browsers），然后运行：")
    click.echo("  python -m sourcing run-pipeline --mode auto")


@cli.command("zombie-clean")
@click.option("--port", type=int, default=9223, help="CDP 端口（默认 9223 共享浏览器；有米云 9555）")
@click.option("--keep", "keep_frags", multiple=True, help="额外保留的 URL 片段（可多次，追加到该端口默认保留集）")
def zombie_clean(port, keep_frags) -> None:
    """P-016 防复发：清理共享浏览器僵尸标签页（保留采集目标页，不触碰登录态）。

    默认保留（端口相关）：9223 → opprotunity/rank-product；9555 → console.youshu.youcloud.com；
    --keep 追加保留片段；找不到任何可保留目标页时防御性不关闭任何页面（safe_aborted）。
    """
    from .zombie_clean import clean_zombie_targets, default_keep_fragments

    frags: tuple[str, ...] | None = None
    if keep_frags:
        frags = tuple(default_keep_fragments(port)) + tuple(keep_frags)
    stats = clean_zombie_targets(port, keep_url_fragments=frags)
    click.echo(
        f"CDP :{port} targets={stats['targets_seen']} 页面={stats['pages_seen']} "
        f"保留={stats['kept']} 关闭={stats['closed']} "
        f"关闭失败={stats['close_failed']} 跳过={stats['skipped']}"
    )
    for err in stats["errors"][:10]:
        click.echo(f"  ⚠ {err}")
    if not stats["ok"]:
        click.echo(f"✗ 列表拉取失败（{stats['error']}）——浏览器可能未启动")
        sys.exit(1)
    if stats["safe_aborted"]:
        click.echo("⚠ 未找到可保留的采集目标页，防御性未关闭任何页面（safe_aborted）")


@cli.command()
@click.pass_obj
def probe_browsers(config) -> None:
    """探测各来源浏览器端口：是否可连 + 当前页面（确认登录了哪个平台）。

    P-016 防复发：探测前先对每个启用来源端口做僵尸标签页清理（保留采集目标页
    opprotunity/rank-product、有米云 console.youshu.youcloud.com），避免
    playwright connect_over_cdp 被僵尸页挂起；清理幂等容错，失败仅提示不中断。
    """
    from .zombie_clean import clean_zombie_targets

    # --- P-016 前置：僵尸标签页清理（按端口去重，幂等/容错，失败不阻塞探测） ---
    seen_ports: set[int] = set()
    for name, label in [
        ("opportunities", "视频号商机中心"),
        ("youmi", "有米云"),
        ("doudian", "抖店电商罗盘"),
        ("alibaba", "1688"),
        ("taobao", "淘宝"),
    ]:
        spec = getattr(config, name)
        if not spec.enabled or spec.cdp_port in seen_ports:
            continue
        seen_ports.add(spec.cdp_port)
        stats = clean_zombie_targets(spec.cdp_port)
        if not stats["ok"]:
            click.echo(f"[P-016 清理] CDP :{spec.cdp_port} ✗ 跳过（{stats['error']}）")
        elif stats["safe_aborted"]:
            click.echo(f"[P-016 清理] CDP :{spec.cdp_port} ⚠ 未找到采集目标页，防御性不关闭任何页面")
        else:
            click.echo(
                f"[P-016 清理] CDP :{spec.cdp_port} targets={stats['targets_seen']} "
                f"保留={stats['kept']} 关闭={stats['closed']} "
                f"失败={stats['close_failed']} 跳过={stats['skipped']}"
            )

    from playwright.sync_api import sync_playwright

    pw = sync_playwright().start()
    try:
        for name, label in [
            ("opportunities", "视频号商机中心"),
            ("youmi", "有米云"),
            ("doudian", "抖店电商罗盘"),
            ("alibaba", "1688"),
            ("taobao", "淘宝"),
        ]:
            spec = getattr(config, name)
            if not spec.enabled:
                click.echo(f"[{label}] 未启用")
                continue
            port = spec.cdp_port
            try:
                b = pw.chromium.connect_over_cdp(f"http://127.0.0.1:{port}")
                pages: list[str] = []
                for ctx in b.contexts:
                    for pg in ctx.pages[:3]:
                        try:
                            pages.append(pg.url[:90])
                        except Exception:
                            pass
                b.close()
                shown = pages[:3] if pages else ["(无标签页)"]
                click.echo(f"[{label}] CDP :{port} ✓")
                for u in shown:
                    click.echo(f"    {u}")
            except Exception as e:
                err = str(e)
                if "ECONNREFUSED" in err or "closed" in err or "connect" in err:
                    click.echo(f"[{label}] CDP :{port} ✗ 未监听（浏览器未启动）")
                else:
                    click.echo(f"[{label}] CDP :{port} ✗ {err[:70]}")
    finally:
        pw.stop()


@cli.command()
@click.option("--source", required=True, help="来源（opportunities/youmi/doudian/alibaba/taobao）")
@click.option("--url", default=None, help="要打开的 URL，默认取该来源配置的 home_url")
@click.pass_obj
def inspect_page(config, source, url) -> None:
    """连接来源浏览器打开页面，输出类名统计 + 可见文本，用于校准 row/title/price 选择器。"""
    from collections import Counter

    from .collectors.browser import SharedBrowser

    spec = getattr(config, source)
    browser = SharedBrowser(spec.cdp_port, spec.chrome_path)
    page = browser.page()
    try:
        target = url or spec.selectors.get("home_url", "")
        if not target:
            click.echo("未配置 URL，请用 --url 指定")
            return
        click.echo(f"打开: {target}")
        page.goto(target, timeout=45000, wait_until="domcontentloaded")
        page.wait_for_timeout(3000)
        click.echo(f"当前 URL: {page.url}")

        classes = page.eval_on_selector_all(
            "div, li, tr, [class]",
            "els => els.map(e => e.className && typeof e.className === 'string' ? e.className : (e.getAttribute('class') || '')).filter(Boolean)",
        )
        cnt: Counter = Counter()
        for c in classes:
            for token in str(c).split():
                cnt[token] += 1
        click.echo("\n=== 高频类名（前 25，可用于 row/title/price 选择器）===")
        for token, n in cnt.most_common(25):
            click.echo(f"  .{token}  x{n}")

        texts = page.eval_on_selector_all(
            "body *",
            "els => els.filter(e => e.children.length === 0).map(e => (e.textContent || '').trim()).filter(t => t && t.length < 60).slice(0, 40)",
        )
        click.echo("\n=== 页面可见文本（前 40）===")
        for t in texts:
            click.echo(f"  {t}")
    finally:
        page.close()
        browser.close()


@cli.command()
@click.option("--source", "sources", multiple=True, help="来源（可多次），默认三源")
@click.option("--mode", default="fixtures", type=click.Choice(["fixtures", "auto", "live"]))
@click.option("--top-n", type=int, default=None, help="入池数量上限")
@click.option("--no-quotes", is_flag=True, help="跳过 1688 询价")
@click.option("--no-persist", is_flag=True, help="不写库，仅内存运行")
@click.option("--json-out", type=click.Path(dir_okay=False), default=None, help="将完整结果写为 JSON 文件")
@click.pass_obj
def run_pipeline(config, sources, mode, top_n, no_quotes, no_persist, json_out) -> None:
    """执行完整选品流水线：采集→去重→合规→补全→打分→TopN 入池。"""
    from .db import Database
    from .pipeline import SourcingPipeline

    if not sources:
        sources = ["opportunities", "youmi", "doudian"]
    if not no_persist:
        Database(config).create_all()
    pipe = SourcingPipeline(config)
    result = pipe.run(
        sources=list(sources), mode=mode, top_n=top_n,
        do_quotes=not no_quotes, persist=not no_persist,
    )
    if json_out:
        from pathlib import Path

        import json as _json

        Path(json_out).write_text(
            _json.dumps(result.model_dump(mode="json"), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        click.echo(f"JSON 已写入 {json_out}")
    click.echo(
        f"采集 {result.collected} → 去重后 {result.after_dedup} "
        f"→ 候选 {result.candidates}（拒 {result.hard_rejected}/人工 {result.manual_review}）"
        f"→ 询价 {result.quoted} → 入池 {result.pool_entered}"
    )
    for i, cand in enumerate(result.pool[:10], 1):
        click.echo(f"  #{i} [{cand.score.total:5.1f}] {cand.score.summary()}")
        click.echo(f"      {cand.sanitized_title[:44]}（{cand.category}）成本={cand.real_cost} 建议售价={cand.suggested_price}")


@cli.command()
@click.option("--once", is_flag=True, help="只跑一轮")
@click.option("--loop", is_flag=True, help="常驻循环")
@click.option("--interval", type=float, default=60.0, help="循环轮询间隔（秒）")
@click.option("--mode", default="fixtures", type=click.Choice(["fixtures", "auto", "live"]))
@click.pass_obj
def scheduler(config, once, loop, interval, mode) -> None:
    """调度器：账本/节流/熔断/降频，一轮或常驻（独立进程运行）。"""
    from .db import Database
    from .scheduler import SourcingScheduler

    Database(config).create_all()
    sch = SourcingScheduler(config, mode=mode)
    if once:
        stats = sch.run_once()
        click.echo(json.dumps(stats, ensure_ascii=False, indent=2))
    else:
        sch.loop(interval_seconds=interval)


@cli.command()
@click.option("--source", required=True)
@click.option("--board", default=None)
@click.option("--mode", default="fixtures", type=click.Choice(["fixtures", "auto", "live"]))
@click.pass_obj
def collect(config, source, board, mode) -> None:
    """单榜试采集并打印条目。"""
    from .collectors import make_collector, resolve_mode

    collector = make_collector(source, config, resolve_mode(source, config, mode))
    boards = [board] if board else collector.boards
    for b in boards:
        items = collector.collect_board(b, limit=20)
        click.echo(f"== {source}/{b}: {len(items)} 条 ==")
        for it in items[:10]:
            click.echo(f"  [{it.rank}] {it.title[:40]} ¥{it.price} 销量{it.sales} 类目={it.category}")


@cli.command()
@click.option("--limit", type=int, default=20)
@click.pass_obj
def pool(config, limit) -> None:
    """查看商品池（按得分排序）。"""
    from .db import Database
    from .repo import pool_summary

    db = Database(config)
    with db.session() as session:
        click.echo(pool_summary(session, limit=limit))


@cli.command()
@click.option("--product-id", type=int, required=True)
@click.pass_obj
def score(config, product_id) -> None:
    """查看单个商品的完整打分理由。"""
    from .db import Database
    from .repo import dump_product

    db = Database(config)
    with db.session() as session:
        data = dump_product(session, product_id)
    click.echo(json.dumps(data, ensure_ascii=False, indent=2))


@cli.command()
@click.option("--product-id", type=int, required=True)
@click.pass_obj
def gate_confirm(config, product_id) -> None:
    """人工复核闸门：确认 manual_review 商品入池。"""
    from .db import Database
    from .repo import list_pool
    from sqlalchemy import select

    from . import tables as T

    db = Database(config)
    with db.session() as session:
        row = session.get(T.Product, product_id)
        if row is None:
            click.echo(f"商品 {product_id} 不存在")
            sys.exit(1)
        if row.state == "pool":
            click.echo(f"商品 {product_id} 已在池中")
            return
        row.state = "pool"
        click.echo(f"商品 {product_id}（{row.sanitized_title[:40]}）已确认入池")


@cli.command()
@click.option("--apply", is_flag=True, help="实际放行达标类目 manual_review 商品（缺省 = --dry-run 只报告）")
@click.option("--dry-run", "force_dry", is_flag=True, help="显式 dry-run：只报告不放行（默认）")
@click.option("--category", "categories", multiple=True, help="类目子集过滤（可多次）；缺省用 gate.relax.categories")
@click.option("--limit", type=int, default=None, help="最多处理 N 条 manual_review 商品（按 id 升序）")
@click.pass_obj
def gate_relax(config, apply, force_dry, categories, limit) -> None:
    """人工闸门按达标自动放松（S5）：对存量 manual_review 商品判定并（可选）放行。

    策略读 app_config `gate.relax.*`（enabled 默认 false=不放松）；达标=窗口内
    该类目通过率 ≥ pass_rate 且样本 ≥ min_samples（10 文档第五节口径：95%×50 品）。
    默认 dry-run 只报告不放行；--apply 才实际放行（达标类目 state → pool）。
    """
    from .db import Database
    from .gate import relax_manual_review

    dry_run = (not apply) or force_dry
    db = Database(config)
    db.create_all()  # 保险：表不存在时建表（读 app_config 需要），幂等
    report = relax_manual_review(db, dry_run=dry_run, categories=categories, limit=limit)
    cfg = report.config
    click.echo(
        f"[{'DRY-RUN 只报告' if report.dry_run else '已放行'}] gate.relax: {cfg.describe()}"
    )
    click.echo(
        f"存量 manual_review {len(report.actions)} 条 → "
        f"达标可放行 {report.relaxed_count} / 保持人工复核 {report.kept_count}"
    )
    for a in report.actions:
        mark = "→pool" if a.relaxed else "保持  "
        reason = a.reasons[0] if a.reasons else ""
        click.echo(f"  #{a.product_id} [{mark}] {a.category or '(空类目)'}: {reason}")


@cli.command()
@click.pass_obj
def config_show(config) -> None:
    """打印生效配置（类目白名单/打分权重/调度参数）。"""
    click.echo(f"DB: {config.db_url}")
    click.echo(f"类目白名单: {config.category_whitelist}")
    click.echo(f"打分维度满分: {config.scoring.dimension_max}")
    click.echo(f"投放转化权重: {config.scoring.ad_conversion_weight}")
    click.echo(f"TopN: {config.scoring.top_n}")
    click.echo(f"调度: {config.scheduler.model_dump()}")
    click.echo(f"来源与浏览器端口:")
    for name, label in [
        ("opportunities", "视频号商机中心"),
        ("youmi", "有米云(独立浏览器)"),
        ("doudian", "抖店电商罗盘(独立)"),
        ("alibaba", "1688(询价)"),
        ("taobao", "淘宝(素材)"),
    ]:
        spec = getattr(config, name)
        click.echo(f"  {label:<12} enabled={spec.enabled} cdp_port={spec.cdp_port} profile={spec.profile_dir or '(共享)'}")


@cli.command()
@click.option(
    "--file",
    "file_path",
    type=click.Path(dir_okay=False),
    default=None,
    help="M5 投放转化交换文件路径；缺省读 config.ad_exchange_file（契约 C-2）",
)
@click.pass_obj
def ad_sync(config, file_path) -> None:
    """导入 M5 投放转化回写（幂等写 m1_ad_conversion_cache / m1_ad_conversion_ingests）。"""
    from .ad_backfill import AdBackfillError, apply_exchange, load_exchange
    from .db import Database

    if not file_path:
        file_path = config.ad_exchange_file
    if not file_path:
        click.echo(
            "未指定交换文件：请用 --file 指定，或在配置中设置 ad_exchange_file"
            "（契约 C-2：_management/data-exchange/m5-ad-conversion.json）"
        )
        sys.exit(1)
    db = Database(config)
    db.create_all()
    try:
        exchange = load_exchange(file_path)
    except AdBackfillError as e:
        click.echo(f"交换文件校验失败：{e}")
        sys.exit(1)
    if exchange is None:
        click.echo(f"交换文件不可用（不存在或解析失败）：{file_path}")
        sys.exit(1)
    stats = apply_exchange(db, exchange, file_path)
    click.echo(
        f"ad-sync 完成：类目 {stats['categories']} 个"
        f" / 新增 {stats['inserted']} / 更新 {stats['upserted']}"
        f" / 跳过 {stats['skipped']} / 载入 {stats['rows_loaded']}"
    )


@cli.command("report-daily")
@click.option("--days", type=int, default=7, help="统计最近 N 天（UTC 日粒度），默认 7")
@click.option("--json-out", type=click.Path(dir_okay=False), default=None, help="将结果写为 JSON 文件")
@click.pass_obj
def report_daily(config, days, json_out) -> None:
    """S4 日有效候选度量：每日 采集事件/运行/有效候选，≥200 达标判定（只读查询）。

    口径（context README「S4 日有效候选度量」小节）：
    有效候选 = products.state ∈ (pool, manual_review) 按 created_at UTC 日分组；
    target_met = effective_candidates ≥ 200；gap = max(0, 200 - 数)；空数据 daily=[]。
    """
    from .db import Database
    from .report import SourcingReport

    db = Database(config)
    data = SourcingReport(db).daily_effective_candidates(days=days)
    if json_out:
        Path(json_out).write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        click.echo(f"JSON 已写入 {json_out}")
    click.echo(json.dumps(data, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    cli()
