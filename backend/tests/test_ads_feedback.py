"""M5 自动小店投放（商品托管）· 数据回写测试（v0.5 回流层）。

覆盖：类目聚合（同/异类目、spend=0 跳过、弱样本仍输出、未知商品跳过、空输入、
混合场景）、C-2 交换文件（结构对齐/时间归一/非法 period/roi≤0/非 int 字段）、
JSON 写出（UTF-8 中文/幂等覆盖/父目录自动创建）、素材评估回流（结构/枚举校验/
asset_id 缺失/缺省时间/与 M2 枚举对齐）、review_reason 回写（字段校验/failed_at
变体）、category_map 加载（两种形状/坏文件）、**C-2 契约交叉验证**（M1 消费端
sourcing.ad_backfill.load_exchange 可直接消费本层产出）。

fixtures 全部在测试文件内自建（独立 tmp_path，不写任何模块库），conftest 零改动。

运行（P-001 + P-011：必须带独立 basetemp `.pytest-tmp-m5`，禁止共用 .pytest-tmp）：
  python -m pytest tests/test_ads_feedback.py -q --basetemp=".pytest-tmp-m5"
"""

import json
from datetime import datetime, timedelta, timezone

import pytest

from ads.feedback import (
    EVALUATION_VALUES,
    aggregate_by_category,
    build_exchange_file,
    build_material_evaluation_file,
    build_review_reason_file,
    load_category_map,
    write_exchange_file,
)


# ---------------------------------------------------------------- 测试工具
def _row(pid, gmv=0, spend=0, count=1):
    """构造一行产品转化数据（金额分 int）。"""
    return {"product_id": pid, "gmv_fen": gmv, "spend_fen": spend, "sample_count": count}


_UTC = timezone.utc


# ===========================================================================
# 一、aggregate_by_category
# ===========================================================================
def test_aggregate_same_category_sums():
    rows = [
        _row(101, gmv=1000, spend=500, count=2),
        _row(102, gmv=2000, spend=500, count=3),
    ]
    out = aggregate_by_category(rows, {101: "收纳整理", 102: "收纳整理"})
    assert out["data"] == {
        "收纳整理": {"roi": 3.0, "sales_amount": 3000, "sample_count": 5},
    }
    assert out["skipped"] == []


def test_aggregate_multiple_categories():
    rows = [
        _row(101, gmv=1000, spend=1000, count=1),
        _row(202, gmv=4000, spend=1000, count=4),
        _row(303, gmv=2000, spend=2000, count=2),
    ]
    out = aggregate_by_category(rows, {101: "收纳整理", 202: "宠物用品", 303: "厨房用品"})
    assert out["data"]["收纳整理"] == {"roi": 1.0, "sales_amount": 1000, "sample_count": 1}
    assert out["data"]["宠物用品"] == {"roi": 4.0, "sales_amount": 4000, "sample_count": 4}
    assert out["data"]["厨房用品"] == {"roi": 1.0, "sales_amount": 2000, "sample_count": 2}
    assert out["skipped"] == []


def test_aggregate_skip_spend_zero_category():
    """类目总 spend=0 → ROI 无意义，整体跳过计入 skipped（product_id 取该类目首个商品）。"""
    rows = [
        _row(101, gmv=0, spend=0, count=1),
        _row(102, gmv=500, spend=0, count=2),
    ]
    out = aggregate_by_category(rows, {101: "收纳整理", 102: "收纳整理"})
    assert out["data"] == {}
    assert len(out["skipped"]) == 1
    assert out["skipped"][0] == {"product_id": 101, "reason": "spend=0"}


def test_aggregate_partial_spend_zero_within_category():
    """类目内部分商品 spend=0：类目总 spend>0 则整体计入（含 spend=0 商品的 gmv/样本）。"""
    rows = [
        _row(101, gmv=1000, spend=0, count=2),
        _row(102, gmv=2000, spend=1000, count=3),
    ]
    out = aggregate_by_category(rows, {101: "收纳整理", 102: "收纳整理"})
    assert out["data"] == {
        "收纳整理": {"roi": 3.0, "sales_amount": 3000, "sample_count": 5},
    }
    assert out["skipped"] == []


