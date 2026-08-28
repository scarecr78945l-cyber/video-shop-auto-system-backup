"""M2 素材标签化与内容合规预审（子代理 B4-1）测试。

零外网零浏览器零 ffmpeg：纯代码 + 临时 SQLite（db_materials fixture，独立 basetemp）。
覆盖：generate_tags（平台/达人/类目/标题关键词/去重截断/空输入/配置覆盖）；
check_material 四类检查与 pass/review 路径（供应链词参数化 6 词）；
evaluate_and_record 证据留痕集成（pass→passed / reject→rejected + hit_words_json 落库
/ review 语义保持 pending / derivation_note 进 note）；
mark_platform_rejected → upload_status=disabled 幂等（R-M2-20）；
词库复用验收：tagger 引用的就是 sourcing.compliance 的同名单对象（不复制词表）。
"""

import json

import pytest
from sqlalchemy import select

from materials import tables as T
from materials.config import load_config
from materials.repo import AssetNotFoundError, AssetRepo
from materials.tagger import (
    CHECK_TYPE_BRAND,
    CHECK_TYPE_EFFICACY,
    CHECK_TYPE_PRE_CHECK,
    CHECK_TYPE_PROHIBITED,
    CHECK_TYPE_SUPPLY_CHAIN,
    MaterialCompliance,
    generate_tags,
)


def base_asset(**over):
    data = dict(
        asset_type="video",
        source_platform="视频号",
        source_url="https://example.com/v.mp4",
        source_author="达人A",
        md5="a1b2c3d4e5f60718293a4b5c6d7e8f90",
        phash="0f0f0f0f0f0f0f00",
        file_path="videos/2025/v1.mp4",
        duration=15,
        resolution="720x1280",
        size=204800,
        compliance_status="pending",  # 预审前必须 pending（门禁）
    )
    data.update(over)
    return data


@pytest.fixture()
def comp(cfg_materials) -> MaterialCompliance:
    """显式注入隔离配置，避免读环境变量/默认 .env（测试确定性）。"""
    return MaterialCompliance(config=cfg_materials)


@pytest.fixture()
def repo(db_materials) -> AssetRepo:
    return AssetRepo(db_materials)


# ================================================================ generate_tags
def test_generate_tags_platform_only():
    assert generate_tags("视频号") == ["视频号素材"]
    assert generate_tags("抖音") == ["抖音素材"]


def test_generate_tags_platform_and_author():
    assert generate_tags("抖音", "达人A") == ["抖音素材", "达人A"]


def test_generate_tags_category_hint():
    assert generate_tags("视频号", None, None, "美妆") == ["视频号素材", "美妆"]


def test_generate_tags_title_keywords_dedupe():
    tags = generate_tags("视频号", None, "洁面慕斯 补水 洁面慕斯 补水")
    assert tags == ["视频号素材", "洁面慕斯", "补水"]  # 去重保序


def test_generate_tags_default_stopwords_filtered():
    tags = generate_tags("视频号", None, "好物 推荐 洁面 慕斯")
    assert "好物" not in tags       # 默认停用词剔除
    assert "推荐" not in tags
    assert "洁面" in tags


def test_generate_tags_truncates_to_max_tags():
    tags = generate_tags("视频号", "达人A", "洁面 补水 保湿 修护", max_tags=3)
    assert len(tags) == 3
    assert tags == ["视频号素材", "达人A", "洁面"]


def test_generate_tags_empty_inputs_no_crash():
    assert generate_tags("视频号", None, "") == ["视频号素材"]   # 标题空不崩
    assert generate_tags("视频号", None, None) == ["视频号素材"]
    assert generate_tags(None, None, None) == []
    assert generate_tags("", None, None) == []


def test_generate_tags_unknown_platform_passthrough():
    assert generate_tags("某新平台", None) == ["某新平台"]


def test_generate_tags_config_override(cfg_materials):
    cfg = load_config(
        tagger={"max_tags": 2, "tag_keyword_stopwords": ["洁面"]},
        db_url=cfg_materials.db_url,
        data_dir=cfg_materials.data_dir,
    )
    tags = generate_tags("视频号", "达人A", "洁面 补水", config=cfg)
    assert tags == ["视频号素材", "达人A"]   # 洁面被停用词剔除，且总数上限 2


