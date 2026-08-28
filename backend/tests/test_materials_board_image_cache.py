"""materials.collectors.board_image_cache 单元测试（有米云/考古加榜单图缓存，R-M2-09 / context 2.4）。

覆盖（任务书验收 ①~⑦）：
  ① key_for 格式正确（含 source/board_id/item_id）
  ② 首次缓存 miss→下载落盘→cached=True；二次缓存 hit（不重复下载，计数器验证）
  ③ 批量缓存单条 404 失败隔离（其他条成功；ok/failed 统计正确）
  ④ 失败分类：404→NO_MATCH、超时→TIMEOUT、429→RATE_LIMIT（对齐 downloader.py 码表）
  ⑤ storage 抽象注入：MockStorage（内存计数，验证 hit 不写盘）+ LocalStorage（注入目录优先于配置）
  ⑥ config 缓存目录可配（cache_dir 覆盖 + 默认值断言）
  ⑦ 多源接口化：sources 白名单默认 ["youmi"]、register_source 动态注册（kaogujia 预留）
另：enabled=False 总开关不下载；网络错误不抛出（返回 UNEXPECTED dict）；批量缺字段隔离；
    CLI 子命令 board-cache（python -m materials ...，subprocess 实测）。

纪律：pytest 必须带独立 basetemp（宪法第 12 节 / P-011），M2 模块统一
`--basetemp=".pytest-tmp-m2"`；临时文件只放 tmp_path；全程本地 http.server（标准库线程），
零外网、零登录态（R-M2-17）。
"""

from __future__ import annotations

import base64
import json
import socket
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from materials.collectors.board_image_cache import DEFAULT_SOURCES, BoardImageCache
from materials.config import load_config
from materials.downloader import NO_MATCH, RATE_LIMIT, TIMEOUT, UNEXPECTED
from materials.storage import LocalStorage

BACKEND = Path(__file__).resolve().parents[1]

# 1x1 透明 PNG（合法图片字节，假图片用）
PNG_1PX = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)


# ===========================================================================
# 本地假图片服务器（标准库 http.server，线程；零外网 R-M2-17）
# ===========================================================================
class _ImageHandler(BaseHTTPRequestHandler):
    """端点：/ok.png→200、/missing.png→404、/ratelimit.png→429、/slow.png→慢响应。"""

    def do_GET(self):
        state = self.server.state
        counts = state["counts"]
        path = self.path.split("?", 1)[0]
        if path == "/ok.png":
            counts["ok"] += 1
            self._send(200, "image/png", state["png"])
        elif path == "/slow.png":
            counts["slow"] += 1
            time.sleep(state.get("slow_seconds", 2.0))
            self._send(200, "image/png", state["png"])
        elif path == "/ratelimit.png":
            counts["ratelimit"] += 1
            self._send(429, "text/plain", b"rate limited")
        elif path == "/missing.png":
            counts["missing"] += 1
            self._send(404, "text/plain", b"not found")
        else:
            counts["other"] += 1
            self._send(404, "text/plain", b"not found")

    def _send(self, code: int, ctype: str, body: bytes) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        try:
            self.wfile.write(body)
        except OSError:
            pass  # 客户端已断开（如超时场景）

    def log_message(self, *args):  # 静默访问日志
        pass


class _ImageServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, addr, handler, state):
        super().__init__(addr, handler)
        self.state = state


@pytest.fixture()
def image_server():
    """yield (url, state)；state.counts 记录各端点命中次数（幂等/不重复下载验证用）。"""
    state = {
        "counts": {"ok": 0, "slow": 0, "ratelimit": 0, "missing": 0, "other": 0},
        "png": PNG_1PX,
        "slow_seconds": 2.0,
    }
    server = _ImageServer(("127.0.0.1", 0), _ImageHandler, state)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    url = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        yield url, state
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


@pytest.fixture()
def cache_config(tmp_path):
    """榜单图缓存隔离配置（临时缓存目录 + 默认白名单 youmi）。"""
    return load_config(
        board_cache={
            "cache_dir": tmp_path / "board_cache",
            "enabled": True,
            "sources": ["youmi"],
            "timeout_seconds": 5.0,
        }
    )


def _cache(cache_config):
    return BoardImageCache(cache_config)


