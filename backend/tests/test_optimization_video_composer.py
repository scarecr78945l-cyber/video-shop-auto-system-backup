"""M3 视频二创流水线 · 编排层（子代理-C2 · v0.3）测试。

覆盖（全部 fixtures 离线模式：autouse 删除 DEEPSEEK_API_KEY，零网络）：
1. 拆解降级（BreakdownGenerator）：无 Key → rule_fallback，仅按 sku_spec_json 真实字段
   切分要点且必过 compliance 预审；LLM 成功 / LLM 命中合规剔除 / 全命中回落规则；
2. 模板三段式（TemplatePlanner/plan_segments）：片头/中段/片尾结构 + 配置化参数
   （默认值取模板参数配置：opening_seconds/subtitle_style/badge_position/bgm_loudness/
   cut_count/params_version）+ 类目微调 + overrides；
3. composer 全链路 fixtures（原始素材 + 文案 → ≥2 版本落库，MockFFmpegRunner）：
   variant 记录完整（product_id/source_asset_id/variant_no/template_params_snapshot/
   spec_check_json/compliance_json/evaluation），v1/v2 片头/文案/节奏差异化；
4. 文案合规拦截：构造含供应链词文案 → 该版作废改用备选（rejected 留证据）；全部命中 → 跳过；
5. spec 校验失败不落 uploaded（upload_status 保持 local，spec_ok=0，failures 逐项记录）；
6. run_pipeline 一站式（fixtures 离线）：拆解→模板→文案→多版出片落库；
7. 无明文密钥；video 包级重导出（C1 内容不破坏）。

运行：python -m pytest tests/test_optimization_video_composer.py -q --basetemp=".pytest-tmp-m3"
（P-011：独立 basetemp，禁止共用 .pytest-tmp）
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from optimization.compliance import check_text
from optimization.config import load_config
from optimization.db import Database
from optimization.models import CopywriteDraft
from optimization.video import (
    BREAKDOWN_SCHEMA,
    TEMPLATE_DEFAULTS,
    BreakdownGenerator,
    MockFFmpegRunner,
    TemplatePlan,
    TemplatePlanner,
    VideoBreakdown,
    VideoComposer,
    VideoVariantRepo,
    build_template,
    detect_ffmpeg,
    generate_breakdown,
    plan_segments,
    probe_from_asset,
    run_pipeline,
)

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures" / "optimization"

GOOD_SCRIPT_V2 = "甄选陶瓷材质，容量350ml，日常更安心。"
BAD_SCRIPT_V1 = "厂家直发一件代发，超值好物，快来看看！"


def _load_fixture(name: str) -> dict:
    with open(FIXTURES / name, encoding="utf-8") as f:
        return json.load(f)


def _good_probe(**overrides) -> dict:
    """合规基线出片元数据（720x1280 / 9:16 / mp4 / 100MB / 30s），可按维度覆盖。"""
    base = {
        "width": 720,
        "height": 1280,
        "duration": 30.0,
        "size_bytes": 100 * 1024 * 1024,
        "format": "mp4",
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------- fixtures


@pytest.fixture
def asset() -> dict:
    return _load_fixture("source_asset_fixture.json")


@pytest.fixture
def product() -> dict:
    return _load_fixture("product_fixture.json")


@pytest.fixture
def cfg(tmp_path):
    """内存库 + 临时 data_dir（P-011：避开 .pytest-tmp 文件锁）。"""
    return load_config(
        db_url="sqlite:///:memory:", fixtures_dir=FIXTURES, data_dir=tmp_path / "data"
    )


@pytest.fixture
def db(cfg):
    database = Database(cfg)
    database.create_all()
    return database


@pytest.fixture
def good_runner(asset) -> MockFFmpegRunner:
    """Mock 出片：probe 预设 = 素材元数据换算（合规基线）。"""
    return MockFFmpegRunner(probe_from_asset(asset))


@pytest.fixture(autouse=True)
def _offline_env(monkeypatch):
    """默认零 API Key（fixtures 离线模式）；单测按需 setenv 覆盖。"""
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)


# ---------------------------------------------------------------- 拆解降级

class TestBreakdown:
    def test_rule_fallback_no_key(self, cfg, product):
        bd = BreakdownGenerator(cfg).generate(
            product["product_id"], product["category"], product["sku_spec_json"]
        )
        assert isinstance(bd, VideoBreakdown)
        assert bd.product_id == product["product_id"]
        assert bd.source == "rule_fallback"
        assert bd.meta.get("llm_rejected") == "no_api_key"
        assert bd.opening_hook
        assert bd.selling_shots and bd.voiceover_points
        # 全部要点过合规预审
        for s in bd.selling_shots:
            assert s["title"] and s["shot"]
            assert check_text(s["shot"]) == []
        for p in bd.voiceover_points:
            assert p
            assert check_text(p) == []
        # 基于 SKU 真实字段（材质/容量/颜色/数量/包装/产地）
        shots_text = "".join(s["shot"] for s in bd.selling_shots)
        points_text = "".join(bd.voiceover_points)
        assert "陶瓷" in shots_text or "陶瓷" in points_text
        assert "350ml" in points_text
        assert "单件装" in points_text
        assert bd.meta.get("fallback") is True

    def test_llm_success_when_key_and_valid(self, cfg, product, monkeypatch):
        monkeypatch.setenv("DEEPSEEK_API_KEY", "placeholder-key-not-real")
        body = json.dumps({"choices": [{"message": {"content": json.dumps({
            "opening_hook": "陶瓷好物，一眼心动",
            "selling_shots": [
                {"title": "材质", "shot": "近景展示陶瓷材质细节"},
                {"title": "容量", "shot": "中景呈现350ml容量规格"},
            ],
            "voiceover_points": ["甄选陶瓷材质，容量350ml", "颜色多样可选"],
        })}}]})
        called: list[int] = []

        def post(url, headers, payload, timeout):
            called.append(1)
            assert "Authorization" in headers and headers["Authorization"].startswith("Bearer ")
            assert "placeholder-key-not-real" not in json.dumps(payload)
            return 200, body

        from optimization.copywriting.llm import DeepSeekClient

        bd = BreakdownGenerator(cfg, llm=DeepSeekClient(cfg, post=post)).generate(
            product["product_id"], product["category"], product["sku_spec_json"]
        )
        assert called, "有 Key 时应发起一次请求"
        assert bd.source == "llm"
        assert bd.opening_hook == "陶瓷好物，一眼心动"
        assert len(bd.selling_shots) == 2
        assert bd.voiceover_points == ["甄选陶瓷材质，容量350ml", "颜色多样可选"]

    def test_llm_compliance_hits_dropped(self, cfg, product, monkeypatch):
        monkeypatch.setenv("DEEPSEEK_API_KEY", "placeholder-key-not-real")
        body = json.dumps({"choices": [{"message": {"content": json.dumps({
            "opening_hook": "厂家源头好货",
            "selling_shots": [
                {"title": "材质", "shot": "厂家直发陶瓷材质"},
                {"title": "容量", "shot": "中景呈现350ml容量规格"},
            ],
            "voiceover_points": ["一件代发 源头好货", "甄选陶瓷材质，容量350ml"],
        })}}]})

        def post(url, headers, payload, timeout):
            return 200, body

        from optimization.copywriting.llm import DeepSeekClient

        bd = BreakdownGenerator(cfg, llm=DeepSeekClient(cfg, post=post)).generate(
            product["product_id"], product["category"], product["sku_spec_json"]
        )
        assert bd.source == "llm"          # 仍有合规要点 → 保留 LLM 结果
        assert bd.opening_hook == ""       # 钩子命中合规 → 剔除
        assert all("厂家" not in s["shot"] for s in bd.selling_shots)
        assert all("代发" not in p for p in bd.voiceover_points)
        assert bd.meta.get("llm_dropped"), "被剔除清单必须留证据"
        kinds = {d["kind"] for d in bd.meta["llm_dropped"]}
        assert {"hook", "shot", "voiceover"} <= kinds

    def test_llm_all_hits_fall_back_to_rules(self, cfg, product, monkeypatch):
        monkeypatch.setenv("DEEPSEEK_API_KEY", "placeholder-key-not-real")
        body = json.dumps({"choices": [{"message": {"content": json.dumps({
            "opening_hook": "一件代发源头",
            "selling_shots": [{"title": "x", "shot": "厂家直发批发"}],
            "voiceover_points": ["1688 源头工厂货"],
        })}}]})

        def post(url, headers, payload, timeout):
            return 200, body

        from optimization.copywriting.llm import DeepSeekClient

        bd = BreakdownGenerator(cfg, llm=DeepSeekClient(cfg, post=post)).generate(
            product["product_id"], product["category"], product["sku_spec_json"]
        )
        assert bd.source == "rule_fallback"
        assert bd.meta.get("llm_rejected") == "compliance_hits_all"
        assert bd.selling_shots and bd.voiceover_points  # 规则兜底非空

    def test_empty_sku_still_non_empty(self, cfg, product):
        bd = BreakdownGenerator(cfg).generate(product["product_id"], product["category"], {})
        assert bd.source == "rule_fallback"
        assert bd.selling_shots and bd.voiceover_points
        assert all(not check_text(p) for p in bd.voiceover_points)

    def test_module_entry_matches_instance(self, cfg, product):
        bd1 = generate_breakdown(
            product["product_id"], product["category"], product["sku_spec_json"], cfg
        )
        bd2 = BreakdownGenerator(cfg).generate(
            product["product_id"], product["category"], product["sku_spec_json"]
        )
        assert bd1.to_dict() == bd2.to_dict()
        assert bd1.source == "rule_fallback"

    def test_schema_requires_all_sections(self):
        assert BREAKDOWN_SCHEMA["type"] == "object"
        assert set(BREAKDOWN_SCHEMA["required"]) == {
            "opening_hook", "selling_shots", "voiceover_points"
        }


# ---------------------------------------------------------------- 模板三段式

class TestTemplates:
    def test_defaults_from_template_params_config(self):
        tpl = build_template("家居日用")
        assert isinstance(tpl, TemplatePlan)
        assert tpl.params["opening_seconds"] == TEMPLATE_DEFAULTS["opening_seconds"] == 3
        assert tpl.params["subtitle_style"] == {
            "position": "bottom", "font_size": 36, "stroke": True
        }
        assert tpl.params["badge_position"] == "top-right"
        assert tpl.params["bgm_loudness"] == -16.0
        assert tpl.params["cut_count"] == 3
        assert tpl.params["params_version"] == 1

    def test_category_adjustments(self):
        assert build_template("宠物用品").params["cut_count"] == 2
        assert build_template("家居日用").params["cut_count"] == 3
        assert build_template("未知类目").params["cut_count"] == TEMPLATE_DEFAULTS["cut_count"]

    def test_overrides_win(self):
        tpl = build_template("家居日用", overrides={"opening_seconds": 5, "badge_position": "bottom-left"})
        assert tpl.params["opening_seconds"] == 5
        assert tpl.params["badge_position"] == "bottom-left"
        assert tpl.params["cut_count"] == 3  # 未覆盖字段保持

    def test_template_id_deterministic(self):
        assert build_template("家居日用").template_id == build_template("家居日用").template_id
        assert build_template("家居日用").template_id != build_template("宠物用品").template_id
        assert build_template("家居日用", overrides={"params_version": 2}).template_id != \
            build_template("家居日用").template_id

    def test_three_section_structure(self):
        tpl = build_template("家居日用")
        seg = plan_segments(tpl.params, 18.5)
        assert set(seg) == {"opening", "middle", "ending", "total_seconds"}
        assert seg["opening"]["type"] == "opening"
        assert seg["opening"]["seconds"] == 3
        assert "商品展示" in seg["opening"]["elements"] and "卖点卡点" in seg["opening"]["elements"]
        assert seg["middle"]["type"] == "middle"
        assert seg["middle"]["kind"] == "mashup"          # 3 片段 → 混剪
        assert len(seg["middle"]["segments"]) == 3
        for i, s in enumerate(seg["middle"]["segments"], start=1):
            assert s["index"] == i and s["end"] > s["start"]
        assert seg["ending"]["type"] == "ending"
        assert "行动引导" in seg["ending"]["elements"]
        assert seg["total_seconds"] == pytest.approx(18.5)

    def test_segments_short_asset_original(self):
        seg = plan_segments(build_template("家居日用").params, 4.0)
        assert seg["middle"]["kind"] == "original"
        assert seg["middle"]["segments"] == []
        assert seg["total_seconds"] == pytest.approx(4.0)

    def test_segments_cut_count_override(self):
        seg = plan_segments(build_template("家居日用").params, 18.5, cut_count=2)
        assert seg["middle"]["kind"] == "mashup"
        assert len(seg["middle"]["segments"]) == 2

    def test_planner_defaults_injection(self):
        # 注入默认值生效（无类目微调的类目）；有类目微调时微调优先（见 test_category_adjustments）
        planner = TemplatePlanner(defaults={"opening_seconds": 5})
        assert planner.build("未知类目").params["opening_seconds"] == 5


# ---------------------------------------------------------------- composer 全链路

class TestComposer:
    def _offline_drafts(self, product) -> list[CopywriteDraft]:
        from optimization.copywriting.ads import AdBadgeGenerator
        from optimization.copywriting.script import ScriptGenerator

        pid = product["product_id"]
        category = product["category"]
        spec = product["sku_spec_json"]
        gen = AdBadgeGenerator()
        drafts: list[CopywriteDraft] = [ScriptGenerator().generate(pid, category, spec)]
        drafts += gen.generate_ads(pid, category, spec)
        drafts += gen.generate_badges(pid, category, spec)
        assert all(d.passed for d in drafts)
        return drafts

    def test_full_chain_fixtures(self, cfg, db, asset, product, good_runner):
        drafts = self._offline_drafts(product)
        template = build_template(product["category"], asset_duration=asset["duration"])
        composer = VideoComposer(cfg, db=db, runner=good_runner)
        rows = composer.compose(asset, drafts, template, variants=2)

        assert len(rows) == 2
        assert [r["variant_no"] for r in rows] == [1, 2]
        for r in rows:
            # 记录完整：product_id/source_asset_id/variant_no/快照/校验/合规/评估
            assert r["product_id"] == product["product_id"]
            assert r["source_asset_id"] == asset["asset_id"]
            assert r["template_id"].startswith("tpl_")
            assert r["copywrite_ids"]
            assert r["template_params_snapshot"]["template_id"] == r["template_id"]
            assert r["template_params_snapshot"]["segments"]["opening"]["seconds"] >= 3
            assert r["spec_check_json"]["passed"] is True
            assert r["spec_check_json"]["failures"] == []
            assert r["spec_ok"] is True
            assert r["compliance_json"]["subtitle"]["passed"] is True
            assert r["compliance_json"]["subtitle"]["rejected"] == []
            assert r["evaluation"] == "exploration"
            assert r["upload_status"] == "local"
            assert r["review_status"] == "pending"
            assert str(r["file_path"]).endswith(".mp4")
            assert "video_variants" in r["file_path"]

        # 变体差异化：v1 口播稿字幕 / v2 投放文案字幕；片头秒数 +1；节奏（片段数/BGM）不同
        assert rows[0]["compliance_json"]["subtitle"]["copy_type"] == "script"
        assert rows[1]["compliance_json"]["subtitle"]["copy_type"] == "ad"
        p1 = rows[0]["template_params_snapshot"]["params"]
        p2 = rows[1]["template_params_snapshot"]["params"]
        assert p1["opening_seconds"] == 3 and p2["opening_seconds"] == 4
        assert p1["cut_count"] == 3 and p2["cut_count"] == 2
        assert p1["bgm_loudness"] == -16.0 and p2["bgm_loudness"] == -16.5
        assert p1["params_version"] == p2["params_version"] == 1

        # Mock 出片命令：build_transcode_cmd 打底 + 字幕/角标 drawtext
        assert len(good_runner.transcode_calls) == 2
        for cmd, timeout in good_runner.transcode_calls:
            assert cmd[0] == "ffmpeg"
            vf = cmd[cmd.index("-vf") + 1]
            assert "scale=720:1280" in vf
            assert vf.count("drawtext") == 2        # 字幕 + 角标
            assert timeout == 300.0

    def test_persisted_rows(self, cfg, db, asset, product, good_runner):
        drafts = self._offline_drafts(product)
        template = build_template(product["category"])
        composer = VideoComposer(cfg, db=db, runner=good_runner)
        rows = composer.compose(asset, drafts, template, variants=2)

        repo = VideoVariantRepo(db)
        stored = repo.list_by_product(product["product_id"])
        assert len(stored) == 2
        for r in rows:
            assert r["variant_id"].startswith("vv_")
            match = next(s for s in stored if s["variant_no"] == r["variant_no"])
            assert match["variant_id"] == r["variant_id"]
            assert match["spec_ok"] is True
            assert match["evaluation"] == "exploration"
            assert match["template_params_snapshot"]["params"]["opening_seconds"] == \
                r["template_params_snapshot"]["params"]["opening_seconds"]

    def test_upsert_idempotent(self, cfg, db, asset, product, good_runner):
        drafts = self._offline_drafts(product)
        template = build_template(product["category"])
        composer = VideoComposer(cfg, db=db, runner=good_runner)
        composer.compose(asset, drafts, template, variants=2)
        composer.compose(asset, drafts, template, variants=2)  # 同 (product_id, variant_no) 覆盖
        assert len(VideoVariantRepo(db).list_by_product(product["product_id"])) == 2

    def test_compliance_intercept_uses_backup(self, cfg, db, asset, product, good_runner):
        """含供应链词文案 → 该版作废改用备选（rejected 留证据，行正常落库）。"""
        pid = product["product_id"]
        drafts = [
            CopywriteDraft(
                product_id=pid, copy_type="script", variant_no=1,
                content=BAD_SCRIPT_V1, char_len=len(BAD_SCRIPT_V1),
                compliance_hits=["供应链词:厂家"], passed=False, source="rule_fallback",
            ),
            CopywriteDraft(
                product_id=pid, copy_type="script", variant_no=2,
                content=GOOD_SCRIPT_V2, char_len=len(GOOD_SCRIPT_V2),
                compliance_hits=[], passed=True, source="rule_fallback",
            ),
            CopywriteDraft(
                product_id=pid, copy_type="ad", variant_no=1,
                content="精选好物，日常之选。", char_len=9,
                compliance_hits=[], passed=True, source="rule_fallback",
            ),
            CopywriteDraft(
                product_id=pid, copy_type="badge", variant_no=1,
                content="精选好物", char_len=4,
                compliance_hits=[], passed=True, source="rule_fallback",
            ),
        ]
        template = build_template(product["category"])
        composer = VideoComposer(cfg, db=db, runner=good_runner)
        rows = composer.compose(asset, drafts, template, variants=1)

        assert len(rows) == 1
        sub = rows[0]["compliance_json"]["subtitle"]
        assert sub["full_content"] == GOOD_SCRIPT_V2          # 改用备选
        assert sub["shown_content"] == GOOD_SCRIPT_V2         # 未超 24 字不截断
        assert sub["passed"] is True and sub["hits"] == []
        assert len(sub["rejected"]) == 1                       # 被拦截候选留证据
        rej = sub["rejected"][0]
        assert rej["content"] == BAD_SCRIPT_V1
        assert any("厂家" in h for h in rej["hits"])
        assert rows[0]["spec_ok"] is True

    def test_all_candidates_rejected_skips_variant(self, cfg, db, asset, product, good_runner):
        pid = product["product_id"]
        drafts = [
            CopywriteDraft(
                product_id=pid, copy_type="script", variant_no=1,
                content=BAD_SCRIPT_V1, char_len=len(BAD_SCRIPT_V1),
                compliance_hits=["供应链词:厂家"], passed=False, source="rule_fallback",
            ),
            CopywriteDraft(
                product_id=pid, copy_type="ad", variant_no=1,
                content="批发一件代发好货", char_len=8,
                compliance_hits=["供应链词:批发"], passed=False, source="rule_fallback",
            ),
            CopywriteDraft(
                product_id=pid, copy_type="badge", variant_no=1,
                content="官方旗舰", char_len=4,
                compliance_hits=["广告禁用词:官方"], passed=False, source="rule_fallback",
            ),
        ]
        template = build_template(product["category"])
        composer = VideoComposer(cfg, db=db, runner=good_runner)
        rows = composer.compose(asset, drafts, template, variants=1)

        assert rows == []
        assert len(composer.skipped) == 1
        assert composer.skipped[0]["variant_no"] == 1
        assert composer.skipped[0]["reason"] == "no_compliant_subtitle"
        assert VideoVariantRepo(db).list_by_product(pid) == []   # 跳过版不进库

    def test_spec_fail_not_uploaded(self, cfg, db, asset, product):
        """硬规格校验失败：记录 failures，upload_status 不落 uploaded。"""
        bad_runner = MockFFmpegRunner(_good_probe(
            width=480, height=640, duration=400.0,
            size_bytes=700 * 1024 * 1024, format="avi",
        ))
        drafts = self._offline_drafts(product)
        template = build_template(product["category"])
        composer = VideoComposer(cfg, db=db, runner=bad_runner)
        rows = composer.compose(asset, drafts, template, variants=1)

        assert len(rows) == 1
        r = rows[0]
        assert r["spec_ok"] is False
        assert r["spec_check_json"]["passed"] is False
        fields = {f["field"] for f in r["spec_check_json"]["failures"]}
        assert fields == {"resolution", "aspect", "format", "size", "duration"}
        for f in r["spec_check_json"]["failures"]:
            assert f["reason"] and "value" in f
        assert r["spec_check_json"]["probe"]["width"] == 480
        assert r["upload_status"] == "local"            # 不落 uploaded（P-007）
        assert r["evaluation"] == "exploration"
        # 落库同样反映失败
        stored = VideoVariantRepo(db).list_by_product(product["product_id"])
        assert len(stored) == 1 and stored[0]["spec_ok"] is False
        assert stored[0]["spec_check_json"]["passed"] is False

    def test_probe_from_asset(self, asset):
        p = probe_from_asset(asset)
        assert p == {
            "width": 720,
            "height": 1280,
            "duration": 18.5,
            "size_bytes": int(12.3 * 1024 * 1024),
            "format": "mp4",
        }


# ---------------------------------------------------------------- run_pipeline 一站式

class TestRunPipeline:
    def test_pipeline_fixtures_offline(self, cfg, db, asset, product, good_runner):
        result = run_pipeline(
            asset, product, variants=2, config=cfg, db=db, runner=good_runner
        )
        assert result["product_id"] == product["product_id"]
        assert result["asset_id"] == asset["asset_id"]
        assert result["breakdown"]["source"] == "rule_fallback"     # 无 Key 降级
        assert result["breakdown"]["voiceover_points"]
        assert result["template"]["segments"]["opening"]["elements"] == ["商品展示", "卖点卡点"]
        assert result["draft_count"] >= 5                            # 口播稿1 + 文案≥2 + 角标≥2
        assert len(result["variants"]) == 2
        assert result["skipped"] == []
        for r in result["variants"]:
            assert r["variant_id"].startswith("vv_")
            assert r["spec_ok"] is True
            assert r["evaluation"] == "exploration"
        assert len(VideoVariantRepo(db).list_by_product(product["product_id"])) == 2

    def test_pipeline_default_db_in_memory(self, cfg, asset, product, good_runner):
        """db 缺省 → 内存库（不触碰本模块真实库）。"""
        result = run_pipeline(asset, product, variants=2, config=cfg, runner=good_runner)
        assert len(result["variants"]) == 2

    def test_pipeline_variants_at_least_two(self, cfg, db, asset, product, good_runner):
        result = run_pipeline(asset, product, variants=3, config=cfg, db=db, runner=good_runner)
        nos = [r["variant_no"] for r in result["variants"]]
        assert nos == [1, 2, 3]
        assert len({r["compliance_json"]["subtitle"]["full_content"] for r in result["variants"]}) >= 2


# ---------------------------------------------------------------- 无明文密钥 / 包级重导出

class TestHygiene:
    def test_no_plaintext_keys_in_modules(self):
        here = Path(__file__).resolve().parent.parent / "optimization" / "video"
        for py in sorted(here.glob("*.py")):
            text = py.read_text(encoding="utf-8")
            assert "sk-" not in text, f"{py.name} 含疑似明文密钥"
            assert "api_key=" not in text.lower().replace("api_key_env", ""), f"{py.name} 含密钥字面量"

    def test_package_reexports_preserve_c1(self):
        import optimization.video as video_pkg

        for name in (
            # C1 ffmpeg 层
            "detect_ffmpeg", "VideoToolError", "FFmpegRunner", "FFmpegProcessRunner",
            "MockFFmpegRunner", "validate_specs", "build_transcode_cmd",
            # C2 编排层
            "BREAKDOWN_SCHEMA", "VideoBreakdown", "BreakdownGenerator", "generate_breakdown",
            "TEMPLATE_DEFAULTS", "TemplatePlan", "TemplatePlanner", "build_template",
            "plan_segments", "VideoComposer", "VideoVariantRepo", "probe_from_asset",
            "run_pipeline",
        ):
            assert hasattr(video_pkg, name), f"包级缺少重导出: {name}"
        assert video_pkg.detect_ffmpeg is detect_ffmpeg
        assert video_pkg.MockFFmpegRunner is MockFFmpegRunner
