"""M2 数据联动服务层测试（子代理 B4-2 + 相关性门 C3 v1.1）：evaluation 回流协议 +
上传小店素材库抽象 + 相关性门预检接口。

- evaluation 回流：合法三值 / 非法枚举→PLATFORM_REJECT / 素材不存在→NO_MATCH /
  幂等（重复回写同值，repo 台账语义）/ get_evaluation 读当前值；
- 上传抽象：mock provider 成功→mark_uploaded+asset_uploads 记录 / 失败分类
  （TIMEOUT/PLATFORM_REJECT/UNEXPECTED）/ 已上传幂等 / 冲突 / 素材不存在 /
  真实骨架 NotImplementedError / provider 工厂与配置；
- 相关性门（REC-迁移-03 C3）：receive_relevance 三态映射（pass→passed/
  reject→failed/manual_review→manual_review）/ 非法→PLATFORM_REJECT /
  素材不存在→NO_MATCH / 幂等收敛（changed 语义）/ is_ready_for_chain
  （仅 passed 放行，failed 淘汰、manual_review 待人工、pending 未判定）；
- 全零外网零登录态（R-M2-17）：上传走 MockUploadProvider fixtures，不触碰真实 API。
"""

import pytest
from sqlalchemy import select

from materials import tables as T
from materials.config import EVALUATION_VALUES as CFG_EVALUATION_VALUES
from materials.config import RELEVANCE_RESULT_TO_STATUS as CFG_RESULT_TO_STATUS
from materials.config import RELEVANCE_STATUS_VALUES as CFG_RELEVANCE_STATUS_VALUES
from materials.config import load_config
from materials.integration import (
    EVALUATION_VALUES,
    RELEVANCE_RESULT_TO_STATUS,
    RELEVANCE_STATUS_VALUES,
    EvaluationFeedbackService,
    MaterialUploadService,
    MockUploadProvider,
    RelevanceGateService,
    ShopMaterialUploadProvider,
    UploadProvider,
    build_upload_provider,
)
from materials.repo import AssetRepo


# ---------------------------------------------------------------- 测试工具
def base_video(**over):
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
        compliance_status="passed",
    )
    data.update(over)
    return data


def base_image(**over):
    data = dict(
        asset_type="image",
        source_platform="抖音",
        source_url="https://example.com/i.jpg",
        source_author="达人B",
        md5="feedfacecafebeef0000000000000001",
        phash="1010101010101010",
        file_path="images/2025/i1.jpg",
        size=51200,
        compliance_status="passed",
    )
    data.update(over)
    return data


def make_repo(db_materials) -> AssetRepo:
    return AssetRepo(db_materials)


def make_eval_service(db_materials) -> EvaluationFeedbackService:
    return EvaluationFeedbackService(make_repo(db_materials))


# ================================================================ evaluation 回流
def test_evaluation_values_aligned_with_config():
    """integration.EVALUATION_VALUES 与 config.py 同口径（唯一枚举源）。"""
    assert EVALUATION_VALUES == CFG_EVALUATION_VALUES == ("exploring", "efficient", "potential")


def test_receive_evaluation_all_three_values(db_materials):
    """合法三值端到端：写审计 + 更新 asset_items.evaluation（context 3.3 / 1.4）。"""
    svc = make_eval_service(db_materials)
    repo = make_repo(db_materials)
    aid = repo.create_asset(**base_video())
    assert svc.get_evaluation(aid) is None  # M2 入库时 evaluation 为空
    for idx, value in enumerate(("exploring", "efficient", "potential")):
        out = svc.receive_evaluation(aid, value, {"batch": f"B{idx}"}, "M5")
        assert out == {
            "ok": True,
            "asset_id": aid,
            "evaluation": value,
            "recorded": True,
        }
        assert repo.get_asset(aid)["evaluation"] == value  # 只存当前值
    with db_materials.session() as s:
        audits = s.execute(
            select(T.AssetEvaluation).where(T.AssetEvaluation.asset_id == aid)
        ).scalars().all()
        assert len(audits) == 3                       # 每次回写留痕
        assert [a.evaluation for a in audits] == ["exploring", "efficient", "potential"]
        assert all(a.source_agent == "M5" for a in audits)
        assert audits[0].evidence_json == '{"batch": "B0"}'


