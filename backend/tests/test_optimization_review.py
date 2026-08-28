"""M3 自动素材优化模块 · 审核闸门（子代理-D · v1.0）测试。

覆盖（全部 fixtures 离线模式，零网络零 API Key）：
1. 规则预审（rules.py）：供应链词/品牌词/广告禁用词 → rejected 且命中词列表正确；
   干净素材 → passed；视频字幕/角标、图片提示词/文件名、文案内容各场景逐字段留痕；
2. 素材评估（evaluate.py）：硬规格全过=优秀、1~2 项软性不足=良好、
   硬规格失败或 ≥3 项不足=待优化，优化项可解释；平台诊断回读 issues 计入软性不足；
3. 人工抽检（manual.py）：sample_rate 确定性哈希生效（0.5 约一半抽中）、
   0/1 边界、高风险类目强制抽中；
4. ReviewGate 编排 + 落库（gate.py）：clean 素材 3 条记录全 pass、
   规则拒绝短路 1 条、评估拒绝短路 2 条、抽中 manual_review、reviewer=system、
   reasons_json 完整、run_batch ≤50/批；
5. 无明文密钥；包级重导出完整。

运行：cd backend && python -m pytest tests/test_optimization_review.py -q --basetemp=".pytest-tmp-m3"
（P-011：独立 basetemp，禁止共用 .pytest-tmp）
"""

from __future__ import annotations

from pathlib import Path

import pytest

from optimization.config import ReviewSpec, load_config
from optimization.db import Database
from optimization.review import (
    FINAL_MANUAL_REVIEW,
    FINAL_PASSED,
    FINAL_REJECTED,
    MAX_BATCH_SIZE,
    ManualSampler,
    MaterialEvaluator,
    MaterialRules,
    ReviewGate,
    ReviewRecordRepo,
    evaluate_material,
    run_rule_precheck,
    should_manual_review,
)

GOOD_CONTENT = "甄选陶瓷材质，容量350ml，日常更安心。"
BAD_CONTENT = "厂家直发一件代发，超值好物，快来看看！"


def _clean_video(target_id: str = "v_001", **overrides) -> dict:
    """合规 + 硬规格全过 + 质量分高的视频素材（评估=优秀，人工按配置抽检）。"""
    material = {
        "target_type": "video",
        "content": GOOD_CONTENT,
        "subtitles": [GOOD_CONTENT],
        "badges": ["精选好物"],
        "resolution": "720x1280",
        "ratio": "9:16",
        "duration": 30.0,
        "size_mb": 100.0,
        "file_path": f"data/video_variants/{target_id}.mp4",
        "quality_score": 85,
    }
    material.update(overrides)
    return material


def _clean_copy(target_id: str = "c_001", **overrides) -> dict:
    material = {
        "target_type": "copywrite",
        "copy_type": "title",
        "content": "甄选陶瓷马克杯 简约耐用 350ml",
        "char_len": 16,
        "quality_score": 80,
    }
    material.update(overrides)
    return material


def _clean_image(target_id: str = "img_001", **overrides) -> dict:
    material = {
        "target_type": "image",
        "image_type": "main",
        "prompts": ["白色背景下的陶瓷马克杯特写"],
        "file_path": f"data/images/{target_id}.png",
        "width": 800,
        "height": 800,
        "quality_score": 90,
    }
    material.update(overrides)
    return material


# ---------------------------------------------------------------- fixtures


@pytest.fixture
def cfg(tmp_path):
    """内存库 + 临时 data_dir；sample_rate=0 默认不抽检（单测按需覆盖）。"""
    return load_config(
        db_url="sqlite:///:memory:",
        fixtures_dir=tmp_path / "fixtures",
        data_dir=tmp_path / "data",
        review=ReviewSpec(sample_rate=0.0, high_risk_categories=()),
    )


@pytest.fixture
def db(cfg):
    database = Database(cfg)
    database.create_all()
    return database


@pytest.fixture
def gate(cfg, db) -> ReviewGate:
    return ReviewGate(config=cfg, db=db)


