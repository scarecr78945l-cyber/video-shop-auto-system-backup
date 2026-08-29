"""M3 A/B 闭环 · 模板重训练数据驱动链路测试（v1.1-②，总工联调验收）。

验证数据驱动全链路（真实运行时的数据流）：
  M5 投放快照回写（ingest_m5_record 摄取，v1.1-① 已验收）
    → opt_evaluation_feedback 积累
    → TemplateRetrainer.retrain_all（样本闸门 min_samples，有效样本=曝光>0 或成交>0）
    → opt_templates.stats_json / opt_category_memory.template_stats_json 更新
    → best_template_for_category 决策（类目下平均 ROI 最高模板）

运行：python -m pytest tests/test_optimization_retrain_driven.py -q --basetemp=".pytest-tmp-m3"（P-001/P-011）
"""

from __future__ import annotations

import pytest

from optimization import tables
from optimization.ab.ingest import ingest_m5_record
from optimization.ab.retrain import RetrainPolicy, TemplateRetrainer
from optimization.config import load_config
from optimization.db import Database

# 模板/版本种子：家居日用 3 模板（v1 高 ROI、v2 低 ROI、v3 零样本）、宠物用品 1 模板
_TEMPLATES = [
    ("tpl_home_v1", "家居日用", "片头3s"),
    ("tpl_home_v2", "家居日用", "片头5s"),
    ("tpl_home_v3", "家居日用", "片头8s"),   # 零回写 → skipped
    ("tpl_pet_v1", "宠物用品", "宠物模板"),
]

# (variant_id, template_id, product_id, category, variant_no)
# 注意：variant_no 是「同商品 A/B 版本号」，商品内必须唯一（opt_video_variants 唯一约束）
_VARIANTS = [
    ("vv_h1a", "tpl_home_v1", "p_demo_001", "家居日用", 1),
    ("vv_h1b", "tpl_home_v1", "p_demo_001", "家居日用", 2),
    ("vv_h2a", "tpl_home_v2", "p_demo_001", "家居日用", 3),
    ("vv_h2b", "tpl_home_v2", "p_demo_001", "家居日用", 4),
    ("vv_p1a", "tpl_pet_v1", "p_demo_002", "宠物用品", 1),
]

# variant → (spend_cents, gmv_cents)：roi = gmv/spend
_ROI_SEED = {
    "vv_h1a": (1000, 3000),   # roi 3.0
    "vv_h1b": (1000, 2500),   # roi 2.5
    "vv_h2a": (1000, 1200),   # roi 1.2
    "vv_h2b": (1000, 1000),   # roi 1.0
    "vv_p1a": (1000, 2000),   # roi 2.0
}

_DATES = ["2026-08-26", "2026-08-27", "2026-08-28"]


@pytest.fixture
def rt_cfg(tmp_path):
    return load_config(db_url="sqlite:///:memory:", data_dir=tmp_path / "data")


@pytest.fixture
def rt_db(rt_cfg):
    db = Database(rt_cfg)
    db.create_all()
    with db.session() as s:
        for tid, cat, name in _TEMPLATES:
            s.add(tables.OptTemplate(
                template_id=tid, category=cat, template_name=name,
                opening_seconds=3,
            ))
        for vid, tid, pid, cat, no in _VARIANTS:
            s.add(tables.OptVideoVariant(
                variant_id=vid, product_id=pid, source_asset_id="a_src",
                variant_no=no, template_id=tid,
                template_params_snapshot={"category": cat},
                file_path=f"fixtures/{vid}.mp4", spec_ok=1,
                review_status="passed", upload_status="uploaded",
                platform_material_id=f"mat_{vid}", evaluation="exploration",
            ))
    return db


def _ingest_all(db):
    """按种子回写全部版本（每版本 3 个日期，≥ min_samples=3）。"""
    for vid, (spend_cents, gmv_cents) in _ROI_SEED.items():
        for d in _DATES:
            ingest_m5_record(db, {
                "platform_material_id": f"mat_{vid}",
                "report_date": d,
                "impressions": 500,
                "clicks": 40,
                "spend_cents": spend_cents,
                "gmv_cents": gmv_cents,
                "orders": 2,
                "diagnosis": "优秀",
            })