# ================================================================ check_material
@pytest.mark.parametrize(
    "word",
    ["一件代发", "批发", "供应商", "1688", "厂家直销", "代发"],
)
def test_check_material_supply_chain_rejects(comp, word):
    """R-M2-19 铁律：供应链词命中 → reject（6 词参数化）。"""
    out = comp.check_material(title=f"优质{word}货源")
    assert out["result"] == "reject"
    assert out["check_type"] == CHECK_TYPE_SUPPLY_CHAIN
    assert word in out["hit_words"]["supply_chain_word"]
    assert "供应链词" in str(out["reasons"])


def test_check_material_brand_rejects(comp):
    out = comp.check_material(title="正品耐克运动鞋")
    assert out["result"] == "reject"
    assert out["check_type"] == CHECK_TYPE_BRAND
    assert "耐克" in out["hit_words"]["brand_word"]


def test_check_material_efficacy_review(comp):
    """功效词命中 → review（需资质，人工闸门）。"""
    out = comp.check_material(title="美白祛斑面霜")
    assert out["result"] == "review"
    assert out["check_type"] == CHECK_TYPE_EFFICACY
    assert "美白祛斑" in out["hit_words"]["efficacy_word"]


def test_check_material_prohibited_rejects(comp):
    out = comp.check_material(title="电子烟")
    assert out["result"] == "reject"
    assert out["check_type"] == CHECK_TYPE_PROHIBITED
    assert "电子烟" in out["hit_words"]["prohibited_word"]


def test_check_material_pass_clean(comp):
    out = comp.check_material(title="洁面慕斯清爽补水")
    assert out["result"] == "pass"
    assert out["check_type"] == CHECK_TYPE_PRE_CHECK
    for v in out["hit_words"].values():
        assert v == []


def test_check_material_extra_text_combined(comp):
    """标题 + 附加文本合并检查（文案类字段单独强校验，R-M2-19）。"""
    out = comp.check_material(title="洁面慕斯", extra_text="源头一件代发")
    assert out["result"] == "reject"
    assert out["check_type"] == CHECK_TYPE_SUPPLY_CHAIN
    assert "一件代发" in out["hit_words"]["supply_chain_word"]


def test_check_material_severity_priority(comp):
    """多类同时命中 → 取最严重者（禁售 > 品牌 > 供应链 > 功效）。"""
    out = comp.check_material(title="批发香烟")   # 供应链「批发」+ 禁售「香烟」
    assert out["result"] == "reject"
    assert out["check_type"] == CHECK_TYPE_PROHIBITED


def test_check_material_asset_type_context(comp):
    out = comp.check_material(title="洁面慕斯", asset_type="video")
    assert out["result"] == "pass"
    assert out["asset_type"] == "video"


# ================================================================ evaluate_and_record
def test_evaluate_pass_records_and_syncs_status(repo, comp, db_materials):
    aid = repo.create_asset(**base_asset())
    out = comp.evaluate_and_record(repo, aid, title="洁面慕斯清爽补水")
    assert out["result"] == "pass"
    assert out["check_type"] == CHECK_TYPE_PRE_CHECK
    assert repo.get_asset(aid)["compliance_status"] == "passed"   # repo 同步
    with db_materials.session() as s:
        rows = s.execute(
            select(T.AssetComplianceCheck).where(T.AssetComplianceCheck.asset_id == aid)
        ).scalars().all()
        assert len(rows) == 1
        assert rows[0].check_type == CHECK_TYPE_PRE_CHECK
        assert rows[0].result == "pass"
        assert json.loads(rows[0].hit_words_json)["supply_chain_word"] == []


