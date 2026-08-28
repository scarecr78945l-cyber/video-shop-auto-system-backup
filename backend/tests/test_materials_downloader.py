"""materials.downloader 单元测试：本地 http.server 测试文件服务器 + 内存 fake repo。

场景（任务书验收）：
  ① 成功下载 + MD5 正确
  ② 断点续传（服务端支持 Range，客户端中断后续传一致；416 → 全量重下）
  ③ 错误分类（404→NO_MATCH、429→RATE_LIMIT、超时→TIMEOUT）
  ④ 退避 next_run_at 计算（RATE_LIMIT 180s，节流 0~4 级 ×1/2/4/8/16；AUTH_REQUIRED→None）
  ⑤ 熔断：同平台连续失败 ≥2 → risk_control=1；冷却后探针成功 → 恢复 0
  ⑥ 租约过期回收 + 同 worker 进程重启恢复
  ⑦ fake repo 全程注入，不依赖真实 DB（零 SQLite 文件产生）
  另：worker 全链路（claim→fetch→storage→md5→finish_success）与 HTTP API 冒烟。

纪律：pytest 一律带 --basetemp=".pytest-tmp"（P-001）；临时文件只放 tmp_path；
不访问任何外网（全部走 127.0.0.1 本地服务器）。
"""

from __future__ import annotations

import hashlib
import json
import re
import threading
import time
from datetime import datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

import pytest
import requests

from materials.config import DownloadConfig, load_config
from materials.downloader import (
    DownloadError,
    DownloadWorker,
    DownloaderService,
    InMemoryDownloadJobRepo,
    RETRY_BACKOFF_SECONDS,
    compute_md5,
    compute_next_run_at,
    fetch_file,
    redact_url,
)
from materials.downloader import _iso_now, _utcnow
from materials.downloader_api import DownloadApiServer
from materials.storage import LocalStorage


# ===========================================================================
# 本地测试文件服务器（Range 206 / 404 / 固定状态码 / 慢速端点）
# ===========================================================================
class _RangeHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):  # 静默，不刷测试输出
        pass

    def do_GET(self):
        srv = self.server
        url = urlsplit(self.path)
        if url.path.startswith("/slow"):
            time.sleep(srv.slow_seconds)
        if url.path.startswith("/status/"):
            code = int(url.path.split("/")[2])
            self.send_response(code)
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        rel = url.path.lstrip("/")
        fp = Path(srv.root) / rel
        if not fp.is_file():
            self.send_response(404)
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        data = fp.read_bytes()
        rng = self.headers.get("Range")
        if rng:
            m = re.match(r"bytes=(\d+)-(\d*)$", rng.strip())
            if m:
                start = int(m.group(1))
                end = int(m.group(2)) if m.group(2) else len(data) - 1
                end = min(end, len(data) - 1)
                if start >= len(data):
                    self.send_response(416)
                    self.send_header("Content-Range", f"bytes */{len(data)}")
                    self.end_headers()
                    return
                chunk = data[start : end + 1]
                self.send_response(206)
                self.send_header("Content-Range", f"bytes {start}-{end}/{len(data)}")
                self.send_header("Content-Length", str(len(chunk)))
                self.send_header("Accept-Ranges", "bytes")
                self.end_headers()
                self.wfile.write(chunk)
                return
        self.send_response(200)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Accept-Ranges", "bytes")
        self.end_headers()
        self.wfile.write(data)


class RangeFileServer:
    """本地测试文件服务器（127.0.0.1，随机端口）。"""

    def __init__(self, root: Path, slow_seconds: float = 0.0):
        self.root = root
        self.slow_seconds = slow_seconds
        self._server: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None
        self.port: int | None = None

    def start(self) -> "RangeFileServer":
        self._server = ThreadingHTTPServer(("127.0.0.1", 0), _RangeHandler)
        self._server.root = str(self.root)
        self._server.slow_seconds = self.slow_seconds
        self.port = self._server.server_address[1]
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()
        return self

    def url(self, rel: str) -> str:
        return f"http://127.0.0.1:{self.port}/{rel}"

    def stop(self) -> None:
        if self._server:
            self._server.shutdown()
            self._server.server_close()


