"""M3 A/B 优化闭环（backend/optimization/ab/）测试（子代理-E · v1.0 集成任务 2）。

覆盖（全部临时 SQLite 内存库，零网络零真实平台调用）：
1. 评分 scoring：默认权重公式正确（ROI/CTR/诊断输入 → score）；无数据 → 0 分；
   饱和点/诊断映射/自定义权重/配置非法校验/环境变量覆盖；
2. 标签 evaluate：阈值边界（高效/潜力/探索期）；EvaluationService.record 幂等
   （同 variant+日期重复写不新增行）；stale 标记（无新数据）；
3. 排序 ranking：高效 > 潜力 > 探索期，同级 score 降序，稳定；类目过滤；
   only_uploaded 过滤；输出元组形状；
4. 版本管理 variants：≥2 版清单 + 差异摘要；不足 2 版提示；
5. 重训练 retrain：样本达标更新 stats_json/template_stats_json；
   样本不足不更新；基模板归并（-vN 后缀）；
6. 无明文密钥；ab 包级重导出。

运行：python -m pytest tests/test_optimization_ab.py -q --basetemp=".pytest-tmp-m3"
（P-011：模块独立 basetemp，禁止共用 .pytest-tmp）
"""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import select

from optimization import tables
from optimization.ab import (
    AB_MIN_VARIANTS,
    EXPLORATION,
    HIGH_EFFICIENCY,
    POTENTIAL,
    EvaluationPolicy,
    EvaluationService,
    MaterialRanker,
    MaterialScorer,
    RetrainPolicy,
    ScoringPolicy,
    TemplateRetrainer,
    VariantManager,
    base_template_id,
    compute_score,
    ctr_of,
    diag_score,
    label_for,
)
from optimization.config import load_config
from optimization.db import Database
from optimization.models import EvaluationSnapshot

# ---------------------------------------------------------------- fixtures

DEFAULT_PARAMS = {
    "opening_seconds": 3,
    "cut_count": 3,
    "bgm_loudness": -16.0,
    "badge_position": "top-right",
    "subtitle_style": {"position": "bottom", "font_size": 36, "stroke": True},
}


@pytest.fixture
def cfg(tmp_path):
    """内存库（P-011：不触碰 .pytest-tmp 与真实 m3-optimization.db）。"""
    return load_config(
        db_url="sqlite:///:memory:",
        fixtures_dir=Path(__file__).resolve().parent.parent / "fixtures",
        data_dir=tmp_path / "data",
    )


@pytest.fixture
def db(cfg):
    database = Database(cfg)
    database.create_all()
    return database


@pytest.fixture
def scorer():
    return MaterialScorer()


@pytest.fixture
def service(db, scorer):
    return EvaluationService(db, scorer=scorer)


@pytest.fixture
def ranker(db, service):
    return MaterialRanker(db, service=service)


@pytest.fixture
def manager(db):
    return VariantManager(db)


@pytest.fixture
def retrainer(db):
    return TemplateRetrainer(db, policy=RetrainPolicy(min_samples=5))


# ---------------------------------------------------------------- 造数工具


def _add_variant(
    db,
    product_id: str,
    variant_no: int,
    *,
    template_id: str | None = None,
    params: dict | None = None,
    copywrite_ids: list | None = None,
    platform_material_id: str = "",
    category: str = "家居日用",
    snapshot: dict | None = None,
    evaluation: str = "exploring",
    spec_ok: bool = True,
) -> str:
    overrides = params or {}
    params = dict(DEFAULT_PARAMS)
    params.update(overrides)
    template_id = template_id or f"tpl_{category}_v1-v{variant_no}"
    snapshot = snapshot or {
        "template_id": template_id,
        "category": category,
        "params": params,
        "segments": {},
    }
    variant_id = f"vv_{product_id}_{variant_no}"
    with db.session() as s:
        s.add(
            tables.OptVideoVariant(
                variant_id=variant_id,
                product_id=product_id,
                source_asset_id="a_src",
                variant_no=variant_no,
                template_id=template_id,
                copywrite_ids=copywrite_ids or [f"ad:{variant_no}"],
                template_params_snapshot=snapshot,
                file_path=f"data/video_variants/{product_id}_v{variant_no:02d}.mp4",
                spec_check_json={},
                spec_ok=int(spec_ok),
                compliance_json={},
                review_status="passed",
                upload_status="uploaded" if platform_material_id else "local",
                platform_material_id=platform_material_id,
                evaluation=evaluation,
            )
        )
    return variant_id


def _feedback(
    service: EvaluationService,
    variant_id: str,
    report_date: str,
    *,
    exposure: int = 0,
    clicks: int = 0,
    spend: float = 0.0,
    orders: int = 0,
    roi: float = 0.0,
    diagnosis: dict | None = None,
    pm: str = "",
) -> str:
    return service.record_metrics(
        variant_id,
        report_date,
        exposure=exposure,
        clicks=clicks,
        spend=spend,
        orders=orders,
        roi=roi,
        diagnosis=diagnosis,
        platform_material_id=pm,
    )