# ===========================================================================
# ① key_for 格式正确
# ===========================================================================
class TestKeyFor:
    def test_format_contains_source_board_item(self):
        cache = _cache(load_config())
        key = cache.key_for("youmi", "B1", "12345")
        assert key == "board_cache/youmi/B1/12345.jpg"

    def test_multisource_kaogujia_reserved_key(self):
        # 多源接口化：考古加（预留源）的键格式同样成立（注册与否由白名单控制）
        cache = _cache(load_config())
        key = cache.key_for("kaogujia", "B2", "678")
        assert key == "board_cache/kaogujia/B2/678.jpg"

    def test_unsafe_components_sanitized(self):
        # 组件消毒：路径分隔符/../特殊字符替换为 _，防路径穿越（LocalStorage._resolve 双保险）
        cache = _cache(load_config())
        key = cache.key_for("youmi", "../etc", "a/b\\c")
        assert "/../" not in key and ".." not in key
        assert key == "board_cache/youmi/_etc/a_b_c.jpg"
        # None/空回退 unknown
        assert cache.key_for("youmi", "B1", None) == "board_cache/youmi/B1/unknown.jpg"


# ===========================================================================
# ② 首次 miss→下载落盘；二次 hit 不重复下载（幂等）
# ===========================================================================
class TestCacheImage:
    def test_first_miss_downloads_to_disk(self, image_server, cache_config):
        url, _state = image_server
        cache = _cache(cache_config)
        result = cache.cache_image("youmi", "B1", "1", f"{url}/ok.png")
        assert result["cached"] is True
        assert result["hit"] is False
        assert result["path"] == "board_cache/youmi/B1/1.jpg"
        assert result["size"] == len(PNG_1PX)
        # 落盘位置 = 配置 cache_dir（storage 默认 LocalStorage(config.board_cache.cache_dir)）
        st = LocalStorage(cache_config.board_cache.cache_dir)
        assert st.exists("board_cache/youmi/B1/1.jpg")
        assert st.read("board_cache/youmi/B1/1.jpg") == PNG_1PX

    def test_second_hit_no_redownload(self, image_server, cache_config):
        url, state = image_server
        cache = _cache(cache_config)
        r1 = cache.cache_image("youmi", "B1", "1", f"{url}/ok.png")
        r2 = cache.cache_image("youmi", "B1", "1", f"{url}/ok.png")
        assert r1["cached"] is True and r1["hit"] is False
        assert r2["cached"] is True and r2["hit"] is True
        assert r2["path"] == r1["path"]
        assert r2["size"] == len(PNG_1PX)
        # 计数器验证：只下载了一次（幂等，hit 不重复下载）
        assert state["counts"]["ok"] == 1

    def test_headers_passed_through(self, image_server, cache_config):
        url, state = image_server
        cache = _cache(cache_config)
        result = cache.cache_image("youmi", "B1", "h1", f"{url}/ok.png", headers={"X-Test": "1"})
        assert result["cached"] is True
        assert state["counts"]["ok"] == 1


# ===========================================================================
# ④ 失败分类（对齐 downloader.py 码表）
# ===========================================================================
class TestFailureClassification:
    def test_404_maps_to_no_match(self, image_server, cache_config):
        url, _state = image_server
        cache = _cache(cache_config)
        result = cache.cache_image("youmi", "B1", "miss", f"{url}/missing.png")
        assert result["cached"] is False and result["hit"] is False
        assert result["path"] is None
        assert result["error_code"] == NO_MATCH
        assert result["http_status"] == 404

    def test_timeout_maps_to_timeout(self, image_server, tmp_path):
        config = load_config(board_cache={"cache_dir": tmp_path / "bc", "timeout_seconds": 0.5})
        url, _state = image_server
        cache = BoardImageCache(config)
        result = cache.cache_image("youmi", "B1", "slow", f"{url}/slow.png")
        assert result["cached"] is False
        assert result["error_code"] == TIMEOUT

    def test_429_maps_to_rate_limit(self, image_server, cache_config):
        url, _state = image_server
        cache = _cache(cache_config)
        result = cache.cache_image("youmi", "B1", "rl", f"{url}/ratelimit.png")
        assert result["cached"] is False
        assert result["error_code"] == RATE_LIMIT
        assert result["http_status"] == 429

    def test_network_error_never_raises(self, cache_config):
        # 连接被拒：返回 UNEXPECTED dict，不抛出（R-M2-09 缓存失败不影响主流程）
        s = socket.socket()
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
        s.close()
        cache = _cache(cache_config)
        result = cache.cache_image("youmi", "B1", "refused", f"http://127.0.0.1:{port}/x.png")
        assert result["cached"] is False
        assert result["error_code"] == UNEXPECTED