@pytest.fixture()
def srv(tmp_path):
    server = RangeFileServer(tmp_path).start()
    yield server
    server.stop()


def _config(tmp_path: Path, **dl_overrides):
    return load_config(
        db_url=f"sqlite:///{tmp_path / 't.db'}",
        storage_dir=tmp_path / "store",
        download=DownloadConfig(**dl_overrides),
    )


# ===========================================================================
# ① 成功下载 + MD5
# ===========================================================================
def test_fetch_success_and_md5(tmp_path, srv):
    content = bytes(range(256)) * 512  # 131072 字节
    (tmp_path / "clip.mp4").write_bytes(content)
    dest = tmp_path / "dl" / "out.mp4"
    result = fetch_file(srv.url("clip.mp4"), dest)
    assert result["size"] == len(content)
    assert result["resumed"] is False
    assert dest.read_bytes() == content
    assert compute_md5(dest) == hashlib.md5(content).hexdigest()


# ===========================================================================
# ② 断点续传（Range 206）+ 416 全量重下
# ===========================================================================
def test_resume_range(tmp_path, srv):
    content = bytes((i * 7) % 256 for i in range(200_000))
    (tmp_path / "big.bin").write_bytes(content)
    dest = tmp_path / "dl" / "big.bin"
    dest.parent.mkdir(parents=True, exist_ok=True)
    # 模拟中断：本地已有前 60000 字节
    dest.write_bytes(content[:60000])
    result = fetch_file(srv.url("big.bin"), dest, resume=True)
    assert result["resumed"] is True
    assert result["size"] == len(content)
    assert dest.read_bytes() == content
    assert compute_md5(dest) == hashlib.md5(content).hexdigest()


def test_resume_416_restart(tmp_path, srv):
    # 部分文件比源还大（远端文件已变更）→ 服务端 416 → 全量重下
    (tmp_path / "s.txt").write_bytes(b"small-content")
    dest = tmp_path / "dl" / "s.txt"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(b"a" * 1000)
    result = fetch_file(srv.url("s.txt"), dest, resume=True)
    assert result["resumed"] is False
    assert dest.read_bytes() == b"small-content"


# ===========================================================================
# ③ 错误分类
# ===========================================================================
def test_error_404_no_match(tmp_path, srv):
    with pytest.raises(DownloadError) as ei:
        fetch_file(srv.url("missing.mp4"), tmp_path / "dl" / "x.mp4")
    assert ei.value.error_code == "NO_MATCH"
    assert ei.value.http_status == 404


def test_error_429_rate_limit(tmp_path, srv):
    with pytest.raises(DownloadError) as ei:
        fetch_file(srv.url("status/429"), tmp_path / "dl" / "x.mp4")
    assert ei.value.error_code == "RATE_LIMIT"


def test_error_401_auth_required(tmp_path, srv):
    with pytest.raises(DownloadError) as ei:
        fetch_file(srv.url("status/401"), tmp_path / "dl" / "x.mp4")
    assert ei.value.error_code == "AUTH_REQUIRED"


def test_error_500_unexpected(tmp_path, srv):
    with pytest.raises(DownloadError) as ei:
        fetch_file(srv.url("status/500"), tmp_path / "dl" / "x.mp4")
    assert ei.value.error_code == "UNEXPECTED"


def test_error_timeout(tmp_path):
    srv = RangeFileServer(tmp_path, slow_seconds=1.0).start()
    try:
        # 慢速端点：sleep 后仍正常提供文件（路径 /slow/... 会先 sleep）
        slow_dir = tmp_path / "slow"
        slow_dir.mkdir(parents=True, exist_ok=True)
        (slow_dir / "slow.bin").write_bytes(b"x" * 100)
        with pytest.raises(DownloadError) as ei:
            fetch_file(srv.url("slow/slow.bin"), tmp_path / "dl" / "x.bin", timeout=0.2)
        assert ei.value.error_code == "TIMEOUT"
    finally:
        srv.stop()