# ---------------------------------------------------------------- 1. 评分

class TestScoring:
    def test_default_formula(self):
        # roi_score=3/5=0.6, ctr_score=0.03/0.05=0.6, diag=1.0
        # 0.5*0.6 + 0.3*0.6 + 0.2*1.0 = 0.68
        assert compute_score(3.0, 0.03, {"level": "excellent"}) == pytest.approx(0.68)
        assert MaterialScorer().score(3.0, 0.03, "excellent") == pytest.approx(0.68)

    def test_no_data_zero(self):
        assert compute_score(0, 0, {}) == 0.0
        assert MaterialScorer().score(0, 0, None) == 0.0
        assert MaterialScorer().score_for_metrics(0, 0, 0, None) == 0.0

    def test_roi_saturation(self):
        # ROI=10 ≥ cap 5 → roi_score=1.0 → 权重 0.5
        assert compute_score(10.0, 0.0, None) == pytest.approx(0.5)
        assert compute_score(5.0, 0.0, None) == pytest.approx(0.5)

    def test_ctr_saturation(self):
        # CTR=0.10 ≥ cap 0.05 → ctr_score=1.0 → 权重 0.3
        assert compute_score(0.0, 0.10, None) == pytest.approx(0.3)
        assert compute_score(0.0, 0.05, None) == pytest.approx(0.3)

    def test_diag_mapping_strings(self):
        assert diag_score("excellent") == 1.0
        assert diag_score("good") == pytest.approx(0.7)
        assert diag_score("optimize_1") == pytest.approx(0.4)
        assert diag_score("optimize_n") == pytest.approx(0.2)
        assert diag_score("unknown") == 0.0
        assert diag_score("") == 0.0
        assert diag_score(None) == 0.0
        assert diag_score("Excellent") == 1.0

    def test_diag_mapping_chinese(self):
        assert diag_score("优秀") == 1.0
        assert diag_score("良好") == pytest.approx(0.7)
        assert diag_score("1项待优化") == pytest.approx(0.4)
        assert diag_score("N项待优化") == pytest.approx(0.2)
        assert diag_score("3 项待优化") == pytest.approx(0.2)

    def test_diag_mapping_dict_and_number(self):
        assert diag_score({"level": "良好"}) == pytest.approx(0.7)
        assert diag_score({"diagnosis": "optimize_1"}) == pytest.approx(0.4)
        assert diag_score({"evaluation": "优秀"}) == 1.0
        assert diag_score({"score": 0.85}) == pytest.approx(0.85)
        assert diag_score({"score": 85}) == pytest.approx(0.85)
        assert diag_score(0.8) == pytest.approx(0.8)
        assert diag_score(80) == pytest.approx(0.8)
        assert diag_score({"other": 1}) == 0.0

    def test_ctr_of(self):
        assert ctr_of(30, 1000) == pytest.approx(0.03)
        assert ctr_of(0, 0) == 0.0
        assert ctr_of(5, 0) == 0.0
        assert ctr_of(0, 100) == 0.0

    def test_custom_weights(self):
        policy = ScoringPolicy(roi_weight=0.7, ctr_weight=0.2, diag_weight=0.1)
        # roi=5 → 1.0, ctr=0.05 → 1.0, good → 0.7
        # 0.7 + 0.2 + 0.07 = 0.97
        assert MaterialScorer(policy).score(5.0, 0.05, {"level": "good"}) == pytest.approx(0.97)

    def test_weights_sum_must_be_one(self):
        with pytest.raises(ValueError):
            ScoringPolicy(roi_weight=0.5, ctr_weight=0.3, diag_weight=0.3)

    def test_caps_must_be_positive(self):
        with pytest.raises(ValueError):
            ScoringPolicy(roi_score_cap=0)
        with pytest.raises(ValueError):
            ScoringPolicy(ctr_score_cap=-1)

    def test_negative_inputs_clamped(self):
        assert compute_score(-1.0, -0.1, None) == 0.0
        assert compute_score(3.0, -0.1, {"level": "unknown"}) == pytest.approx(0.5 * 0.6)

    def test_score_max_clamped(self):
        assert compute_score(100, 1.0, {"level": "excellent"}) == 1.0

    def test_policy_from_env(self, monkeypatch):
        monkeypatch.setenv("M3_AB_ROI_WEIGHT", "0.6")
        monkeypatch.setenv("M3_AB_CTR_WEIGHT", "0.3")
        monkeypatch.setenv("M3_AB_DIAG_WEIGHT", "0.1")
        monkeypatch.setenv("M3_AB_ROI_SCORE_CAP", "10")
        monkeypatch.setenv("M3_AB_CTR_SCORE_CAP", "0.1")
        p = ScoringPolicy.from_env()
        assert p.roi_weight == pytest.approx(0.6)
        assert p.ctr_weight == pytest.approx(0.3)
        assert p.diag_weight == pytest.approx(0.1)
        assert p.roi_score_cap == pytest.approx(10)
        assert p.ctr_score_cap == pytest.approx(0.1)
        # 非法值回退默认（其余权重还原，避免和≠1 校验误触发）
        monkeypatch.delenv("M3_AB_CTR_WEIGHT", raising=False)
        monkeypatch.delenv("M3_AB_DIAG_WEIGHT", raising=False)
        monkeypatch.setenv("M3_AB_ROI_WEIGHT", "not-a-number")
        assert ScoringPolicy.from_env().roi_weight == pytest.approx(0.5)


