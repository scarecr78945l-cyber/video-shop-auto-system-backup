"""app_config 类目白名单接线测试（S1b）。

- app_config.category_whitelist（list[str]）运行时覆盖 config 默认（写入前 manual_review 的类目 → 写入后 candidate，反之亦然）；
- app_config 无该键 → 回落 config.category_whitelist；
- 读取异常（未建表库）→ 回落 config 默认，不抛异常打断流水线。
"""

from sourcing import repo
from sourcing.db import Database
from sourcing.models import ComplianceState, SourceItem
from sourcing.pipeline import SourcingPipeline


def _item(category: str, title: str = "免打孔收纳置物架") -> SourceItem:
    return SourceItem(
        source="opportunities", board="机会品", platform_item_id="wl-1",
        title=title, category=category,
    )


def test_appconfig_whitelist_overrides_config_default(cfg, db):
    """写入前（默认 9 类白名单，无「美妆」）→ manual_review；写入后 → candidate。"""
    it = _item(category="美妆", title="美妆蛋收纳盒")
    pipe_before = SourcingPipeline(cfg, db)
    assert pipe_before.compliance.evaluate(it).state == ComplianceState.MANUAL_REVIEW

    with db.session() as session:
        repo.set_config_value(session, "category_whitelist", ["美妆", "家居日用"])

    # 重建流水线 → 重新读取 app_config → 新白名单生效
    pipe_after = SourcingPipeline(cfg, db)
    assert pipe_after.compliance.evaluate(it).state == ComplianceState.CANDIDATE


def test_appconfig_whitelist_can_remove_config_category(cfg, db):
    """反向：app_config 白名单不含默认类目 → 原 candidate 变 manual_review。"""
    with db.session() as session:
        repo.set_config_value(session, "category_whitelist", ["美妆"])

    pipe = SourcingPipeline(cfg, db)
    it = _item(category="家居日用")  # 默认白名单含「家居日用」
    assert pipe.compliance.evaluate(it).state == ComplianceState.MANUAL_REVIEW


def test_no_appconfig_falls_back_to_config_default(cfg, db):
    """app_config 无 category_whitelist 键 → 回落 config.category_whitelist。"""
    cfg.category_whitelist = ["美妆"]  # 声明字段，允许赋值
    pipe = SourcingPipeline(cfg, db)
    it = _item(category="美妆", title="美妆蛋收纳盒")
    assert pipe.compliance.evaluate(it).state == ComplianceState.CANDIDATE


def test_appconfig_read_failure_falls_back(cfg, tmp_path):
    """未建表库：读 app_config 失败 → 回落 config 默认，不抛异常打断流水线。"""
    empty_db = Database(cfg)  # 未 create_all → app_config 表不存在
    pipe = SourcingPipeline(cfg, empty_db)  # 构造过程不应抛异常
    it = _item(category="美妆", title="美妆蛋收纳盒")
    assert pipe.compliance.evaluate(it).state == ComplianceState.MANUAL_REVIEW


def test_appconfig_whitelist_ignores_non_list_value(cfg, db):
    """app_config 值为非 list（脏数据）→ 回落 config 默认，不抛异常。"""
    with db.session() as session:
        repo.set_config_value(session, "category_whitelist", "美妆")  # 字符串，非法类型

    pipe = SourcingPipeline(cfg, db)
    it = _item(category="美妆", title="美妆蛋收纳盒")
    assert pipe.compliance.evaluate(it).state == ComplianceState.MANUAL_REVIEW
