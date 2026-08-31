"""app_config 类目白名单接线测试（S1b）。

- app_config.category.whitelist（list[str]，REC-010 键名对齐后）运行时覆盖 config 默认
  （写入前 hard_reject 的类目 → 写入后 candidate，反之亦然；P-031 用户裁定白名单外 hard_reject）；
- app_config 无该键 → 回落 config.category_whitelist（config 字段名不变，仅 app_config 键名用点分隔）；
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
    """写入前（默认 9 类白名单，无「美妆」）→ hard_reject；写入后 → candidate。"""
    it = _item(category="美妆", title="美妆蛋收纳盒")
    pipe_before = SourcingPipeline(cfg, db)
    assert pipe_before.compliance.evaluate(it).state == ComplianceState.HARD_REJECT

    with db.session() as session:
        repo.set_config_value(session, "category.whitelist", ["美妆", "家居日用"])

    # 重建流水线 → 重新读取 app_config → 新白名单生效
    pipe_after = SourcingPipeline(cfg, db)
    assert pipe_after.compliance.evaluate(it).state == ComplianceState.CANDIDATE


def test_appconfig_whitelist_can_remove_config_category(cfg, db):
    """反向：app_config 白名单不含默认类目 → 原 candidate 变 hard_reject。"""
    with db.session() as session:
        repo.set_config_value(session, "category.whitelist", ["美妆"])

    pipe = SourcingPipeline(cfg, db)
    it = _item(category="家居日用")  # 默认白名单含「家居日用」
    assert pipe.compliance.evaluate(it).state == ComplianceState.HARD_REJECT


def test_no_appconfig_falls_back_to_config_default(cfg, db):
    """app_config 无 category.whitelist 键 → 回落 config.category_whitelist（config 字段）。"""
    cfg.category_whitelist = ["美妆"]  # 声明字段，允许赋值
    pipe = SourcingPipeline(cfg, db)
    it = _item(category="美妆", title="美妆蛋收纳盒")
    assert pipe.compliance.evaluate(it).state == ComplianceState.CANDIDATE


def test_appconfig_read_failure_falls_back(cfg, tmp_path):
    """未建表库：读 app_config 失败 → 回落 config 默认，不抛异常打断流水线。"""
    empty_db = Database(cfg)  # 未 create_all → app_config 表不存在
    pipe = SourcingPipeline(cfg, empty_db)  # 构造过程不应抛异常
    it = _item(category="美妆", title="美妆蛋收纳盒")
    assert pipe.compliance.evaluate(it).state == ComplianceState.HARD_REJECT


def test_appconfig_whitelist_ignores_non_list_value(cfg, db):
    """app_config 值为非 list（脏数据）→ 回落 config 默认，不抛异常。"""
    with db.session() as session:
        repo.set_config_value(session, "category.whitelist", "美妆")  # 字符串，非法类型

    pipe = SourcingPipeline(cfg, db)
    it = _item(category="美妆", title="美妆蛋收纳盒")
    assert pipe.compliance.evaluate(it).state == ComplianceState.HARD_REJECT