# ---------------------------------------------------------------- 2. 标签

class TestLabels:
    def test_high_by_roi_boundary(self):
        assert label_for(1000, 10, 100, 5, 2.0, {}) == HIGH_EFFICIENCY
        assert label_for(1000, 10, 100, 5, 2.5, {}) == HIGH_EFFICIENCY

    def test_high_by_ctr_and_roi_boundary(self):
        # ctr = 20/1000 = 0.02 达标且 roi=1.0 → 高效
        assert label_for(1000, 20, 100, 3, 1.0, {}) == HIGH_EFFICIENCY
        # ctr 达标但 roi=0.9 < 1.0 → 不高效
        assert label_for(1000, 30, 100, 2, 0.9, {}) == POTENTIAL

    def test_roi_just_below_high(self):
        # roi=1.9999 不达 2.0，ctr=0.01 不达标 → 潜力（有曝光无成交）
        assert label_for(1000, 10, 100, 0, 1.9999, {}) == POTENTIAL

    def test_exposure_no_orders_potential(self):
        assert label_for(1000, 10, 50, 0, 0.0, {}) == POTENTIAL

    def test_low_data_exploring(self):
        # exposure=99 < min_exposure=100 → 探索期
        assert label_for(99, 5, 10, 0, 0.0, {}) == EXPLORATION
        assert label_for(99, 5, 10, 3, 1.5, {}) == EXPLORATION

    def test_min_exposure_boundary(self):
        # exposure=100 恰达阈值 → 有曝光无成交 → 潜力
        assert label_for(100, 5, 10, 0, 0.0, {}) == POTENTIAL

    def test_no_data_exploring(self):
        assert label_for(0, 0, 0, 0, 0.0, {}) == EXPLORATION
        assert label_for(None, None, None, None, None, {}) == EXPLORATION

    def test_orders_underperforming_potential(self):
        # 有成交但 ROI/CTR 均未达高效 → 潜力（成交待观察）
        assert label_for(1000, 5, 100, 8, 0.5, {}) == POTENTIAL

    def test_custom_policy(self):
        policy = EvaluationPolicy(roi_high=3.0, ctr_qualify=0.05, roi_potential=2.0)
        # roi=2.5 < 3.0；ctr=0.02 < 0.05 → 不高效 → 潜力
        assert label_for(1000, 20, 100, 5, 2.5, {}, policy) == POTENTIAL
        # roi=3.0 ≥ 3.0 → 高效
        assert label_for(1000, 0, 100, 5, 3.0, {}, policy) == HIGH_EFFICIENCY

    def test_policy_from_env(self, monkeypatch):
        monkeypatch.setenv("M3_AB_EVAL_ROI_HIGH", "3.0")
        monkeypatch.setenv("M3_AB_EVAL_MIN_EXPOSURE", "500")
        p = EvaluationPolicy.from_env()
        assert p.roi_high == pytest.approx(3.0)
        assert p.min_exposure == 500
        assert p.stale_days == 7
        assert label_for(1000, 10, 100, 3, 2.5, {}, p) == POTENTIAL

    def test_policy_invalid(self):
        with pytest.raises(ValueError):
            EvaluationPolicy(min_exposure=-1)
        with pytest.raises(ValueError):
            EvaluationPolicy(stale_days=-2)


