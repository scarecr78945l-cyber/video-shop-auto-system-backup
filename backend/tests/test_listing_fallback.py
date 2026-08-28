"""M4 UI 兜底降级通道单元测试（零真实浏览器，全部 MockPageOps 脚本化注入）。

覆盖：MockPageOps 基本操作；verify_page_signature 锚点校验（齐全/缺失）；
FallbackRunner 成功/失败结构化返回（不抛到队列层）；连续失败 >=2 → UNEXPECTED
人工接管；batch_size / item_interval_s 参数生效（ops 时间戳间隔）；截图目录自动创建。

运行：cd backend && python -m pytest tests/test_listing_fallback.py -q --basetemp=".pytest-tmp-m4"
"""

import os
import time

import pytest

from listing.ui_fallback import (
    FallbackRunner,
    MockPageOps,
    PageChangedError,
    UiFallbackConfig,
    verify_page_signature,
)


SIGNATURES = {
    "category_form": [".category-tree", "#submit-btn"],
    "purchase_limit_form": ["#purchase-limit", ".save-btn"],
}


def _config(tmp_path, **overrides):
    base = dict(
        screenshot_dir=str(tmp_path / "ui_evidence"),
        signatures=SIGNATURES,
    )
    base.update(overrides)
    return UiFallbackConfig(**base)


# ---------------------------------------------------------------- MockPageOps


def test_mock_page_ops_basic_records_history():
    ops = MockPageOps()
    ops.goto("category_form")
    ops.click(".category-tree")
    ops.fill("#purchase-limit", "2")

    assert ops.current_url() == "https://mock.page/category_form"
    assert ops.has_selector(".category-tree") is True
    assert [e["op"] for e in ops.ops] == ["goto", "click", "fill"]
    assert ops.ops[0]["selector"] == "category_form"
    assert ops.ops[2]["selector"] == "#purchase-limit"
    assert ops.ops[2]["value"] == "2"
    assert all("at" in e and isinstance(e["at"], float) for e in ops.ops)  # 时间戳留痕


# ---------------------------------------------------------------- verify_page_signature


def test_verify_page_signature_passes(tmp_path):
    config = _config(tmp_path)
    ops = MockPageOps()
    verify_page_signature(ops, "category_form", config)  # 锚点齐全 → 不抛异常
    assert [e["op"] for e in ops.ops] == ["has_selector", "has_selector"]


def test_verify_page_signature_missing_raises_with_evidence_and_screenshot(tmp_path):
    config = _config(tmp_path)
    ops = MockPageOps(script={"missing_selectors": [".category-tree"]})
    with pytest.raises(PageChangedError) as exc_info:
        verify_page_signature(ops, "category_form", config)

    evidence = exc_info.value.evidence
    assert evidence["page_key"] == "category_form"
    assert ".category-tree" in evidence["missing"]
    assert "#submit-btn" not in evidence["missing"]
    assert evidence["current_url"] == "https://mock.page/"
    assert evidence["screenshot_path"].startswith(str(tmp_path / "ui_evidence"))

    # 截图目录自动创建 + 证据文件真实写入（P-003 改版留证）
    assert (tmp_path / "ui_evidence").is_dir()
    assert os.path.exists(evidence["screenshot_path"])
    with open(evidence["screenshot_path"], "rb") as f:
        assert f.read() == b"mock-screenshot-png"


# ---------------------------------------------------------------- FallbackRunner


def test_runner_success_ok_true(tmp_path):
    runner = FallbackRunner(_config(tmp_path))
    result = runner.run(
        "category_form", "select_category", params={"category_id": 2001}
    )
    assert result["ok"] is True
    assert result["evidence"]["page_key"] == "category_form"
    assert result["evidence"]["operation"] == "select_category"
    assert result["evidence"]["url"] == "https://mock.page/category_form"
    assert runner.consecutive_failures == 0


def test_runner_page_changed_structured_failure(tmp_path):
    ops = MockPageOps(script={"missing_selectors": ["#submit-btn"]})
    runner = FallbackRunner(_config(tmp_path), ops=ops)
    result = runner.run("category_form", "select_category")
    assert result["ok"] is False
    assert result["error_code"] == "page_changed"
    assert "#submit-btn" in result["evidence"]["missing"]
    assert result["evidence"]["screenshot_path"]
    assert runner.consecutive_failures == 1  # 失败计数（不抛到队列层）