def test_aggregate_weak_sample_still_output():
    """弱样本（sample_count<5）仍输出（消费端 M1 过滤，本层不丢弃）。"""
    out = aggregate_by_category([_row(101, gmv=1000, spend=500, count=2)], {101: "收纳整理"})
    assert out["data"]["收纳整理"]["sample_count"] == 2
    assert out["data"]["收纳整理"]["roi"] == 2.0
    assert out["skipped"] == []


def test_aggregate_unknown_product_skipped():
    out = aggregate_by_category([_row(999, gmv=1000, spend=500, count=1)], {101: "收纳整理"})
    assert out["data"] == {}
    assert out["skipped"] == [{"product_id": 999, "reason": "unknown product_id"}]
    # 缺失 product_id 同样按未知跳过
    out2 = aggregate_by_category([{"gmv_fen": 1, "spend_fen": 1}], {})
    assert out2["skipped"][0]["reason"] == "unknown product_id"


def test_aggregate_empty_input():
    assert aggregate_by_category([], {}) == {"data": {}, "skipped": []}


def test_aggregate_mixed_skip_and_keep():
    rows = [
        _row(101, gmv=1000, spend=1000, count=1),   # 有效
        _row(999, gmv=1000, spend=500, count=1),    # 未知商品 → 跳过
        _row(202, gmv=0, spend=0, count=3),         # 类目总 spend=0 → 跳过
    ]
    out = aggregate_by_category(rows, {101: "收纳整理", 202: "家居日用"})
    assert set(out["data"].keys()) == {"收纳整理"}
    assert {s["reason"] for s in out["skipped"]} == {"unknown product_id", "spend=0"}


# ===========================================================================
# 二、build_exchange_file（C-2 结构）
# ===========================================================================
def test_build_exchange_c2_structure():
    data = {
        "收纳整理": {"roi": 3.2, "sales_amount": 12800000, "sample_count": 34},
        "厨房用品": {"roi": 2.1, "sales_amount": 5400000, "sample_count": 3},
    }
    out = build_exchange_file(data, "2026-08-21", "2026-08-28", "2026-08-28T08:00:00+08:00")
    # 顶层键集合严格对齐 C-2
    assert set(out.keys()) == {"schema_version", "period", "generated_at", "data"}
    assert out["schema_version"] == 1
    assert set(out["period"].keys()) == {"start", "end"}
    assert out["period"] == {"start": "2026-08-21", "end": "2026-08-28"}
    assert datetime.fromisoformat(out["generated_at"]).tzinfo is not None
    for category, entry in out["data"].items():
        assert set(entry.keys()) == {"roi", "sales_amount", "sample_count"}
        assert isinstance(entry["roi"], float) and entry["roi"] > 0
        assert isinstance(entry["sales_amount"], int)
        assert isinstance(entry["sample_count"], int)
    # json.dumps 直写直读无损失（含中文类目）
    assert json.loads(json.dumps(out, ensure_ascii=False)) == out


def test_build_exchange_generated_at_variants():
    data = {"收纳整理": {"roi": 3.2, "sales_amount": 1000, "sample_count": 5}}
    # naive datetime → 自动补 UTC
    out = build_exchange_file(data, "2025-01-01", "2025-01-07", datetime(2025, 1, 7, 8, 0))
    assert out["generated_at"] == "2025-01-07T08:00:00+00:00"
    # aware +08:00 → 转 UTC
    tz8 = timezone(timedelta(hours=8))
    out2 = build_exchange_file(data, "2025-01-01", "2025-01-07", datetime(2025, 1, 7, 8, 0, tzinfo=tz8))
    assert out2["generated_at"] == "2025-01-07T00:00:00+00:00"
    # ISO 字符串：Z 后缀 / 带偏移
    out3 = build_exchange_file(data, "2025-01-01", "2025-01-07", "2025-01-07T08:00:00Z")
    assert out3["generated_at"] == "2025-01-07T08:00:00+00:00"
    out4 = build_exchange_file(data, "2025-01-01", "2025-01-07", "2025-01-07T16:00:00+08:00")
    assert out4["generated_at"] == "2025-01-07T08:00:00+00:00"