class TestEvaluationService:
    def test_record_computes_and_persists(self, db, service):
        _add_variant(db, "p1", 1, platform_material_id="pm_1")
        fid = _feedback(
            service, "vv_p1_1", "2026-08-28",
            exposure=1000, clicks=30, spend=100, orders=5, roi=3.0,
            diagnosis={"level": "excellent"}, pm="pm_1",
        )
        assert fid.startswith("ev_")
        latest = service.latest("vv_p1_1")
        assert latest is not None
        assert latest["evaluation"] == HIGH_EFFICIENCY
        assert latest["score"] == pytest.approx(0.68)
        assert latest["stale"] is False
        with db.session() as s:
            row = s.get(tables.OptEvaluationFeedback, fid)
            assert row.platform_material_id == "pm_1"  # 骨架置空后补写成功

    def test_upsert_idempotent_same_row(self, db, service):
        _add_variant(db, "p1", 1)
        _feedback(service, "vv_p1_1", "2026-08-28", exposure=1000, clicks=10, orders=0, roi=0)
        _feedback(service, "vv_p1_1", "2026-08-28", exposure=1000, clicks=30, orders=5, roi=3.0,
                  diagnosis={"level": "excellent"})
        # 同 (variant_id, report_date) 重复写不新增行，后写覆盖
        with db.session() as s:
            rows = s.execute(
                select(tables.OptEvaluationFeedback).where(
                    tables.OptEvaluationFeedback.variant_id == "vv_p1_1"
                )
            ).scalars().all()
            assert len(rows) == 1
            assert rows[0].score == pytest.approx(0.68)
            assert rows[0].evaluation == HIGH_EFFICIENCY

    def test_multi_date_latest(self, db, service):
        _add_variant(db, "p1", 1)
        _feedback(service, "vv_p1_1", "2026-08-27", exposure=1000, clicks=10, orders=0, roi=0)
        _feedback(service, "vv_p1_1", "2026-08-28", exposure=1000, clicks=30, orders=5, roi=3.0)
        latest = service.latest("vv_p1_1")
        assert latest["report_date"] == "2026-08-28"
        assert latest["evaluation"] == HIGH_EFFICIENCY
        with db.session() as s:
            rows = s.execute(
                select(tables.OptEvaluationFeedback)
            ).scalars().all()
            assert len(rows) == 2  # 不同日期 → 2 行

    def test_no_feedback_none(self, service):
        assert service.latest("vv_ghost") is None

    def test_latest_map(self, db, service):
        _add_variant(db, "p1", 1)
        _add_variant(db, "p1", 2)
        _feedback(service, "vv_p1_1", "2026-08-27", exposure=1000, clicks=10, orders=0, roi=0)
        _feedback(service, "vv_p1_1", "2026-08-28", exposure=1000, clicks=30, orders=5, roi=3.0)
        _feedback(service, "vv_p1_2", "2026-08-28", exposure=1000, clicks=50, orders=0, roi=0)
        m = service.latest_map(["vv_p1_1", "vv_p1_2", "vv_ghost"])
        assert m["vv_p1_1"]["report_date"] == "2026-08-28"
        assert m["vv_p1_1"]["evaluation"] == HIGH_EFFICIENCY
        assert m["vv_p1_2"]["evaluation"] == POTENTIAL
        assert "vv_ghost" not in m
        assert service.latest_map([]) == {}

    def test_stale_old_marked(self, db, service):
        _add_variant(db, "p1", 1)
        _feedback(service, "vv_p1_1", "2026-08-20", exposure=1000, clicks=10, orders=5, roi=2.5)
        assert service.mark_stale("vv_p1_1", today="2026-08-28") is True
        latest = service.latest("vv_p1_1")
        assert latest["stale"] is True

    def test_stale_fresh_and_boundary(self, db, service):
        _add_variant(db, "p1", 1)
        # 恰 7 天（cutoff = 2026-08-21）：不超期
        _feedback(service, "vv_p1_1", "2026-08-21", exposure=1000, clicks=10, orders=5, roi=2.5)
        assert service.mark_stale("vv_p1_1", today="2026-08-28") is False
        assert service.latest("vv_p1_1")["stale"] is False
        # 更近的数据也不 stale
        _feedback(service, "vv_p1_1", "2026-08-22", exposure=1000, clicks=10, orders=5, roi=2.5)
        assert service.mark_stale("vv_p1_1", today="2026-08-28") is False

    def test_stale_self_heal_and_idempotent(self, db, service):
        _add_variant(db, "p1", 1)
        _feedback(service, "vv_p1_1", "2026-08-20", exposure=1000, clicks=10, orders=5, roi=2.5)
        assert service.mark_stale("vv_p1_1", today="2026-08-28") is True
        assert service.mark_stale("vv_p1_1", today="2026-08-28") is True  # 幂等
        # 新数据写入后自愈：最新变新鲜 → 不再 stale
        _feedback(service, "vv_p1_1", "2026-08-28", exposure=1000, clicks=30, orders=5, roi=3.0)
        assert service.mark_stale("vv_p1_1", today="2026-08-28") is False

    def test_mark_stale_all(self, db, service):
        _add_variant(db, "p1", 1)
        _add_variant(db, "p1", 2)
        _feedback(service, "vv_p1_1", "2026-08-20", exposure=1000, clicks=10, orders=0, roi=0)
        _feedback(service, "vv_p1_2", "2026-08-28", exposure=1000, clicks=10, orders=0, roi=0)
        assert service.mark_stale_all(today="2026-08-28") == 1
        assert service.latest("vv_p1_1")["stale"] is True
        assert service.latest("vv_p1_2")["stale"] is False

    def test_record_recompute_false_preserves(self, db, service):
        _add_variant(db, "p1", 1)
        snap = EvaluationSnapshot(
            variant_id="vv_p1_1", report_date="2026-08-28",
            exposure=1000, clicks=10, orders=0, roi=0,
            score=0.99, evaluation=HIGH_EFFICIENCY,
        )
        service.record(snap, recompute=False)
        latest = service.latest("vv_p1_1")
        assert latest["score"] == pytest.approx(0.99)
        assert latest["evaluation"] == HIGH_EFFICIENCY

    def test_no_data_score_zero_exploring(self, db, ranker):
        _add_variant(db, "p1", 1, platform_material_id="pm_1")
        rows = ranker.rank_for_product("p1")
        assert rows == [("vv_p1_1", "pm_1", EXPLORATION, 0.0)]


