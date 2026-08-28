"""M4 上架前校验硬门禁（listing_gate）单测。

覆盖：六项硬门禁全通过 happy path；每项失败用例；边界（标题 15/35 字符、
恰好 5 张互不相同主图）；配置注入生效。
测试图片用 Pillow 在 tmp 目录生成（不依赖大文件 fixtures）。
"""

from PIL import Image

from services.listing_gate import (
    ListingCandidate,
    ListingGate,
    ListingGateConfig,
    PurchaseSettings,
    SkuInput,
)

VALID_TITLE = "免打孔卫生间置物架 浴室收纳架"  # 15 字符


def make_image(path, size=(100, 100), color=(200, 30, 30)):
    img = Image.new("RGB", size, color)
    img.save(path)
    return str(path)


def make_main_images(tmp_path, n, size=(100, 100), distinct=True):
    paths = []
    for i in range(n):
        color = ((i * 40) % 256, (i * 61) % 256, (i * 83) % 256) if distinct else (200, 30, 30)
        paths.append(make_image(tmp_path / f"main_{i}.png", size, color))
    return paths


def valid_candidate(tmp_path, **overrides):
    # 先取出图片覆盖项，避免默认生成的主图覆盖测试自备文件（文件哈希/宽高比校验依赖内容）
    main_images = overrides.pop("main_images", None)
    detail_images = overrides.pop("detail_images", None)
    data = dict(
        product_id=1001,
        title=VALID_TITLE,
        category_id=1,
        category_name="家居日用",
        qualification={"qualification_id": "Q-001", "expires_at": "2027-12-31"},
        main_images=(
            make_main_images(tmp_path, 5) if main_images is None else main_images
        ),
        detail_images=(
            [make_image(tmp_path / "detail_0.png")]
            if detail_images is None
            else detail_images
        ),
        skus=[SkuInput(code="SKU-A", cost_cents=300, price_cents=990)],
        purchase_settings=PurchaseSettings(
            purchase_limit={"per_user": 2, "period": "month"},
            freight_template_id="FT-001",
            after_sale="7 天无理由退货",
        ),
    )
    data.update(overrides)
    return ListingCandidate(**data)


def gate(**config_overrides):
    return ListingGate(ListingGateConfig(**config_overrides))


def item_by(result, item_name):
    return next(i for i in result.items if i.item == item_name)


# ------------------------------------------------------------------ happy path


def test_happy_path_all_gates_pass(tmp_path):
    result = ListingGate().evaluate(valid_candidate(tmp_path))
    assert result.passed is True
    assert result.rejected_reason_codes == []
    assert len(result.items) == 12
    assert all(i.passed for i in result.items)
    assert ListingGate().is_allowed(valid_candidate(tmp_path)) is True


# ------------------------------------------------------------------ 标题


def test_title_too_short_14_chars_rejected(tmp_path):
    result = ListingGate().evaluate(valid_candidate(tmp_path, title="短" * 14))
    assert result.passed is False
    assert "title_length" in result.rejected_reason_codes


def test_title_too_long_36_chars_rejected(tmp_path):
    result = ListingGate().evaluate(valid_candidate(tmp_path, title="长" * 36))
    assert result.passed is False
    assert "title_length" in result.rejected_reason_codes


def test_title_boundary_15_and_35_chars_pass(tmp_path):
    assert ListingGate().evaluate(valid_candidate(tmp_path, title="标" * 15)).passed is True
    assert ListingGate().evaluate(valid_candidate(tmp_path, title="标" * 35)).passed is True


def test_title_brand_word_rejected(tmp_path):
    result = ListingGate().evaluate(valid_candidate(tmp_path, title="耐克官方旗舰店运动水杯"))
    assert result.passed is False
    assert "title_compliance" in result.rejected_reason_codes


def test_title_supply_chain_word_rejected(tmp_path):
    result = ListingGate().evaluate(valid_candidate(tmp_path, title="1688 厂家直销厨房收纳架"))
    assert result.passed is False
    assert "title_compliance" in result.rejected_reason_codes


# ------------------------------------------------------------------ 类目与资质


def test_category_not_in_whitelist_rejected(tmp_path):
    result = ListingGate().evaluate(valid_candidate(tmp_path, category_name="美妆"))
    assert result.passed is False
    assert "category" in result.rejected_reason_codes


def test_qualification_missing_rejected(tmp_path):
    result = ListingGate().evaluate(valid_candidate(tmp_path, qualification=None))
    assert result.passed is False
    assert "qualification" in result.rejected_reason_codes


# ------------------------------------------------------------------ 图片


def test_main_images_4_rejected(tmp_path):
    c = valid_candidate(tmp_path, main_images=make_main_images(tmp_path, 4))
    result = ListingGate().evaluate(c)
    assert result.passed is False
    assert "images_count" in result.rejected_reason_codes


def test_main_images_non_1to1_rejected(tmp_path):
    images = make_main_images(tmp_path, 4) + [make_image(tmp_path / "tall.png", size=(100, 200))]
    result = ListingGate().evaluate(valid_candidate(tmp_path, main_images=images))
    assert result.passed is False
    assert "images_ratio" in result.rejected_reason_codes