def test_build_exchange_invalid_period_raises():
    data = {"收纳整理": {"roi": 3.2, "sales_amount": 1000, "sample_count": 5}}
    ts = datetime(2025, 1, 7, tzinfo=_UTC)
    for bad in ("2025-13-01", "2025-01-32", "2025/01/01", "20250101", "", None, 20250101):
        with pytest.raises(ValueError, match="period"):
            build_exchange_file(data, bad, "2025-01-07", ts)
        with pytest.raises(ValueError, match="period"):
            build_exchange_file(data, "2025-01-01", bad, ts)


def test_build_exchange_roi_nonpositive_raises():
    ts = datetime(2025, 1, 7, tzinfo=_UTC)
    cases = [
        {"收纳整理": {"roi": 0, "sales_amount": 1000, "sample_count": 5}},
        {"收纳整理": {"roi": -3.2, "sales_amount": 1000, "sample_count": 5}},
        {"收纳整理": {"roi": float("nan"), "sales_amount": 1000, "sample_count": 5}},
        {"收纳整理": {"roi": True, "sales_amount": 1000, "sample_count": 5}},  # bool 按非法
        {"收纳整理": {"sales_amount": 1000, "sample_count": 5}},               # roi 缺失
    ]
    for bad in cases:
        with pytest.raises(ValueError, match="roi"):
            build_exchange_file(bad, "2025-01-01", "2025-01-07", ts)


def test_build_exchange_non_int_fields_raises():
    ts = datetime(2025, 1, 7, tzinfo=_UTC)
    cases = [
        {"收纳整理": {"roi": 3.2, "sales_amount": 1000.5, "sample_count": 5}},  # sales 非 int
        {"收纳整理": {"roi": 3.2, "sales_amount": "1000", "sample_count": 5}},
        {"收纳整理": {"roi": 3.2, "sales_amount": True, "sample_count": 5}},   # bool 按非 int
        {"收纳整理": {"roi": 3.2, "sales_amount": 1000, "sample_count": 5.0}},  # sample 非 int
        {"收纳整理": {"roi": 3.2, "sales_amount": 1000, "sample_count": "5"}},
        {"收纳整理": {"roi": 3.2, "sales_amount": 1000}},                        # sample 缺失
    ]
    for bad in cases:
        with pytest.raises(ValueError, match="sales_amount|sample_count"):
            build_exchange_file(bad, "2025-01-01", "2025-01-07", ts)


# ===========================================================================
# 三、write_exchange_file
# ===========================================================================
def test_write_exchange_utf8_chinese_readback(tmp_path):
    exchange = build_exchange_file(
        {"收纳整理": {"roi": 3.2, "sales_amount": 12800000, "sample_count": 34}},
        "2026-08-21",
        "2026-08-28",
        datetime(2026, 8, 28, 8, 0, tzinfo=_UTC),
    )
    target = tmp_path / "m5-ad-conversion.json"
    meta = write_exchange_file(exchange, target)
    assert set(meta.keys()) == {"path", "bytes", "written_at"}
    assert meta["path"] == str(target)
    assert meta["bytes"] > 0
    assert meta["written_at"].endswith("+00:00")  # UTC ISO8601
    raw = target.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf")  # UTF-8 无 BOM
    text = raw.decode("utf-8")
    assert "收纳整理" in text  # 中文原样（ensure_ascii=False）
    assert json.loads(text) == exchange