# ---------------------------------------------------------------- 3. 排序

class TestRanking:
    def _setup(self, db, service):
        _add_variant(db, "p1", 1, platform_material_id="pm_1")
        _add_variant(db, "p1", 2, platform_material_id="pm_2")
        _add_variant(db, "p1", 3)  # 未上传、无数据
        # v1: 高效 0.68
        _feedback(service, "vv_p1_1", "2026-08-28",
                  exposure=1000, clicks=30, orders=5, roi=3.0,
                  diagnosis={"level": "excellent"}, pm="pm_1")
        # v2: 潜力 0.3（ctr 0.05 → ctr_score 1.0 → 0.3）
        _feedback(service, "vv_p1_2", "2026-08-28",
                  exposure=1000, clicks=50, orders=0, roi=0, pm="pm_2")

    def test_order_by_evaluation(self, db, service, ranker):
        self._setup(db, service)
        rows = ranker.rank_for_product("p1")
        assert [r[0] for r in rows] == ["vv_p1_1", "vv_p1_2", "vv_p1_3"]
        assert [r[2] for r in rows] == [HIGH_EFFICIENCY, POTENTIAL, EXPLORATION]
        assert rows[0][3] > rows[1][3] > rows[2][3]

    def test_same_evaluation_score_desc(self, db, service, ranker):
        self._setup(db, service)
        # vv_p1_4: 潜力 0.24（roi 1.8 → 0.18，ctr 0.01 → 0.06）
        _add_variant(db, "p1", 4, platform_material_id="pm_4")
        _feedback(service, "vv_p1_4", "2026-08-28",
                  exposure=1000, clicks=10, orders=3, roi=1.8, pm="pm_4")
        rows = ranker.rank_for_product("p1")
        potentials = [r for r in rows if r[2] == POTENTIAL]
        assert [r[0] for r in potentials] == ["vv_p1_2", "vv_p1_4"]
        assert potentials[0][3] == pytest.approx(0.3)
        assert potentials[1][3] == pytest.approx(0.24)

    def test_stable_ties(self, db, service, ranker):
        self._setup(db, service)
        # 与 vv_p1_4 完全同指标 → 同 evaluation 同 score，保持 variant_no 顺序
        _add_variant(db, "p1", 4, platform_material_id="pm_4")
        _add_variant(db, "p1", 5, platform_material_id="pm_5")
        _feedback(service, "vv_p1_4", "2026-08-28",
                  exposure=1000, clicks=10, orders=3, roi=1.8, pm="pm_4")
        _feedback(service, "vv_p1_5", "2026-08-28",
                  exposure=1000, clicks=10, orders=3, roi=1.8, pm="pm_5")
        rows = ranker.rank_for_product("p1")
        potentials = [r[0] for r in rows if r[2] == POTENTIAL]
        # vv_p1_2（0.3）在前；vv_p1_4 与 vv_p1_5 同分同标签 → 稳定保持 4 在 5 前
        assert potentials == ["vv_p1_2", "vv_p1_4", "vv_p1_5"]

    def test_only_uploaded(self, db, service, ranker):
        self._setup(db, service)
        rows = ranker.rank_for_product("p1", only_uploaded=True)
        assert [r[0] for r in rows] == ["vv_p1_1", "vv_p1_2"]  # vv_p1_3 无平台素材 ID 被滤除
        assert all(r[1] for r in rows)

    def test_rank_for_category(self, db, service, ranker):
        self._setup(db, service)
        _add_variant(db, "p2", 1, platform_material_id="pm_p2", category="宠物用品")
        _feedback(service, "vv_p2_1", "2026-08-28",
                  exposure=1000, clicks=30, orders=5, roi=3.0, pm="pm_p2")
        rows = ranker.rank_for_category("家居日用")
        assert {r[0] for r in rows} == {"vv_p1_1", "vv_p1_2", "vv_p1_3"}
        rows_pet = ranker.rank_for_category("宠物用品")
        assert [r[0] for r in rows_pet] == ["vv_p2_1"]
        assert rows_pet[0][2] == HIGH_EFFICIENCY

    def test_empty_product(self, ranker):
        assert ranker.rank_for_product("ghost") == []
        assert ranker.rank_for_category("不存在的类目") == []

    def test_tuple_shape(self, db, service, ranker):
        self._setup(db, service)
        for row in ranker.rank_for_product("p1"):
            assert isinstance(row, tuple) and len(row) == 4
            assert isinstance(row[0], str)
            assert isinstance(row[1], str)
            assert isinstance(row[2], str)
            assert isinstance(row[3], float)

    def test_unknown_evaluation_sorted_last(self):
        # 未知标签按探索期桶处理（rank=2），且分数更低时排在 exploring 之后
        items = [
            ("a", "pm", "bogus", 0.1),
            ("b", "pm", HIGH_EFFICIENCY, 0.1),
            ("c", "pm", EXPLORATION, 0.5),
            ("d", "pm", POTENTIAL, 0.7),
        ]
        rows = MaterialRanker.sort(items)
        assert [r[2] for r in rows] == [HIGH_EFFICIENCY, POTENTIAL, EXPLORATION, "bogus"]
        assert rows[0][0] == "b"

    def test_sort_stability_explicit(self):
        items = [
            ("x1", "pm", POTENTIAL, 0.5),
            ("x2", "pm", POTENTIAL, 0.5),
            ("x3", "pm", POTENTIAL, 0.5),
        ]
        rows = MaterialRanker.sort(items)
        assert [r[0] for r in rows] == ["x1", "x2", "x3"]


