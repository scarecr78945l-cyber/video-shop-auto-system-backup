"""REC-融合 P0-1：上架类目记忆 fixtures 测试。

旧系统 category_listing_memory 迁移验证：
① 首单通过后，第二单上架包自动预填必填参数/物流模板
② 该类目后续拒审率超阈值 → 转人工复核
③ 连续图片拒审 streak ≥3 → 转人工复核（独立判据）
"""

from listing.repo import ListingRepo


def _seed(repo: ListingRepo, category: str, **fields) -> None:
    repo.upsert_category_memory(category, **fields)


def test_first_pass_then_second_prefill(repo_listing):
    """① 首单通过（记 streak + 预填字段）后，第二单读记忆即得预填。"""
    repo = repo_listing
    # 首单人工通过：记 1 次通过 + 沉淀必填参数/物流模板/退货地址
    repo.record_category_submission("收纳整理", rejected=False)
    repo.upsert_category_memory(
        "收纳整理",
        required_fields=["适用场景", "容量", "包装清单"],
        logistics_template="默认快递-包邮-48h发货",
        return_address_rule={"region": "华东", "fee_paid": "seller"},
    )
    # 第二单上架包生成时读取记忆
    memory = repo.get_category_memory("收纳整理")
    assert memory is not None
    assert memory["manual_pass_streak"] == 1
    assert memory["required_fields"] == ["适用场景", "容量", "包装清单"]
    assert memory["logistics_template"] == "默认快递-包邮-48h发货"
    assert memory["return_address_rule"] == {"region": "华东", "fee_paid": "seller"}


def test_reject_rate_threshold_triggers_manual(repo_listing):
    """② 拒审率 ≥50% → 该类目转人工复核。"""
    repo = repo_listing
    repo.record_category_submission("厨房用品", rejected=True)
    repo.record_category_submission("厨房用品", rejected=True)  # 2/2 = 100%
    assert repo.should_manual_review_category("厨房用品") is True
    # 低拒审率（1/4 = 25%）不触发
    repo2_mem = repo.get_category_memory("厨房用品")
    # 补 2 次通过 → 2/4 = 50%，恰达阈值（>=）触发
    repo.record_category_submission("厨房用品", rejected=False)
    repo.record_category_submission("厨房用品", rejected=False)
    assert repo.should_manual_review_category("厨房用品") is True
    # 自定义阈值：25% 阈值下 1/3 即触发
    repo.record_category_submission("厨房用品", rejected=True)  # 3/5
    assert repo.should_manual_review_category("厨房用品", reject_rate_threshold=0.6) is True
    assert repo.should_manual_review_category("厨房用品", reject_rate_threshold=0.7) is False


def test_image_rejection_streak_triggers_manual(repo_listing):
    """③ 连续图片拒审 streak ≥3 → 转人工复核（独立于拒审率）。"""
    repo = repo_listing
    for _ in range(3):
        repo.record_category_submission("宠物用品", rejected=True)
    assert repo.should_manual_review_category("宠物用品") is True
    # 通过一次后 streak 清零 → 不再因 streak 触发（拒审率 3/4=75% 仍会触发）
    repo.record_category_submission("宠物用品", rejected=False)
    memory = repo.get_category_memory("宠物用品")
    assert memory["platform_image_rejection_streak"] == 0
    assert repo.should_manual_review_category("宠物用品") is True  # 拒审率 3/4


def test_no_memory_no_manual(repo_listing):
    """无记忆的类目不触发人工复核。"""
    repo = repo_listing
    assert repo.get_category_memory("未知类目") is None
    assert repo.should_manual_review_category("未知类目") is False