def test_receive_evaluation_invalid_enum_rejected(db_materials):
    """非法枚举 → PLATFORM_REJECT 结构化返回，不落库不污染当前值。"""
    svc = make_eval_service(db_materials)
    repo = make_repo(db_materials)
    aid = repo.create_asset(**base_video())
    out = svc.receive_evaluation(aid, "great")
    assert out["ok"] is False
    assert out["code"] == "PLATFORM_REJECT"
    assert "invalid evaluation" in out["reason"]
    assert out["asset_id"] == aid
    assert repo.get_asset(aid)["evaluation"] is None
    with db_materials.session() as s:
        assert s.execute(select(T.AssetEvaluation)).scalars().all() == []


def test_receive_evaluation_asset_missing_no_match(db_materials):
    """素材不存在 → NO_MATCH 结构化返回。"""
    svc = make_eval_service(db_materials)
    out = svc.receive_evaluation(99999, "exploring", None, "M5")
    assert out["ok"] is False
    assert out["code"] == "NO_MATCH"
    assert out["asset_id"] == 99999


def test_receive_evaluation_idempotent_same_value(db_materials):
    """重复回写同值幂等：收敛不报错（repo 台账语义：审计表每次回写留痕）。"""
    svc = make_eval_service(db_materials)
    repo = make_repo(db_materials)
    aid = repo.create_asset(**base_video())
    r1 = svc.receive_evaluation(aid, "exploring", {"batch": "B1"}, "M5")
    r2 = svc.receive_evaluation(aid, "exploring", {"batch": "B1"}, "M5")
    assert r1["ok"] is True and r2["ok"] is True
    assert r1["evaluation"] == r2["evaluation"] == "exploring"
    assert repo.get_asset(aid)["evaluation"] == "exploring"  # 当前值收敛
    with db_materials.session() as s:
        audits = s.execute(
            select(T.AssetEvaluation).where(T.AssetEvaluation.asset_id == aid)
        ).scalars().all()
        assert len(audits) == 2                    # 台账语义：每次回写留痕（对齐 repo 契约）
        assert {a.evaluation for a in audits} == {"exploring"}


def test_get_evaluation_reads_current(db_materials):
    """get_evaluation 读当前标签；未回写/素材不存在返回 None。"""
    svc = make_eval_service(db_materials)
    repo = make_repo(db_materials)
    aid = repo.create_asset(**base_video())
    assert svc.get_evaluation(aid) is None
    svc.receive_evaluation(aid, "potential", {"batch": "B1"}, "M5")
    assert svc.get_evaluation(aid) == "potential"
    assert svc.get_evaluation(99999) is None


# ================================================================ 上传抽象
def test_upload_provider_abstract_cannot_instantiate():
    with pytest.raises(TypeError):
        UploadProvider()


def test_mock_provider_health():
    assert MockUploadProvider().health() == {"ok": True, "mode": "mock", "calls": 0}
    assert MockUploadProvider(fail_code="TIMEOUT").health()["ok"] is False


def test_upload_success_writes_backfill_and_record(db_materials):
    """mock provider 成功：mark_uploaded 回填 + asset_uploads 记录 + metadata 透传。"""
    repo = make_repo(db_materials)
    provider = MockUploadProvider()
    svc = MaterialUploadService(repo, provider)
    aid = repo.create_asset(**base_video())
    out = svc.upload(aid, title="素材-01")
    assert out == {
        "ok": True,
        "asset_id": aid,
        "platform_material_id": f"mock-mat-{aid}",
        "already_uploaded": False,
    }
    assert provider.calls and provider.calls[0]["title"] == "素材-01"
    assert provider.calls[0]["file_path"] == "videos/2025/v1.mp4"
    assert provider.calls[0]["metadata"]["asset_type"] == "video"
    asset = repo.get_asset(aid)
    assert asset["upload_status"] == "uploaded"
    assert asset["platform_material_id"] == f"mock-mat-{aid}"
    with db_materials.session() as s:
        ups = s.execute(
            select(T.AssetUpload).where(T.AssetUpload.asset_id == aid)
        ).scalars().all()
        assert len(ups) == 1
        assert ups[0].status == "success"
        assert ups[0].attempt == 1
        assert ups[0].platform_material_id == f"mock-mat-{aid}"
    assert svc.health() == {"ok": True, "mode": "mock", "calls": 1}


