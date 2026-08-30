"""REC-融合 P1-6：选品周报聚合（旧系统 sourcing_report.py 迁移）。

聚合 source_runs / source_collection_events / products：
- 来源分布：每来源运行次数 / 成功 / 失败 / 成功率 / 采集条目；
- 错误分布：按错误文本关键词归类（AUTH_REQUIRED/RATE_LIMIT/风控等）；
- 漏斗：采集 → 去重 → 合规候选 → 入池（对齐 11 文档四节周报口径）；
- S4 日有效候选度量：按 UTC 日聚合 采集事件/运行/有效候选，≥200 达标；
- 输出对齐 REC-005/DA-001（金额分 int，时间 UTC）。

用法：SourcingReport(db).weekly() / SourcingReport(db).daily_effective_candidates(days=N)
→ dict（供 _management/dashboard.md 或 CLI 消费）。
"""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select

from .db import Database
from .models import ensure_aware
from .tables import Product, SourceCollectionEvent, SourceRun

# S4 联调度量：日有效候选目标（04 文档验收标准「日有效候选 ≥200」）
DAILY_EFFECTIVE_TARGET = 200

# 有效候选口径：products.state ∈ (pool, manual_review)（实现内明确，context README 登记）
_EFFECTIVE_STATES = ("pool", "manual_review")


def _utc_date(dt) -> str:
    """任意 datetime → UTC 日 YYYY-MM-DD（SQLite 落库丢失 tzinfo，按 UTC 解释）。"""
    return ensure_aware(dt).astimezone(timezone.utc).strftime("%Y-%m-%d")


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
            candidates = sum(1 for p in products if getattr(p, "state", "") in _EFFECTIVE_STATES)
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

    def daily_effective_candidates(self, days: int = 7) -> dict:
        """S4 日有效候选度量：按 UTC 日聚合 采集事件/运行/有效候选，≥200 达标判定。

        口径（context README 已登记）：
        - 有效候选 = products.state ∈ (pool, manual_review)，按 created_at 的 UTC 日期分组计数；
          rejected 等其余状态不计；
        - 每日采集事件数 = source_collection_events.created_at 按 UTC 日计数；
        - 每日运行 = source_runs.started_at 按 UTC 日计数（ok_runs 为 ok=True 数）；
        - target_met = effective_candidates ≥ DAILY_EFFECTIVE_TARGET(200)；
          gap = max(0, 200 - effective_candidates)（达标日 gap=0）；
        - 窗口 = 最近 N 天滚动窗口（切点与 weekly() 一致），首/末日可为不完整日；
        - 空数据 → daily=[]，不抛异常。
        """
        since = datetime.now(timezone.utc) - timedelta(days=days)

        def _new_day() -> dict:
            return {
                "collected_events": 0,
                "runs": 0,
                "ok_runs": 0,
                "effective_candidates": 0,
            }

        with self.db.session() as session:
            event_dates = session.scalars(
                select(SourceCollectionEvent.created_at).where(
                    SourceCollectionEvent.created_at >= since
                )
            ).all()
            run_rows = session.execute(
                select(SourceRun.started_at, SourceRun.ok).where(
                    SourceRun.started_at >= since
                )
            ).all()
            product_rows = (
                session.execute(
                    select(Product.created_at, Product.state).where(
                        Product.created_at >= since
                    )
                ).all()
                if hasattr(Product, "created_at")
                else []
            )

        daily: dict[str, dict] = defaultdict(_new_day)
        for dt in event_dates:
            daily[_utc_date(dt)]["collected_events"] += 1
        for started_at, ok in run_rows:
            day = daily[_utc_date(started_at)]
            day["runs"] += 1
            if ok:
                day["ok_runs"] += 1
        for created_at, state in product_rows:
            if state in _EFFECTIVE_STATES:
                daily[_utc_date(created_at)]["effective_candidates"] += 1

        rows = []
        for date in sorted(daily):
            d = daily[date]
            rows.append(
                {
                    "date": date,
                    "collected_events": d["collected_events"],
                    "runs": d["runs"],
                    "ok_runs": d["ok_runs"],
                    "effective_candidates": d["effective_candidates"],
                    "target_met": d["effective_candidates"] >= DAILY_EFFECTIVE_TARGET,
                    "gap": max(0, DAILY_EFFECTIVE_TARGET - d["effective_candidates"]),
                }
            )

        return {
            "period_days": days,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "daily": rows,
        }