# ---------------------------------------------------------------- 4. 版本管理

class TestVariants:
    def test_list_variants_ordered(self, db, manager):
        _add_variant(db, "p1", 2)
        _add_variant(db, "p1", 1)
        _add_variant(db, "p1", 3)
        rows = manager.list_variants("p1")
        assert [r["variant_no"] for r in rows] == [1, 2, 3]
        assert all(r["product_id"] == "p1" for r in rows)
        assert manager.list_variants("ghost") == []

    def test_difference_summary_highlights_diffs(self, db, manager):
        _add_variant(
            db, "p1", 1,
            template_id="tpl_家居日用_v1-v1",
            copywrite_ids=["script:1", "badge:1"],
            params={"opening_seconds": 3, "cut_count": 3, "bgm_loudness": -16.0},
        )
        _add_variant(
            db, "p1", 2,
            template_id="tpl_家居日用_v1-v2",
            copywrite_ids=["ad:2", "badge:2"],
            params={"opening_seconds": 4, "cut_count": 2, "bgm_loudness": -16.5},
        )
        summary = manager.difference_summary("p1")
        assert summary["variant_count"] == 2
        assert "template_id" in summary["differences"]
        assert "copywrite_ids" in summary["differences"]
        assert "opening_seconds" in summary["differences"]
        assert "cut_count" in summary["differences"]
        assert "bgm_loudness" in summary["differences"]
        assert summary["differences"]["opening_seconds"]["values"]["1"] == 3
        assert summary["differences"]["opening_seconds"]["values"]["2"] == 4
        # 未差异字段归 identical
        assert "badge_position" in summary["identical_fields"]
        assert "subtitle_style" in summary["identical_fields"]
        assert "差异字段" in summary["hint"]

    def test_difference_summary_identical(self, db, manager):
        _add_variant(db, "p1", 1, template_id="tpl_家居日用_v1", copywrite_ids=["ad:1"], params={})
        _add_variant(db, "p1", 2, template_id="tpl_家居日用_v1", copywrite_ids=["ad:1"], params={})
        summary = manager.difference_summary("p1")
        assert summary["differences"] == {}
        assert set(summary["identical_fields"]) >= {
            "template_id", "copywrite_ids", "opening_seconds",
            "cut_count", "bgm_loudness", "badge_position", "subtitle_style",
        }
        assert "完全一致" in summary["hint"]

    def test_difference_summary_insufficient(self, db, manager):
        _add_variant(db, "p1", 1)
        summary = manager.difference_summary("p1")
        assert summary["variant_count"] == 1
        assert summary["differences"] == {}
        assert "版本不足" in summary["hint"]
        assert "无法进行差异比对" in summary["hint"]

    def test_check_ab_ready_two(self, db, manager):
        _add_variant(db, "p1", 1)
        _add_variant(db, "p1", 2)
        result = manager.check_ab_ready("p1")
        assert result["ab_ready"] is True
        assert result["variant_count"] == 2
        assert result["needed"] == 0
        assert result["hint"] == ""

    def test_check_ab_ready_one(self, db, manager):
        _add_variant(db, "p1", 1)
        result = manager.check_ab_ready("p1")
        assert result["ab_ready"] is False
        assert result["variant_count"] == 1
        assert result["needed"] == 1
        assert "至少需要 2 版素材" in result["hint"]

    def test_check_ab_ready_zero(self, db, manager):
        result = manager.check_ab_ready("p1")
        assert result["ab_ready"] is False
        assert result["variant_count"] == 0
        assert result["needed"] == AB_MIN_VARIANTS
        assert result["hint"]

    def test_ab_min_variants_constant(self):
        assert AB_MIN_VARIANTS == 2


