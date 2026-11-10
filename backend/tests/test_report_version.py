# -*- coding: utf-8 -*-
"""P0-2 批次 1（B3）：B1 纯函数测试（round-133）。

覆盖 round-132-cdx §四.1（三源优先级/时间 canonical/NFC/case-sensitive ID/hash 绑定/
长度边界/captured_at 排除）+ §3.2 黄金向量。纯函数无 DB。
"""
import unicodedata
from datetime import datetime, timezone, timedelta
from decimal import Decimal

import pytest

import sys
sys.path.insert(0, __file__.rsplit("\\", 2)[0])
from domain.report.version import (  # noqa: E402
    ObservationValidationError,
    build_report_version_key,
    canonical_ts,
    hash_raw_evidence,
    normalize_version_id,
)


# ---------------------------------------------------------------- 三源优先级
def test_priority_id_only():
    assert build_report_version_key("ABC", None, None) == "id:ABC"


def test_priority_ts_only():
    dt = datetime(2025, 1, 1, 8, 0, 0, 123456, tzinfo=timezone(timedelta(hours=8)))
    assert build_report_version_key(None, dt, None) == "ts:2025-01-01T00:00:00.123456Z"


def test_priority_hash_only():
    assert build_report_version_key(None, None, "a" * 64) == "hash:" + "a" * 64


def test_priority_id_wins_over_ts_hash():
    dt = datetime(2025, 1, 1, tzinfo=timezone.utc)
    assert build_report_version_key("ID1", dt, "b" * 64) == "id:ID1"


def test_priority_ts_wins_over_hash():
    dt = datetime(2025, 1, 1, tzinfo=timezone.utc)
    assert build_report_version_key(None, dt, "c" * 64) == "ts:2025-01-01T00:00:00.000000Z"


def test_all_sources_missing_raises():
    with pytest.raises(ObservationValidationError):
        build_report_version_key(None, None, None)


# ---------------------------------------------------------------- 时间 canonical（F132 §3.2）
def test_canonical_ts_fixed_6_micros_z():
    dt = datetime(2025, 6, 15, 12, 30, 45, 999999, tzinfo=timezone.utc)
    assert canonical_ts(dt) == "2025-06-15T12:30:45.999999Z"


def test_canonical_ts_cross_timezone_same():
    utc = datetime(2025, 1, 1, 0, 0, 0, 123456, tzinfo=timezone.utc)
    shanghai = datetime(2025, 1, 1, 8, 0, 0, 123456, tzinfo=timezone(timedelta(hours=8)))
    assert canonical_ts(utc) == canonical_ts(shanghai) == "2025-01-01T00:00:00.123456Z"


def test_canonical_ts_naive_rejected():
    with pytest.raises(ObservationValidationError):
        canonical_ts(datetime(2025, 1, 1, tzinfo=None))


# ---------------------------------------------------------------- NFC / case-sensitive ID（F132-3）
def test_version_id_nfc_normalized():
    # é 组合与分解形式 NFC 后同一
    composed = "caf\u00e9"
    decomposed = "cafe\u0301"
    assert normalize_version_id(composed) == normalize_version_id(decomposed) == "caf\u00e9"
    k1 = build_report_version_key(composed, None, None)
    k2 = build_report_version_key(decomposed, None, None)
    assert k1 == k2 == "id:" + unicodedata.normalize("NFC", composed)


def test_version_id_case_sensitive():
    assert build_report_version_key("ABC", None, None) != build_report_version_key("abc", None, None)


def test_version_id_trim_internal_preserved():
    assert normalize_version_id("  abc  def  ") == "abc  def"
    assert build_report_version_key("  ABC  ", None, None) == "id:ABC"


def test_version_id_empty_is_missing():
    assert normalize_version_id("") is None
    assert normalize_version_id("   ") is None
    assert build_report_version_key("   ", datetime(2025, 1, 1, tzinfo=timezone.utc), None) \
        == "ts:2025-01-01T00:00:00.000000Z"


# ---------------------------------------------------------------- hash 绑定（F132-4）
def test_hash_raw_evidence_known():
    # sha256(b"x")
    assert hash_raw_evidence(b"x") == \
        "2d711642b726b04401627ca9fbac32f5c8530fb1903cc4db02258717921a4881"


def test_hash_raw_evidence_empty_rejected():
    with pytest.raises(ObservationValidationError):
        hash_raw_evidence(b"")
    with pytest.raises(ObservationValidationError):
        hash_raw_evidence("not bytes")  # type: ignore