def test_redact_url_sensitive_params():
    url = "https://example.com/v?a=1&token=SECRET&x-bogus=abc&keep=ok"
    r = redact_url(url)
    assert "SECRET" not in r and "abc" not in r
    assert "keep=ok" in r and "a=1" in r


# ===========================================================================
# ④ 退避 next_run_at 计算
# ===========================================================================
def test_compute_next_run_at_pure():
    t0 = _utcnow()
    assert compute_next_run_at("TIMEOUT", 0, now=t0) is not None
    # 人工接管类错误码：不自动续跑
    assert compute_next_run_at("AUTH_REQUIRED", 0, now=t0) is None
    assert compute_next_run_at("VERIFICATION_REQUIRED", 0, now=t0) is None
    # 节流级 0~4：×1/2/4/8/16
    r0 = compute_next_run_at("TIMEOUT", 0, now=t0)
    r4 = compute_next_run_at("TIMEOUT", 4, now=t0)
    dt0 = datetime.fromisoformat(r0) - t0
    dt4 = datetime.fromisoformat(r4) - t0
    assert dt4.total_seconds() == pytest.approx(dt0.total_seconds() * 16, rel=1e-9)
    # 默认基表：RATE_LIMIT 180s / TIMEOUT 60s / NO_MATCH 120s
    assert (datetime.fromisoformat(compute_next_run_at("RATE_LIMIT", 0, now=t0)) - t0).total_seconds() == pytest.approx(180.0)
    assert (datetime.fromisoformat(compute_next_run_at("TIMEOUT", 0, now=t0)) - t0).total_seconds() == pytest.approx(60.0)
    assert (datetime.fromisoformat(compute_next_run_at("NO_MATCH", 0, now=t0)) - t0).total_seconds() == pytest.approx(120.0)


def test_worker_backoff_next_run_at(tmp_path, srv):
    cfg = _config(tmp_path, circuit_breaker_failures=2)
    repo = InMemoryDownloadJobRepo()
    repo.enqueue("抖音", srv.url("status/429"), "video")
    worker = DownloadWorker(repo, LocalStorage(cfg.storage_dir), cfg)
    stats = worker.run_once()
    assert stats["claimed"] == 1 and stats["failed"] == 1
    job = repo.get_job(1)
    assert job["status"] == "queued"  # 可重试，仍排队
    assert job["error_code"] == "RATE_LIMIT"
    assert job["retry_count"] == 1
    assert job["throttle_level"] == 1
    # next_run_at ≈ now + 180 × 2^1 = 360s（容忍 ±10s）
    delta = (datetime.fromisoformat(job["next_run_at"]) - _utcnow()).total_seconds()
    assert 350 <= delta <= 370
    # 退避未到期：下一轮不重复领取
    stats2 = worker.run_once()
    assert stats2["claimed"] == 0


def test_worker_auth_required_blocks(tmp_path, srv):
    # P-002：AUTH_REQUIRED 不自动重试 → blocked 等人工
    cfg = _config(tmp_path)
    repo = InMemoryDownloadJobRepo()
    repo.enqueue("视频号", srv.url("status/401"), "video")
    worker = DownloadWorker(repo, LocalStorage(cfg.storage_dir), cfg)
    worker.run_once()
    job = repo.get_job(1)
    assert job["status"] == "blocked"
    assert job["error_code"] == "AUTH_REQUIRED"
    assert job["next_run_at"] is None