def test_runner_no_match_mapping(tmp_path):
    ops = MockPageOps(
        script={"click:.save-btn": RuntimeError("NO_MATCH: element .save-btn not found")}
    )
    runner = FallbackRunner(_config(tmp_path), ops=ops)
    result = runner.run(
        "purchase_limit_form", "set_purchase_limit", params={"purchase_limit": 2}
    )
    assert result["ok"] is False
    assert result["error_code"] == "NO_MATCH"


def test_runner_timeout_mapping(tmp_path):
    ops = MockPageOps(
        script={"fill:#purchase-limit": TimeoutError("page load timeout")}
    )
    runner = FallbackRunner(_config(tmp_path), ops=ops)
    result = runner.run(
        "purchase_limit_form", "set_purchase_limit", params={"purchase_limit": 2}
    )
    assert result["ok"] is False
    assert result["error_code"] == "TIMEOUT"


def test_runner_consecutive_failures_unexpected_manual_takeover(tmp_path):
    ops = MockPageOps(script={"click:.save-btn": RuntimeError("NO_MATCH")})
    runner = FallbackRunner(_config(tmp_path), ops=ops)
    first = runner.run(
        "purchase_limit_form", "set_purchase_limit", params={"purchase_limit": 2}
    )
    second = runner.run(
        "purchase_limit_form", "set_purchase_limit", params={"purchase_limit": 2}
    )
    assert first["ok"] is False and first["error_code"] == "NO_MATCH"
    assert second["ok"] is False
    assert second["error_code"] == "UNEXPECTED"  # 连续失败 >=2 → UNEXPECTED
    assert second["evidence"]["manual_takeover"] is True  # 建议人工接管（R10/R11）
    assert second["evidence"]["consecutive_failures"] == 2


def test_runner_batch_size_limit(tmp_path):
    runner = FallbackRunner(_config(tmp_path, batch_size=2))
    items = [
        {"page_key": "category_form", "operation": "select_category"}
        for _ in range(3)
    ]
    results = runner.run_batch(items)
    assert len(results) == 2  # 超出 batch_size 的部分不处理（P-006 ≤50/批）
    assert all(r["ok"] for r in results)


def test_runner_item_interval_timestamps(tmp_path):
    config = _config(tmp_path, item_interval_s=0.05, batch_size=10)
    runner = FallbackRunner(config)
    items = [
        {"page_key": "category_form", "operation": "select_category"}
        for _ in range(2)
    ]
    runner.run_batch(items)
    gotos = [e["at"] for e in runner.ops.ops if e["op"] == "goto"]
    assert len(gotos) == 2
    # 批内相邻商品间隔 >= item_interval_s（防风控间隔生效）
    assert gotos[1] - gotos[0] >= config.item_interval_s - 0.01


def test_runner_fill_operations_record_values(tmp_path):
    runner = FallbackRunner(_config(tmp_path))
    result = runner.run(
        "purchase_limit_form",
        "set_purchase_limit",
        params={"purchase_limit": 3},
    )
    assert result["ok"] is True
    fills = [e for e in runner.ops.ops if e["op"] == "fill"]
    assert fills[0]["selector"] == "#purchase-limit"
    assert fills[0]["value"] == "3"

    r2 = runner.run(
        "purchase_limit_form", "fill_custom_param", params={"value": "ABC-123"}
    )
    assert r2["ok"] is True
    fills2 = [e for e in runner.ops.ops if e["op"] == "fill"]
    assert fills2[-1]["selector"] == "#custom-param"
    assert fills2[-1]["value"] == "ABC-123"


def test_runner_unknown_operation_unexpected(tmp_path):
    runner = FallbackRunner(_config(tmp_path))
    result = runner.run("category_form", "no_such_operation")
    assert result["ok"] is False
    assert result["error_code"] == "UNEXPECTED"
    assert "未知 UI 操作" in result["evidence"]["error"]