def test_upload_already_uploaded_idempotent(db_materials):
    """已上传幂等：platform_material_id 已存在 → 直接返回，不再调 provider、不重复插记录。"""
    repo = make_repo(db_materials)
    provider = MockUploadProvider()
    svc = MaterialUploadService(repo, provider)
    aid = repo.create_asset(**base_video())
    svc.upload(aid)
    n_calls = len(provider.calls)
    out = svc.upload(aid)
    assert out["ok"] is True
    assert out["already_uploaded"] is True
    assert out["platform_material_id"] == f"mock-mat-{aid}"
    assert len(provider.calls) == n_calls          # 幂等：不再调 provider
    with db_materials.session() as s:
        assert len(s.execute(select(T.AssetUpload)).scalars().all()) == 1  # 不重复插记录


@pytest.mark.parametrize(
    ("fail_code", "expected_code"),
    [
        ("TIMEOUT", "TIMEOUT"),
        ("PLATFORM_REJECT", "PLATFORM_REJECT"),
        ("UNEXPECTED", "UNEXPECTED"),
    ],
)
def test_upload_failure_classified(db_materials, fail_code, expected_code):
    """失败分类结构化返回（不抛出）：不污染 upload_status、不写上传记录。"""
    repo = make_repo(db_materials)
    provider = MockUploadProvider(fail_code=fail_code)
    svc = MaterialUploadService(repo, provider)
    aid = repo.create_asset(**base_video())
    out = svc.upload(aid)
    assert out["ok"] is False
    assert out["code"] == expected_code
    assert out["asset_id"] == aid
    assert "reason" in out
    asset = repo.get_asset(aid)
    assert asset["upload_status"] == "local"       # 失败不污染状态
    assert asset["platform_material_id"] is None
    with db_materials.session() as s:
        assert s.execute(select(T.AssetUpload)).scalars().all() == []  # 失败不写记录


def test_upload_asset_missing_no_match(db_materials):
    """素材不存在 → NO_MATCH，不调 provider。"""
    repo = make_repo(db_materials)
    provider = MockUploadProvider()
    svc = MaterialUploadService(repo, provider)
    out = svc.upload(99999)
    assert out["ok"] is False
    assert out["code"] == "NO_MATCH"
    assert provider.calls == []


def test_upload_platform_material_id_conflict(db_materials):
    """platform_material_id 被其他素材占用 → PLATFORM_REJECT（防重复回填）。"""
    repo = make_repo(db_materials)
    a1 = repo.create_asset(**base_video())
    a2 = repo.create_asset(**base_image())
    repo.mark_uploaded(a1, "mat-conflict")
    svc = MaterialUploadService(repo, MockUploadProvider(material_id="mat-conflict"))
    out = svc.upload(a2)
    assert out["ok"] is False
    assert out["code"] == "PLATFORM_REJECT"
    assert "already owned by asset" in out["reason"]
    assert repo.get_asset(a2)["upload_status"] == "local"


def test_shop_provider_skeleton_not_implemented():
    """真实 provider 骨架：待小店素材库 API/登录态确认，方法抛 NotImplementedError。"""
    prov = ShopMaterialUploadProvider()
    with pytest.raises(NotImplementedError):
        prov.upload(1, "videos/x.mp4", "t", {})
    with pytest.raises(NotImplementedError):
        prov.health()


def test_upload_config_and_factory(monkeypatch):
    """config.upload：mode 默认 mock（env MATERIALS_UPLOAD_MODE 覆盖）+ 工厂接线。"""
    monkeypatch.delenv("MATERIALS_UPLOAD_MODE", raising=False)
    cfg = load_config()
    assert cfg.upload.mode == "mock"               # 默认 mock（fixtures）
    assert isinstance(build_upload_provider(cfg), MockUploadProvider)
    monkeypatch.setenv("MATERIALS_UPLOAD_MODE", "shop")
    assert load_config().upload.mode == "shop"     # 环境变量覆盖
    assert isinstance(build_upload_provider(load_config()), ShopMaterialUploadProvider)
    # 按字段名覆盖（populate_by_name，测试/CLI 常用）
    assert load_config(upload={"mode": "shop"}).upload.mode == "shop"


