"""P-031：白名单类目解析器测试（category_map.infer_category）。"""

import pytest

from sourcing.category_map import CATEGORY_KEYWORDS, infer_category


def test_infer_kitchen():
    """厨房用品：锅/杯/保鲜袋等。"""
    assert infer_category("不锈钢锅刷 不伤锅具 长柄厨房清洁刷") == "厨房用品"
    assert infer_category("加厚抽取式保鲜袋 食品级 100只") == "厨房用品"
    assert infer_category("大容量保温杯 316不锈钢 便携水杯") == "厨房用品"


def test_infer_home():
    """家居日用：收纳/衣架/纸巾等。"""
    assert infer_category("免打孔卫生间置物架 浴室收纳架") == "家居日用"
    assert infer_category("折叠伸缩晾衣架 阳台晒被子架") == "家居日用"


def test_infer_pet_digital_office_outdoor():
    """宠物/数码/办公/户外。"""
    assert infer_category("宠物自动饮水机 过滤循环静音款") == "宠物用品"
    assert infer_category("车载手机支架 铝合金 磁吸") == "数码配件"
    assert infer_category("A4文件夹 资料册 办公用品") == "办公文具"
    assert infer_category("运动健身瑜伽垫 加厚防滑 家用垫") == "户外运动"


def test_infer_none_for_food():
    """食品/饮品不映射（用户裁定只找白名单内的品，食品由 permanent 双保险兜底）。"""
    assert infer_category("新疆纯驼乳粉320g*2罐") is None
    assert infer_category("0蔗糖低温酸奶 无蔗糖代餐") is None
    assert infer_category("2026新茶茉莉雪螺王 袋装茶叶") is None


def test_infer_none_for_unmappable():
    """无法映射的商品 → None（合规层 hard_reject）。"""
    assert infer_category("汽车雨刮器 通用款") is None
    assert infer_category("") is None
    assert infer_category(None) is None


def test_keywords_cover_nine_whitelist_categories():
    """9 个白名单类目均有关键词覆盖（与 config 白名单一致）。"""
    from sourcing.config import DEFAULT_CATEGORY_WHITELIST

    assert set(CATEGORY_KEYWORDS.keys()) == set(DEFAULT_CATEGORY_WHITELIST)