def test_write_exchange_idempotent_overwrite(tmp_path):
    target = tmp_path / "out" / "exchange.json"
    e1 = build_exchange_file(
        {"甲类": {"roi": 2.0, "sales_amount": 2000, "sample_count": 4}},
        "2025-01-01", "2025-01-07", "2025-01-07T00:00:00Z",
    )
    write_exchange_file(e1, target)
    e2 = build_exchange_file(
        {"乙类": {"roi": 5.0, "sales_amount": 5000, "sample_count": 9}},
        "2025-01-01", "2025-01-07", "2025-01-08T00:00:00Z",
    )
    m2 = write_exchange_file(e2, target)  # 幂等覆盖：第二次直接覆盖，不追加不报错
    assert json.loads(target.read_text(encoding="utf-8")) == e2
    assert "甲类" not in target.read_text(encoding="utf-8")
    expected_bytes = len(json.dumps(e2, ensure_ascii=False, indent=2).encode("utf-8"))
    assert m2["bytes"] == expected_bytes


def test_write_exchange_parent_dir_autocreate(tmp_path):
    target = tmp_path / "a" / "b" / "c" / "m5-ad-conversion.json"
    exchange = build_exchange_file(
        {"收纳整理": {"roi": 1.5, "sales_amount": 1500, "sample_count": 6}},
        "2025-01-01", "2025-01-07", "2025-01-07T00:00:00Z",
    )
    write_exchange_file(exchange, target)
    assert target.parent.is_dir()
    assert target.exists()


# ===========================================================================
# 四、build_material_evaluation_file（M5-OUT-02 → M2）
# ===========================================================================
def test_material_eval_valid_structure():
    rows = [
        {"asset_id": 11, "evaluation": "efficient", "impressions": 12000, "gmv_fen": 30000, "spend_fen": 10000},
        {"asset_id": 22, "evaluation": "potential", "impressions": 800, "gmv_fen": 0, "spend_fen": 2000},
        {"asset_id": "33", "evaluation": "exploring"},  # 缺省指标 → evidence 补 0
    ]
    out = build_material_evaluation_file(rows, generated_at=datetime(2025, 1, 1, 8, 0, tzinfo=_UTC))
    assert set(out.keys()) == {"schema_version", "generated_at", "data"}
    assert out["schema_version"] == 1
    assert out["generated_at"] == "2025-01-01T08:00:00+00:00"
    assert len(out["data"]) == 3
    first = out["data"][0]
    assert first["asset_id"] == 11
    assert first["evaluation"] == "efficient"
    assert set(first["evidence"].keys()) == {"impressions", "gmv_fen", "spend_fen", "source_agent"}
    assert first["evidence"] == {"impressions": 12000, "gmv_fen": 30000, "spend_fen": 10000, "source_agent": "M5"}
    assert out["data"][2]["asset_id"] == 33  # 字符串数字 → int 归一
    assert out["data"][2]["evidence"] == {"impressions": 0, "gmv_fen": 0, "spend_fen": 0, "source_agent": "M5"}


def test_material_eval_enum_validation():
    # 三个合法枚举全部通过
    for val in ("exploring", "efficient", "potential"):
        out = build_material_evaluation_file([{"asset_id": 1, "evaluation": val}])
        assert out["data"][0]["evaluation"] == val
    # 非法（含中文标签）→ ValueError
    with pytest.raises(ValueError, match="evaluation"):
        build_material_evaluation_file([{"asset_id": 1, "evaluation": "高效"}])
    with pytest.raises(ValueError, match="evaluation"):
        build_material_evaluation_file([{"asset_id": 1, "evaluation": None}])
    with pytest.raises(ValueError, match="evaluation"):
        build_material_evaluation_file([{"asset_id": 1, "evaluation": ""}])
    # 契约对齐：与 M2 materials.config.EVALUATION_VALUES 完全一致（镜像校验，零 M2 库访问）
    from materials.config import EVALUATION_VALUES as M2_EVAL

    assert set(EVALUATION_VALUES) == set(M2_EVAL)


def test_material_eval_missing_asset_id_raises():
    with pytest.raises(ValueError, match="asset_id"):
        build_material_evaluation_file([{"evaluation": "efficient"}])
    with pytest.raises(ValueError, match="asset_id"):
        build_material_evaluation_file([{"asset_id": None, "evaluation": "efficient"}])
    with pytest.raises(ValueError, match="asset_id"):
        build_material_evaluation_file([{"asset_id": "abc", "evaluation": "efficient"}])


