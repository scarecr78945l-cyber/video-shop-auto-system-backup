"""M3 ↔ M5 跨模块联调契约测试（v1.1-①，总工联调验收）。

验证 M5 投放快照回写（ad_report_snapshots 口径，经 data-audit 数据联动）经
``ab.ingest.ingest_m5_record/batch`` 消费后，评估标签/评分/排序/幂等全链路正确。

契约要点（对齐 M5 context 数据字典 + DA-001）：
- 金额「分」int（spend_cents/gmv_cents）→ M3 侧换算元与 ROI；
- diagnosis 中文枚举（优秀/良好/1项待优化/N项待优化）→ ab.scoring 兼容；
- platform_material_id → opt_video_variants 反查；unmatched 不落库（失败隔离）；
- 幂等键 (variant_id, report_date)。

运行：python -m pytest tests/test_optimization_m5_integration.py -q --basetemp=".pytest-tmp-m3"（P-001/P-011）
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from sqlalchemy import func, select

from optimization.ab.evaluate import EvaluationService
from optimization.ab.ingest import ingest_m5_batch, ingest_m5_record
from optimization.ab.ranking import MaterialRanker
from optimization.config import load_config
from optimization.db import Database
from optimization.repo import VideoVariantRepo
from optimization.video.composer import run_pipeline

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures" / "optimization"


def _load(name: str) -> dict:
    with open(FIXTURES / name, encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture
def m5_cfg(tmp_path):
    return load_config(
        db_url="sqlite:///:memory:",
        data_dir=tmp_path / "data",
        fixtures_dir=FIXTURES,
    )


@pytest.fixture
def m5_db(m5_cfg):
    db = Database(m5_cfg)
    db.create_all()
    return db


@pytest.fixture
def uploaded_variants(m5_cfg, m5_db):
    """两个已上传（有 platform_material_id）的 A/B 版本，供回写反查。"""
    product = _load("product_fixture.json")
    asset = _load("source_asset_fixture.json")
    result = run_pipeline(asset, product, variants=2, config=m5_cfg, db=m5_db)
    assert len(result["variants"]) >= 2
    vrepo = VideoVariantRepo(m5_db)
    ids = [row["variant_id"] for row in result["variants"]]
    for i, vid in enumerate(ids):
        assert vrepo.update_platform_material_id(vid, f"material_{i + 1:04d}")
    return ids


def _record(material_id: str, **overrides) -> dict:
    rec = {
        "platform_material_id": material_id,
        "report_date": "2026-08-28",
        "impressions": 1000,
        "clicks": 120,
        "spend_cents": 5000,      # 50.00 元
        "gmv_cents": 12500,       # 125.00 元 → roi = 2.5
        "orders": 8,
        "diagnosis": "优秀",       # M5 中文枚举
    }
    rec.update(overrides)
    return rec


def test_ingest_single_record(m5_db, uploaded_variants):
    """单条回写：金额分直存（DA-001）、roi 计算、M5 中文诊断兼容、落库正确。"""
    ok, fid = ingest_m5_record(m5_db, _record("material_0001"))
    assert ok, fid
    service = EvaluationService(m5_db)
    latest = service.latest(uploaded_variants[0])
    assert latest is not None
    assert latest["spend"] == pytest.approx(5000.0)  # 5000 分（DA-001 金额单位=分 int）
    assert latest["roi"] == pytest.approx(2.5)       # gmv/spend = 12500/5000
    assert latest["evaluation"] == "efficient"        # roi 2.5 ≥ 2.0（M2/M5 共口径）
    assert latest["exposure"] == 1000


def test_ingest_unmatched_isolated(m5_db, uploaded_variants):
    """未知 platform_material_id → 不落库、返回 unmatched（失败隔离）。"""
    ok, info = ingest_m5_record(m5_db, _record("material_not_exist"))
    assert not ok
    assert "unmatched" in info
    # 批次失败隔离：3 条（1 条 unknown）→ ingested=2
    records = [
        _record("material_0001", report_date="2026-08-28"),
        _record("material_0002", report_date="2026-08-28"),
        _record("material_9999", report_date="2026-08-28"),
    ]
    result = ingest_m5_batch(m5_db, records)
    assert result["ingested"] == 2
    assert len(result["unmatched"]) == 1


def test_ingest_idempotent(m5_db, uploaded_variants):
    """幂等：同 (variant_id, report_date) 重复回写不新增行。"""
    from optimization import tables

    rec = _record("material_0001")
    ingest_m5_record(m5_db, rec)
    ingest_m5_record(m5_db, rec)   # 同日重复回写
    ingest_m5_record(m5_db, rec)
    with m5_db.session() as s:
        cnt = s.execute(select(func.count()).select_from(tables.OptEvaluationFeedback)).scalar()
    assert cnt == 1, f"幂等键 (variant_id, report_date) 应只保留 1 行，实际 {cnt}"


def test_ranking_consumes_ingested(m5_db, uploaded_variants):
    """摄取后排序消费：only_uploaded 可见、高效 > 探索期。"""
    ingest_m5_record(m5_db, _record("material_0001"))            # 高效（roi 2.5）
    ingest_m5_record(m5_db, _record("material_0002", impressions=0, clicks=0,
                                    spend_cents=0, gmv_cents=0, orders=0))  # 无数据 → 探索期
    ranker = MaterialRanker(m5_db)
    ranked = ranker.rank_for_product("p_demo_001", only_uploaded=True)
    assert len(ranked) == 2
    assert ranked[0][2] == "efficient"   # 高效排前（M2/M5 共口径）
    assert ranked[0][1] == "material_0001"
    assert ranked[1][2] == "exploring"


def test_diagnosis_chinese_variants(m5_db, uploaded_variants):
    """M5 中文诊断枚举全兼容：优秀/良好/1项待优化/N项待优化。"""
    from optimization.ab.scoring import diag_score

    assert diag_score("优秀") == pytest.approx(1.0)
    assert diag_score("良好") == pytest.approx(0.7)
    assert diag_score("1项待优化") == pytest.approx(0.4)
    assert diag_score("N项待优化") == pytest.approx(0.2)
    assert diag_score("") == 0.0