# ---------------------------------------------------------------- 规则预审

class TestRules:
    def test_clean_copywrite_passed(self):
        r = run_rule_precheck(_clean_copy(), "copywrite")
        assert r["passed"] is True
        assert r["result"] == "pass"
        assert r["hits"] == []
        assert r["fields"] == {}
        assert "copywrite:内容合规" in r["rules"]
        assert "compliance.check_text" in r["rules"]

    def test_supply_chain_rejected_with_hits(self):
        r = run_rule_precheck({"target_type": "copywrite", "content": BAD_CONTENT}, "copywrite")
        assert r["passed"] is False
        assert r["result"] == "reject"
        assert any("厂家" in h for h in r["hits"])
        assert any("一件代发" in h for h in r["hits"])
        assert r["fields"]["content"] == r["hits"]          # 字段级命中与扁平一致

    def test_brand_word_rejected(self):
        r = run_rule_precheck({"target_type": "copywrite", "content": "耐克同款跑鞋"}, "copywrite")
        assert r["passed"] is False
        assert any("耐克" in h for h in r["hits"])           # 品牌词
        assert any("同款" in h for h in r["hits"])           # 广告禁用词

    def test_ad_badge_forbidden_rejected(self):
        r = run_rule_precheck({"target_type": "copywrite", "content": "官方旗舰店直营好物"}, "copywrite")
        assert r["passed"] is False
        assert any("官方" in h for h in r["hits"])

    def test_effcacy_word_rejected(self):
        r = run_rule_precheck({"target_type": "copywrite", "content": "使用后美白祛斑效果显著"}, "copywrite")
        assert r["passed"] is False
        assert any("美白" in h for h in r["hits"])           # 功效词（缺资质）

    def test_video_subtitle_compliance(self):
        material = _clean_video(subtitles=["厂家直发陶瓷杯，源头好货"])
        r = run_rule_precheck(material, "video")
        assert r["passed"] is False
        assert any("厂家" in h for h in r["hits"])
        assert "subtitle[0]" in r["fields"]
        assert r["rules"] == ["compliance.check_text", "video:字幕/角标文本合规"]

    def test_video_badge_compliance(self):
        material = _clean_video(badges=["官方旗舰"])
        r = run_rule_precheck(material, "video")
        assert r["passed"] is False
        assert any("官方" in h for h in r["hits"])
        assert "badge[0]" in r["fields"]

    def test_image_prompt_compliance(self):
        material = _clean_image(prompts=["1688 源头工厂直供好物"])
        r = run_rule_precheck(material, "image")
        assert r["passed"] is False
        assert any("1688" in h for h in r["hits"])
        assert "prompt[0]" in r["fields"]
        assert r["rules"] == ["compliance.check_text", "image:提示词与文件名合规"]

    def test_image_filename_compliance(self):
        material = _clean_image(file_path="data/images/nike_shoes.png")
        r = run_rule_precheck(material, "image")
        assert r["passed"] is False
        assert any("nike" in h for h in r["hits"])           # 品牌词出现在文件名
        assert "file_name" in r["fields"]

    def test_hits_flattened_dedupe(self):
        material = _clean_video(
            subtitles=["厂家直发"], badges=["厂家直发"],
        )
        r = run_rule_precheck(material, "video")
        assert r["passed"] is False
        assert len(r["hits"]) == len(set(r["hits"]))         # 扁平去重
        assert set(r["fields"].keys()) == {"subtitle[0]", "badge[0]"}

    def test_no_text_fields_passed(self):
        r = run_rule_precheck({"target_type": "video"}, "video")
        assert r["passed"] is True
        assert r["texts_checked"] == 0

    def test_target_type_override_wins(self):
        # 显式 target_type 优先于 material 自带键
        material = _clean_copy()
        material["target_type"] = "video"                     # 材料自标错误类型
        r = run_rule_precheck(material, "copywrite")
        assert r["target_type"] == "copywrite"

    def test_rule_verdict_consistent_with_gate(self, gate):
        r = gate.run("copywrite", "c_bad", {"target_type": "copywrite", "content": BAD_CONTENT}, "家居日用")
        assert r["final"]["result"] == FINAL_REJECTED
        assert r["final"]["stage"] == "rule"
        assert r["rule"]["passed"] is False
        assert any("厂家" in h for h in r["rule"]["hits"])