# ---------------------------------------------------------------- 5. 重训练

class TestRetrain:
    def _setup_trained_data(self, db, service):
        """模板 tpl_家居日用_v1 + 2 版本（-v1/-v2 后缀）共 5 条有效回写。"""
        with db.session() as s:
            s.add(tables.OptTemplate(
                template_id="tpl_家居日用_v1", category="家居日用",
                template_name="默认三段式", params_version=1,
            ))
        _add_variant(db, "p1", 1, template_id="tpl_家居日用_v1-v1")
        _add_variant(db, "p1", 2, template_id="tpl_家居日用_v1-v2")
        # v1：2 条（roi 2.0/ctr 0.03, roi 4.0/ctr 0.01）
        _feedback(service, "vv_p1_1", "2026-08-26", exposure=1000, clicks=30, orders=2, roi=2.0)
        _feedback(service, "vv_p1_1", "2026-08-27", exposure=1000, clicks=10, orders=4, roi=4.0)
        # v2：3 条（roi 1.0/0.02, 2.0/0.02, 3.0/0.04）
        _feedback(service, "vv_p1_2", "2026-08-26", exposure=1000, clicks=50, orders=1, roi=1.0)
        _feedback(service, "vv_p1_2", "2026-08-27", exposure=1000, clicks=20, orders=2, roi=2.0)
        _feedback(service, "vv_p1_2", "2026-08-28", exposure=1000, clicks=40, orders=3, roi=3.0)

    def test_trained_updates_stats(self, db, service, retrainer):
        self._setup_trained_data(db, service)
        report = retrainer.retrain_category("家居日用")
        assert "tpl_家居日用_v1" in report["trained"]
        stats = report["trained"]["tpl_家居日用_v1"]
        # avg_roi = (2+4+1+2+3)/5 = 2.4；avg_ctr = 150/5000 = 0.03
        assert stats["avg_roi"] == pytest.approx(2.4)
        assert stats["avg_ctr"] == pytest.approx(0.03)
        assert stats["sample_count"] == 5
        assert report["skipped"] == {}
        assert report["category_memory_updated"] is True
        with db.session() as s:
            tpl = s.get(tables.OptTemplate, "tpl_家居日用_v1")
            assert tpl.stats_json["avg_roi"] == pytest.approx(2.4)
            assert tpl.stats_json["avg_ctr"] == pytest.approx(0.03)
            assert tpl.stats_json["sample_count"] == 5
            assert tpl.params_version == 1  # 只更新统计，不改参数
            mem = s.get(tables.OptCategoryMemory, "家居日用")
            assert mem is not None
            assert mem.template_stats_json["templates"]["tpl_家居日用_v1"]["avg_roi"] == pytest.approx(2.4)

    def test_insufficient_samples_not_updated(self, db, service, retrainer):
        with db.session() as s:
            s.add(tables.OptTemplate(
                template_id="tpl_宠物用品_v1", category="宠物用品",
                template_name="默认三段式", stats_json={"avg_roi": 9.9},
            ))
        _add_variant(db, "p3", 1, template_id="tpl_宠物用品_v1-v1", category="宠物用品")
        _feedback(service, "vv_p3_1", "2026-08-28", exposure=1000, clicks=10, orders=1, roi=1.0)
        _feedback(service, "vv_p3_1", "2026-08-27", exposure=1000, clicks=20, orders=1, roi=2.0)
        report = retrainer.retrain_category("宠物用品")
        assert report["trained"] == {}
        assert report["skipped"]["tpl_宠物用品_v1"]["reason"] == "insufficient_samples"
        assert report["skipped"]["tpl_宠物用品_v1"]["sample_count"] == 2
        assert report["category_memory_updated"] is False
        with db.session() as s:
            tpl = s.get(tables.OptTemplate, "tpl_宠物用品_v1")
            assert tpl.stats_json == {"avg_roi": 9.9}  # 保持原值
            assert s.get(tables.OptCategoryMemory, "宠物用品") is None  # 未创建记忆行

    def test_boundary_exact_min_samples(self, db, service):
        retrainer = TemplateRetrainer(db, policy=RetrainPolicy(min_samples=2))
        with db.session() as s:
            s.add(tables.OptTemplate(
                template_id="tpl_食品_v1", category="食品", template_name="默认三段式",
            ))
        _add_variant(db, "p4", 1, template_id="tpl_食品_v1-v1", category="食品")
        _feedback(service, "vv_p4_1", "2026-08-28", exposure=1000, clicks=10, orders=1, roi=1.0)
        _feedback(service, "vv_p4_1", "2026-08-27", exposure=1000, clicks=20, orders=2, roi=3.0)
        report = retrainer.retrain_category("食品")
        assert "tpl_食品_v1" in report["trained"]
        assert report["trained"]["tpl_食品_v1"]["sample_count"] == 2
        assert report["trained"]["tpl_食品_v1"]["avg_roi"] == pytest.approx(2.0)

    def test_base_template_suffix_strip(self):
        assert base_template_id("tpl_家居日用_v1-v2") == "tpl_家居日用_v1"
        assert base_template_id("tpl_家居日用_v1") == "tpl_家居日用_v1"
        assert base_template_id("tpl_x-v99") == "tpl_x"

    def test_zero_roi_rows_counted(self, db, service, retrainer):
        with db.session() as s:
            s.add(tables.OptTemplate(
                template_id="tpl_服饰_v1", category="服饰", template_name="默认三段式",
            ))
        _add_variant(db, "p5", 1, template_id="tpl_服饰_v1-v1", category="服饰")
        for i in range(5):
            _feedback(service, "vv_p5_1", f"2026-08-{24 + i:02d}",
                      exposure=1000, clicks=10, orders=0, roi=0)
        report = retrainer.retrain_category("服饰")
        stats = report["trained"]["tpl_服饰_v1"]
        assert stats["sample_count"] == 5  # 有曝光无成交也算有效样本
        assert stats["avg_roi"] == 0.0
        assert stats["avg_ctr"] == pytest.approx(0.01)

    def test_retrain_all_multiple_categories(self, db, service, retrainer):
        self._setup_trained_data(db, service)
        with db.session() as s:
            s.add(tables.OptTemplate(
                template_id="tpl_宠物用品_v1", category="宠物用品", template_name="默认三段式",
            ))
        _add_variant(db, "p3", 1, template_id="tpl_宠物用品_v1-v1", category="宠物用品")
        _feedback(service, "vv_p3_1", "2026-08-28", exposure=1000, clicks=10, orders=1, roi=1.0)
        result = retrainer.retrain_all()
        assert result["trained_total"] == 1
        assert result["skipped_total"] == 1
        assert "家居日用" in result["categories"]
        assert "宠物用品" in result["categories"]
        assert result["categories"]["家居日用"]["category_memory_updated"] is True
        assert result["categories"]["宠物用品"]["category_memory_updated"] is False

    def test_best_template_for_category(self, db, service, retrainer):
        with db.session() as s:
            s.add(tables.OptTemplate(
                template_id="tpl_a", category="家居日用", template_name="模板A",
                stats_json={"avg_roi": 2.4},
            ))
            s.add(tables.OptTemplate(
                template_id="tpl_b", category="家居日用", template_name="模板B",
                stats_json={"avg_roi": 1.2},
            ))
        assert retrainer.best_template_for_category("家居日用") == "tpl_a"
        assert retrainer.best_template_for_category("未知类目") is None

    def test_policy_from_env(self, monkeypatch):
        monkeypatch.setenv("M3_AB_RETRAIN_MIN_SAMPLES", "10")
        assert RetrainPolicy.from_env().min_samples == 10
        monkeypatch.setenv("M3_AB_RETRAIN_MIN_SAMPLES", "bad")
        assert RetrainPolicy.from_env().min_samples == 5
        with pytest.raises(ValueError):
            RetrainPolicy(min_samples=0)


