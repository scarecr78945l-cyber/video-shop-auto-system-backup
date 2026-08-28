"""选品打分（v2，五维，满分 100）。

热度趋势 35 / 利润率 30 / 售后风险 20 / 供给稳定 15 / 投放转化 10（新增）。

投放转化无数据时不生效：该维权重折入其他四维，和仍为 100
（对应 M2「数据结构先行，无数据时权重=0 不生效」）。

每维打分理由写入 ScoreBreakdown，可逐条解释（验收标准）。
"""

from __future__ import annotations

from .config import ScoringConfig
from .models import ScoreBreakdown, ScoreDimension

DIM_LABELS = {
    "trend": "热度趋势",
    "profit": "利润率",
    "after_sale": "售后风险",
    "supply": "供给稳定",
    "ad_conversion": "投放转化",
}


def _band_score(
    bands: list[tuple[float, float]],
    value: float,
    default: float = 0.0,
    higher_better: bool = False,
) -> float:
    """bands: [(阈值, 得分)]，按顺序取第一个命中的档。

    higher_better=False：value <= 阈值（排名、退货率，越低越好）
    higher_better=True ：value >= 阈值（销量、毛利率、供应商数、ROI，越高越好）
    """
    for threshold, score in bands:
        if (value >= threshold) if higher_better else (value <= threshold):
            return score
    return default


class ScoreInput:
    """打分所需数据（由流水线组装）。"""

    def __init__(
        self,
        rank: int = 0,
        sales: int = 0,
        board_count: int = 1,
        platform_price: float = 0.0,
        real_cost: float | None = None,
        suggested_price: float | None = None,
        return_rate: float | None = None,
        supplier_count: int = 0,
        ad_roi: float | None = None,  # 该类目历史托管 ROI（无数据=None）
        ad_sales: float | None = None,
    ):
        self.rank = rank
        self.sales = sales
        self.board_count = board_count
        self.platform_price = platform_price
        self.real_cost = real_cost
        self.suggested_price = suggested_price
        self.return_rate = return_rate
        self.supplier_count = supplier_count
        self.ad_roi = ad_roi
        self.ad_sales = ad_sales