def test_evaluate_reject_records_hit_words(repo, comp, db_materials):
    aid = repo.create_asset(**base_asset())
    out = comp.evaluate_and_record(repo, aid, title="优质1688货源")
    assert out["result"] == "reject"
    assert out["check_type"] == CHECK_TYPE_SUPPLY_CHAIN
    assert repo.get_asset(aid)["compliance_status"] == "rejected"
    with db_materials.session() as s:
        rows = s.execute(
            select(T.AssetComplianceCheck).where(T.AssetComplianceCheck.asset_id == aid)
        ).scalars().all()
        assert len(rows) == 1
        assert rows[0].check_type == CHECK_TYPE_SUPPLY_CHAIN
        assert rows[0].result == "reject"
        hit = json.loads(rows[0].hit_words_json)
        assert "1688" in hit["supply_chain_word"]      # 命中词证据落库


def test_evaluate_review_keeps_pending(repo, comp, db_materials):
    """review 语义按 repo 实现：合规状态不动（保持 pending，人工闸门）。"""
    aid = repo.create_asset(**base_asset())
    out = comp.evaluate_and_record(repo, aid, title="美白祛斑面霜")
    assert out["result"] == "review"
    assert out["check_type"] == CHECK_TYPE_EFFICACY
    assert repo.get_asset(aid)["compliance_status"] == "pending"
    with db_materials.session() as s:
        rows = s.execute(
            select(T.AssetComplianceCheck).where(T.AssetComplianceCheck.asset_id == aid)
        ).scalars().all()
        assert len(rows) == 1
        assert rows[0].result == "review"


def test_evaluate_records_derivation_note_evidence(repo, comp, db_materials):
    """二创义务标记（R-M2-18）与来源平台上下文进 note 证据。"""
    aid = repo.create_asset(**base_asset())
    comp.evaluate_and_record(
        repo, aid, title="洁面慕斯", derivation_note="去水印/混剪", source_platform="抖音"
    )
    with db_materials.session() as s:
        row = s.execute(
            select(T.AssetComplianceCheck).where(T.AssetComplianceCheck.asset_id == aid)
        ).scalar_one()
        assert "derivation_note=去水印/混剪" in row.note
        assert "source_platform=抖音" in row.note


def test_evaluate_missing_asset_raises(repo, comp):
    with pytest.raises(AssetNotFoundError):
        comp.evaluate_and_record(repo, 99999, title="洁面慕斯")


# ================================================================ 拒审下架 R-M2-20
def test_mark_platform_rejected_disables_and_records_ledger(repo, comp, db_materials):
    aid = repo.create_asset(**base_asset())
    out = comp.mark_platform_rejected(repo, aid, "平台审核不通过")
    assert out["upload_status"] == "disabled"
    assert repo.get_asset(aid)["upload_status"] == "disabled"
    with db_materials.session() as s:
        ups = s.execute(
            select(T.AssetUpload).where(T.AssetUpload.asset_id == aid)
        ).scalars().all()
        assert len(ups) == 1
        assert ups[0].status == "disabled"
        ev = json.loads(ups[0].evidence_json)
        assert ev["reason"] == "平台审核不通过"


def test_mark_platform_rejected_idempotent(repo, comp, db_materials):
    aid = repo.create_asset(**base_asset())
    comp.mark_platform_rejected(repo, aid, "拒审原因A")
    comp.mark_platform_rejected(repo, aid, "拒审原因B")   # 幂等：重复调用直接返回
    assert repo.get_asset(aid)["upload_status"] == "disabled"
    with db_materials.session() as s:
        ups = s.execute(
            select(T.AssetUpload).where(T.AssetUpload.asset_id == aid)
        ).scalars().all()
        assert len(ups) == 1          # 台账不重复


def test_repo_mark_disabled_missing_asset_raises(repo):
    with pytest.raises(AssetNotFoundError):
        repo.mark_disabled(99999, "x")


# ================================================================ 词库复用验收
def test_word_lists_reused_from_sourcing_not_copied():
    """验收 3：词库单一事实源——tagger 引用的就是 sourcing.compliance 的同名单对象。"""
    from sourcing import compliance as src
    from materials import tagger as tag

    assert tag.SUPPLY_CHAIN_WORDS is src.SUPPLY_CHAIN_WORDS
    assert tag.BRAND_WORDS is src.BRAND_WORDS
    assert tag.EFFICACY_WORDS is src.EFFICACY_WORDS
    assert tag.PROHIBITED_WORDS is src.PROHIBITED_WORDS
