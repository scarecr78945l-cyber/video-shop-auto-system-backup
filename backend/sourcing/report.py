"""REC-融合 P1-6：选品周报聚合（旧系统 sourcing_report.py 迁移）。

聚合 source_runs / source_collection_events / products：
- 来源分布：每来源运行次数 / 成功 / 失败 / 成功率 / 采集条目；
- 错误分布：按错误文本关键词归类（AUTH_REQUIRED/RATE_LIMIT/风控等）；
- 漏斗：采集 → 去重 → 合规候选 → 入池（对齐 11 文档四节周报口径）；
- 输出对齐 REC-005/DA-001（金额分 int，时间 UTC）。

用法：SourcingReport(db).weekly() → dict（供 _management/dashboard.md 或 CLI 消费）。
"""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select

from .db import Database
from .tables import Product, SourceCollectionEvent, SourceRun

# 错误分类关键词 → 类别（复用 09 码表语义；风控/登录/限流为运营关注点）
_ERROR_CLASSES: list[tuple[str, list[str]]] = [
    ("AUTH_REQUIRED", ["登录", "auth", "AUTH_REQUIRED", "登录态"]),
    ("VERIFICATION_REQUIRED", ["验证码", "verification", "VERIFICATION_REQUIRED"]),
    ("RATE_LIMIT", ["限流", "频繁", "rate", "RATE_LIMIT"]),
    ("风控", ["风控", "risk", "risk_control", "封禁"]),
    ("TIMEOUT", ["超时", "timeout", "TIMEOUT"]),
    ("NO_MATCH", ["无同款", "no_match", "NO_MATCH", "未匹配"]),
    ("PLATFORM_REJECT", ["驳回", "platform_reject", "PLATFORM_REJECT"]),
    ("PAGE_CHANGED", ["改版", "page_changed", "PAGE_CHANGED"]),
]


def classify_error(error_text: str) -> str:
    """错误文本 → 类别（未知 → UNEXPECTED）。"""
    low = (error_text or "").lower()
    for label, keywords in _ERROR_CLASSES:
        if any(k.lower() in low for k in keywords):
            return label
    return "UNEXPECTED"


class SourcingReport:
    """选品周报聚合器（只读查询）。"""

    def __init__(self, db: Database) -> None:
        self.db = db

    def weekly(self, days: int = 7) -> dict:
        """最近 N 天周报：来源分布 / 错误分布 / 漏斗。"""
        since = datetime.now(timezone.utc) - timedelta(days=days)
        with self.db.session() as session:
            runs = list(
                session.scalars(
                    select(SourceRun).where(SourceRun.started_at >= since)
                ).all()
            )
            # 来源分布
            per_source: dict[str, dict] = {}
            for r in runs:
                s = per_source.setdefault(
                    r.source, {"runs": 0, "ok": 0, "failed": 0, "items": 0}
                )
                s["runs"] += 1
                s["items"] += r.item_count
                if r.ok:
                    s["ok"] += 1
                else:
                    s["failed"] += 1
            for s in per_source.values():
                s["success_rate"] = (
                    round(s["ok"] / s["runs"], 2) if s["runs"] else 0.0
                )

            # 错误分布（按类别）
            error_counts: Counter = Counter()
            for r in runs:
                if not r.ok and r.error:
                    error_counts[classify_error(r.error)] += 1

            # 漏斗：采集事件 → 商品候选 → 入池
            collected = (
                session.execute(
                    select(func.count()).select_from(SourceCollectionEvent).where(
                        SourceCollectionEvent.created_at >= since
                    )
                ).scalar_one()
            )
            products = list(
                session.scalars(
                    select(Product).where(Product.created_at >= since)
                ).all()
            ) if hasattr(Product, "created_at") else []
            candidates = sum(1 for p in products if getattr(p, "state", "") in ("pool", "manual_review"))
            pooled = sum(1 for p in products if getattr(p, "state", "") == "pool")

            return {
                "period_days": days,
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "sources": per_source,
                "error_distribution": dict(error_counts.most_common()),
                "funnel": {
                    "collected_events": collected,
                    "products": len(products),
                    "candidates": candidates,
                    "pooled": pooled,
                },
            }