# ---------------------------------------------------------------- 6. 卫生

class TestHygiene:
    def test_no_plaintext_keys_in_ab(self):
        here = Path(__file__).resolve().parent.parent / "optimization" / "ab"
        for py in sorted(here.glob("*.py")):
            text = py.read_text(encoding="utf-8")
            assert "sk-" not in text, f"{py.name} 含疑似明文密钥"
            assert "api_key=" not in text.lower().replace("api_key_env", ""), \
                f"{py.name} 含密钥字面量"

    def test_package_reexports(self):
        import optimization.ab as ab_pkg

        for name in (
            # scoring
            "ScoringPolicy", "MaterialScorer", "compute_score", "ctr_of",
            "roi_score", "ctr_score", "diag_score",
            # evaluate
            "EvaluationPolicy", "EvaluationService", "label_for",
            "HIGH_EFFICIENCY", "POTENTIAL", "EXPLORATION", "EVALUATION_VALUES",
            # ranking
            "MaterialRanker", "EVALUATION_ORDER",
            # variants
            "VariantManager", "AB_MIN_VARIANTS", "PARAM_DIFF_FIELDS",
            # retrain
            "RetrainPolicy", "TemplateRetrainer", "base_template_id",
        ):
            assert hasattr(ab_pkg, name), f"包级缺少重导出: {name}"

    def test_ab_module_uses_own_tables_only(self):
        """ab 包只 import optimization.tables（本模块 opt_* 表）。"""
        here = Path(__file__).resolve().parent.parent / "optimization" / "ab"
        for py in here.glob("*.py"):
            text = py.read_text(encoding="utf-8")
            assert "sourcing" not in text, f"{py.name} 引用了其他模块"
            assert "materials" not in text, f"{py.name} 引用了其他模块"
            assert "listing" not in text, f"{py.name} 引用了其他模块"
            assert "ads" not in text, f"{py.name} 引用了其他模块"
