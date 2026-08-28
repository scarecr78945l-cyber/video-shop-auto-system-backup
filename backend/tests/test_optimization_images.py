"""M3 主图/详情图管线（子代理-B2 · 迭代 v0.4）测试。

覆盖 4 能力：planner / provider / quality_gate / memory，全部 fixtures 离线模式
（autouse 删除 KIMI_API_KEY / WAN_API_KEY），零网络、零第三方新依赖。
运行：python -m pytest tests/test_optimization_images.py -q --basetemp=".pytest-tmp"（P-001）
"""

from __future__ import annotations

import base64
import io
import json
from pathlib import Path

import pytest
from PIL import Image

from optimization.compliance import check_supply_chain
from optimization.config import load_config
from optimization.db import Database
from optimization.images import (
    CategoryListingMemory,
    ImageQualityGate,
    KimiImagePlanner,
    MemoryPolicy,
    WanImageError,
    WanImageProvider,
    hamming_distance,
    phash_ahash,
    phash_dhash,
    regenerate_until_ok,
)
from optimization.models import ImageDraft, ImagePlan
from optimization.repo import ImageRepo
from sqlalchemy import func, select

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures" / "optimization"
SUPPLY_WORDS = ["1688", "工厂", "源头", "厂家", "一件代发", "批发"]


# ---------------------------------------------------------------- fixtures

def _load_fixture(name: str) -> dict:
    with open(FIXTURES / name, encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture
def products() -> list[dict]:
    return [_load_fixture("product_fixture.json"), _load_fixture("product_fixture_pet.json")]


@pytest.fixture
def house_product(products) -> dict:
    return products[0]  # 家居日用


@pytest.fixture
def pet_product(products) -> dict:
    return products[1]  # 宠物用品


@pytest.fixture
def cfg(tmp_path):
    return load_config(
        db_url=f"sqlite:///{tmp_path / 'm3-test.db'}",
        data_dir=tmp_path / "data",
        fixtures_dir=FIXTURES,
    )


@pytest.fixture
def db(cfg):
    database = Database(cfg)
    database.create_all()
    return database


@pytest.fixture(autouse=True)
def _offline_env(monkeypatch):
    """默认零 API Key（fixtures 离线模式）；单测按需 setenv 覆盖。"""
    monkeypatch.delenv("KIMI_API_KEY", raising=False)
    monkeypatch.delenv("WAN_API_KEY", raising=False)
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)


