"""M3 自动素材优化 · 端到端集成测试（v1.0-4，总工集成验收）。

全链路（fixtures 离线、零网络、零 API Key、零真实 ffmpeg）：
  原始素材 + 商品信息
    → ① 文案管线（标题/口播稿/投放文案/角标，无 Key 规则降级）
    → ② 视频二创（composer.run_pipeline，MockFFmpegRunner，≥2 版落 opt_video_variants）
    → ③ 审核闸门（ReviewGate：规则预审 + 素材评估 + 人工抽检 0%）
    → ④ A/B 闭环（EvaluationService 回写 + MaterialRanker 排序）
    → ⑤ 上传素材库（create_uploader("api") mock 上传拿 platform_material_id）
运行：python -m pytest tests/test_optimization_e2e.py -q --basetemp=".pytest-tmp-m3"（P-001/P-011）
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from sqlalchemy import func, select

from optimization.ab.evaluate import EvaluationService
from optimization.ab.ranking import EVALUATION_ORDER, MaterialRanker
from optimization.config import load_config
from optimization.copywriting.ads import generate_ads, generate_badges
from optimization.copywriting.cleaner import clean_title
from optimization.copywriting.script import generate_script
from optimization.db import Database
from optimization.review.gate import ReviewGate
from optimization.review.manual import ManualSampler
from optimization.upload.factory import create_uploader
from optimization.video.composer import run_pipeline
from optimization.video.ffmpeg import MockFFmpegRunner

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures" / "optimization"


def _load(name: str) -> dict:
    with open(FIXTURES / name, encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture
def e2e_cfg(tmp_path):
    return load_config(
        db_url="sqlite:///:memory:",
        data_dir=tmp_path / "data",
        fixtures_dir=FIXTURES,
    )


@pytest.fixture
def e2e_db(e2e_cfg):
    db = Database(e2e_cfg)
    db.create_all()
    return db


def test_end_to_end_pipeline(e2e_cfg, e2e_db, tmp_path):
    product = _load("product_fixture.json")
    asset = _load("source_asset_fixture.json")
    product_id = product["product_id"]
    category = product["category"]

    # ---------- ① 文案管线（无 Key 规则降级） ----------
    title = clean_title(product["taobao_original_title"])
    assert title.ok, title.reasons
    assert e2e_cfg.copywriting.title_min_chars <= title.char_len <= e2e_cfg.copywriting.title_max_chars
    script = generate_script(product_id, category, product["sku_spec_json"], e2e_cfg)
    ads = generate_ads(product_id, category, product["sku_spec_json"], e2e_cfg)
    badges = generate_badges(product_id, category, product["sku_spec_json"], e2e_cfg)
    assert script.passed, script.compliance_hits
    assert len(ads) >= e2e_cfg.copywriting.ad_variants_min
    assert len(badges) >= e2e_cfg.copywriting.badge_variants_min
    assert all(d.passed for d in ads + badges)

    # ---------- ② 视频二创（Mock 出片，≥2 版落库） ----------
    # runner 缺省：detect_ffmpeg() 未就绪 → composer 自动用带 probe_from_asset 预设的 MockFFmpegRunner
    result = run_pipeline(
        asset, product, variants=2,
        config=e2e_cfg, db=e2e_db,
    )
    variants = result["variants"]
    assert len(variants) >= 2, "同一商品必须产出 ≥2 版素材（A/B）"
    for row in variants:
        assert row["variant_no"] >= 1
        assert row["spec_ok"], row.get("spec_check_json")
        assert row["review_status"] == "pending"
        assert row["evaluation"] == "exploration"
    variant_ids = [r["variant_id"] for r in variants]

    # ---------- ③ 审核闸门（规则/评估/抽检 0%，干净素材全过） ----------
    gate = ReviewGate(
        e2e_cfg, db=e2e_db, sampler=ManualSampler(e2e_cfg, sample_rate=0.0)
    )
    for row in variants:
        material = {
            "subtitles": ["品质好物，安心选购。"],
            "badges": ["精选好物"],
            "voiceover": "",
            "content": title.title,
            # 素材规格元数据（供评估闸门硬规格校验，取自原始素材契约）
            "resolution": asset["resolution"],   # 720x1280
            "duration": asset["duration"],        # 18.5s
            "size_mb": asset["size_mb"],          # 12.3MB
            "format": "mp4",
            "quality": 90,
        }
        verdict = gate.run("video", row["variant_id"], material, category)
        assert verdict["final"]["result"] == "passed", verdict
        assert verdict["final"]["stage"] == "manual"

    # ---------- ④ A/B 闭环（回写 + 排序） ----------
    ev = EvaluationService(e2e_db)
    ev.record_metrics(
        variant_ids[0], "2026-08-28",
        exposure=1000, clicks=120, spend=50.0, orders=10, roi=2.5,
        diagnosis={"score": 90},
    )
    # v2 无回写 → exploration 排最后
    ranker = MaterialRanker(e2e_db)
    ranked = ranker.rank_for_product(product_id)
    assert len(ranked) == len(variant_ids)
    order_vals = [EVALUATION_ORDER[it[2]] for it in ranked]
    assert order_vals == sorted(order_vals), f"排序必须 高效>潜力>探索期：{ranked}"
    assert ranked[-1][2] == "exploration"
    assert ranked[-1][0] == variant_ids[1]
    assert ranked[0][2] in ("high_efficiency", "potential")

    # ---------- ⑤ 上传素材库（api mock 拿 platform_material_id） ----------
    demo_file = tmp_path / "demo_video.mp4"
    demo_file.write_bytes(b"fake-video-bytes-for-mock-upload")
    uploader = create_uploader("api", config=e2e_cfg, db=e2e_db)
    from optimization.repo import VideoVariantRepo

    variant_repo = VideoVariantRepo(e2e_db)
    for row in variants:
        up = uploader.upload_video(
            str(demo_file),
            {"product_id": product_id, "duration": asset["duration"]},
            target_id=row["variant_id"], batch_no=1,
        )
        assert up.status == "success", up
        assert up.platform_material_id, up
        # 集成闭环：上传成功 → 回填 variant.platform_material_id（供 A/B 排序 only_uploaded 消费）
        assert variant_repo.update_platform_material_id(
            row["variant_id"], up.platform_material_id
        ), f"回填失败：{row['variant_id']}"
    # opt_upload_records 落库（≤50/批语义由 upload_batch 覆盖，此处验证单条落库）
    from optimization import tables

    with e2e_db.session() as s:
        cnt = s.execute(select(func.count()).select_from(tables.OptUploadRecord)).scalar()
    assert cnt == len(variants), f"上传记录应为 {len(variants)} 条，实际 {cnt}"

    # ---------- 收尾断言：A/B 与上传联动（已上传素材可被 M5 选择） ----------
    ranked_uploaded = ranker.rank_for_product(product_id, only_uploaded=True)
    assert len(ranked_uploaded) == len(variants)
    assert all(it[1] for it in ranked_uploaded), "已上传素材必须带 platform_material_id"


def test_e2e_reject_path(e2e_cfg, e2e_db):
    """端到端拒绝路径：含供应链词的文案 → 审核闸门 rejected（不进入 A/B 与上传）。"""
    product = _load("product_fixture_pet.json")  # 宠物用品：含厂家直发/一件代发脏词
    asset = _load("source_asset_fixture.json")
    result = run_pipeline(
        asset, product, variants=2,
        config=e2e_cfg, db=e2e_db,
    )
    gate = ReviewGate(e2e_cfg, db=e2e_db, sampler=ManualSampler(e2e_cfg, sample_rate=0.0))
    rejected = 0
    for row in result["variants"]:
        material = {
            "subtitles": ["厂家直发，一件代发，源头好货"],  # 供应链词必拒
            "badges": ["精选好物"],
            "voiceover": "",
            "content": "",
        }
        verdict = gate.run("video", row["variant_id"], material, category=product["category"])
        if verdict["final"]["result"] == "rejected":
            rejected += 1
    assert rejected >= 1, "含供应链词的素材必须被审核闸门拦截"
