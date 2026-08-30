"""人工闸门按达标自动放松（S5，v1.1+）。

背景（风险 R-54 / 10 文档第五节）：全自动选品对高风险类目强制 `manual_review`
人工复核，但「闸门放松」需按数据积累逐步进行——10 文档第五节口径：
**该类目通过率连续达标（如 95% × 50 品）才自动放行**，避免人工闸门失效
（全自动误放行高合规风险品）或反向的闸门永不放松（复核量堆积）。

本模块实现**配置化放松策略**（读 app_config，不写——共享表只读纪律）：
- 配置键（点分隔命名空间，REC-010 / DA-008 键名纪律，与 `category.whitelist` 同约定）：
  `gate.relax.enabled`（bool，默认 false=不放松）、
  `gate.relax.min_samples`（int，默认 50）、
  `gate.relax.pass_rate`（float，默认 0.95）、
  `gate.relax.window_days`（int，默认 30，统计窗口）、
  `gate.relax.categories`（list[str]，默认 [] = 全部类目）。
- 复核统计口径：窗口内该类目 `products` 中
  通过数 = `state='pool'`、拒绝数 = `state='rejected'`（在途 manual_review 不计），
  样本数 = 通过 + 拒绝，通过率 = 通过 / 样本数。
- 判定：`enabled 且 样本数 ≥ min_samples 且 通过率 ≥ pass_rate` → 放行；
  任一不满足 → 保持人工复核（reasons 逐条可解释，对齐打分可解释纪律）。
- 生效点：`relax_manual_review()`（存量 manual_review 商品，dry-run 默认只报告）
  与 pipeline 接线（新一批 manual_review 候选人工复核前自动放行）。
  默认 `enabled=false` 行为零变化（既有测试不回归）。

只读 app_config：`load_gate_relax_config` 经 `repo.get_config_value` 读取；
键缺失/类型非法/异常一律回落默认，绝不抛异常（对齐 `_load_category_whitelist` 纪律）。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import select

from . import repo
from . import tables as T
from .models import utcnow

# ---------------------------------------------------------------- app_config 键名
# 点分隔命名空间（REC-010/DA-008 键名纪律，与 category.whitelist 同约定；键名以本文件为权威）。
KEY_ENABLED = "gate.relax.enabled"
KEY_MIN_SAMPLES = "gate.relax.min_samples"
KEY_PASS_RATE = "gate.relax.pass_rate"
KEY_WINDOW_DAYS = "gate.relax.window_days"
KEY_CATEGORIES = "gate.relax.categories"

RELAX_KEYS: tuple[str, ...] = (
    KEY_ENABLED,
    KEY_MIN_SAMPLES,
    KEY_PASS_RATE,
    KEY_WINDOW_DAYS,
    KEY_CATEGORIES,
)


# ---------------------------------------------------------------- 配置载体
@dataclass(frozen=True)
class GateRelaxConfig:
    """闸门放松配置（默认 = 不放松，行为零变化）。

    `categories` 为空元组 = 全部类目参与；非空 = 仅这些类目可放松。
    """

    enabled: bool = False
    min_samples: int = 50
    pass_rate: float = 0.95
    window_days: int = 30
    categories: tuple[str, ...] = ()

    def describe(self) -> str:
        return (
            f"enabled={self.enabled} min_samples={self.min_samples} "
            f"pass_rate={self.pass_rate} window_days={self.window_days} "
            f"categories={list(self.categories) or '(全部)'}"
        )


DEFAULT_GATE_RELAX = GateRelaxConfig()


# ---------------------------------------------------------------- 类型校验（app_config 值落地默认）
def _as_bool(v, default: bool) -> bool:
    return v if isinstance(v, bool) else default


def _as_int(v, default: int, minimum: Optional[int] = None) -> int:
    if isinstance(v, bool) or v is None:
        return default
    if isinstance(v, int):
        n = v
    elif isinstance(v, float) and v.is_integer():
        n = int(v)
    else:
        try:
            n = int(v)
        except (TypeError, ValueError):
            return default
    if minimum is not None and n < minimum:
        return default
    return n


def _as_float(v, default: float, lo: Optional[float] = None, hi: Optional[float] = None) -> float:
    if isinstance(v, bool) or v is None:
        return default
    try:
        f = float(v)
    except (TypeError, ValueError):
        return default
    if lo is not None and f < lo:
        return default
    if hi is not None and f > hi:
        return default
    return f


def _as_str_list(v, default: tuple[str, ...]) -> tuple[str, ...]:
    if isinstance(v, (list, tuple)) and all(isinstance(x, str) for x in v):
        return tuple(x for x in v if x)
    return default


def load_gate_relax_config(session) -> GateRelaxConfig:
    """从 app_config 读取 `gate.relax.*` 键（只读；写经总控协调，本模块不写）。

    - 键缺失 → 默认值；类型非法/越界 → 该键回落默认；任何异常 → 整体回落默认；
    - 默认 `enabled=false`：未配置即不放松（既有行为零变化）。
    """
    try:
        enabled = _as_bool(repo.get_config_value(session, KEY_ENABLED, False), False)
        min_samples = _as_int(
            repo.get_config_value(session, KEY_MIN_SAMPLES, 50), 50, minimum=1
        )
        pass_rate = _as_float(
            repo.get_config_value(session, KEY_PASS_RATE, 0.95), 0.95, lo=0.0, hi=1.0
        )
        if not (0.0 < pass_rate <= 1.0):
            pass_rate = 0.95
        window_days = _as_int(
            repo.get_config_value(session, KEY_WINDOW_DAYS, 30), 30, minimum=1
        )
        categories = _as_str_list(repo.get_config_value(session, KEY_CATEGORIES, []), ())
    except Exception:
        return DEFAULT_GATE_RELAX
    return GateRelaxConfig(
        enabled=enabled,
        min_samples=min_samples,
        pass_rate=pass_rate,
        window_days=window_days,
        categories=categories,
    )


# ---------------------------------------------------------------- 复核统计
@dataclass(frozen=True)
class GateRelaxStats:
    """窗口内单类目复核统计（通过/拒绝/样本/通过率）。"""

    category: str
    passed: int
    rejected: int
    window_days: int
    window_start: datetime

    @property
    def sample_size(self) -> int:
        return self.passed + self.rejected

    @property
    def pass_rate(self) -> float:
        return self.passed / self.sample_size if self.sample_size else 0.0


def _stats_in_session(session, category: str, config: GateRelaxConfig, now=None) -> GateRelaxStats:
    """同一会话内统计该类目复核数据（通过=state='pool'，拒绝=state='rejected'）。

    - 统计窗口：created_at >= now - window_days（在途 manual_review / hard_reject 不计）；
    - 口径对齐 10 文档第五节「通过率连续达标」：通过率 = 通过 / (通过 + 拒绝)。
    """
    now = now or utcnow()
    cutoff = now - timedelta(days=max(1, int(config.window_days)))
    states = list(
        session.execute(
            select(T.Product.state).where(
                T.Product.category == category,
                T.Product.created_at >= cutoff,
                T.Product.state.in_(["pool", "rejected"]),
            )
        ).scalars()
    )
    passed = states.count("pool")
    return GateRelaxStats(
        category=category,
        passed=passed,
        rejected=len(states) - passed,
        window_days=int(config.window_days),
        window_start=cutoff,
    )


def compute_category_stats(db, category: str, config: GateRelaxConfig, now=None) -> GateRelaxStats:
    """对外统计入口：给定 Database，返回窗口内该类目复核统计。"""
    with db.session() as session:
        return _stats_in_session(session, category, config, now)


# ---------------------------------------------------------------- 判定
def decide_relax(
    stats: GateRelaxStats,
    category: str,
    config: GateRelaxConfig,
    subset=None,
) -> tuple[bool, list[str]]:
    """纯判定（无 IO）：给定统计与配置返回 (是否放行, 理由列表)。

    - 未启用 → 不放松（默认行为零变化）；
    - 空类目 → 保守不放松（无法按类目统计，R-54 兜底）；
    - categories 子集（config.categories；subset 非 None 时覆盖）不命中 → 不放松；
    - 样本 < min_samples → 不放松；通过率 < pass_rate → 不放松；
    - 全部达标 → 放行。每步 reason 可解释（对齐打分可解释纪律）。
    """
    if not config.enabled:
        return False, ["gate.relax 未启用（gate.relax.enabled=false），保持人工复核（默认行为零变化）"]
    if not category:
        return False, ["类目为空，无法按类目统计，保持人工复核（保守默认）"]
    cats = config.categories if subset is None else tuple(subset)
    if cats and category not in cats:
        return False, [
            f"类目「{category}」不在 gate.relax.categories 子集（{len(cats)} 类），保持人工复核"
        ]
    if stats.sample_size < config.min_samples:
        return False, [
            f"样本不足：窗口内 {stats.sample_size} 品 < min_samples {config.min_samples}"
            f"（通过 {stats.passed} / 拒绝 {stats.rejected}），保持人工复核"
        ]
    if stats.pass_rate < config.pass_rate:
        return False, [
            f"通过率不足：{stats.pass_rate:.4f} < 阈值 {config.pass_rate}"
            f"（通过 {stats.passed} / 拒绝 {stats.rejected}），保持人工复核"
        ]
    return True, [
        f"达标放行：pass_rate={stats.pass_rate:.4f} ≥ {config.pass_rate}"
        f" 且样本 {stats.sample_size} ≥ {config.min_samples}"
        f"（窗口 {config.window_days} 天：通过 {stats.passed} / 拒绝 {stats.rejected}）"
    ]


def should_relax_category(db, category: str, config: GateRelaxConfig) -> tuple[bool, list[str]]:
    """S5 核心判定：该类目 manual_review 品是否按达标自动放行 pool。

    Args:
        db: 本模块 Database（products/app_config 均在本模块库）。
        category: 类目名（空串 → 保守不放松）。
        config: 已解析的 GateRelaxConfig（pipeline/CLI 从 app_config 加载后传入）。

    Returns:
        (bool, reasons)：True=达标可放行；reasons 逐条可解释（对齐打分可解释纪律）。
    """
    stats = compute_category_stats(db, category, config)
    return decide_relax(stats, category, config)


# ---------------------------------------------------------------- 存量放行操作
@dataclass
class RelaxAction:
    """单条 manual_review 商品的放松判定结果。"""

    product_id: int
    category: str
    state: str  # 判定后状态（放行=pool / 保持=manual_review）
    relaxed: bool
    reasons: list[str] = field(default_factory=list)


@dataclass
class RelaxReport:
    """一次 gate-relax 运行的报告（dry-run 只报告不放行）。"""

    dry_run: bool
    config: GateRelaxConfig = DEFAULT_GATE_RELAX
    actions: list[RelaxAction] = field(default_factory=list)

    @property
    def relaxed_count(self) -> int:
        return sum(1 for a in self.actions if a.relaxed)

    @property
    def kept_count(self) -> int:
        return len(self.actions) - self.relaxed_count


def relax_manual_review(
    db,
    config: Optional[GateRelaxConfig] = None,
    dry_run: bool = True,
    categories=None,
    limit: Optional[int] = None,
) -> RelaxReport:
    """对存量 `state='manual_review'` 商品执行闸门放松判定（默认 dry-run 只报告不放行）。

    - config: None → 从 app_config 读取（load_gate_relax_config）；
    - categories: 类目子集覆盖（list/tuple[str]）；None → 用 config.categories；
    - dry_run=True：不改库（安全默认）；dry_run=False：达标商品 state → pool；
    - limit: 最多处理 N 条（按 id 升序，防批量误操作）。
    """
    with db.session() as session:
        resolved = config if config is not None else load_gate_relax_config(session)
        report = RelaxReport(dry_run=dry_run, config=resolved)
        query = (
            select(T.Product)
            .where(T.Product.state == "manual_review")
            .order_by(T.Product.id)
        )
        rows = list(session.execute(query).scalars())
        if limit is not None:
            rows = rows[:limit]
        for row in rows:
            cat = row.category or ""
            stats = _stats_in_session(session, cat, resolved)
            ok, reasons = decide_relax(stats, cat, resolved, subset=categories)
            if ok and not dry_run:
                row.state = "pool"
            report.actions.append(
                RelaxAction(
                    product_id=row.id,
                    category=cat,
                    state=row.state,
                    relaxed=ok,
                    reasons=reasons,
                )
            )
    return report