# ---------------------------------------------------------------- 素材评估

class TestEvaluate:
    def _ev(self, material, diagnosis=None):
        return evaluate_material(material, diagnosis)

    def test_video_hard_all_pass_excellent(self):
        ev = self._ev(_clean_video())
        assert ev["verdict"] == "excellent"
        assert ev["label"] == "优秀"
        assert ev["passed"] is True
        assert ev["result"] == "pass"
        assert ev["hard_failures"] == [] and ev["soft_issues"] == []
        assert ev["optimization_items"] == []

    def test_video_quality_soft_good(self):
        ev = self._ev(_clean_video(quality_score=50))
        assert ev["verdict"] == "good"
        assert ev["label"] == "良好"
        assert ev["passed"] is True
        assert [s["field"] for s in ev["soft_issues"]] == ["quality"]
        assert "质量分" in ev["optimization_items"][0]

    def test_video_hard_fail_resolution_needs_optimization(self):
        ev = self._ev(_clean_video(resolution="480x640", ratio="3:4"))
        assert ev["verdict"] == "needs_optimization"
        assert ev["label"] == "待优化"
        assert ev["passed"] is False
        assert ev["result"] == "reject"
        fields = {f["field"] for f in ev["hard_failures"]}
        assert "resolution" in fields and "ratio" in fields
        assert any("分辨率不足" in it for it in ev["optimization_items"])

    def test_video_duration_out_of_range(self):
        ev = self._ev(_clean_video(duration=400.0))
        assert ev["verdict"] == "needs_optimization"
        assert any(f["field"] == "duration" for f in ev["hard_failures"])

    def test_video_size_over_limit(self):
        ev = self._ev(_clean_video(size_mb=700.0))
        assert ev["verdict"] == "needs_optimization"
        assert any(f["field"] == "size" for f in ev["hard_failures"])
        assert any("500" in it for it in ev["optimization_items"])

    def test_video_format_not_allowed(self):
        ev = self._ev(_clean_video(file_path="data/v.avi", format="avi"))
        assert ev["verdict"] == "needs_optimization"
        assert any(f["field"] == "format" for f in ev["hard_failures"])

    def test_soft_three_issues_needs_optimization(self):
        material = _clean_video(quality_score=50)
        diagnosis = {"issues": ["画面抖动明显", "字幕可读性差"]}
        ev = self._ev(material, diagnosis)
        assert ev["verdict"] == "needs_optimization"          # 1 quality + 2 platform = 3 软性
        assert ev["passed"] is False
        assert len(ev["soft_issues"]) == 3

    def test_platform_diagnosis_two_issues_good(self):
        material = _clean_video(quality_score=70)             # 质量分合格
        diagnosis = {"issues": ["画面抖动明显", "字幕可读性差"]}
        ev = self._ev(material, diagnosis)
        assert ev["verdict"] == "good"                        # 2 项软性不足
        assert ev["passed"] is True
        assert [s["field"] for s in ev["soft_issues"]] == ["platform", "platform"]
        assert any("画面抖动" in it for it in ev["optimization_items"])

    def test_platform_diagnosis_dict_issues(self):
        diagnosis = {"suggestions": {"清晰度": "建议提高分辨率"}}
        ev = self._ev(_clean_video(quality_score=80), diagnosis)
        assert ev["verdict"] == "good"
        assert any("清晰度" in it for it in ev["optimization_items"])

    def test_image_main_ok_excellent(self):
        ev = self._ev(_clean_image())
        assert ev["verdict"] == "excellent"

    def test_image_main_ratio_fail(self):
        ev = self._ev(_clean_image(width=800, height=1000))
        assert ev["verdict"] == "needs_optimization"
        assert any(f["field"] == "ratio" for f in ev["hard_failures"])

    def test_image_detail_min_edge(self):
        ev = self._ev(_clean_image(image_type="detail", width=600, height=800))
        assert ev["verdict"] == "needs_optimization"
        assert any(f["field"] == "resolution" for f in ev["hard_failures"])  # 600 < 750

    def test_copywrite_title_range_ok(self):
        ev = self._ev(_clean_copy())
        assert ev["verdict"] == "excellent"

    def test_copywrite_title_too_short(self):
        ev = self._ev(_clean_copy(content="短标题", char_len=3))
        assert ev["verdict"] == "needs_optimization"
        assert any(f["field"] == "title_len" for f in ev["hard_failures"])

    def test_copywrite_empty_content(self):
        ev = self._ev(_clean_copy(content="", char_len=0))
        assert ev["verdict"] == "needs_optimization"
        assert any(f["field"] == "content" for f in ev["hard_failures"])