def test_main_images_with_duplicate_rejected(tmp_path):
    images = make_main_images(tmp_path, 3)
    dup = make_image(tmp_path / "dup_1.png")
    images += [dup, dup]  # 同一文件两次 → 同一 SHA256（5 张含重复）
    result = ListingGate().evaluate(valid_candidate(tmp_path, main_images=images))
    assert result.passed is False
    assert "images_duplicate" in result.rejected_reason_codes


def test_main_images_all_identical_rejected(tmp_path):
    images = make_main_images(tmp_path, 5, distinct=False)
    result = ListingGate().evaluate(valid_candidate(tmp_path, main_images=images))
    assert result.passed is False
    assert "images_duplicate" in result.rejected_reason_codes


def test_exactly_5_distinct_main_images_pass(tmp_path):
    result = ListingGate().evaluate(valid_candidate(tmp_path))
    assert result.passed is True
    dup_item = item_by(result, "images_duplicate")
    assert dup_item.passed is True
    assert dup_item.evidence["unique"] == 5


def test_detail_images_missing_rejected(tmp_path):
    result = ListingGate().evaluate(valid_candidate(tmp_path, detail_images=[]))
    assert result.passed is False
    assert "detail_images" in result.rejected_reason_codes


# ------------------------------------------------------------------ SKU 成本/售价


def test_sku_cost_zero_rejected(tmp_path):
    skus = [SkuInput(code="SKU-A", cost_cents=0, price_cents=990)]
    result = ListingGate().evaluate(valid_candidate(tmp_path, skus=skus))
    assert result.passed is False
    assert "sku_cost" in result.rejected_reason_codes


def test_sku_price_not_above_cost_rejected(tmp_path):
    skus = [SkuInput(code="SKU-A", cost_cents=300, price_cents=300)]
    result = ListingGate().evaluate(valid_candidate(tmp_path, skus=skus))
    assert result.passed is False
    assert "sku_price" in result.rejected_reason_codes


# ------------------------------------------------------------------ 购买设置


def test_purchase_settings_missing_all_rejected(tmp_path):
    result = ListingGate().evaluate(valid_candidate(tmp_path, purchase_settings=None))
    assert result.passed is False
    assert "purchase_settings" in result.rejected_reason_codes


def test_purchase_settings_missing_field_rejected(tmp_path):
    ps = PurchaseSettings(
        purchase_limit={"per_user": 2, "period": "month"},
        freight_template_id="FT-001",
        # after_sale 缺失
    )
    result = ListingGate().evaluate(valid_candidate(tmp_path, purchase_settings=ps))
    assert result.passed is False
    assert "purchase_settings" in result.rejected_reason_codes


# ------------------------------------------------------------------ 合规预审


def test_compliance_efficacy_word_rejected(tmp_path):
    result = ListingGate().evaluate(valid_candidate(tmp_path, title="生姜防脱发洗发水"))
    assert result.passed is False
    assert "compliance_preview" in result.rejected_reason_codes
    assert "title_compliance" in result.rejected_reason_codes  # 标题门禁同词库同步拒


# ------------------------------------------------------------------ 配置注入


def test_config_injection_title_range(tmp_path):
    g = gate(title_min=3, title_max=50)
    result = g.evaluate(valid_candidate(tmp_path, title="短标题"))  # 3 字符 = 注入下限
    assert result.passed is True
    assert item_by(result, "title_length").passed is True


def test_config_injection_main_images_min(tmp_path):
    g = gate(main_images_min=3)
    c = valid_candidate(tmp_path, main_images=make_main_images(tmp_path, 3))
    result = g.evaluate(c)
    assert result.passed is True


def test_config_injection_sku_cost_min(tmp_path):
    g = gate(sku_cost_min_cents=100)
    skus = [SkuInput(code="SKU-A", cost_cents=50, price_cents=990)]
    result = g.evaluate(valid_candidate(tmp_path, skus=skus))
    assert result.passed is False
    assert "sku_cost" in result.rejected_reason_codes


def test_config_injection_ratio_tolerance(tmp_path):
    g = gate(image_ratio_tolerance=0.5)
    images = make_main_images(tmp_path, 4) + [make_image(tmp_path / "tall.png", size=(100, 200))]
    result = g.evaluate(valid_candidate(tmp_path, main_images=images))
    assert result.passed is True  # 容差 0.5 → ratio 0.5 可接受


def test_config_injection_category_whitelist(tmp_path):
    g = gate(category_whitelist=["美妆", "家居日用"])
    result = g.evaluate(valid_candidate(tmp_path, category_name="美妆"))
    assert result.passed is True


# ------------------------------------------------------------------ 结构化拒绝


def test_rejected_result_structured(tmp_path):
    result = ListingGate().evaluate(
        valid_candidate(tmp_path, title="短", main_images=[])
    )
    assert result.passed is False
    assert isinstance(result.rejected_reason_codes, list)
    assert "title_length" in result.rejected_reason_codes
    assert "images_count" in result.rejected_reason_codes
    for i in result.items:
        assert i.reason_code == i.item
        assert isinstance(i.evidence, dict)
