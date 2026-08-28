"""端到端流水线测试（fixtures 离线模式）。"""

from sqlalchemy import select

from sourcing import repo
from sourcing.db import Database
from sourcing.models import ComplianceState
from sourcing.pipeline import SourcingPipeline
from sourcing.tables import ProductSourceEvidence


def test_pipeline_end_to_end(cfg, db):
    pipe = SourcingPipeline(cfg, db)
    result = pipe.run(mode="fixtures", top_n=50)

    # 采集（三源 fixtures 合计：有米云 7 + 商机中心 5 + 抖店罗盘 11）
    assert result.collected >= 20
    # 去重后小于原始（多源同款合并：置物架/保温杯/榨汁杯/晾衣架/瑜伽垫/饮水机跨源出现）
    assert result.after_dedup < result.collected
    # 硬拒：古驰品牌（ym-006）+ 电子烟（dd-006）
    assert result.hard_rejected >= 2
    # 人工复核：防脱发功效词（dd-007）+ 美妆类目（dd-008）
    assert result.manual_review >= 2
    # 询价：有 quotes 数据的候选
    assert result.quoted >= 5
    # 入池
    assert 0 < result.pool_entered <= 50

    # 打分理由可解释 + 最高分商品合理
    top = result.pool[0]
    assert top.score.total > 0
    assert top.score.note
    for dim in top.score.dimensions.values():
        if dim.active:
            assert dim.reasons

    # 持久化：products / evidence / sku / library / events
    with db.session() as session:
        products = repo.list_pool(session, limit=100)
        assert len(products) >= result.pool_entered
        ev = session.execute(select(ProductSourceEvidence)).scalars().all()
        assert len(ev) > 0


def test_pipeline_no_duplicates_across_runs(cfg, db):
    """二次运行同一批次：全部判重，不再新增入库。"""
    pipe = SourcingPipeline(cfg, db)
    r1 = pipe.run(mode="fixtures")
    with db.session() as session:
        before = len(repo.list_pool(session, limit=1000))
    r2 = pipe.run(mode="fixtures")
    with db.session() as session:
        after = len(repo.list_pool(session, limit=1000))
    assert r2.pool_entered <= r1.pool_entered
    assert after >= before
    # 同批次再跑不应产生新指纹商品
    assert after == before


def test_pipeline_persist_off(cfg, db):
    pipe = SourcingPipeline(cfg, db)
    result = pipe.run(mode="fixtures", persist=False)
    assert result.pool_entered > 0
    with db.session() as session:
        assert len(repo.list_pool(session, limit=10)) == 0


def test_pipeline_manual_review_not_in_pool(cfg, db):
    pipe = SourcingPipeline(cfg, db)
    result = pipe.run(mode="fixtures")
    for cand in result.pool:
        assert cand.compliance.state == ComplianceState.CANDIDATE