class Scorer:
    def __init__(self, config: ScoringConfig):
        self.cfg = config

    def score(self, data: ScoreInput) -> ScoreBreakdown:
        raw: dict[str, float] = {}
        reasons: dict[str, list[str]] = {}
        active: set[str] = set()

        # --- 热度趋势 35 ---
        rank = data.rank or 0
        if rank > 0:
            score = _band_score(
                [(t, s) for t, s in self.cfg.trend_rank_bands],
                rank,
                default=4.0,
            )
            reasons["trend"] = [f"榜单排名第 {rank}"]
        else:
            score = 4.0
            reasons["trend"] = ["无榜单排名，按最低档"]
        if data.sales > 0:
            sales_s = _band_score(self.cfg.trend_sales_bands, data.sales, default=1.0, higher_better=True)
            score += sales_s
            reasons["trend"].append(f"销量 {data.sales}（+{sales_s:.0f}）")
        if data.board_count >= 2:
            score += self.cfg.trend_cross_bonus
            reasons["trend"].append(f"多榜/多源交叉确认（+{self.cfg.trend_cross_bonus:.0f}）")
        raw["trend"] = min(score, self.cfg.dimension_max["trend"])
        active.add("trend")

        # --- 利润率 30 ---
        if data.real_cost is not None and data.real_cost >= 0 and data.suggested_price:
            margin = (data.suggested_price - data.real_cost) / data.suggested_price
            profit_s = _band_score(self.cfg.profit_margin_bands, margin, default=2.0, higher_better=True)
            raw["profit"] = profit_s
            reasons["profit"] = [
                f"成本 {data.real_cost:.2f} → 建议售价 {data.suggested_price:.1f}，"
                f"毛利率 {margin:.0%}（+{profit_s:.0f}）"
            ]
            active.add("profit")
        elif data.platform_price > 0 and data.real_cost is None:
            # 未询价：按平台价 45% 估成本，标记为估算（后续询价回填重算）
            est_cost = data.platform_price * 0.45
            margin = (data.platform_price - est_cost) / data.platform_price
            profit_s = _band_score(self.cfg.profit_margin_bands, margin, default=2.0, higher_better=True)
            raw["profit"] = profit_s
            reasons["profit"] = [
                f"未询价，按平台价 {data.platform_price:.1f} 的 55% 毛利估算（+{profit_s:.0f}），待 1688 询价回填"
            ]
            active.add("profit")
        else:
            reasons["profit"] = ["无价格数据，利润维度不参与"]
            raw["profit"] = 0.0

        # --- 售后风险 20 ---
        if data.return_rate is not None:
            as_s = _band_score(self.cfg.after_sale_bands, data.return_rate, default=0.0)
            raw["after_sale"] = as_s
            reasons["after_sale"] = [
                f"退货率 {data.return_rate:.0%}（+{as_s:.0f}）"
            ]
            active.add("after_sale")
        else:
            raw["after_sale"] = self.cfg.after_sale_unknown
            reasons["after_sale"] = [
                f"退货率未知，取中间档（+{self.cfg.after_sale_unknown:.0f}），待平台数据回填"
            ]
            active.add("after_sale")

        # --- 供给稳定 15 ---
        if data.supplier_count > 0:
            sup_s = _band_score(self.cfg.supply_bands, data.supplier_count, default=2.0, higher_better=True)
            raw["supply"] = sup_s
            reasons["supply"] = [f"1688 同款供应商 {data.supplier_count} 家（+{sup_s:.0f}）"]
            active.add("supply")
        else:
            raw["supply"] = 0.0
            reasons["supply"] = ["暂无同款供应商数据"]
            active.add("supply")

        # --- 投放转化（新增，无数据维度不生效）---
        if data.ad_roi is not None:
            ad_s = _band_score(self.cfg.ad_roi_bands, data.ad_roi, default=self.cfg.ad_roi_below, higher_better=True)
            raw["ad_conversion"] = ad_s
            reasons["ad_conversion"] = [
                f"该类目历史托管 ROI {data.ad_roi:.2f}（+{ad_s:.0f}）"
            ]
            active.add("ad_conversion")
        else:
            raw["ad_conversion"] = 0.0
            reasons["ad_conversion"] = ["该类目暂无托管投放数据，维度权重折入其他四维"]
            # 不加入 active → 权重折算

        # --- 权重归一化 ---
        # 基础四维满分和 = 100；投放转化满分 = ad_conversion_weight（从其他维折算）。
        # 有投放数据：基础四维按 (100 - ad_weight)/100 折算，投放转化占 ad_weight。
        # 无投放数据：基础四维满分（和 100），投放转化权重 0。
        base_dims = ["trend", "profit", "after_sale", "supply"]
        dim_max = self.cfg.dimension_max
        base_total = sum(dim_max[k] for k in base_dims)  # = 100
        ad_active = "ad_conversion" in active
        scale = (
            (base_total - self.cfg.ad_conversion_weight) / base_total
            if ad_active
            else 1.0
        )

        breakdown = ScoreBreakdown()
        total = 0.0
        for key, label in DIM_LABELS.items():
            if key == "ad_conversion":
                if not ad_active:
                    breakdown.dimensions[key] = ScoreDimension(
                        key=key, label=label, raw=0.0, weight=0.0, weighted=0.0,
                        active=False, reasons=reasons.get(key, ["无数据，未参与"]),
                    )
                    continue
                weight = self.cfg.ad_conversion_weight / base_total
                weighted = round(raw[key], 1)  # raw 已是 0~ad_conversion_weight 分
                total += weighted
                breakdown.dimensions[key] = ScoreDimension(
                    key=key, label=label, raw=raw[key], weight=round(weight, 4),
                    weighted=weighted, active=True, reasons=reasons[key],
                )
                continue
            if key not in active:
                breakdown.dimensions[key] = ScoreDimension(
                    key=key, label=label, raw=0.0, weight=0.0, weighted=0.0,
                    active=False, reasons=reasons.get(key, ["无数据，未参与"]),
                )
                continue
            weight = (dim_max[key] / base_total) * scale
            weighted = round(raw[key] * scale, 1)
            total += weighted
            breakdown.dimensions[key] = ScoreDimension(
                key=key, label=label, raw=raw[key], weight=round(weight, 4),
                weighted=weighted, active=True, reasons=reasons[key],
            )
        breakdown.total = round(total, 1)
        breakdown.note = (
            f"参与维度 {len(active)}/5"
            + ("" if ad_active else "（投放转化无数据）")
        )
        return breakdown