# ================================================================ 相关性门（REC-迁移-03 C3）
def make_relevance_service(db_materials) -> RelevanceGateService:
    return RelevanceGateService(make_repo(db_materials))


def test_relevance_status_values_aligned_with_config():
    """integration 枚举/映射与 config.py 同口径（唯一枚举源）。"""
    assert RELEVANCE_STATUS_VALUES == CFG_RELEVANCE_STATUS_VALUES == (
        "pending", "passed", "failed", "manual_review",
    )
    assert RELEVANCE_RESULT_TO_STATUS == CFG_RESULT_TO_STATUS == {
        "pass": "passed",
        "reject": "failed",
        "manual_review": "manual_review",
    }


def test_receive_relevance_three_states(db_materials):
    """M3 三态结果消费：pass→passed / reject→failed / manual_review→manual_review。"""
    svc = make_relevance_service(db_materials)
    repo = make_repo(db_materials)
    aid = repo.create_asset(**base_video())
    assert svc.get_relevance_status(aid) == "pending"   # 入库默认 pending
    for result, status in (
        ("pass", "passed"),
        ("reject", "failed"),
        ("manual_review", "manual_review"),
    ):
        out = svc.receive_relevance(aid, result, {"verdict": result}, "M3")
        assert out["ok"] is True
        assert out["relevance_status"] == status
        assert out["changed"] is True
        assert repo.get_asset(aid)["relevance_status"] == status   # 只存当前值


def test_receive_relevance_idempotent(db_materials):
    """幂等：同值重复回写 changed=False，不报错（断点续跑可重放）。"""
    svc = make_relevance_service(db_materials)
    repo = make_repo(db_materials)
    aid = repo.create_asset(**base_video())
    first = svc.receive_relevance(aid, "pass")
    second = svc.receive_relevance(aid, "pass")
    assert first["changed"] is True
    assert second["changed"] is False
    assert repo.get_asset(aid)["relevance_status"] == "passed"


def test_receive_relevance_invalid_result_rejected(db_materials):
    """非法 result → PLATFORM_REJECT（拒绝，不落库）。"""
    svc = make_relevance_service(db_materials)
    repo = make_repo(db_materials)
    aid = repo.create_asset(**base_video())
    out = svc.receive_relevance(aid, "related")   # M3 verdict 而非 gate.result 口径
    assert out["ok"] is False
    assert out["code"] == "PLATFORM_REJECT"
    assert repo.get_asset(aid)["relevance_status"] == "pending"


def test_receive_relevance_asset_missing_no_match(db_materials):
    """素材不存在 → NO_MATCH（结构化返回，不抛出）。"""
    svc = make_relevance_service(db_materials)
    out = svc.receive_relevance(99999, "pass")
    assert out["ok"] is False
    assert out["code"] == "NO_MATCH"


def test_is_ready_for_chain_only_passed(db_materials):
    """仅 relevance_status=passed 放行进入询价/上架链；其余（pending/failed/
    manual_review）均不放行；素材不存在返回 False。"""
    svc = make_relevance_service(db_materials)
    repo = make_repo(db_materials)
    aid = repo.create_asset(**base_video())
    assert svc.is_ready_for_chain(aid) is False            # pending 未判定
    svc.receive_relevance(aid, "reject")
    assert svc.is_ready_for_chain(aid) is False            # failed 淘汰
    svc.receive_relevance(aid, "manual_review")
    assert svc.is_ready_for_chain(aid) is False            # manual_review 待人工确认
    svc.receive_relevance(aid, "pass")
    assert svc.is_ready_for_chain(aid) is True             # passed 放行
    assert svc.is_ready_for_chain(99999) is False          # 素材不存在
    assert svc.get_relevance_status(99999) is None