# ===========================================================================
# ⑤ 熔断：连续失败 ≥2 → risk_control=1；冷却后探针成功 → 恢复 0
# ===========================================================================
def test_circuit_breaker_and_recovery(tmp_path, srv):
    # concurrency=1：每轮只处理 1 个任务，保证「连续失败≥2 → 熔断」逐轮可断言
    cfg = _config(tmp_path, circuit_breaker_failures=2, concurrency=1)
    repo = InMemoryDownloadJobRepo()
    worker = DownloadWorker(
        repo, LocalStorage(cfg.storage_dir), cfg, breaker_cooldown_seconds=1.0
    )
    (tmp_path / "ok.mp4").write_bytes(b"probe-data")
    repo.enqueue("抖音", srv.url("missing1.mp4"), "video")
    repo.enqueue("抖音", srv.url("missing2.mp4"), "video")
    repo.enqueue("抖音", srv.url("ok.mp4"), "video")  # 探针用（成功 URL）

    # 两次连续失败 → 熔断
    assert worker.run_once()["failed"] == 1
    assert worker.run_once()["failed"] == 1
    assert repo.source_risk_control("抖音") == 1
    assert ("抖音", 1) in repo.risk_control_calls

    # 冷却期内：该平台任务被跳过（放回队列）
    stats = worker.run_once()
    assert stats["skipped"] == 1
    assert "抖音" in stats["paused_platforms"]
    assert repo.get_job(3)["status"] == "queued"

    # 冷却结束：探针放行 → 下载成功 → 恢复 risk_control=0
    time.sleep(1.1)
    stats = worker.run_once()
    assert stats["succeeded"] == 1
    assert repo.source_risk_control("抖音") == 0
    assert ("抖音", 0) in repo.risk_control_calls
    assert repo.get_job(3)["status"] == "success"


# ===========================================================================
# ⑥ 租约过期回收 + 同 worker 进程重启恢复
# ===========================================================================
def test_lease_expiry_reclaim(tmp_path):
    cfg = _config(tmp_path)
    repo = InMemoryDownloadJobRepo()
    repo.enqueue("快手", "http://example.invalid/1.mp4", "video")
    job1 = repo.claim_next("worker-a", 45)
    assert job1["status"] == "running"
    assert job1["lease_owner"] == "worker-a"
    # 租约未过期：其他 worker 领不到
    assert repo.claim_next("worker-b", 45) is None
    # 同 worker 进程重启恢复（recover_after_process_restart）：同 lease_owner 可再认领
    again = repo.claim_next("worker-a", 45)
    assert again is not None and again["id"] == job1["id"]
    # 强制租约过期 → 其他 worker 回收
    past = (_utcnow() - timedelta(minutes=1)).isoformat(timespec="microseconds")
    repo._jobs[1]["lease_expires_at"] = past
    reclaimed = repo.claim_next("worker-b", 45)
    assert reclaimed is not None and reclaimed["id"] == job1["id"]
    assert reclaimed["lease_owner"] == "worker-b"
    assert reclaimed["lease_expires_at"] > _iso_now()


# ===========================================================================
# ⑦ fake repo 全程注入：零 DB 依赖 + 入队幂等 + retry
# ===========================================================================
def test_fake_repo_no_db(tmp_path, srv):
    cfg = _config(tmp_path)
    repo = InMemoryDownloadJobRepo()
    (tmp_path / "ok.mp4").write_bytes(b"fake-repo-data")
    repo.enqueue("小红书", srv.url("ok.mp4"), "image")
    worker = DownloadWorker(repo, LocalStorage(cfg.storage_dir), cfg)
    worker.run_once()
    # 全程内存：无任何 SQLite 文件产生
    assert not list(tmp_path.glob("*.db"))
    assert repo.get_job(1)["status"] == "success"


def test_enqueue_idempotent(tmp_path):
    repo = InMemoryDownloadJobRepo()
    job1, created1 = repo.enqueue("抖音", "http://example.invalid/a.mp4", "video")
    assert created1 is True
    job2, created2 = repo.enqueue("抖音", "http://example.invalid/a.mp4", "video")
    assert created2 is False
    assert job2["id"] == job1["id"]
    # 成功后允许再入队新建
    repo.finish_success(job1["id"], "video/202501/a.mp4", "x" * 32, 3, {})
    job3, created3 = repo.enqueue("抖音", "http://example.invalid/a.mp4", "video")
    assert created3 is True and job3["id"] != job1["id"]


