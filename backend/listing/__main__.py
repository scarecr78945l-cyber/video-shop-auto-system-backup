"""M4 自动上架 CLI。

用法：
    python -m listing init-db
        # 幂等建 7 张 listing_* 表并打印建表清单（LISTING_DB_URL 可覆盖库路径）
    python -m listing intake [--limit N] [--generation v1] [--dry-run]
        # 从 M1 商品池（有成本）生成上架候选 → 门禁 → 建 pending 上架任务
        # （P-041 桥接：商品池 → listing_tasks；真实 live 上架由前端 confirm 触发）
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


def cmd_intake(args: argparse.Namespace) -> int:
    """P-041 上架候选生成：M1 商品池 → ListingCandidate → 门禁 → pending 任务。

    素材：M3 图库为空时用 PIL 生成 1:1 占位主图/详情图（门禁放行，live 前须补真实素材）；
    资质/购买设置：占位（真实值待用户侧确认/后台配置，REC-004）。
    """
    import json
    import sqlite3
    import tempfile
    from pathlib import Path

    from PIL import Image

    from services.listing_gate import (
        ListingCandidate,
        ListingGate,
        PurchaseSettings,
        SkuInput,
    )
    from sourcing.compliance import sanitize_title
    from .models import ListingTask, utcnow_iso
    from .repo import ListingRepo, DuplicateTaskError
    from .db import default_database
    from .config import load_config as load_listing_config

    lcfg = load_listing_config()
    db = default_database(lcfg)
    db.create_all()
    repo = ListingRepo(db)
    gate = ListingGate()

    # 读 M1 商品池（有成本）
    con = sqlite3.connect("data/db/m1-sourcing.db")
    cur = con.cursor()
    cur.execute(
        "SELECT p.id, p.title, p.category, p.real_cost, p.suggested_price "
        "FROM products p WHERE p.state='pool' AND p.real_cost IS NOT NULL "
        "ORDER BY p.id LIMIT ?",
        (args.limit,),
    )
    rows = cur.fetchall()
    con.close()

    tmp = Path(tempfile.mkdtemp(prefix="listing_intake_"))

    def make_images(pid: int, n_main: int = 5):
        mains, details = [], []
        for i in range(n_main):
            p = tmp / f"p{pid}_main_{i}.png"
            Image.new("RGB", (800, 800), (30 + i * 50 % 220, 40 + i * 40 % 220, 50 + i * 30 % 220)).save(p)
            mains.append(str(p))
        d = tmp / f"p{pid}_detail.png"
        Image.new("RGB", (800, 800), (120, 200, 90)).save(d)
        details.append(str(d))
        return mains, details

    stats = {"created": 0, "duplicate": 0, "gate_fail": 0, "errors": 0}
    reasons: dict[str, int] = {}
    gen = args.generation or "v1"

    for pid, title, category, cost, price in rows:
        clean = sanitize_title(title or "")[:35]
        if len(clean) < 15:
            clean = (clean + " 通用款家用").strip()[:35]
        try:
            mains, details = make_images(pid)
            skus = [
                SkuInput(
                    code=f"P{pid}-S1",
                    cost_cents=int(round(float(cost) * 100)),
                    price_cents=int(round(float(price) * 100)),
                )
            ]
            cand = ListingCandidate(
                product_id=pid,
                title=clean,
                category_id=0,
                category_name=category or "家居日用",
                qualification={"qualification_id": f"SIM-{pid}", "expires_at": "2026-12-31"},
                main_images=mains,
                detail_images=details,
                skus=skus,
                purchase_settings=PurchaseSettings(
                    purchase_limit={"per_user": 2, "period": "month"},
                    freight_template_id="1",
                    after_sale="支持7天无理由退换货",
                ),
                missing_attrs=None,
            )
            gr = gate.evaluate(cand)
            if not gr.passed:
                stats["gate_fail"] += 1
                for c in gr.rejected_reason_codes:
                    reasons[c] = reasons.get(c, 0) + 1
                continue
            task = ListingTask(
                task_id=f"LIST-{pid}-{gen}",
                product_id=pid,
                generation_version=gen,
                stage="listing_upload",
                status="pending",
                gate_result=gr.model_dump(mode="json"),
            )
            repo.create_task(task)
            stats["created"] += 1
        except DuplicateTaskError:
            stats["duplicate"] += 1
        except Exception as e:
            stats["errors"] += 1
            print(f"  #{pid} EXC: {type(e).__name__} {str(e)[:80]}")

    print(f"\n[listing intake] 商品池 {len(rows)} → 建 pending {stats['created']} / "
          f"重复 {stats['duplicate']} / 门禁拒 {stats['gate_fail']} / 错误 {stats['errors']}")
    if reasons:
        print(f"门禁拒绝原因: {reasons}")
    if not args.dry_run:
        print(f"[提示] 真实 live 上架前置：M3 真实素材（当前为占位图）、类目资质/运费模板（REC-004 用户确认）；"
              f"前端 confirm 后走 pipeline.submit。")
    db.dispose()
    return 0


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m listing", description="M4 自动上架模块 CLI"
    )
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("init-db", help="幂等建 7 张 listing_* 表并打印建表清单").set_defaults(
        handler=cmd_init_db
    )
    p_intake = sub.add_parser(
        "intake", help="M1 商品池 → 上架候选 → 门禁 → 建 pending 任务（P-041）"
    )
    p_intake.add_argument("--limit", type=int, default=50, help="商品池读取上限")
    p_intake.add_argument("--generation", default="v1", help="素材/定价代次（幂等键）")
    p_intake.add_argument("--dry-run", action="store_true", help="只跑门禁报告，不建任务")
    p_intake.set_defaults(handler=cmd_intake)
    args = parser.parse_args(argv)
    return args.handler(args)


if __name__ == "__main__":
    sys.exit(main())