# ---------------------------------------------------------------- 人工抽检

class TestManual:
    def test_sample_rate_zero_none(self, cfg):
        s = ManualSampler(cfg, sample_rate=0.0)
        assert all(not s.should_manual(f"m_{i}", "") for i in range(50))

    def test_sample_rate_one_all(self, cfg):
        s = ManualSampler(cfg, sample_rate=1.0)
        assert all(s.should_manual(f"m_{i}", "") for i in range(50))

    def test_half_ratio_approximate(self, cfg):
        s = ManualSampler(cfg, sample_rate=0.5)
        sampled = [i for i in range(200) if s.should_manual(f"m_{i:03d}", "")]
        assert 60 <= len(sampled) <= 140                     # 期望 ≈100，宽裕区间防抖动

    def test_low_rate_ratio(self, cfg):
        s = ManualSampler(cfg, sample_rate=0.1)
        sampled = [i for i in range(1000) if s.should_manual(f"id_{i}", "")]
        assert 40 <= len(sampled) <= 160                     # 期望 ≈100

    def test_deterministic(self, cfg):
        s = ManualSampler(cfg, sample_rate=0.5)
        assert s.should_manual("m_007", "") == s.should_manual("m_007", "")

    def test_high_risk_forced_even_zero_rate(self, cfg):
        s = ManualSampler(cfg, sample_rate=0.0, high_risk_categories=["美妆", "保健"])
        assert s.should_manual("m_001", "美妆") is True
        assert s.should_manual("m_002", "保健") is True

    def test_high_risk_not_matching_not_forced(self, cfg):
        s = ManualSampler(cfg, sample_rate=0.0, high_risk_categories=["美妆"])
        assert s.should_manual("m_001", "家居日用") is False

    def test_high_risk_config_injection(self, cfg):
        s = ManualSampler(cfg, sample_rate=0.0)
        assert not s.should_manual("m_001", "美妆")          # 配置未注入 → 不强制
        s2 = ManualSampler(cfg, high_risk_categories=("美妆",))
        assert s2.should_manual("m_001", "美妆") is True

    def test_invalid_rate_raises(self, cfg):
        with pytest.raises(ValueError):
            ManualSampler(cfg, sample_rate=1.5)

    def test_module_entry_matches(self, cfg):
        cfg_half = load_config(
            db_url=cfg.db_url, data_dir=cfg.data_dir, fixtures_dir=cfg.fixtures_dir,
            review=ReviewSpec(sample_rate=0.5),
        )
        s = ManualSampler(cfg_half)
        assert should_manual_review("m_007", "", cfg_half) == s.should_manual("m_007", "")


# ---------------------------------------------------------------- ReviewGate 编排 + 落库