def _png_bytes(size: tuple[int, int], color=(200, 100, 50)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", size, color).save(buf, format="PNG")
    return buf.getvalue()


def _wan_success_body(img_bytes: bytes) -> str:
    return json.dumps({
        "output": {"results": [{"b64_json": base64.b64encode(img_bytes).decode()}]}
    })


# ---------------------------------------------------------------- 感知哈希

class TestPhash:
    def test_hamming_distance_basics(self):
        assert hamming_distance("0" * 16, "0" * 16) == 0
        assert hamming_distance("f" * 16, "0" * 16) == 64
        assert 0 <= hamming_distance("1234abcd1234abcd", "1234abcd1234abce") <= 64

    def test_dhash_identical_images_equal(self, tmp_path):
        p1, p2 = tmp_path / "a.png", tmp_path / "b.png"
        img = Image.new("RGB", (200, 200), (120, 60, 30))
        img.save(p1)
        img.save(p2)
        assert phash_dhash(p1) == phash_dhash(p2) == phash_ahash(p1)

    def test_dhash_different_images_differ(self, tmp_path):
        p1, p2 = tmp_path / "a.png", tmp_path / "b.png"
        Image.new("RGB", (200, 200), (255, 255, 255)).save(p1)
        Image.new("RGB", (200, 200), (10, 10, 10)).save(p2)
        assert hamming_distance(phash_dhash(p1), phash_dhash(p2)) > 8


# ---------------------------------------------------------------- planner

class TestPlanner:
    def test_main_offline_rule_fallback(self, cfg, house_product):
        plan = KimiImagePlanner(cfg).plan(house_product, "main")
        assert plan.source == "rule_fallback"
        assert plan.image_type == "main"
        assert len(plan.prompts) == cfg.image.main_image_count == 5
        # 5 张 prompts 不全相同（角度/背景/卖点焦点差异化）
        assert len(set(plan.prompts)) == 5
        # 白底 + 商品主体 + 卖点角标提示 的默认策略描述
        assert "白底" in plan.strategy
        assert "差异化" in plan.strategy

    def test_detail_offline_rule_fallback(self, cfg, pet_product):
        plan = KimiImagePlanner(cfg).plan(pet_product, "detail")
        assert plan.source == "rule_fallback"
        assert len(plan.prompts) >= cfg.image.detail_image_min >= 3
        assert len(set(plan.prompts)) == len(plan.prompts)
        assert "细节" in plan.strategy

    def test_planner_rejects_unknown_type(self, cfg, house_product):
        with pytest.raises(ValueError):
            KimiImagePlanner(cfg).plan(house_product, "video")

    def test_llm_success(self, cfg, house_product, monkeypatch):
        monkeypatch.setenv("KIMI_API_KEY", "sk-test-placeholder-not-real")
        prompts = [
            "电商商品主图：正面平视，纯白背景，突出整体造型与卖点",
            "电商商品主图：微俯视四十五度，浅灰渐变背景，突出材质质感",
            "电商商品主图：侧三十度视角，白底柔和投影，突出规格尺寸",
            "电商商品主图：平视略仰，家居生活场景背景，突出使用场景",
            "电商商品主图：俯视六十度，纯白背景，突出颜色包装",
        ]
        body = json.dumps({"choices": [{"message": {"content": json.dumps({
            "strategy": "白底为主差异化拍摄",
            "prompts": prompts,
        })}}]})

        def post(url, headers, payload, timeout):
            assert "Authorization" in headers and "Bearer" in headers["Authorization"]
            assert "KIMI" not in json.dumps(payload)  # 无明文密钥落 payload
            return 200, body

        plan = KimiImagePlanner(cfg, post=post).plan(house_product, "main")
        assert plan.source == "llm"
        assert len(plan.prompts) == 5
        assert len(set(plan.prompts)) == 5
        assert plan.strategy == "白底为主差异化拍摄"

    def test_llm_http_error_falls_back(self, cfg, house_product, monkeypatch):
        monkeypatch.setenv("KIMI_API_KEY", "sk-test-placeholder-not-real")

        def post(url, headers, payload, timeout):
            return 500, "server error"

        plan = KimiImagePlanner(cfg, post=post).plan(house_product, "main")
        assert plan.source == "rule_fallback"
        assert len(plan.prompts) == 5

    def test_llm_bad_schema_falls_back(self, cfg, house_product, monkeypatch):
        monkeypatch.setenv("KIMI_API_KEY", "sk-test-placeholder-not-real")
        body = json.dumps({"choices": [{"message": {"content": json.dumps({
            "strategy": "x", "prompts": ["只有一条"]})}}]})

        def post(url, headers, payload, timeout):
            return 200, body

        plan = KimiImagePlanner(cfg, post=post).plan(house_product, "main")
        assert plan.source == "rule_fallback"  # 主图数量不足 → 降级


# ---------------------------------------------------------------- provider

class TestProvider:
    def test_main_placeholders_distinct_and_1x1(self, cfg, house_product, tmp_path):
        provider = WanImageProvider(cfg, out_dir=tmp_path / "imgs")
        plan = KimiImagePlanner(cfg).plan(house_product, "main")
        drafts = [provider.generate(house_product, plan, variant_no=v)
                  for v in range(1, 6)]
        assert all(d.image_type == "main" for d in drafts)
        # 1:1 800x800 + 宽高记录
        for d in drafts:
            assert (d.width, d.height) == (800, 800)
            assert Path(d.file_path).exists()
            assert d.phash
        # 验收 #3：两两汉明距离 > 8（Pillow 自实现 dHash）
        for i in range(5):
            for j in range(i + 1, 5):
                assert hamming_distance(drafts[i].phash, drafts[j].phash) > 8, \
                    f"主图 {i+1}/{j+1} 判为相似"

    def test_detail_placeholders(self, cfg, pet_product, tmp_path):
        provider = WanImageProvider(cfg, out_dir=tmp_path / "imgs")
        plan = KimiImagePlanner(cfg).plan(pet_product, "detail")
        drafts = [provider.generate(pet_product, plan, variant_no=v)
                  for v in range(1, len(plan.prompts) + 1)]
        assert len(drafts) >= 3
        for d in drafts:
            assert (d.width, d.height) == (750, 1000)  # 3:4 详情图
            assert Path(d.file_path).exists()

    def test_out_dir_auto_created(self, cfg, house_product):
        provider = WanImageProvider(cfg)  # 默认 data/optimization/images
        out = provider.out_dir
        assert not out.exists()
        provider.generate(house_product, KimiImagePlanner(cfg).plan(house_product, "main"), 1)
        assert out.exists() and out.is_dir()

    def test_rate_limit_backoff_then_success(self, cfg, house_product, monkeypatch):
        monkeypatch.setenv("WAN_API_KEY", "sk-test-placeholder-not-real")
        sleeps: list[float] = []
        calls: list[int] = []
        body = _wan_success_body(_png_bytes((64, 64)))

        def post(url, headers, payload, timeout):
            calls.append(1)
            if len(calls) <= 2:
                return 429, "rate limited"
            return 200, body

        provider = WanImageProvider(cfg, post=post, sleep_fn=sleeps.append)
        plan = KimiImagePlanner(cfg).plan(house_product, "main")
        draft = provider.generate(house_product, plan, variant_no=1)
        assert draft.file_path and Path(draft.file_path).exists()
        assert draft.width == 64 and draft.height == 64  # 宽高记录
        # RATE_LIMIT 180s 退避 ×2 次后成功
        assert len(sleeps) == 2
        assert all(s == 180.0 for s in sleeps)

    def test_rate_limit_exhausted_raises(self, cfg, house_product, monkeypatch):
        monkeypatch.setenv("WAN_API_KEY", "sk-test-placeholder-not-real")
        sleeps: list[float] = []

        def post(url, headers, payload, timeout):
            return 429, "rate limited"

        provider = WanImageProvider(cfg, post=post, sleep_fn=sleeps.append)
        plan = KimiImagePlanner(cfg).plan(house_product, "main")
        with pytest.raises(WanImageError) as ei:
            provider.generate(house_product, plan, variant_no=1)
        assert ei.value.error_code == "RATE_LIMIT"
        assert len(sleeps) == cfg.llm.max_retries + 1  # 每次尝试都 180s 退避
        assert all(s == 180.0 for s in sleeps)

    def test_timeout_classification(self, cfg, house_product, monkeypatch):
        monkeypatch.setenv("WAN_API_KEY", "sk-test-placeholder-not-real")
        sleeps: list[float] = []

        def post(url, headers, payload, timeout):
            raise TimeoutError("socket timeout")

        provider = WanImageProvider(cfg, post=post, sleep_fn=sleeps.append)
        plan = KimiImagePlanner(cfg).plan(house_product, "main")
        with pytest.raises(WanImageError) as ei:
            provider.generate(house_product, plan, variant_no=1)
        assert ei.value.error_code == "TIMEOUT"

    def test_4xx_platform_reject(self, cfg, house_product, monkeypatch):
        monkeypatch.setenv("WAN_API_KEY", "sk-test-placeholder-not-real")

        def post(url, headers, payload, timeout):
            return 400, "bad prompt"

        provider = WanImageProvider(cfg, post=post)
        plan = KimiImagePlanner(cfg).plan(house_product, "main")
        with pytest.raises(WanImageError) as ei:
            provider.generate(house_product, plan, variant_no=1)
        assert ei.value.error_code.startswith("PLATFORM_REJECT")


# ---------------------------------------------------------------- quality_gate

class TestQualityGate:
    def _make_draft(self, cfg, tmp_path, plan, product, variant_no) -> ImageDraft:
        return WanImageProvider(cfg, out_dir=tmp_path / "imgs").generate(
            product, plan, variant_no=variant_no
        )

    def test_inspect_ok(self, cfg, house_product, tmp_path):
        gate = ImageQualityGate(cfg)
        plan = KimiImagePlanner(cfg).plan(house_product, "main")
        d = self._make_draft(cfg, tmp_path, plan, house_product, 1)
        verdict = gate.inspect("img_1", d.file_path, "main")
        assert verdict.ok
        assert verdict.score == 100.0
        assert verdict.issues == []

    def test_inspect_resolution_fail(self, cfg, tmp_path):
        gate = ImageQualityGate(cfg)
        small = tmp_path / "small.png"
        Image.new("RGB", (100, 100), (128, 128, 128)).save(small)
        verdict = gate.inspect("img_small", small, "main")
        assert not verdict.ok
        assert any("分辨率不足" in i for i in verdict.issues)

    def test_inspect_main_not_square(self, cfg, tmp_path):
        gate = ImageQualityGate(cfg)
        wide = tmp_path / "wide.png"
        Image.new("RGB", (1200, 800), (128, 128, 128)).save(wide)
        verdict = gate.inspect("img_wide", wide, "main")
        assert not verdict.ok
        assert any("非 1:1" in i for i in verdict.issues)

    def test_inspect_blank_image(self, cfg, tmp_path):
        gate = ImageQualityGate(cfg)
        blank = tmp_path / "blank.png"
        Image.new("RGB", (800, 800), (128, 128, 128)).save(blank)
        verdict = gate.inspect("img_blank", blank, "main")
        assert not verdict.ok
        assert any("空白" in i for i in verdict.issues)

    def test_inspect_missing_file(self, cfg, tmp_path):
        gate = ImageQualityGate(cfg)
        verdict = gate.inspect("img_missing", tmp_path / "nope.png", "main")
        assert not verdict.ok
        assert verdict.score == 0.0

    def test_batch_similar_detected(self, cfg, house_product, tmp_path):
        gate = ImageQualityGate(cfg)
        plan = KimiImagePlanner(cfg).plan(house_product, "main")
        d = self._make_draft(cfg, tmp_path, plan, house_product, 1)
        # 两张完全相同 → 判同图
        items = [
            {"image_id": "a", "file_path": d.file_path},
            {"image_id": "b", "file_path": d.file_path},
        ]
        res = gate.gate_batch(items, "main")
        assert not res["ok"]
        assert res["similar_pairs"] and res["similar_pairs"][0]["hamming"] == 0

    def test_batch_five_main_all_pass(self, cfg, house_product, tmp_path):
        gate = ImageQualityGate(cfg)
        plan = KimiImagePlanner(cfg).plan(house_product, "main")
        provider = WanImageProvider(cfg, out_dir=tmp_path / "imgs")
        drafts = [provider.generate(house_product, plan, v) for v in range(1, 6)]
        items = [{"image_id": f"m{v}", "file_path": d.file_path}
                 for v, d in enumerate(drafts, 1)]
        res = gate.gate_batch(items, "main")
        assert res["ok"] is True
        assert res["similar_pairs"] == []


# ---------------------------------------------------------------- 打回重生成

def _fixed_draft(tmp_path, plan, product, fixed_file) -> ImageDraft:
    return ImageDraft(
        batch_id="", product_id=product["product_id"], image_type=plan.image_type,
        variant_no=1, file_path=str(fixed_file), phash=phash_dhash(str(fixed_file)),
        width=800, height=800,
    )


class TestRegenerate:
    def test_similar_then_distinct_recovers(self, cfg, house_product, tmp_path):
        gate = ImageQualityGate(cfg)
        plan = KimiImagePlanner(cfg).plan(house_product, "main")
        provider = WanImageProvider(cfg, out_dir=tmp_path / "imgs")
        first = provider.generate(house_product, plan, variant_no=1)
        fixed = tmp_path / "fixed.png"
        fixed.write_bytes(Path(first.file_path).read_bytes())
        calls = {"n": 0}

        def generate_one(v):
            calls["n"] += 1
            if calls["n"] <= 5:  # 第一轮全部同图 → 触发打回
                return _fixed_draft(tmp_path, plan, house_product, fixed)
            return provider.generate(house_product, plan, variant_no=v)

        res = regenerate_until_ok(gate, generate_one, plan, house_product, "b_rec")
        assert res["ok"] is True
        assert res["failed"] is False
        assert res["attempts"] == 1  # 打回 1 次后重生成通过

    def test_failed_after_max_regenerate(self, cfg, house_product, tmp_path):
        gate = ImageQualityGate(cfg)
        plan = KimiImagePlanner(cfg).plan(house_product, "main")
        provider = WanImageProvider(cfg, out_dir=tmp_path / "imgs")
        first = provider.generate(house_product, plan, variant_no=1)
        fixed = tmp_path / "fixed.png"
        fixed.write_bytes(Path(first.file_path).read_bytes())

        def generate_one(v):  # 永远同图 → 重生成超限标记失败
            return _fixed_draft(tmp_path, plan, house_product, fixed)

        res = regenerate_until_ok(gate, generate_one, plan, house_product, "b_fail")
        assert res["ok"] is False
        assert res["failed"] is True
        assert res["attempts"] == cfg.image.max_regenerate == 2  # 超限


# ---------------------------------------------------------------- 类目记忆

class TestMemory:
    def test_record_counts_and_reasons(self, db, cfg):
        mem = CategoryListingMemory(db, cfg)
        mem.record("家居日用", passed=True)
        mem.record("家居日用", passed=False, reject_reason="平台拒审:图片模糊")
        mem.record("家居日用", passed=False, reject_reason="平台拒审:图片模糊")
        mem.record("家居日用", passed=False, reject_reason="平台拒审:文字违规")

        got = mem.get("家居日用")
        assert got.pass_count == 1
        assert got.reject_count == 3
        assert got.reject_reasons == {
            "平台拒审:图片模糊": 2, "平台拒审:文字违规": 1
        }

    def test_below_threshold_no_adjust(self, db, cfg):
        mem = CategoryListingMemory(db, cfg)
        mem.record("家居日用", passed=True)
        mem.record("家居日用", passed=False, reject_reason="r1")
        assert mem.get("家居日用").image_strategy == {}  # 样本 < 3 不触发

    def test_high_reject_rate_switches_background(self, db, cfg):
        mem = CategoryListingMemory(db, cfg)
        mem.record("家居日用", passed=True)
        mem.record("家居日用", passed=False, reject_reason="r1")
        mem.record("家居日用", passed=False, reject_reason="r2")
        # 3 样本、拒审率 2/3 ≥ 0.5 → 背景 white → scenario
        strategy = mem.strategy_for("家居日用")
        assert strategy.get("background") == "scenario"
        assert strategy.get("reject_rate") == pytest.approx(2 / 3, abs=0.01)
        assert "auto_adjust" in strategy.get("note", "")

    def test_rotation_continues(self, db, cfg):
        mem = CategoryListingMemory(db, cfg)
        mem.update_strategy("宠物用品", {"background": "scenario"})
        mem.record("宠物用品", passed=False, reject_reason="r")
        mem.record("宠物用品", passed=False, reject_reason="r")
        mem.record("宠物用品", passed=False, reject_reason="r")
        assert mem.strategy_for("宠物用品").get("background") == "gradient"

    def test_policy_injected(self, db, cfg):
        policy = MemoryPolicy(reject_rate_threshold=1.0, min_samples=1)
        mem = CategoryListingMemory(db, cfg, policy=policy)
        mem.record("家居日用", passed=False, reject_reason="r")
        assert mem.get("家居日用").image_strategy == {}  # 拒审率 1.0 < 1.0 不触发


# ---------------------------------------------------------------- 全链路（fixtures 离线）

class TestFullChain:
    def test_plan_generate_gate_memory(self, db, cfg, products):
        planner = KimiImagePlanner(cfg)
        provider = WanImageProvider(cfg)  # 默认 out_dir = data/optimization/images
        gate = ImageQualityGate(cfg)
        memory = CategoryListingMemory(db, cfg)
        repo = ImageRepo(db)

        for product in products:
            category = product["category"]
            for image_type in ("main", "detail"):
                plan = planner.plan(product, image_type)
                assert plan.source == "rule_fallback"
                batch_id = f"b_{product['product_id']}_{image_type}"

                # 1) plan → generate
                drafts = [provider.generate(product, plan, v)
                          for v in range(1, len(plan.prompts) + 1)]
                # 2) 落库批次 + 单图（骨架 repo，只使用）
                repo.create_batch(batch_id, product["product_id"], image_type,
                                  plan.model_dump(), len(drafts))
                for v, d in enumerate(drafts, 1):
                    d.batch_id = batch_id
                    repo.upsert_image({
                        "batch_id": batch_id, "product_id": product["product_id"],
                        "image_type": image_type, "variant_no": v,
                        "file_path": d.file_path, "phash": d.phash,
                        "width": d.width, "height": d.height,
                        "quality_json": {}, "quality_ok": False,
                    })
                # 3) gate
                items = [{"image_id": f"{batch_id}_{v}", "file_path": d.file_path}
                         for v, d in enumerate(drafts, 1)]
                result = gate.gate_batch(items, image_type)
                assert result["ok"] is True, result
                if image_type == "main":
                    assert result["similar_pairs"] == []
                # gate_json 只存 JSON 安全结构（pydantic 模型先 model_dump）
                repo.set_batch_status(batch_id, "reviewed", gate={
                    "ok": result["ok"],
                    "threshold": result["threshold"],
                    "similar_pairs": result["similar_pairs"],
                    "verdicts": [v.model_dump() for v in result["verdicts"]],
                })

                # 4) memory：本批次通过
                memory.record(category, passed=True)

            # 主图 5 张 phash 两两 > 8（验收 #3）
            plan_main = planner.plan(product, "main")
            drafts = [provider.generate(product, plan_main, v) for v in range(1, 6)]
            for i in range(5):
                for j in range(i + 1, 5):
                    assert hamming_distance(drafts[i].phash, drafts[j].phash) > 8

        # 库内断言：opt_images 行数 = 2 商品 × (5 主图 + 3 详情图)
        with db.session() as s:
            from optimization.tables import OptImage
            total = s.execute(select(func.count()).select_from(OptImage)).scalar()
            assert total == 2 * 8

        # 类目记忆：两个类目各 2 次通过（main + detail）
        assert memory.get("家居日用").pass_count == 2
        assert memory.get("宠物用品").pass_count == 2


# ---------------------------------------------------------------- 合规（供应链词零命中）

class TestCompliance:
    @pytest.mark.parametrize("fixture_name", ["product_fixture.json", "product_fixture_pet.json"])
    def test_prompts_no_supply_chain_words(self, cfg, fixture_name):
        product = _load_fixture(fixture_name)
        planner = KimiImagePlanner(cfg)
        for image_type in ("main", "detail"):
            plan = planner.plan(product, image_type)
            # 提示词与策略文本全部零命中供应链词
            for text in [plan.strategy, *plan.prompts]:
                hits = check_supply_chain(text)
                assert hits == [], f"{fixture_name}/{image_type} 命中供应链词 {hits}"

    @pytest.mark.parametrize("fixture_name", ["product_fixture.json", "product_fixture_pet.json"])
    def test_llm_prompts_sanitized(self, cfg, fixture_name, monkeypatch):
        """LLM 返回含供应链词的提示词 → 清洗后零命中。"""
        monkeypatch.setenv("KIMI_API_KEY", "sk-test-placeholder-not-real")
        product = _load_fixture(fixture_name)
        raw = [
            "电商商品主图：1688 源头工厂直发，纯白背景，正面平视",
            "电商商品主图：厂家批发价，浅灰背景，微俯视",
            "电商商品主图：一件代发包邮，白底，侧视角",
            "电商商品主图：纯白背景，平视略仰，突出使用场景",
            "电商商品主图：俯视六十度，白底，突出颜色包装",
        ]
        body = json.dumps({"choices": [{"message": {"content": json.dumps({
            "strategy": "批发供应链词必须清洗", "prompts": raw})}}]})

        def post(url, headers, payload, timeout):
            return 200, body

        plan = KimiImagePlanner(cfg, post=post).plan(product, "main")
        for p in plan.prompts:
            assert check_supply_chain(p) == []
            for w in SUPPLY_WORDS:
                assert w not in p
        assert check_supply_chain(plan.strategy) == []


# ---------------------------------------------------------------- 无明文密钥

class TestSecrets:
    def test_no_plaintext_keys_in_modules(self):
        """images 子包代码不得含明文密钥字面量（sk-/api_key 值形式）。"""
        here = Path(__file__).resolve().parent.parent / "optimization" / "images"
        for py in sorted(here.glob("*.py")):
            text = py.read_text(encoding="utf-8")
            assert "sk-" not in text, f"{py.name} 含疑似明文密钥"
            assert "sk_test" not in text
            assert "api_key=" not in text.lower().replace("api_key_env", "")

    def test_keys_only_from_env(self, cfg):
        planner = KimiImagePlanner(cfg)
        provider = WanImageProvider(cfg)
        assert planner.key_env == "KIMI_API_KEY" and "sk-" not in planner.key_env
        assert provider.key_env == "WAN_API_KEY" and "sk-" not in provider.key_env
