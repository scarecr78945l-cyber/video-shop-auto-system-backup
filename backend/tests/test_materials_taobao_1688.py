"""materials.collectors.taobao_refs / alibaba_1688 单元测试（子代理 B2'；context/README.md 2.3 + R-M2-08）。

覆盖（任务书验收 ⑥ + 附加）：
  ① fixtures 解析：images/videos 字段完整（数量/字段/URL 脱敏），id/URL/裸 id 匹配
  ② 降级路径（R-M2-08）：视频缺失/失败 → images 照常 + videos=[] + note
  ③ page_changed（P-003）：选择器未命中 → HTML 快照证据 + PLATFORM_REJECT 结构化失败
  ④ 错误分类：AUTH_REQUIRED/PLATFORM_REJECT/NO_MATCH/TIMEOUT/RATE_LIMIT/UNEXPECTED
     （对齐 downloader.py 码表；classify_error 纯函数 + fixtures simulate_error）
  ⑤ source_platform 口径：淘宝 → "淘宝"；1688 → "1688"（含每条媒体条目）
另：limit 截断、NO_MATCH、enabled=False 开关、config 默认值/覆盖、auto 骨架 NotImplementedError、
    CLI 子命令（python -m materials taobao-refs，subprocess 实测，含验收 URL 不崩溃）。

纪律：pytest 必须带独立 basetemp（宪法第 12 节 / P-011）：--basetemp=".pytest-tmp-m2"；
样本用仓库真实 fixtures（cfg_materials.fixtures_dir=backend/fixtures）+ tmp 定制样本；
零外网、零登录态、零浏览器（R-M2-17）。
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from materials.collectors.alibaba_1688 import AlibabaCollector
from materials.collectors.taobao_refs import ERROR_CODES, TaobaoReferencesCollector
from materials.config import load_config
from materials.downloader import (
    AUTH_REQUIRED,
    NO_MATCH,
    PLATFORM_REJECT,
    RATE_LIMIT,
    TIMEOUT,
    UNEXPECTED,
)

BACKEND = Path(__file__).resolve().parents[1]


def _taobao(config, **kw) -> TaobaoReferencesCollector:
    return TaobaoReferencesCollector(config, **kw)


def _alibaba(config, **kw) -> AlibabaCollector:
    return AlibabaCollector(config, **kw)


def _write_fixture(tmp_path, filename: str, items: list) -> Path:
    """写 tmp 定制 fixtures（materials/<filename>），返回 fixtures_dir。"""
    d = tmp_path / "fixtures" / "materials"
    d.mkdir(parents=True, exist_ok=True)
    (d / filename).write_text(
        json.dumps({"items": items}, ensure_ascii=False), encoding="utf-8"
    )
    return tmp_path / "fixtures"


def _tmp_config(tmp_path, filename: str, items: list):
    return load_config(
        fixtures_dir=_write_fixture(tmp_path, filename, items),
        data_dir=tmp_path / "data",
    )


# ===========================================================================
# ① fixtures 解析（images/videos 字段完整 + 匹配方式）
# ===========================================================================
class TestFixturesParse:
    def test_images_videos_complete(self, cfg_materials):
        result = _taobao(cfg_materials).collect("710000001", limit=5)
        assert result["ok"] is True
        assert result["error_code"] is None
        assert result["source_platform"] == "淘宝"
        assert result["title"]
        assert len(result["images"]) == 3
        assert len(result["videos"]) == 2
        for img in result["images"]:
            assert img["url"].startswith("http")
            assert img["source_platform"] == "淘宝"
            assert img["media_type"] == "image"
        for v in result["videos"]:
            assert v["url"].startswith("http")
            assert v["source_platform"] == "淘宝"
            assert v["media_type"] == "video"
            assert v["duration"] > 0
            assert v["resolution"]
        ev = result["evidence"]
        assert ev["mode"] == "fixtures"
        assert "taobao_refs.json" in ev["source_file"]
        assert ev["matched_id"] == "710000001"

    def test_match_by_full_url(self, cfg_materials):
        result = _taobao(cfg_materials).collect("https://item.taobao.com/item.htm?id=710000002")
        assert result["ok"] is True
        assert result["evidence"]["matched_id"] == "710000002"

    def test_match_by_bare_id(self, cfg_materials):
        result = _taobao(cfg_materials).collect("710000005")
        assert result["ok"] is True
        assert result["evidence"]["matched_id"] == "710000005"

    def test_limit_truncation(self, cfg_materials):
        # 710000001：3 图 2 视频；limit=2 → 各自截断
        result = _taobao(cfg_materials).collect("710000001", limit=2)
        assert len(result["images"]) == 2
        assert len(result["videos"]) == 2
        assert result["evidence"]["limit"] == 2

    def test_unknown_input_no_match(self, cfg_materials):
        result = _taobao(cfg_materials).collect("https://item.taobao.com/item.htm?id=999999999999")
        assert result["ok"] is False
        assert result["error_code"] == NO_MATCH
        assert result["images"] == [] and result["videos"] == []
        assert result["evidence"]["fixtures_count"] == 5

    def test_1688_match_by_offer_url(self, cfg_materials):
        result = _alibaba(cfg_materials).collect("https://detail.1688.com/offer/812345678901.html")
        assert result["ok"] is True
        assert result["source_platform"] == "1688"
        assert len(result["images"]) == 3
        assert len(result["videos"]) == 2


# ===========================================================================
# ② 降级路径（R-M2-08：视频失败/缺失 → images 照常 + videos=[] + note）
# ===========================================================================
class TestDegrade:
    def test_videos_empty_note_degrade(self, cfg_materials):
        # 真实样本 710000003 无视频（videos=[]）→ 降级
        result = _taobao(cfg_materials).collect("710000003")
        assert result["ok"] is True
        assert result["videos"] == []
        assert len(result["images"]) == 4  # images 照常
        assert result["note"] and "R-M2-08" in result["note"]

    def test_videos_error_note_mentions_code(self, tmp_path):
        items = [{
            "id": "1", "url": "https://item.taobao.com/item.htm?id=1", "title": "样本",
            "images": ["https://img.example.com/1.jpg"],
            "videos_error": "TIMEOUT",
            "evidence": {"fixture_key": "tmp"},
        }]
        config = _tmp_config(tmp_path, "taobao_refs.json", items)
        result = _taobao(config).collect("1")
        assert result["ok"] is True
        assert result["videos"] == []
        assert len(result["images"]) == 1
        assert "TIMEOUT" in result["note"] and "R-M2-08" in result["note"]

    def test_1688_degrade(self, cfg_materials):
        # 真实样本 812345678903 无视频 → 降级
        result = _alibaba(cfg_materials).collect("812345678903")
        assert result["ok"] is True
        assert result["videos"] == []
        assert len(result["images"]) == 3
        assert result["note"] and "R-M2-08" in result["note"]


# ===========================================================================
# ③ page_changed（P-003：选择器未命中 → HTML 快照证据 + PLATFORM_REJECT）
# ===========================================================================
class TestPageChanged:
    def test_simulated_page_changed_rejects_with_evidence(self, tmp_path):
        items = [{
            "id": "2", "url": "https://item.taobao.com/item.htm?id=2", "title": "样本",
            "images": ["https://img.example.com/2.jpg"],
            "videos": [],
            "simulate_page_changed": True,
            "missing_selectors": ["img_list", "video_box"],
            "page_changed_snapshot": "<html><body>page_changed 模拟快照内容</body></html>",
            "evidence": {"fixture_key": "tmp"},
        }]
        config = _tmp_config(tmp_path, "taobao_refs.json", items)
        result = _taobao(config).collect("2")
        assert result["ok"] is False
        assert result["error_code"] == PLATFORM_REJECT
        assert result["images"] == [] and result["videos"] == []
        ev = result["evidence"]
        assert ev["missing_selectors"] == ["img_list", "video_box"]
        assert "page_changed" in result["message"] or "page_changed" in ev["message"]
        # HTML 快照已落盘（data_dir/evidence/page_changed/）
        assert ev["html_snapshot_path"]
        snap = Path(ev["html_snapshot_path"])
        assert snap.is_file()
        assert "page_changed 模拟快照内容" in snap.read_text(encoding="utf-8")

    def test_check_selectors_pure_helper(self, cfg_materials):
        html = '<div class="gallery"><img src="a.jpg"></div><video src="b.mp4"></video>'
        sels = {"gallery": r'class="gallery"', "video": r"<video", "title": r"<h1"}
        collector = _taobao(cfg_materials)
        assert collector.check_selectors(html, sels) == ["title"]
        assert collector.page_changed(html, sels) is True
        assert collector.page_changed(html, {"gallery": r'class="gallery"', "video": r"<video"}) is False
        assert collector.check_selectors("<html></html>", {}) == []


# ===========================================================================
# ④ 错误分类（对齐 downloader.py 码表）
# ===========================================================================
class TestErrorClassification:
    def test_error_codes_aligned_with_downloader(self):
        assert set(ERROR_CODES) == {AUTH_REQUIRED, PLATFORM_REJECT, NO_MATCH, TIMEOUT, RATE_LIMIT, UNEXPECTED}

    @pytest.mark.parametrize(
        "text,expected",
        [
            ("请先登录后再查看商品详情", AUTH_REQUIRED),
            ("登录失效，请重新登录", AUTH_REQUIRED),
            ("请求过于频繁，请稍后再试", RATE_LIMIT),
            ("触发验证码校验", RATE_LIMIT),
            ("签名校验失败，请求被拒绝", PLATFORM_REJECT),
            ("页面结构变化（page_changed）", PLATFORM_REJECT),
            ("正常商品页 HTML", None),
        ],
    )
    def test_classify_error_hints(self, cfg_materials, text, expected):
        assert _taobao(cfg_materials).classify_error(text) == expected

    def test_classify_error_auth_precedence(self, cfg_materials):
        # 顺序敏感：登录特征优先于频控
        assert _taobao(cfg_materials).classify_error("请登录，访问过于频繁") == AUTH_REQUIRED

    @pytest.mark.parametrize("code", [AUTH_REQUIRED, TIMEOUT, PLATFORM_REJECT, RATE_LIMIT])
    def test_simulated_error_from_fixture(self, tmp_path, code):
        items = [{
            "id": "3", "url": "https://item.taobao.com/item.htm?id=3", "title": "样本",
            "images": ["https://img.example.com/3.jpg"],
            "videos": [],
            "simulate_error": code,
            "evidence": {"fixture_key": "tmp"},
        }]
        config = _tmp_config(tmp_path, "taobao_refs.json", items)
        result = _taobao(config).collect("3")
        assert result["ok"] is False
        assert result["error_code"] == code
        assert result["images"] == [] and result["videos"] == []
        assert result["evidence"]["simulated"] is True


# ===========================================================================
# ⑤ source_platform 口径（context 1.1：淘宝 / 1688）
# ===========================================================================
class TestSourcePlatform:
    def test_taobao_platform(self, cfg_materials):
        result = _taobao(cfg_materials).collect("710000001")
        assert result["source_platform"] == "淘宝"

    def test_1688_platform(self, cfg_materials):
        result = _alibaba(cfg_materials).collect("812345678901")
        assert result["source_platform"] == "1688"

    def test_media_items_carry_platform(self, cfg_materials):
        result = _alibaba(cfg_materials).collect("812345678901")
        assert all(i["source_platform"] == "1688" for i in result["images"] + result["videos"])
        result2 = _taobao(cfg_materials).collect("710000001")
        assert all(i["source_platform"] == "淘宝" for i in result2["images"] + result2["videos"])


# ===========================================================================
# config：默认值 + 覆盖 + enabled 开关 + auto 骨架
# ===========================================================================
class TestConfig:
    def test_defaults(self):
        cfg = load_config()
        assert cfg.taobao_refs.enabled is True
        assert cfg.taobao_refs.fixtures_mode is True
        assert cfg.taobao_refs.cdp_port == 9223
        assert cfg.taobao_refs.selectors == {}
        assert cfg.alibaba.enabled is True
        assert cfg.alibaba.fixtures_mode is True
        assert cfg.alibaba.cdp_port == 9223
        assert cfg.alibaba.selectors == {}

    def test_overrides_via_load_config(self):
        cfg = load_config(
            taobao_refs={"enabled": False, "fixtures_mode": False, "cdp_port": 9333,
                         "selectors": {"title": r"<h1"}},
            alibaba={"cdp_port": 9444},
        )
        assert cfg.taobao_refs.enabled is False
        assert cfg.taobao_refs.fixtures_mode is False
        assert cfg.taobao_refs.cdp_port == 9333
        assert cfg.taobao_refs.selectors == {"title": r"<h1"}
        assert cfg.alibaba.cdp_port == 9444

    def test_disabled_returns_structured_failure(self, tmp_path):
        config = _tmp_config(tmp_path, "taobao_refs.json", [])
        config = load_config(
            taobao_refs={"enabled": False},
            fixtures_dir=config.fixtures_dir, data_dir=config.data_dir,
        )
        result = _taobao(config).collect("710000001")
        assert result["ok"] is False
        assert result["error_code"] == UNEXPECTED
        assert "禁用" in result["evidence"]["message"]

    def test_auto_mode_raises_not_implemented(self, tmp_path):
        config = _tmp_config(tmp_path, "taobao_refs.json", [])
        config = load_config(
            taobao_refs={"fixtures_mode": False},
            fixtures_dir=config.fixtures_dir, data_dir=config.data_dir,
        )
        with pytest.raises(NotImplementedError):
            _taobao(config).collect("710000001")


# ===========================================================================
# CLI 子命令（python -m materials taobao-refs，subprocess 实测）
# ===========================================================================
class TestCliTaobaoRefs:
    def test_fixtures_cli_outputs_valid_json(self):
        r = subprocess.run(
            [sys.executable, "-m", "materials", "taobao-refs",
             "--url", "https://item.taobao.com/item.htm?id=710000001",
             "--mode", "fixtures", "--limit", "3"],
            cwd=str(BACKEND), capture_output=True, timeout=60,
        )
        assert r.returncode == 0, r.stderr.decode("utf-8", "replace")
        data = json.loads(r.stdout.decode("utf-8", "replace"))
        assert data["ok"] is True
        assert data["source_platform"] == "淘宝"
        assert len(data["images"]) == 3
        assert len(data["videos"]) == 2

    def test_acceptance_url_no_crash_valid_json(self):
        # 任务书验收命令原样：URL 不在 fixtures → NO_MATCH 结构化失败，仍输出合法 JSON 且不崩溃
        r = subprocess.run(
            [sys.executable, "-m", "materials", "taobao-refs",
             "--url", "https://item.taobao.com/xxx",
             "--mode", "fixtures", "--limit", "3"],
            cwd=str(BACKEND), capture_output=True, timeout=60,
        )
        assert r.returncode == 0, r.stderr.decode("utf-8", "replace")
        data = json.loads(r.stdout.decode("utf-8", "replace"))
        assert data["ok"] is False
        assert data["error_code"] == NO_MATCH
        assert data["images"] == [] and data["videos"] == []

    def test_cli_degrade_entry(self):
        # 710000003 无视频 → CLI 输出降级（videos=[] + note）
        r = subprocess.run(
            [sys.executable, "-m", "materials", "taobao-refs",
             "--url", "710000003", "--mode", "fixtures"],
            cwd=str(BACKEND), capture_output=True, timeout=60,
        )
        assert r.returncode == 0, r.stderr.decode("utf-8", "replace")
        data = json.loads(r.stdout.decode("utf-8", "replace"))
        assert data["ok"] is True
        assert data["videos"] == []
        assert data["note"] and "R-M2-08" in data["note"]
