"""M3 文案管线（copywriting · 子代理-A3 收尾 v0.2）测试。

覆盖 5 能力（全部 fixtures 离线模式：autouse 删除 DEEPSEEK_API_KEY，零网络）：
1. 标题清洗（TitleCleaner/clean_title）：两商品样本脏词零残留 + 过短拒绝 + 超长截断；
2. 口播稿（ScriptGenerator）：无 Key → rule_fallback，仅拼接 SKU 真实规格，
   sku_basis 留痕依据字段，check_text 通过；
3. 投放文案/角标（AdBadgeGenerator）：候选 ≥ config 下限、两两不同、合规必过；
4. 落库（CopywriteRepo.upsert + Database sqlite:///:memory:）：status/source/char_len 校验；
5. LLM 降级（DeepSeekClient）：无 Key → None + last_error="no_api_key"（不发起网络请求）。

运行：python -m pytest tests/test_optimization_copywriting.py -q --basetemp=".pytest-tmp-m3"
（P-011：独立 basetemp，禁止共用 .pytest-tmp）
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from optimization.compliance import check_text
from optimization.config import load_config
from optimization.copywriting import (
    AdBadgeGenerator,
    DeepSeekClient,
    ScriptGenerator,
    TitleCleaner,
    clean_title,
)
from optimization.db import Database
from optimization.models import CopywriteDraft, TitleCleanResult
from optimization.repo import CopywriteRepo

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures" / "optimization"


# ---------------------------------------------------------------- fixtures

def _load_fixture(name: str) -> dict:
    with open(FIXTURES / name, encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture
def products() -> list[dict]:
    return [_load_fixture("product_fixture.json"), _load_fixture("product_fixture_pet.json")]


@pytest.fixture
def house_product(products) -> dict:
    return products[0]  # 家居日用（含 包邮/2025新款/官方旗舰店同款 脏词）


@pytest.fixture
def pet_product(products) -> dict:
    return products[1]  # 宠物用品（含 厂家直发/一件代发 脏词）


@pytest.fixture
def cfg():
    """内存库配置（避开 .pytest-tmp 文件锁，P-011）。"""
    return load_config(db_url="sqlite:///:memory:", fixtures_dir=FIXTURES)


@pytest.fixture
def db(cfg):
    database = Database(cfg)
    database.create_all()
    return database


@pytest.fixture(autouse=True)
def _offline_env(monkeypatch):
    """默认零 API Key（fixtures 离线模式）；单测按需 setenv 覆盖。"""
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)


# ---------------------------------------------------------------- 包级接口

class TestPackageInterface:
    def test_public_exports(self):
        from optimization.copywriting import __all__

        for name in [
            "TitleCleaner", "clean_title",
            "ScriptGenerator", "generate_script",
            "AdBadgeGenerator", "generate_ads", "generate_badges",
            "DeepSeekClient",
        ]:
            assert name in __all__, f"{name} 未导出"

    def test_package_docstring_describes_pipeline(self):
        import optimization.copywriting as cp

        doc = cp.__doc__ or ""
        assert "文案管线" in doc and "合规" in doc


# ---------------------------------------------------------------- 标题清洗

class TestTitleCleaner:
    def test_house_fixture_cleaned(self, cfg, house_product):
        res = clean_title(house_product["taobao_original_title"], cfg)
        assert isinstance(res, TitleCleanResult)
        assert res.ok, res.reasons
        assert 15 <= res.char_len <= 35, res.char_len
        assert len(res.title) == res.char_len
        # 无供应链/品牌/功效/广告禁用词（用 optimization.compliance.check_text 断言）
        assert check_text(res.title) == [], (res.title, check_text(res.title))
        # 脏词零残留
        for w in ["包邮", "2025", "新款", "官方", "旗舰店", "同款", "热卖"]:
            assert w not in res.title, f"残留脏词：{w}"
        # 证据留痕：营销词/品牌词/广告禁用词命中记录
        assert "包邮" in res.removed.get("营销词", [])
        assert "同款" in res.removed.get("广告禁用词", [])
        assert any("官方旗舰店" in w for w in res.removed.get("品牌词", []))

    def test_pet_fixture_cleaned(self, cfg, pet_product):
        res = clean_title(pet_product["taobao_original_title"], cfg)
        assert res.ok, res.reasons
        assert 15 <= res.char_len <= 35, res.char_len
        assert check_text(res.title) == [], (res.title, check_text(res.title))
        for w in ["厂家", "直发", "一件代发", "2025", "新款"]:
            assert w not in res.title, f"残留脏词：{w}"
        # 供应链词证据：一件代发 / 厂家 均命中
        supply = res.removed.get("供应链词", [])
        assert "一件代发" in supply and "厂家" in supply

    def test_too_short_rejected(self, cfg):
        res = clean_title("水杯", cfg)
        assert res.ok is False
        assert res.char_len < 15
        assert any("不足" in r or "下限" in r for r in res.reasons)
        assert check_text(res.title) == []

    def test_overlong_truncated(self, cfg):
        long_title = (
            "北欧风陶瓷马克杯 简约家用办公室水杯 北欧风陶瓷马克杯 "
            "简约家用办公室水杯 北欧风陶瓷马克杯"
        )
        res = clean_title(long_title, cfg)
        assert res.ok, res.reasons
        assert res.char_len <= 35
        assert res.char_len >= 15
        assert len(res.title) == res.char_len
        assert check_text(res.title) == []
        assert any("截断" in r for r in res.reasons)

    def test_only_dirty_words_rejected(self, cfg):
        res = clean_title("【官方旗舰店】包邮 2025新款 同款", cfg)
        assert res.ok is False
        assert res.title == ""

    def test_instance_api_matches_module_level(self, cfg, house_product):
        res1 = TitleCleaner(cfg).clean(house_product["taobao_original_title"])
        res2 = clean_title(house_product["taobao_original_title"], cfg)
        assert res1 == res2 and res1.ok


# ---------------------------------------------------------------- 口播稿

class TestScriptGenerator:
    def test_house_rule_fallback(self, cfg, house_product):
        os.environ.pop("DEEPSEEK_API_KEY", None)  # 任务要求：显式移除（autouse 已隔离）
        draft = ScriptGenerator(cfg).generate(
            house_product["product_id"],
            house_product["category"],
            house_product["sku_spec_json"],
        )
        assert draft.copy_type == "script"
        assert draft.source == "rule_fallback"
        assert draft.passed is True
        assert draft.compliance_hits == []
        assert check_text(draft.content) == [], (draft.content, check_text(draft.content))
        # 内容基于 SKU 真实规格（「甄选」「陶瓷」等字段句）
        assert "甄选陶瓷材质" in draft.content
        assert "350ml" in draft.content
        assert "白色" in draft.content and "墨绿" in draft.content and "燕麦色" in draft.content
        assert "产地潮州" in draft.content
        # 防虚假承诺：无赠品/效果承诺字眼
        assert "送" not in draft.content and "赠" not in draft.content
        # sku_basis 留痕依据字段（_FIELD_ORDER 顺序）
        assert draft.sku_basis["used_fields"] == ["材质", "容量", "颜色", "数量", "包装", "产地"]
        assert draft.variant_no == 1
        assert draft.char_len == len(draft.content)

    def test_pet_rule_fallback(self, cfg, pet_product):
        os.environ.pop("DEEPSEEK_API_KEY", None)
        draft = ScriptGenerator(cfg).generate(
            pet_product["product_id"],
            pet_product["category"],
            pet_product["sku_spec_json"],
        )
        assert draft.source == "rule_fallback"
        assert draft.passed is True
        assert "甄选高密度瓦楞纸材质" in draft.content
        assert "50x35x8cm" in draft.content
        assert draft.sku_basis["used_fields"] == ["材质", "尺寸", "颜色", "数量", "包装"]
        assert check_text(draft.content) == []

    def test_llm_success_when_key_and_valid(self, cfg, house_product, monkeypatch):
        monkeypatch.setenv("DEEPSEEK_API_KEY", "placeholder-key-not-real")
        llm_content = (
            "今天给大家带来一款家居日用好物，甄选陶瓷材质，容量350ml，"
            "颜色多样可选，喜欢的朋友可以放心入手。"
        )
        body = json.dumps({"choices": [{"message": {"content": json.dumps({
            "content": llm_content, "selling_points": ["甄选陶瓷材质"]})}}]})
        called: list[int] = []

        def post(url, headers, payload, timeout):
            called.append(1)
            assert "Authorization" in headers and headers["Authorization"].startswith("Bearer ")
            assert "placeholder-key-not-real" not in json.dumps(payload)  # 无明文密钥落 payload
            return 200, body

        draft = ScriptGenerator(cfg, llm=DeepSeekClient(cfg, post=post)).generate(
            house_product["product_id"], house_product["category"], house_product["sku_spec_json"]
        )
        assert called, "有 Key 时应发起一次请求"
        assert draft.source == "llm"
        assert draft.passed is True
        assert "甄选陶瓷材质" in draft.content

    def test_llm_compliance_hits_fall_back(self, cfg, house_product, monkeypatch):
        monkeypatch.setenv("DEEPSEEK_API_KEY", "placeholder-key-not-real")
        body = json.dumps({"choices": [{"message": {"content": json.dumps({
            "content": (
                "厂家直发一件代发，今天给大家带来一款家居日用好物，"
                "甄选陶瓷材质，容量350ml，喜欢的朋友可以放心入手。"
            ),
            "selling_points": ["x"]})}}]})

        def post(url, headers, payload, timeout):
            return 200, body

        draft = ScriptGenerator(cfg, llm=DeepSeekClient(cfg, post=post)).generate(
            house_product["product_id"], house_product["category"], house_product["sku_spec_json"]
        )
        assert draft.source == "rule_fallback"
        assert draft.sku_basis["meta"].get("llm_rejected") == "compliance_hits"
        assert check_text(draft.content) == []


# ---------------------------------------------------------------- 投放文案 / 角标

class TestAdBadgeGenerator:
    def test_ads_min_variants(self, cfg, house_product):
        ads = AdBadgeGenerator(cfg).generate_ads(
            house_product["product_id"], house_product["category"], house_product["sku_spec_json"]
        )
        min_count = cfg.copywriting.ad_variants_min
        assert min_count == 2
        assert len(ads) >= min_count
        contents = [a.content for a in ads]
        assert len(set(contents)) == len(contents)  # 候选间内容不同
        for i, a in enumerate(ads, start=1):
            assert a.copy_type == "ad"
            assert a.variant_no == i
            assert a.passed is True
            assert a.compliance_hits == []
            assert check_text(a.content) == [], (a.content, check_text(a.content))
            assert a.source == "rule_fallback"

    def test_badges_min_variants(self, cfg, pet_product):
        badges = AdBadgeGenerator(cfg).generate_badges(
            pet_product["product_id"], pet_product["category"], pet_product["sku_spec_json"]
        )
        min_count = cfg.copywriting.badge_variants_min
        assert min_count == 2
        assert len(badges) >= min_count
        contents = [b.content for b in badges]
        assert len(set(contents)) == len(contents)  # 候选间内容不同
        for i, b in enumerate(badges, start=1):
            assert b.copy_type == "badge"
            assert b.variant_no == i
            assert b.passed is True
            assert check_text(b.content) == [], (b.content, check_text(b.content))
            assert len(b.content) <= 8  # 角标 ≤ 8 字（规则模板保证）

    @pytest.mark.parametrize("fixture_name", ["product_fixture.json", "product_fixture_pet.json"])
    def test_ads_badges_for_both_fixtures(self, cfg, fixture_name):
        product = _load_fixture(fixture_name)
        gen = AdBadgeGenerator(cfg)
        ads = gen.generate_ads(product["product_id"], product["category"], product["sku_spec_json"])
        badges = gen.generate_badges(product["product_id"], product["category"], product["sku_spec_json"])
        assert len(ads) >= 2 and len(badges) >= 2
        for c in [a.content for a in ads] + [b.content for b in badges]:
            assert check_text(c) == [], (c, check_text(c))
        assert len({a.content for a in ads}) == len(ads)
        assert len({b.content for b in badges}) == len(badges)


# ---------------------------------------------------------------- 落库（CopywriteRepo）

class TestPersistence:
    def test_upsert_script_and_query(self, db, cfg, house_product):
        os.environ.pop("DEEPSEEK_API_KEY", None)
        draft = ScriptGenerator(cfg).generate(
            house_product["product_id"], house_product["category"], house_product["sku_spec_json"]
        )
        repo = CopywriteRepo(db)
        cw_id = repo.upsert(draft)
        assert cw_id.startswith("cw_")
        rows = repo.list_by_product(house_product["product_id"], copy_type="script")
        assert len(rows) == 1
        row = rows[0]
        assert row["status"] == "passed"
        assert row["source"] == "rule_fallback"
        assert row["char_len"] == draft.char_len == len(draft.content)
        assert row["copy_type"] == "script"
        assert row["variant_no"] == 1
        assert row["content"] == draft.content

    def test_upsert_idempotent(self, db, cfg, house_product):
        os.environ.pop("DEEPSEEK_API_KEY", None)
        draft = ScriptGenerator(cfg).generate(
            house_product["product_id"], house_product["category"], house_product["sku_spec_json"]
        )
        repo = CopywriteRepo(db)
        repo.upsert(draft)
        repo.upsert(draft)  # 同 (product_id, copy_type, variant_no) 覆盖更新
        rows = repo.list_by_product(house_product["product_id"], copy_type="script")
        assert len(rows) == 1

    def test_ads_and_badges_persisted(self, db, cfg, house_product):
        gen = AdBadgeGenerator(cfg)
        repo = CopywriteRepo(db)
        for d in gen.generate_ads(house_product["product_id"], house_product["category"],
                                  house_product["sku_spec_json"]):
            repo.upsert(d)
        for d in gen.generate_badges(house_product["product_id"], house_product["category"],
                                     house_product["sku_spec_json"]):
            repo.upsert(d)
        ads = repo.list_by_product(house_product["product_id"], copy_type="ad")
        badges = repo.list_by_product(house_product["product_id"], copy_type="badge")
        assert len(ads) >= 2 and len(badges) >= 2
        for r in ads + badges:
            assert r["status"] == "passed"
            assert r["source"] == "rule_fallback"
            assert r["char_len"] == len(r["content"])

    def test_rejected_draft_status(self, db, cfg, house_product):
        draft = CopywriteDraft(
            product_id=house_product["product_id"], copy_type="title",
            content="含一件代发的坏标题", variant_no=1,
            char_len=len("含一件代发的坏标题"),
            compliance_hits=["供应链词:一件代发"], passed=False, source="rule_fallback",
        )
        repo = CopywriteRepo(db)
        repo.upsert(draft)
        rows = repo.list_by_product(house_product["product_id"], copy_type="title")
        assert len(rows) == 1
        assert rows[0]["status"] == "rejected"


# ---------------------------------------------------------------- LLM 降级

class TestDeepSeekDegradation:
    def test_no_key_returns_none_no_network(self, cfg):
        os.environ.pop("DEEPSEEK_API_KEY", None)  # 任务要求：显式移除
        assert DeepSeekClient(cfg).has_key() is False

        def post(*args, **kwargs):
            raise AssertionError("无 Key 不应发起网络请求")

        client = DeepSeekClient(cfg, post=post)
        out = client.generate_structured("system", "user", {"type": "object"})
        assert out is None
        assert client.last_error == "no_api_key"

    def test_transport_error_retries_then_none(self, cfg, monkeypatch):
        monkeypatch.setenv("DEEPSEEK_API_KEY", "placeholder-key-not-real")
        attempts: list[int] = []

        def post(url, headers, payload, timeout):
            attempts.append(1)
            raise TimeoutError("socket timeout")

        client = DeepSeekClient(cfg, post=post)
        out = client.generate_structured("s", "u", {"type": "object"})
        assert out is None
        assert client.last_error == "transport:TimeoutError"
        assert len(attempts) == cfg.llm.max_retries + 1 == 3

    def test_http_500_then_none(self, cfg, monkeypatch):
        monkeypatch.setenv("DEEPSEEK_API_KEY", "placeholder-key-not-real")

        def post(url, headers, payload, timeout):
            return 500, "boom"

        client = DeepSeekClient(cfg, post=post)
        assert client.generate_structured("s", "u", {"type": "object"}) is None
        assert client.last_error == "http_500"

    def test_success_returns_parsed_and_clears_error(self, cfg, monkeypatch):
        monkeypatch.setenv("DEEPSEEK_API_KEY", "placeholder-key-not-real")
        body = json.dumps({"choices": [{"message": {"content": json.dumps({
            "name": "测试商品", "tags": ["a", "b"]})}}]})
        schema = {
            "type": "object",
            "properties": {
                "name": {"type": "string", "minLength": 1},
                "tags": {"type": "array", "items": {"type": "string", "minLength": 1}},
            },
            "required": ["name", "tags"],
        }

        def post(url, headers, payload, timeout):
            assert "Authorization" in headers and headers["Authorization"].startswith("Bearer ")
            assert "placeholder-key-not-real" not in json.dumps(payload)
            return 200, body

        client = DeepSeekClient(cfg, post=post)
        out = client.generate_structured("s", "u", schema)
        assert out == {"name": "测试商品", "tags": ["a", "b"]}
        assert client.last_error == ""


# ---------------------------------------------------------------- 全链路（fixtures 离线）

class TestFullChain:
    def test_clean_script_ads_badges_persist_all(self, db, cfg, products):
        repo = CopywriteRepo(db)
        for product in products:
            pid = product["product_id"]
            # 1) 标题
            title = clean_title(product["taobao_original_title"], cfg)
            assert title.ok, title.reasons
            repo.upsert(CopywriteDraft(
                product_id=pid, copy_type="title", content=title.title,
                variant_no=1, char_len=title.char_len,
                compliance_hits=[], passed=title.ok, source="rule_fallback",
            ))
            # 2) 口播稿（无 Key → 规则降级）
            script = ScriptGenerator(cfg).generate(pid, product["category"], product["sku_spec_json"])
            assert script.source == "rule_fallback"
            repo.upsert(script)
            # 3) 投放文案 / 角标
            for d in AdBadgeGenerator(cfg).generate_ads(pid, product["category"], product["sku_spec_json"]):
                repo.upsert(d)
            for d in AdBadgeGenerator(cfg).generate_badges(pid, product["category"], product["sku_spec_json"]):
                repo.upsert(d)
            # 落库断言
            assert len(repo.list_by_product(pid, copy_type="title")) == 1
            assert len(repo.list_by_product(pid, copy_type="script")) == 1
            assert len(repo.list_by_product(pid, copy_type="ad")) >= 2
            assert len(repo.list_by_product(pid, copy_type="badge")) >= 2
        with db.session() as s:
            from optimization.tables import OptCopywrite
            from sqlalchemy import func, select

            total = s.execute(select(func.count()).select_from(OptCopywrite)).scalar()
            assert total == 2 * (1 + 1 + 3 + 4), total  # 标题/口播 + ad3 + badge4 × 2 商品


# ---------------------------------------------------------------- 无明文密钥

class TestSecrets:
    def test_no_plaintext_keys_in_modules(self):
        """copywriting 子包代码不得含明文密钥字面量（sk-/api_key= 值形式）。"""
        here = Path(__file__).resolve().parent.parent / "optimization" / "copywriting"
        for py in sorted(here.glob("*.py")):
            text = py.read_text(encoding="utf-8")
            assert "sk-" not in text, f"{py.name} 含疑似明文密钥"
            assert "api_key=" not in text.lower().replace("api_key_env", "")

    def test_key_env_name_only(self, cfg):
        client = DeepSeekClient(cfg)
        assert client.key_env == "DEEPSEEK_API_KEY"
        assert "sk-" not in client.key_env