class TestGate:
    def test_clean_material_passed_three_records(self, gate):
        out = gate.run("video", "v_001", _clean_video("v_001"), "家居日用")
        assert out["final"]["result"] == FINAL_PASSED
        assert out["final"]["stage"] == "manual"
        assert out["rule"]["passed"] is True
        assert out["evaluate"]["verdict"] == "excellent"
        assert out["manual"]["sampled"] is False

        records = ReviewRecordRepo(gate.db).list_by_target("video", "v_001")
        assert [r["gate_type"] for r in records] == ["rule", "evaluate", "manual"]
        assert [r["result"] for r in records] == ["pass", "pass", "pass"]
        assert all(r["reviewer"] == "system" for r in records)

    def test_rule_reject_short_circuit(self, gate):
        out = gate.run(
            "copywrite", "c_bad",
            {"target_type": "copywrite", "content": BAD_CONTENT}, "家居日用",
        )
        assert out["final"]["result"] == FINAL_REJECTED
        assert out["final"]["stage"] == "rule"
        assert out["evaluate"] is None and out["manual"] is None
        records = ReviewRecordRepo(gate.db).list_by_target("copywrite", "c_bad")
        assert len(records) == 1                             # 仅规则记录
        assert records[0]["gate_type"] == "rule"
        assert records[0]["result"] == "reject"
        assert any("厂家" in h for h in records[0]["reasons_json"]["hits"])

    def test_evaluate_reject_short_circuit(self, gate):
        material = _clean_video("v_bad", resolution="480x640", ratio="3:4")
        out = gate.run("video", "v_bad", material, "家居日用")
        assert out["final"]["result"] == FINAL_REJECTED
        assert out["final"]["stage"] == "evaluate"
        assert out["rule"]["passed"] is True
        assert out["evaluate"]["passed"] is False
        assert out["manual"] is None
        records = ReviewRecordRepo(gate.db).list_by_target("video", "v_bad")
        assert [r["gate_type"] for r in records] == ["rule", "evaluate"]
        assert records[1]["result"] == "reject"
        assert records[1]["reasons_json"]["verdict"] == "needs_optimization"
        assert any("分辨率不足" in it for it in records[1]["reasons_json"]["optimization_items"])

    def test_manual_sampled_manual_review(self, cfg, db):
        g = ReviewGate(config=cfg, db=db, sampler=ManualSampler(cfg, sample_rate=1.0))
        out = g.run("video", "v_sampled", _clean_video("v_sampled"), "家居日用")
        assert out["final"]["result"] == FINAL_MANUAL_REVIEW
        assert out["final"]["stage"] == "manual"
        assert out["manual"]["sampled"] is True
        records = ReviewRecordRepo(db).list_by_target("video", "v_sampled")
        assert len(records) == 3
        assert records[2]["gate_type"] == "manual"
        assert records[2]["result"] == FINAL_MANUAL_REVIEW
        assert records[2]["reasons_json"]["sampled"] is True
        assert records[2]["reasons_json"]["sample_rate"] == 1.0

    def test_high_risk_category_forced_manual(self, cfg, db):
        g = ReviewGate(
            config=cfg, db=db,
            sampler=ManualSampler(cfg, sample_rate=0.0, high_risk_categories=("美妆",)),
        )
        out = g.run("video", "v_h", _clean_video("v_h"), "美妆")
        assert out["final"]["result"] == FINAL_MANUAL_REVIEW
        assert out["manual"]["high_risk"] is True

    def test_reasons_json_complete(self, gate):
        gate.run("copywrite", "c_ok", _clean_copy("c_ok"), "家居日用")
        records = ReviewRecordRepo(gate.db).list_by_target("copywrite", "c_ok")
        rule_rec = next(r for r in records if r["gate_type"] == "rule")
        ev_rec = next(r for r in records if r["gate_type"] == "evaluate")
        manual_rec = next(r for r in records if r["gate_type"] == "manual")
        assert rule_rec["reasons_json"]["passed"] is True
        assert rule_rec["reasons_json"]["hits"] == []
        assert ev_rec["reasons_json"]["verdict"] == "excellent"
        assert ev_rec["reasons_json"]["optimization_items"] == []
        assert manual_rec["reasons_json"]["sampled"] is False
        assert manual_rec["reasons_json"]["category"] == "家居日用"

    def test_run_batch_two(self, gate):
        items = [
            {"target_type": "video", "target_id": "b1", "material": _clean_video("b1"), "category": "家居日用"},
            {"target_type": "image", "target_id": "b2", "material": _clean_image("b2"), "category": "家居日用"},
        ]
        outs = gate.run_batch(items)
        assert len(outs) == 2
        assert all(o["final"]["result"] == FINAL_PASSED for o in outs)
        repo = ReviewRecordRepo(gate.db)
        assert len(repo.list_by_target("video", "b1")) == 3
        assert len(repo.list_by_target("image", "b2")) == 3

    def test_run_batch_over_50_raises(self, gate):
        items = [
            {"target_type": "video", "target_id": f"i{i}", "material": _clean_video(f"i{i}")}
            for i in range(MAX_BATCH_SIZE + 1)
        ]
        with pytest.raises(ValueError):
            gate.run_batch(items)

    def test_run_batch_exactly_50_ok(self, gate):
        items = [
            {"target_type": "copywrite", "target_id": f"i{i}", "material": _clean_copy(f"i{i}")}
            for i in range(MAX_BATCH_SIZE)
        ]
        outs = gate.run_batch(items)
        assert len(outs) == MAX_BATCH_SIZE

    def test_gate_default_db_in_memory(self):
        """不传 db → 内存库，绝不触碰本模块真实 m3-optimization.db。"""
        g = ReviewGate()
        out = g.run("video", "v_mem", _clean_video("v_mem"), "家居日用")
        assert out["final"]["result"] == FINAL_PASSED
        assert len(ReviewRecordRepo(g.db).list_by_target("video", "v_mem")) == 3

    def test_platform_diagnosis_through_gate(self, gate):
        material = _clean_video("v_diag", quality_score=70)
        material["platform_diagnosis"] = {"issues": ["画面抖动明显"]}
        out = gate.run("video", "v_diag", material, "家居日用")
        assert out["evaluate"]["verdict"] == "good"          # 1 项平台软性 → 良好
        records = ReviewRecordRepo(gate.db).list_by_target("video", "v_diag")
        ev = next(r for r in records if r["gate_type"] == "evaluate")
        assert ev["reasons_json"]["verdict"] == "good"
        assert any("画面抖动" in it for it in ev["reasons_json"]["optimization_items"])


