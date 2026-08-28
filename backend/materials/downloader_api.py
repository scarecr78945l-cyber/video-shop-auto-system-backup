"""多实例下载中台 HTTP API（Python 标准库 http.server.ThreadingHTTPServer，零新增依赖）。

路由：
  POST /jobs              入队（幂等：同 source_url 已存在且未完成 → 返回既有任务 200 existing=true；
                          新建 → 201 existing=false）；body: source_platform/source_url/job_type|asset_type/priority
  GET  /jobs              列表（?status=queued|running|success|failed|paused|blocked）
  GET  /jobs/<id>         任务详情
  POST /jobs/<id>/retry   重置重试（failed/blocked → queued）
  GET  /health            实例存活 + worker 状态

实例标识 WORKER_ID（env，默认 hostname-随机后缀）；多实例并行靠 45min 租约 +
lease_owner 互斥（R-M2-07）。请求/响应 JSON 全 UTF-8（ensure_ascii=False）。
日志脱敏：只记 path/状态码，不落 body（body 可能含 URL 参数，留痕走 evidence 的 redact_url）。
"""

from __future__ import annotations

import json
import logging
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs, urlsplit

from . import __version__
from .downloader import DownloaderService
from .downloader import _iso_now  # 时间戳口径与 D 对齐（ISO8601 UTC）

log = logging.getLogger("materials.api")

JOB_STATUSES = ("queued", "running", "success", "failed", "paused", "blocked")
JOB_TYPES = ("video", "image", "video_page")


class ApiHandler(BaseHTTPRequestHandler):
    server_version = f"MaterialsDownloader/{__version__}"
    protocol_version = "HTTP/1.1"

    # -- 基础 ---------------------------------------------------------------
    def log_message(self, fmt: str, *args: Any) -> None:  # 转标准日志（留痕），不直接打印
        log.info("api %s - %s", self.address_string(), fmt % args)

    def _send_json(self, code: int, obj: Any) -> None:
        body = json.dumps(obj, ensure_ascii=False, default=str).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _read_json(self) -> dict | None:
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            return None
        raw = self.rfile.read(length) if length > 0 else b"{}"
        if not raw:
            return {}
        try:
            data = json.loads(raw.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            return None
        return data if isinstance(data, dict) else None

    def do_GET(self) -> None:
        self._route("GET")

    def do_POST(self) -> None:
        self._route("POST")

    # -- 路由 ---------------------------------------------------------------
    def _route(self, method: str) -> None:
        service: DownloaderService = self.server.service
        parsed = urlsplit(self.path)
        path = parsed.path.rstrip("/") or "/"
        query = parse_qs(parsed.query)
        try:
            if method == "GET" and path == "/health":
                self._send_json(200, {
                    "status": "ok", "service": "materials-downloader",
                    "version": __version__, "ts": _iso_now(), **service.health(),
                })
                return
            if method == "POST" and path == "/jobs":
                self._handle_create(service)
                return
            if method == "GET" and path == "/jobs":
                status = (query.get("status") or [None])[0]
                self._handle_list(service, status)
                return
            parts = path.split("/")
            if method == "GET" and len(parts) == 3 and parts[1] == "jobs" and parts[2].isdigit():
                self._handle_get(service, int(parts[2]))
                return
            if method == "POST" and len(parts) == 4 and parts[1] == "jobs" and parts[2].isdigit() and parts[3] == "retry":
                self._handle_retry(service, int(parts[2]))
                return
            self._send_json(404, {"error": "not found", "path": path})
        except RuntimeError as e:
            # repo/表未就绪等基础设施错误：清晰报错（不泄漏堆栈）
            log.error("API 基础设施错误 %s %s: %s", method, path, e)
            self._send_json(500, {"error": str(e)})
        except Exception:  # 兜底：留日志，对外只给内部错误
            log.exception("API 内部错误 %s %s", method, path)
            self._send_json(500, {"error": "internal error"})

    # -- 各端点 -------------------------------------------------------------
    def _handle_create(self, service: DownloaderService) -> None:
        body = self._read_json()
        if body is None:
            self._send_json(400, {"error": "body 必须是 UTF-8 JSON 对象"})
            return
        sp = str(body.get("source_platform") or "").strip()
        su = str(body.get("source_url") or "").strip()
        if not sp or not su:
            self._send_json(400, {"error": "source_platform/source_url 必填"})
            return
        job_type = str(body.get("job_type") or body.get("asset_type") or "video").strip()
        if job_type not in JOB_TYPES:
            self._send_json(400, {"error": f"job_type 必须是 {'/'.join(JOB_TYPES)}（或传 asset_type）"})
            return
        try:
            priority = int(body.get("priority") or 0)
        except (TypeError, ValueError):
            self._send_json(400, {"error": "priority 必须是整数"})
            return
        job, created = service.enqueue_job(sp, su, job_type, priority)
        self._send_json(201 if created else 200, {"job": job, "existing": not created})

    def _handle_get(self, service: DownloaderService, job_id: int) -> None:
        job = service.get_job(job_id)
        if job is None:
            self._send_json(404, {"error": f"job {job_id} 不存在"})
            return
        self._send_json(200, {"job": job})

    def _handle_list(self, service: DownloaderService, status: str | None) -> None:
        if status is not None and status not in JOB_STATUSES:
            self._send_json(400, {"error": f"status 必须是 {'/'.join(JOB_STATUSES)}"})
            return
        jobs = service.list_jobs(status)
        self._send_json(200, {"jobs": jobs, "count": len(jobs)})

    def _handle_retry(self, service: DownloaderService, job_id: int) -> None:
        ok = service.retry_job(job_id)
        if not ok:
            self._send_json(404, {"error": f"job {job_id} 不存在"})
            return
        self._send_json(200, {"job": service.get_job(job_id)})


class DownloadApiServer(ThreadingHTTPServer):
    """多实例 HTTP API 服务：每请求一线程，daemon 线程不阻塞主进程退出。"""

    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, addr: tuple[str, int], service: DownloaderService):
        super().__init__(addr, ApiHandler)
        self.service = service


def serve_forever(service: DownloaderService, host: str = "127.0.0.1", port: int = 8787) -> None:
    """启动 API 服务（阻塞）。worker 循环由调用方决定是否 start_worker_loop。"""
    server = DownloadApiServer((host, port), service)
    log.info("下载中台 API 启动 http://%s:%d (worker_id=%s)", host, port, service.worker.worker_id)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        log.info("下载中台 API 停止")
    finally:
        server.server_close()