def test_hash_key_rejects_bad_digest():
    with pytest.raises(ObservationValidationError):
        build_report_version_key(None, None, "ABC")  # 非 64 hex
    with pytest.raises(ObservationValidationError):
        build_report_version_key(None, None, "A" * 64)  # 大写 hex 拒绝
    with pytest.raises(ObservationValidationError):
        build_report_version_key(None, None, "a" * 63)  # 长度不足


# ---------------------------------------------------------------- 长度边界（varchar(128)）
def test_length_boundary_127_ok():
    # 全键 127 字符（id: 前缀 3 + 内容 124）——边界内
    key = build_report_version_key("A" * 124, None, None)
    assert key == "id:" + "A" * 124
    assert len(key) == 127 and len(key.encode("utf-8")) == 127


def test_length_boundary_128_exact_ok():
    # 全键 128 字符（id: 前缀 3 + 内容 125）——恰好边界
    key = build_report_version_key("C" * 125, None, None)
    assert len(key) == 128 and len(key.encode("utf-8")) == 128


def test_length_boundary_129_rejected():
    with pytest.raises(ObservationValidationError):
        build_report_version_key("D" * 126, None, None)  # 全键 129
    # hash 源：hash: 前缀 5 + 64 = 69 ok；不超长，此处仅验证不抛错
    assert build_report_version_key(None, None, "e" * 64) == "hash:" + "e" * 64


def test_utf8_multibyte_length_gate():
    # 中文内容：UTF-8 字节长度 > 字符长度；125 个中文字符（375 字节）应超 128 字节边界
    with pytest.raises(ObservationValidationError):
        build_report_version_key("中" * 42, None, None)  # 42*3+3=129 字节


# ---------------------------------------------------------------- captured_at 排除（F132-2）
def test_captured_at_never_in_key():
    dt = datetime(2025, 1, 1, tzinfo=timezone.utc)
    # captured_at 不参与版本键：platform_updated_at 相同则键相同，与 captured_at 无关
    k1 = build_report_version_key(None, dt, None)
    assert k1 == "ts:2025-01-01T00:00:00.000000Z"
    # captured_at 不存在于三源签名中——接口层面已排除；此测试保证 ts 源不被 captured 替代
    assert "captured" not in k1


# ---------------------------------------------------------------- R134-2：非 str version ID / aware 判定
import datetime as _dt


class _NoneOffsetTZ(_dt.tzinfo):
    """utcoffset() 返回 None 的自定义 tzinfo——必须按 naive 拒绝，防跨宿主时区破坏确定性。"""

    def utcoffset(self, dt):
        return None

    def dst(self, dt):
        return None

    def tzname(self, dt):
        return "NONE_OFFSET"


@pytest.mark.parametrize("bad", [123, True, b"bytes", object(), 4.5, ["a"]],
                         ids=["int", "bool", "bytes", "object", "float", "list"])
def test_version_id_non_str_rejected(bad):
    """R134-2：platform_version_id 只接受 None 或真实 str，其余类型拒绝（不再静默 str()）。"""
    with pytest.raises(ObservationValidationError):
        build_report_version_key(bad, None, None)
    with pytest.raises(ObservationValidationError):
        normalize_version_id(bad)


def test_version_id_none_ok():
    assert normalize_version_id(None) is None


def test_canonical_ts_none_offset_tz_rejected():
    """R134-2：tzinfo 存在但 utcoffset() is None -> 拒绝（不能按宿主本地时区解释）。"""
    dt = datetime(2025, 12, 31, tzinfo=_NoneOffsetTZ())
    with pytest.raises(ObservationValidationError):
        canonical_ts(dt)


def test_build_key_none_offset_ts_rejected():
    dt = datetime(2025, 12, 31, tzinfo=_NoneOffsetTZ())
    with pytest.raises(ObservationValidationError):
        build_report_version_key(None, dt, None)


def test_cross_host_tz_determinism():
    """R134-2：同时刻不同时区生成同一版本键（跨宿主确定性，6 位微秒 Z）。"""
    utc = datetime(2025, 1, 1, 0, 0, 0, 123456, tzinfo=timezone.utc)
    sh = datetime(2025, 1, 1, 8, 0, 0, 123456, tzinfo=timezone(timedelta(hours=8)))
    ny = datetime(2024, 12, 31, 19, 0, 0, 123456, tzinfo=timezone(timedelta(hours=-5)))
    keys = {build_report_version_key(None, d, None) for d in (utc, sh, ny)}
    assert keys == {"ts:2025-01-01T00:00:00.123456Z"}