# ---------------------------------------------------------------- 无明文密钥 / 包级重导出

class TestHygiene:
    def test_no_plaintext_keys_in_modules(self):
        here = Path(__file__).resolve().parent.parent / "optimization" / "review"
        for py in sorted(here.glob("*.py")):
            text = py.read_text(encoding="utf-8")
            assert "sk-" not in text, f"{py.name} 含疑似明文密钥"
            assert "api_key=" not in text.lower().replace("api_key_env", ""), f"{py.name} 含密钥字面量"

    def test_package_reexports(self):
        import optimization.review as review_pkg

        for name in (
            "MaterialRules", "run_rule_precheck",
            "MaterialEvaluator", "evaluate_material",
            "VERDICT_EXCELLENT", "VERDICT_GOOD", "VERDICT_NEEDS_OPTIMIZATION",
            "ManualSampler", "should_manual_review",
            "ReviewGate", "ReviewRecordRepo", "MAX_BATCH_SIZE",
            "FINAL_PASSED", "FINAL_REJECTED", "FINAL_MANUAL_REVIEW",
        ):
            assert hasattr(review_pkg, name), f"包级缺少重导出: {name}"
        assert review_pkg.ReviewGate is ReviewGate

    def test_skeleton_untouched(self):
        """公共骨架只读：本测试只验证 review 包存在，不验证骨架内容（防误改）。"""
        import optimization
        from optimization import compliance, config, db, models, repo, tables

        assert optimization.__version__ == "0.1.0"
        for mod in (compliance, config, db, models, repo, tables):
            assert mod is not None