def test_retry_job_resets(tmp_path):
    repo = InMemoryDownloadJobRepo()
    job, _ = repo.enqueue("淘宝", "http://example.invalid/x.jpg", "image")
    repo.finish_failure(job["id"], "NO_MATCH", 3, None, 4, {"message": "重试耗尽"}, status="failed")
    assert repo.get_job(job["id"])["status"] == "failed"
    assert repo.retry_job(job["id"]) is True
    j = repo.get_job(job["id"])
    assert j["status"] == "queued"
    assert j["retry_count"] == 0 and j["throttle_level"] == 0 and j["next_run_at"] is None
    assert repo.retry_job(9999) is False


# ===========================================================================
# worker 全链路：claim → fetch → storage.put_file → md5 → finish_success
# ===========================================================================
def test_worker_download_flow(tmp_path, srv):
    cfg = _config(tmp_path)
    repo = InMemoryDownloadJobRepo()
    content = b"flow-data-" * 1000
    (tmp_path / "clip.mp4").write_bytes(content)
    repo.enqueue("视频号", srv.url("clip.mp4"), "video")
    worker = DownloadWorker(repo, LocalStorage(cfg.storage_dir), cfg)
    stats = worker.run_once()
    assert stats["succeeded"] == 1
    job = repo.get_job(1)
    assert job["status"] == "success"
    assert job["md5"] == hashlib.md5(content).hexdigest()
    assert job["size"] == len(content)
    # 存储键已按 asset_type/YYYYMM/ 分层入库
    assert job["file_path"].startswith("video/")
    stored = LocalStorage(cfg.storage_dir).read(job["file_path"])
    assert stored == content
    # 证据 JSON 已留痕且不含密钥/Cookie
    evidence = json.loads(job["evidence_json"])
    assert evidence["md5"] == hashlib.md5(content).hexdigest()
    assert "cookie" not in str(evidence).lower()


# ===========================================================================
# 多实例 HTTP API 冒烟（标准库 http.server）
# ===========================================================================
def test_api_health_and_jobs(tmp_path):
    cfg = _config(tmp_path, circuit_breaker_failures=2)
    repo = InMemoryDownloadJobRepo()
    service = DownloaderService(repo, config=cfg)
    server = DownloadApiServer(("127.0.0.1", 0), service)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        # GET /health → 200 JSON
        r = requests.get(base + "/health", timeout=5)
        assert r.status_code == 200
        data = r.json()
        assert data["status"] == "ok"
        assert data["worker_id"]
        assert data["repo"] == "InMemoryDownloadJobRepo"
        # POST /jobs 幂等
        body = {"source_platform": "抖音", "source_url": "http://example.invalid/a.mp4", "job_type": "video"}
        r1 = requests.post(base + "/jobs", json=body, timeout=5)
        assert r1.status_code == 201
        job = r1.json()["job"]
        assert r1.json()["existing"] is False
        r2 = requests.post(base + "/jobs", json=body, timeout=5)
        assert r2.status_code == 200
        assert r2.json()["job"]["id"] == job["id"]
        assert r2.json()["existing"] is True
        # GET /jobs/<id> 与 ?status=
        assert requests.get(base + f"/jobs/{job['id']}", timeout=5).status_code == 200
        r4 = requests.get(base + "/jobs?status=queued", timeout=5)
        assert r4.json()["count"] == 1
        # 校验：缺字段 400 / 非法 status 400
        assert requests.post(base + "/jobs", json={"source_platform": "抖音"}, timeout=5).status_code == 400
        assert requests.get(base + "/jobs?status=bogus", timeout=5).status_code == 400
        # retry 与 404
        assert requests.post(base + f"/jobs/{job['id']}/retry", timeout=5).status_code == 200
        assert requests.get(base + "/jobs/999", timeout=5).status_code == 404
        # 响应全 UTF-8 JSON
        assert "charset=utf-8" in r1.headers["Content-Type"]
    finally:
        server.shutdown()
        server.server_close()