def test_material_eval_default_generated_at():
    before = datetime.now(_UTC)
    out = build_material_evaluation_file([{"asset_id": 7, "evaluation": "efficient"}])
    after = datetime.now(_UTC)
    gen = datetime.fromisoformat(out["generated_at"])
    assert gen.tzinfo is not None  # aware
    assert before - timedelta(seconds=1) <= gen <= after + timedelta(seconds=1)
    # 显式传入 naive → 补 UTC
    out2 = build_material_evaluation_file(
        [{"asset_id": 7, "evaluation": "efficient"}], generated_at=datetime(2025, 1, 1, 8, 0)
    )
    assert out2["generated_at"] == "2025-01-01T08:00:00+00:00"


# ===========================================================================
# 五、build_review_reason_file（M5-OUT-03 → M1 商品主表）
# ===========================================================================
def test_review_reason_valid_structure():
    rows = [
        {"product_id": 101, "review_reason": "资质不符", "campaign_id": 5},
        {
            "product_id": "202",
            "review_reason": "素材审核不通过",
            "campaign_id": 6,
            "failed_at": datetime(2025, 1, 2, 3, 4, tzinfo=_UTC),
        },
    ]
    out = build_review_reason_file(rows, generated_at=datetime(2025, 1, 3, tzinfo=_UTC))
    assert set(out.keys()) == {"schema_version", "generated_at", "data"}
    assert out["schema_version"] == 1
    assert out["generated_at"] == "2025-01-03T00:00:00+00:00"
    assert len(out["data"]) == 2
    r0 = out["data"][0]
    assert set(r0.keys()) == {"product_id", "review_reason", "campaign_id", "failed_at"}
    assert r0["product_id"] == 101
    assert r0["review_reason"] == "资质不符"
    assert r0["campaign_id"] == 5
    assert datetime.fromisoformat(r0["failed_at"]).tzinfo is not None  # 缺省 → 当前 UTC
    assert out["data"][1]["product_id"] == 202  # 字符串 → int 归一
    assert out["data"][1]["failed_at"] == "2025-01-02T03:04:00+00:00"


def test_review_reason_failed_at_variants():
    base = [{"product_id": 1, "review_reason": "价格带不符"}]
    # generated_at naive → 补 UTC
    out = build_review_reason_file(base, generated_at=datetime(2025, 1, 1))
    assert out["generated_at"] == "2025-01-01T00:00:00+00:00"
    # failed_at 带偏移字符串 → 转 UTC
    out2 = build_review_reason_file(
        [{"product_id": 1, "review_reason": "x", "failed_at": "2025-01-02T08:00:00+08:00"}]
    )
    assert out2["data"][0]["failed_at"] == "2025-01-02T00:00:00+00:00"
    # failed_at Z 后缀
    out3 = build_review_reason_file(
        [{"product_id": 1, "review_reason": "x", "failed_at": "2025-01-02T08:00:00Z"}]
    )
    assert out3["data"][0]["failed_at"] == "2025-01-02T08:00:00+00:00"
    # 非法 failed_at → ValueError
    with pytest.raises(ValueError, match="failed_at"):
        build_review_reason_file([{"product_id": 1, "review_reason": "x", "failed_at": "not-a-date"}])


def test_review_reason_missing_fields_raise():
    with pytest.raises(ValueError, match="product_id"):
        build_review_reason_file([{"review_reason": "x"}])
    with pytest.raises(ValueError, match="product_id"):
        build_review_reason_file([{"product_id": None, "review_reason": "x"}])
    with pytest.raises(ValueError, match="product_id"):
        build_review_reason_file([{"product_id": "", "review_reason": "x"}])
    with pytest.raises(ValueError, match="review_reason"):
        build_review_reason_file([{"product_id": 1}])
    with pytest.raises(ValueError, match="review_reason"):
        build_review_reason_file([{"product_id": 1, "review_reason": ""}])
    with pytest.raises(ValueError, match="review_reason"):
        build_review_reason_file([{"product_id": 1, "review_reason": "   "}])