def test_retrain_data_driven_full_chain(rt_cfg, rt_db):
    """主链路：摄取 → retrain_all → stats/类目记忆落库 → best_template 决策。"""
    _ingest_all(rt_db)
    retrainer = TemplateRetrainer(rt_db, policy=RetrainPolicy(min_samples=3))
    report = retrainer.retrain_all()

    assert report["trained_total"] == 3      # home_v1 / home_v2 / pet_v1
    assert report["skipped_total"] == 1      # home_v3 零样本

    # home_v1：avg_roi = (3.0*3 + 2.5*3)/6 = 2.75
    stats_v1 = report["categories"]["家居日用"]["trained"]["tpl_home_v1"]
    assert stats_v1["avg_roi"] == pytest.approx(2.75)
    assert stats_v1["sample_count"] == 6
    # home_v2：avg_roi = (1.2*3 + 1.0*3)/6 = 1.1
    stats_v2 = report["categories"]["家居日用"]["trained"]["tpl_home_v2"]
    assert stats_v2["avg_roi"] == pytest.approx(1.1)
    assert stats_v2["sample_count"] == 6
    # pet_v1
    stats_pet = report["categories"]["宠物用品"]["trained"]["tpl_pet_v1"]
    assert stats_pet["avg_roi"] == pytest.approx(2.0)

    # opt_templates.stats_json 已落库
    with rt_db.session() as s:
        row = s.get(tables.OptTemplate, "tpl_home_v1")
        assert (row.stats_json or {}).get("avg_roi") == pytest.approx(2.75)
        row3 = s.get(tables.OptTemplate, "tpl_home_v3")
        assert not (row3.stats_json or {})      # 零样本不更新

    # 类目记忆 template_stats_json 已落库
    with rt_db.session() as s:
        mem = s.get(tables.OptCategoryMemory, "家居日用")
        assert mem is not None
        assert "tpl_home_v1" in (mem.template_stats_json or {}).get("templates", {})

    # best_template 决策：家居日用 → ROI 最高模板
    assert retrainer.best_template_for_category("家居日用") == "tpl_home_v1"
    assert retrainer.best_template_for_category("宠物用品") == "tpl_pet_v1"


def test_retrain_insufficient_and_empty_day(rt_cfg, rt_db):
    """样本闸门：有效样本 < min_samples 不更新；空日（曝光=0 且成交=0）不计样本。"""
    # 只给 home_v2 的 vv_h2a 喂 1 条有效回写 + 1 条空日回写
    ingest_m5_record(rt_db, {
        "platform_material_id": "mat_vv_h2a", "report_date": "2026-08-28",
        "impressions": 500, "clicks": 30,
        "spend_cents": 1000, "gmv_cents": 1200, "orders": 1, "diagnosis": "良好",
    })
    ingest_m5_record(rt_db, {
        "platform_material_id": "mat_vv_h2a", "report_date": "2026-08-27",
        "impressions": 0, "clicks": 0,
        "spend_cents": 0, "gmv_cents": 0, "orders": 0, "diagnosis": "",
    })  # 空日：不算有效样本

    retrainer = TemplateRetrainer(rt_db, policy=RetrainPolicy(min_samples=3))
    report = retrainer.retrain_all()
    home = report["categories"]["家居日用"]
    # 全部模板样本不足 → skipped（home_v2 有效样本仅 1 < 3；空日未计入）
    assert home["skipped"]["tpl_home_v2"]["sample_count"] == 1
    assert home["skipped"]["tpl_home_v1"]["sample_count"] == 0
    assert report["trained_total"] == 0
    # stats 未更新（保持空）
    with rt_db.session() as s:
        row = s.get(tables.OptTemplate, "tpl_home_v2")
        assert not (row.stats_json or {})
    assert retrainer.best_template_for_category("家居日用") is None
