"""REC-融合 P0-2：人审→规则草稿闭环 fixtures 测试。

旧系统 human_learning 迁移验证：
① 人工驳回 → 自动生成对应 stage 规则草稿
② 同 stage+rule_key 重复决定 → 只累计 sample_count 不重复建草稿
③ 人工确认后生效（draft → active）；驳回（draft → rejected）
④ 草稿按 stage 聚类可查询
"""

from pathlib import Path

import pytest

from foundation.config import FoundationConfig
from foundation.db import Database
from foundation.repo import WorkflowQueue


@pytest.fixture()
def queue() -> WorkflowQueue:
    """SQLite 内存库上的队列（foundation 自己的库，含 learning_rule_drafts）。"""
    cfg = FoundationConfig(db_url="sqlite:///:memory:", lease_minutes=45, data_dir=Path("."))
    database = Database(cfg)
    database.create_all()
    database.seed()
    return WorkflowQueue(database)


def test_manual_reject_creates_rule_draft(queue):
    """① 人工驳回 → 生成对应 stage 规则草稿（draft 状态）。"""
    q = queue
    draft_id = q.create_rule_draft(
        stage="listing_upload",
        rule_key="title_brand_word",
        rule_text="标题含品牌词（耐克/阿迪/古驰等）→ 驳回",
        evidence={"sample_product": 1001, "reason": "品牌侵权"},
    )
    assert draft_id.startswith("rd-")
    drafts = q.list_rule_drafts(stage="listing_upload")
    assert len(drafts) == 1
    assert drafts[0]["status"] == "draft"
    assert drafts[0]["sample_count"] == 1


def test_repeated_decision_accumulates_sample(queue):
    """② 同 stage+rule_key 重复决定 → 只累计 sample_count。"""
    q = queue
    id1 = q.create_rule_draft("listing_upload", "title_brand_word", "规则A")
    id2 = q.create_rule_draft("listing_upload", "title_brand_word", "规则A")
    assert id1 == id2
    drafts = q.list_rule_drafts()
    assert len(drafts) == 1
    assert drafts[0]["sample_count"] == 2


def test_confirm_activates_draft(queue):
    """③ 人工确认 → draft → active；生效后列表可见。"""
    q = queue
    draft_id = q.create_rule_draft("source_collect", "apparel_hard_block", "鞋服词硬拦")
    assert q.confirm_rule_draft(draft_id, "active") is True
    drafts = q.list_rule_drafts(status="active")
    assert len(drafts) == 1
    assert drafts[0]["rule_key"] == "apparel_hard_block"
    # 已生效草稿不可再次确认
    assert q.confirm_rule_draft(draft_id, "active") is False


def test_reject_draft_and_stage_clustering(queue):
    """④ 草稿可按 stage 聚类；驳回草稿进入 rejected。"""
    q = queue
    q.create_rule_draft("image_generation", "main_image_ratio", "主图 1:1")
    q.create_rule_draft("listing_upload", "attrs_complete", "必填参数完整")
    d2 = q.create_rule_draft("listing_upload", "attrs_complete_b", "缺参驳回")
    assert q.confirm_rule_draft(d2, "rejected") is True

    img_drafts = q.list_rule_drafts(stage="image_generation")
    assert len(img_drafts) == 1
    listing_drafts = q.list_rule_drafts(stage="listing_upload")
    assert len(listing_drafts) == 2
    rejected = q.list_rule_drafts(status="rejected")
    assert len(rejected) == 1
    assert rejected[0]["rule_key"] == "attrs_complete_b"