# ===========================================================================
# ③ 批量缓存单条失败隔离（R-M2-09）
# ===========================================================================
class TestBatch:
    def test_404_failure_isolation(self, image_server, cache_config):
        url, _state = image_server
        cache = _cache(cache_config)
        items = [
            {"item_id": "1", "image_url": f"{url}/ok.png"},
            {"item_id": "2", "image_url": f"{url}/missing.png"},     # 404 → NO_MATCH
            {"item_id": "3", "image_url": f"{url}/ratelimit.png"},   # 429 → RATE_LIMIT
            {"item_id": "4", "image_url": f"{url}/ok.png"},
        ]
        result = cache.cache_board_images("youmi", "B1", items)
        assert result["ok"] == 2          # 失败条不影响其他条成功
        assert result["total"] == 4
        codes = {f["item_id"]: f["error_code"] for f in result["failed"]}
        assert codes == {"2": NO_MATCH, "3": RATE_LIMIT}
        # 成功条已落盘
        st = LocalStorage(cache_config.board_cache.cache_dir)
        assert st.exists("board_cache/youmi/B1/1.jpg")
        assert st.exists("board_cache/youmi/B1/4.jpg")
        assert not st.exists("board_cache/youmi/B1/2.jpg")

    def test_batch_missing_fields_isolated(self, cache_config):
        cache = _cache(cache_config)
        result = cache.cache_board_images(
            "youmi", "B1",
            [{"item_id": "1"}, {"image_url": "http://127.0.0.1:1/x.png"}],
        )
        assert result["ok"] == 0
        assert len(result["failed"]) == 2
        assert all(f["error_code"] == UNEXPECTED for f in result["failed"])

    def test_batch_empty(self, cache_config):
        cache = _cache(cache_config)
        result = cache.cache_board_images("youmi", "B1", [])
        assert result == {"ok": 0, "total": 0, "failed": []}


# ===========================================================================
# ⑤ storage 抽象注入（MockStorage 计数 + LocalStorage 注入目录）
# ===========================================================================
class MockStorage:
    """内存版 storage（只实现 BoardImageCache 用到的接口，duck-typing）。"""

    def __init__(self):
        self.data: dict[str, bytes] = {}
        self.put_calls: list[str] = []
        self.exists_calls: list[str] = []

    def exists(self, key: str) -> bool:
        self.exists_calls.append(key)
        return key in self.data

    def put(self, key: str, data: bytes) -> str:
        self.put_calls.append(key)
        self.data[key] = data
        return key

    def stat(self, key: str) -> dict:
        if key not in self.data:
            raise FileNotFoundError(key)
        return {"key": key, "size": len(self.data[key])}


class TestStorageInjection:
    def test_mock_storage_hit_no_put(self, image_server, cache_config):
        url, _state = image_server
        mock = MockStorage()
        cache = BoardImageCache(cache_config, storage=mock)
        r1 = cache.cache_image("youmi", "B1", "1", f"{url}/ok.png")
        r2 = cache.cache_image("youmi", "B1", "1", f"{url}/ok.png")
        assert r1["cached"] is True and r1["hit"] is False
        assert r2["cached"] is True and r2["hit"] is True
        assert len(mock.put_calls) == 1          # 只写一次
        assert len(mock.exists_calls) == 2       # 两次都先探测
        assert mock.data["board_cache/youmi/B1/1.jpg"] == PNG_1PX

    def test_local_storage_injected_dir_wins(self, image_server, tmp_path):
        # 注入的 LocalStorage 根目录优先于 config.board_cache.cache_dir
        config = load_config(board_cache={"cache_dir": tmp_path / "ignored"})
        injected = LocalStorage(tmp_path / "injected")
        cache = BoardImageCache(config, storage=injected)
        url, _state = image_server
        result = cache.cache_image("youmi", "B1", "9", f"{url}/ok.png")
        assert result["cached"] is True
        assert (tmp_path / "injected" / "board_cache" / "youmi" / "B1" / "9.jpg").is_file()
        assert not (tmp_path / "ignored" / "board_cache").exists()