# ===========================================================================
# 六、load_category_map
# ===========================================================================
def test_load_category_map_dict_shape(tmp_path):
    p = tmp_path / "products-category.json"
    p.write_text(json.dumps({"101": "收纳整理", "202": "宠物用品", "303": "厨房用品"}), encoding="utf-8")
    assert load_category_map(p) == {101: "收纳整理", 202: "宠物用品", 303: "厨房用品"}


def test_load_category_map_list_shape(tmp_path):
    p = tmp_path / "products-category.json"
    p.write_text(
        json.dumps(
            [
                {"product_id": 101, "category": "收纳整理"},
                {"product_id": "202", "category": "宠物用品"},
            ]
        ),
        encoding="utf-8",
    )
    assert load_category_map(p) == {101: "收纳整理", 202: "宠物用品"}


def test_load_category_map_missing_corrupt_none_empty(tmp_path):
    assert load_category_map(None) == {}  # 未提供 → 空映射
    assert load_category_map(tmp_path / "no-such.json") == {}  # 文件不存在
    p = tmp_path / "bad.json"
    p.write_text("{not json", encoding="utf-8")  # JSON 损坏
    assert load_category_map(p) == {}
    p2 = tmp_path / "wrong-shape.json"
    p2.write_text(json.dumps("just a string"), encoding="utf-8")  # 结构非法
    assert load_category_map(p2) == {}


def test_load_category_map_bad_entries_skipped(tmp_path):
    p = tmp_path / "products-category.json"
    p.write_text(
        json.dumps({"101": "收纳整理", "abc": "坏键", "202": ""}),
        encoding="utf-8",
    )
    assert load_category_map(p) == {101: "收纳整理"}  # 非数字键/空类目跳过
    p2 = tmp_path / "products-category-list.json"
    p2.write_text(
        json.dumps(
            [
                {"product_id": 1, "category": "宠物用品"},
                {"category": "缺 id"},
                {"product_id": 2},
                "not-a-dict",
                {"product_id": None, "category": "x"},
            ]
        ),
        encoding="utf-8",
    )
    assert load_category_map(p2) == {1: "宠物用品"}


# ===========================================================================
# 七、C-2 契约交叉验证（关键：M1 消费端可直接消费本层产出）
# ===========================================================================
def test_c2_cross_validate_with_m1_consumer(tmp_path):
    """C-2 契约会签交叉验证：构造 build_exchange_file 示例 → 写到 tmp 文件 →
    M1 消费端 sourcing.ad_backfill.load_exchange 校验通过（只读校验，不写 M1 库）。"""
    from sourcing.ad_backfill import load_exchange  # M1 消费端（C-2 权威校验入口）

    data = {
        "收纳整理": {"roi": 3.2, "sales_amount": 12800000, "sample_count": 34},
        "宠物用品": {"roi": 2.4, "sales_amount": 8600000, "sample_count": 21},
        "厨房用品": {"roi": 2.1, "sales_amount": 5400000, "sample_count": 3},  # 弱样本仍输出
    }
    exchange = build_exchange_file(
        data,
        period_start="2026-08-21",
        period_end="2026-08-28",
        generated_at="2026-08-28T08:00:00+08:00",
    )
    path = tmp_path / "exchange" / "m5-ad-conversion.json"
    meta = write_exchange_file(exchange, path)
    assert path.exists()
    assert meta["path"] == str(path)

    loaded = load_exchange(path)  # M1 消费端结构/period/generated_at 校验
    assert loaded is not None
    assert loaded.schema_version == 1
    assert loaded.period.start == "2026-08-21"
    assert loaded.period.end == "2026-08-28"
    assert loaded.generated_at.tzinfo is not None  # M1 归一化为 aware datetime
    assert loaded.data["收纳整理"]["roi"] == pytest.approx(3.2)
    assert loaded.data["收纳整理"]["sales_amount"] == 12800000
    assert loaded.data["宠物用品"]["sample_count"] == 21
    assert loaded.data["厨房用品"]["sample_count"] == 3  # 弱样本 M1 仍保留（消费端过滤）