# ===========================================================================
# ⑥ config：缓存目录可配 + 默认值
# ===========================================================================
class TestConfig:
    def test_cache_dir_configurable(self, cache_config, tmp_path):
        assert cache_config.board_cache.cache_dir == tmp_path / "board_cache"
        assert cache_config.board_cache.enabled is True
        assert cache_config.board_cache.sources == ["youmi"]
        assert cache_config.board_cache.timeout_seconds == 5.0

    def test_defaults(self):
        cfg = load_config()
        bc = cfg.board_cache
        assert bc.cache_dir == Path("data/board_cache")
        assert bc.enabled is True
        assert bc.sources == ["youmi"]
        assert bc.timeout_seconds == 30.0
        assert bc.max_bytes > 0

    def test_enabled_false_no_download(self, image_server, tmp_path):
        config = load_config(board_cache={"cache_dir": tmp_path / "bc", "enabled": False})
        cache = BoardImageCache(config)
        url, state = image_server
        result = cache.cache_image("youmi", "B1", "1", f"{url}/ok.png")
        assert result["cached"] is False
        assert result["error_code"] == UNEXPECTED
        assert state["counts"]["ok"] == 0  # 未发起下载


# ===========================================================================
# ⑦ 多源接口化：白名单默认 ["youmi"] + register_source 动态注册（kaogujia 预留）
# ===========================================================================
class TestMultiSource:
    def test_default_whitelist_is_youmi(self):
        cache = _cache(load_config())
        assert DEFAULT_SOURCES == ["youmi"]
        assert cache.sources == {"youmi"}
        assert "kaogujia" not in cache.sources  # 考古加预留，未注册

    def test_unregistered_source_fails_without_raise(self, image_server, cache_config):
        cache = _cache(cache_config)
        url, _state = image_server
        result = cache.cache_image("kaogujia", "B1", "1", f"{url}/ok.png")
        assert result["cached"] is False
        assert result["error_code"] == UNEXPECTED
        assert "考古加" in result["message"] or "kaogujia" in result["message"]

    def test_register_source_enables_kaogujia(self, image_server, cache_config):
        cache = _cache(cache_config)
        cache.register_source("kaogujia")
        assert "kaogujia" in cache.sources
        url, _state = image_server
        result = cache.cache_image("kaogujia", "B1", "1", f"{url}/ok.png")
        assert result["cached"] is True
        assert result["path"] == "board_cache/kaogujia/B1/1.jpg"

    def test_constructor_sources_whitelist(self, cache_config):
        cache = BoardImageCache(cache_config, sources=["youmi", "kaogujia"])
        assert cache.sources == {"youmi", "kaogujia"}


# ===========================================================================
# CLI 子命令（python -m materials board-cache ...，subprocess 实测）
# ===========================================================================
class TestCliBoardCache:
    def test_happy_path_downloads(self, image_server, tmp_path):
        url, _state = image_server
        items = json.dumps([{"item_id": "1", "image_url": f"{url}/ok.png"}])
        cache_dir = tmp_path / "cli-cache"
        r = subprocess.run(
            [sys.executable, "-m", "materials", "board-cache",
             "--source", "youmi", "--board", "B1", "--json", items,
             "--cache-dir", str(cache_dir)],
            cwd=str(BACKEND), capture_output=True, timeout=60,
        )
        assert r.returncode == 0, r.stderr.decode("utf-8", "replace")
        out = r.stdout.decode("utf-8", "replace")
        assert '"ok": 1' in out and '"failed": []' in out
        assert (cache_dir / "board_cache" / "youmi" / "B1" / "1.jpg").is_file()

    def test_all_failed_exits_nonzero(self, image_server, tmp_path):
        url, _state = image_server
        items = json.dumps([{"item_id": "2", "image_url": f"{url}/missing.png"}])
        cache_dir = tmp_path / "cli-cache2"
        r = subprocess.run(
            [sys.executable, "-m", "materials", "board-cache",
             "--source", "youmi", "--board", "B1", "--json", items,
             "--cache-dir", str(cache_dir)],
            cwd=str(BACKEND), capture_output=True, timeout=60,
        )
        assert r.returncode != 0
        out = r.stdout.decode("utf-8", "replace")
        assert '"ok": 0' in out and "NO_MATCH" in out

    def test_invalid_json_exits_nonzero(self, tmp_path):
        r = subprocess.run(
            [sys.executable, "-m", "materials", "board-cache",
             "--source", "youmi", "--board", "B1", "--json", "{not json}"],
            cwd=str(BACKEND), capture_output=True, timeout=60,
        )
        assert r.returncode != 0
        assert "JSON" in (r.stderr or b"").decode("utf-8", "replace")
