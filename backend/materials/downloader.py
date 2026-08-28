"""下载核心服务：fetch_file（Range 断点续传）/ 错误分类 / 退避 / 熔断 / 任务账本协议 / Worker / Service。

设计（子代理 F，decisions.md 已记录）：
- 错误码复用全局码表（09 文档）：RATE_LIMIT/TIMEOUT/NO_MATCH/PLATFORM_REJECT/
  AUTH_REQUIRED/VERIFICATION_REQUIRED/UNEXPECTED
- 退避（R-M2-06）：RATE_LIMIT 180s / TIMEOUT 60s / NO_MATCH 120s / 其他 60s；
  节流级 0~4，next_run_at = now + base × 2^level（×1/2/4/8/16）；
  AUTH_REQUIRED/VERIFICATION_REQUIRED 不自动重试 → blocked 等人工（P-002）
- 熔断（R-M2-04/R-M2-21）：同平台连续失败 ≥ circuit_breaker_failures（默认 2）
  → 镜像写 asset_sources.risk_control=1；冷却期内该平台任务放回队列（release_claim），
  冷却结束后自动放行一个任务当探针，成功即恢复 risk_control=0
- 断点续传两级：fetch_file HTTP Range 续传（416/文件变更→弃部分文件全量重下）；
  worker 按 (worker_id, job_id) 固定 .part 临时文件，失败保留供下次续传，成功入库后清理
- 与 ORM 解耦（并行安全）：DownloadJobRepo 协议注入；SqlAlchemyDownloadJobRepo 延迟
  对接子代理 D 的 backend.materials.repo（未就绪给清晰报错）；单元测试全走内存 fake
- 日志留痕脱敏（P-004）：证据 JSON 只含 redact_url 后的 URL 与状态码/大小，不含 Cookie/密钥
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import secrets
import socket
import tempfile
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from .config import MAX_SIZE_BYTES as HARD_MAX_SIZE_BYTES  # 素材硬规格 ≤500M（P-007 集中定义）
from .config import load_config
from .storage import LocalStorage, Storage

log = logging.getLogger("materials.downloader")

# ---------------------------------------------------------------------------
# 与 D 的时间工具对齐（models.py 未就绪时本地兜底，格式一致可字典序比较）
# ---------------------------------------------------------------------------
try:
    from .models import iso_now as _iso_now
    from .models import utcnow as _utcnow
    from .models import add_minutes_iso as _add_minutes_iso
except ImportError:  # pragma: no cover - 并行开发期兜底

    def _utcnow() -> datetime:
        return datetime.now(timezone.utc)

    def _iso_now() -> str:
        return _utcnow().isoformat(timespec="microseconds")

    def _add_minutes_iso(minutes: int) -> str:
        return (_utcnow() + timedelta(minutes=minutes)).isoformat(timespec="microseconds")


# ---------------------------------------------------------------------------
# 错误码与退避常量（对齐 09 文档错误码体系 + R-M2-06）
# ---------------------------------------------------------------------------
RATE_LIMIT = "RATE_LIMIT"
TIMEOUT = "TIMEOUT"
NO_MATCH = "NO_MATCH"
PLATFORM_REJECT = "PLATFORM_REJECT"
AUTH_REQUIRED = "AUTH_REQUIRED"
VERIFICATION_REQUIRED = "VERIFICATION_REQUIRED"
UNEXPECTED = "UNEXPECTED"

RETRY_BACKOFF_SECONDS: dict[str, float] = {
    RATE_LIMIT: 180.0,
    TIMEOUT: 60.0,
    NO_MATCH: 120.0,
}
DEFAULT_BACKOFF_SECONDS = 60.0
THROTTLE_MAX_LEVEL = 4  # 节流级 0~4，间隔 ×1/2/4/8/16

# 敏感查询参数（脱敏用，值一律替换为 ***，日志/证据不含真实值）
_SENSITIVE_QUERY_KEYS = {
    "token", "access_token", "sign", "sig", "signature", "key", "cookie", "session",
    "ticket", "secret", "x-bogus", "a_bogus", "mstoken", "verify", "captcha", "auth",
}

# 人工接管类错误码：不自动续跑（P-002）
_MANUAL_ERROR_CODES = (AUTH_REQUIRED, VERIFICATION_REQUIRED)


def redact_url(url: str) -> str:
    """脱敏 URL：敏感查询参数值替换为 ***（不落日志/证据）。"""
    try:
        parsed = urlsplit(url or "")
        qs = [
            (k, "***" if k.lower() in _SENSITIVE_QUERY_KEYS else v)
            for k, v in parse_qsl(parsed.query, keep_blank_values=True)
        ]
        return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, urlencode(qs), ""))
    except Exception:  # 解析失败原样返回（不留详情）
        return str(url)[:200]


def classify_http_status(status: int) -> str:
    """HTTP 状态码 → 错误码（任务书映射 + 09 码表）。"""
    if status in (429, 403):
        return RATE_LIMIT          # 频控/风控（任务书明确 429/403→RATE_LIMIT）
    if status == 401:
        return AUTH_REQUIRED       # 登录失效（P-002）
    if status in (404, 410):
        return NO_MATCH            # 内容缺失
    if 400 <= status < 500:
        return PLATFORM_REJECT     # 签名/风控拒绝（非频控 4xx，R-M2-03）
    return UNEXPECTED              # 5xx 及其余


class DownloadError(Exception):
    """下载失败（携带错误码/HTTP 状态/脱敏证据）。"""

    def __init__(
        self,
        error_code: str,
        message: str,
        http_status: int | None = None,
        evidence: dict[str, Any] | None = None,
    ):
        super().__init__(message)
        self.error_code = error_code
        self.message = message
        self.http_status = http_status
        self.evidence = evidence


def compute_md5(path: Path | str) -> str:
    """文件 MD5（32 位小写 hex，分块读取）。"""
    h = hashlib.md5()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def fetch_file(
    url: str,
    dest: Path | str,
    resume: bool = True,
    timeout: float = 30.0,
    extra_headers: dict[str, str] | None = None,
    session: Any = None,
) -> dict[str, Any]:
    """requests 流式下载 + Range 断点续传 + content-length 校验。

    返回 {"path","size","resumed","content_length"}；失败抛 DownloadError(error_code,...)。
    - 416（Range 不被支持/文件已变更）→ 放弃部分文件全量重下（幂等，一次递归）
    - 中途超时保留部分文件（.part 语义），下次 resume=True 续传
    """
    import requests

    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    headers = dict(extra_headers or {})
    initial = dest.stat().st_size if (resume and dest.exists()) else 0
    if initial > 0:
        headers["Range"] = f"bytes={initial}-"

    safe_url = redact_url(url)
    try:
        resp = (session or requests).get(url, stream=True, timeout=timeout, headers=headers)
    except requests.Timeout as e:
        raise DownloadError(TIMEOUT, f"下载超时({timeout}s): {safe_url}", evidence={"url": safe_url}) from e
    except requests.RequestException as e:
        raise DownloadError(UNEXPECTED, f"网络错误 {e.__class__.__name__}: {safe_url}", evidence={"url": safe_url}) from e

    if resp.status_code == 416 and initial > 0:
        # 服务端不支持 Range 或远端文件已变更：弃部分文件全量重下（幂等）
        resp.close()
        dest.unlink(missing_ok=True)
        return fetch_file(url, dest, resume=False, timeout=timeout, extra_headers=extra_headers, session=session)

    if resp.status_code not in (200, 206):
        code = classify_http_status(resp.status_code)
        raise DownloadError(
            code,
            f"HTTP {resp.status_code} 下载被拒: {safe_url}",
            http_status=resp.status_code,
            evidence={"url": safe_url, "http_status": resp.status_code},
        )

    mode = "ab" if (resp.status_code == 206 and initial > 0) else "wb"
    expected: int | None = None
    cl = resp.headers.get("Content-Length")
    if cl:
        expected = int(cl) + (initial if mode == "ab" else 0)
    try:
        with open(dest, mode) as fh:
            for chunk in resp.iter_content(chunk_size=65536):
                if chunk:
                    fh.write(chunk)
    except requests.Timeout as e:
        raise DownloadError(TIMEOUT, f"下载超时({timeout}s): {safe_url}", evidence={"url": safe_url}) from e
    except requests.RequestException as e:
        raise DownloadError(UNEXPECTED, f"下载中断 {e.__class__.__name__}: {safe_url}", evidence={"url": safe_url}) from e
    finally:
        resp.close()

    actual = dest.stat().st_size
    if expected is not None and actual != expected:
        raise DownloadError(
            UNEXPECTED,
            f"content-length 不符 期望{expected} 实际{actual}: {safe_url}",
            evidence={"url": safe_url, "expected": expected, "actual": actual},
        )
    return {"path": str(dest), "size": actual, "resumed": initial > 0, "content_length": expected}


def compute_next_run_at(
    error_code: str,
    throttle_level: int,
    backoff_map: dict[str, float] | None = None,
    default_backoff: float | None = None,
    now: datetime | None = None,
) -> str | None:
    """退避续跑时间：now + base × 2^level（ISO8601 UTC）。

    人工接管类错误码（AUTH_REQUIRED/VERIFICATION_REQUIRED）返回 None（不自动续跑，P-002）。
    """
    if error_code in _MANUAL_ERROR_CODES:
        return None
    base = (backoff_map or RETRY_BACKOFF_SECONDS).get(error_code, default_backoff or DEFAULT_BACKOFF_SECONDS)
    level = max(0, min(int(throttle_level or 0), THROTTLE_MAX_LEVEL))
    seconds = base * (2 ** level)
    return ((now or _utcnow()) + timedelta(seconds=seconds)).isoformat(timespec="microseconds")


def _resolve_worker_id() -> str:
    """实例标识：WORKER_ID 环境变量优先，默认 hostname-随机后缀（多实例互不冲突）。"""
    env = os.environ.get("WORKER_ID")
    if env:
        return env
    host = socket.gethostname() or "host"
    return f"{host}-{secrets.token_hex(2)}"


def _guess_ext(url: str, job_type: str = "video") -> str:
    path = urlsplit(url or "").path
    ext = Path(path).suffix.lower()
    if ext and len(ext) <= 6:
        return ext
    return ".mp4" if job_type == "video" else ".jpg"


def _truncate(text: str, n: int = 500) -> str:
    text = str(text or "")
    return text if len(text) <= n else text[: n - 3] + "..."


# ---------------------------------------------------------------------------
# DownloadJobRepo 协议（字段对齐 database/README.md 的 asset_download_jobs）
# ---------------------------------------------------------------------------
class DownloadJobRepo(Protocol):
    """下载任务账本协议。

    job dict 字段（对齐 asset_download_jobs）：id/asset_id/source_platform/source_url/
    job_type/status/error_code/error_message/retry_count/max_retries/throttle_level/
    next_run_at/lease_owner/lease_expires_at/evidence_json/created_at/updated_at。
    enqueue 返回 (job, created)：同 source_url 已存在且 status!=success 视为未完成
    → 返回既有任务且 created=False（入队幂等，decisions.md）。
    """

    def enqueue(self, source_platform: str, source_url: str, job_type: str, priority: int = 0) -> tuple[dict, bool]: ...
    def get_job(self, job_id: int) -> dict | None: ...
    def list_jobs(self, status: str | None = None) -> list[dict]: ...
    def claim_next(
        self, worker_id: str, lease_minutes: int, blocked_platforms: tuple[str, ...] = ()
    ) -> dict | None: ...
    def release_claim(self, job_id: int) -> bool: ...
    def finish_success(self, job_id: int, file_path: str, md5: str, size: int, evidence: dict) -> None: ...
    def finish_failure(
        self,
        job_id: int,
        error_code: str,
        retry_count: int,
        next_run_at: str | None,
        throttle_level: int,
        evidence: dict,
        status: str = "queued",
    ) -> None: ...
    def retry_job(self, job_id: int) -> bool: ...
    def source_risk_control(self, platform: str) -> int: ...
    def set_source_risk_control(self, platform: str, level: int) -> None: ...


class InMemoryDownloadJobRepo:
    """内存版 DownloadJobRepo（fake）：单元测试/演示/CLI --repo memory 用，零 DB 依赖（R-M2-17）。"""

    def __init__(self) -> None:
        self._jobs: dict[int, dict[str, Any]] = {}
        self._seq = 0
        self._risk: dict[str, int] = {}
        self.risk_control_calls: list[tuple[str, int]] = []  # 留痕，测试断言用

    # -- 任务账本 ----------------------------------------------------------
    def enqueue(self, source_platform: str, source_url: str, job_type: str, priority: int = 0) -> tuple[dict, bool]:
        for j in self._jobs.values():
            if j["source_url"] == source_url and j["status"] != "success":
                return dict(j), False
        self._seq += 1
        now = _iso_now()
        job: dict[str, Any] = {
            "id": self._seq, "asset_id": None, "source_platform": source_platform,
            "source_url": source_url, "job_type": job_type, "status": "queued",
            "error_code": None, "error_message": None, "retry_count": 0, "max_retries": 3,
            "throttle_level": 0, "next_run_at": None, "lease_owner": None,
            "lease_expires_at": None, "evidence_json": None, "created_at": now, "updated_at": now,
        }
        self._jobs[self._seq] = job
        return dict(job), True

    def get_job(self, job_id: int) -> dict | None:
        j = self._jobs.get(job_id)
        return dict(j) if j else None

    def list_jobs(self, status: str | None = None) -> list[dict]:
        jobs = [dict(j) for j in self._jobs.values()]
        if status:
            jobs = [j for j in jobs if j["status"] == status]
        return jobs

    def _claim(self, j: dict[str, Any], worker_id: str, lease_minutes: int, now: str) -> dict:
        j["status"] = "running"
        j["lease_owner"] = worker_id
        j["lease_expires_at"] = _add_minutes_iso(lease_minutes)
        j["updated_at"] = now
        return dict(j)

    def claim_next(self, worker_id: str, lease_minutes: int, blocked_platforms: tuple[str, ...] = ()) -> dict | None:
        now = _iso_now()
        blocked = set(blocked_platforms or ())
        # 1) 到期的 queued 任务（next_run_at 为空或已到）
        for j in self._jobs.values():
            if j["source_platform"] in blocked:
                continue
            if j["status"] == "queued" and (j["next_run_at"] is None or j["next_run_at"] <= now):
                return self._claim(j, worker_id, lease_minutes, now)
        # 2) 租约过期回收 / 同 worker 进程重启恢复（recover_after_process_restart）
        for j in self._jobs.values():
            if j["source_platform"] in blocked:
                continue
            if j["status"] == "running":
                expired = j["lease_expires_at"] is not None and j["lease_expires_at"] < now
                if expired or j["lease_owner"] == worker_id:
                    return self._claim(j, worker_id, lease_minutes, now)
        return None

    def release_claim(self, job_id: int) -> bool:
        j = self._jobs.get(job_id)
        if j is None or j["status"] != "running":
            return False
        now = _iso_now()
        j["status"] = "queued"
        j["lease_owner"] = None
        j["lease_expires_at"] = None
        j["updated_at"] = now
        return True

    def finish_success(self, job_id: int, file_path: str, md5: str, size: int, evidence: dict) -> None:
        j = self._jobs[job_id]
        j["status"] = "success"
        j["error_code"] = None
        j["error_message"] = None
        j["retry_count"] = 0
        j["throttle_level"] = 0
        j["next_run_at"] = None
        j["lease_owner"] = None
        j["lease_expires_at"] = None
        # 内存版额外保留同名字段便于测试断言（DDL 无此三列，SQL 版写入 evidence_json，见 decisions.md）
        j["file_path"] = file_path
        j["md5"] = md5
        j["size"] = size
        j["evidence_json"] = json.dumps({"file_path": file_path, "md5": md5, "size": size, **evidence}, ensure_ascii=False)
        j["updated_at"] = _iso_now()

    def finish_failure(
        self,
        job_id: int,
        error_code: str,
        retry_count: int,
        next_run_at: str | None,
        throttle_level: int,
        evidence: dict,
        status: str = "queued",
    ) -> None:
        j = self._jobs[job_id]
        j["status"] = status
        j["error_code"] = error_code
        j["error_message"] = _truncate(str(evidence.get("message", "")), 500)
        j["retry_count"] = retry_count
        j["throttle_level"] = throttle_level
        j["next_run_at"] = next_run_at
        j["lease_owner"] = None
        j["lease_expires_at"] = None
        j["evidence_json"] = json.dumps(evidence, ensure_ascii=False)
        j["updated_at"] = _iso_now()

    def retry_job(self, job_id: int) -> bool:
        j = self._jobs.get(job_id)
        if j is None:
            return False
        now = _iso_now()
        j.update(
            status="queued", error_code=None, error_message=None, retry_count=0,
            throttle_level=0, next_run_at=None, lease_owner=None, lease_expires_at=None,
            updated_at=now,
        )
        return True

    # -- 熔断账本（asset_sources.risk_control 的内存镜像）------------------
    def source_risk_control(self, platform: str) -> int:
        return self._risk.get(platform, 0)

    def set_source_risk_control(self, platform: str, level: int) -> None:
        self._risk[platform] = level
        self.risk_control_calls.append((platform, level))


class SqlAlchemyDownloadJobRepo:
    """DownloadJobRepo 的 SQLAlchemy 默认实现（asset_download_jobs / asset_sources 表）。

    对接说明（decisions.md，供总工集成验收）：
    - 表结构与子代理 D 的 DDL（database/README.md）直接对齐，本类自包含实现协议，
      不依赖 AssetRepo 内部方法名；D 交付后即可在其表上运行；
    - 延迟导入 backend.materials.repo（AssetRepo）作就绪门禁：strict=True（默认）时
      repo 未就绪 → 方法调用抛清晰 RuntimeError（任务书要求"延迟导入并在不可用时给出清晰报错"）；
      strict=False 跳过门禁（集成冒烟/验收用，需自行保证表已建）；
    - finish_success 的 file_path/md5/size 写入 evidence_json（DDL 无独立列）；
      asset_id 回填由 AssetRepo 后续处理；priority 仅接受不落库（DDL 无列）。
    """

    _JOB_COLUMNS = (
        "id, asset_id, source_platform, source_url, job_type, status, error_code, "
        "error_message, retry_count, max_retries, throttle_level, next_run_at, "
        "lease_owner, lease_expires_at, evidence_json, created_at, updated_at"
    )
    _JOB_FIELDS = [c.strip() for c in _JOB_COLUMNS.split(",")]

    def __init__(self, db_url: str | None = None, strict: bool = True):
        self._db_url = db_url or load_config().db_url
        self.strict = strict
        self._engine = None
        self._ready: bool | None = None

    # -- 基础设施 ----------------------------------------------------------
    def _engine_or_raise(self):
        if self._engine is None:
            from sqlalchemy import create_engine

            connect_args = {"check_same_thread": False} if self._db_url.startswith("sqlite") else {}
            self._engine = create_engine(self._db_url, future=True, connect_args=connect_args)
        return self._engine

    def _ensure_ready(self) -> None:
        if self._ready is not None:
            return
        if self.strict:
            try:
                from . import repo as repo_mod  # backend.materials.repo（子代理 D 的 AssetRepo）

                if not hasattr(repo_mod, "AssetRepo"):
                    raise ImportError("backend.materials.repo 缺少 AssetRepo")
            except ImportError as e:
                raise RuntimeError(
                    "SqlAlchemyDownloadJobRepo: backend.materials.repo(AssetRepo) 尚未就绪。"
                    "v0.1 阶段请注入内存 DownloadJobRepo（如 InMemoryDownloadJobRepo）或 CLI --repo memory；"
                    "待子代理 D 交付 repo 后由总工集成验收。"
                ) from e
        self._ready = True

    @staticmethod
    def _row_to_job(row: Any) -> dict:
        return {c: row._mapping[c] for c in SqlAlchemyDownloadJobRepo._JOB_FIELDS}

    # -- 任务账本 ----------------------------------------------------------
    def enqueue(self, source_platform: str, source_url: str, job_type: str, priority: int = 0) -> tuple[dict, bool]:
        self._ensure_ready()
        from sqlalchemy import text

        now = _iso_now()
        with self._engine_or_raise().begin() as conn:
            existing = conn.execute(
                text(
                    f"SELECT {self._JOB_COLUMNS} FROM asset_download_jobs "
                    "WHERE source_url = :u AND status != 'success' ORDER BY id LIMIT 1"
                ),
                {"u": source_url},
            ).first()
            if existing is not None:
                return self._row_to_job(existing), False
            r = conn.execute(
                text(
                    "INSERT INTO asset_download_jobs "
                    "(source_platform, source_url, job_type, status, retry_count, max_retries, throttle_level, created_at, updated_at) "
                    "VALUES (:p, :u, :t, 'queued', 0, 3, 0, :now, :now)"
                ),
                {"p": source_platform, "u": source_url, "t": job_type, "now": now},
            )
            job = {
                "id": int(r.lastrowid), "asset_id": None, "source_platform": source_platform,
                "source_url": source_url, "job_type": job_type, "status": "queued",
                "error_code": None, "error_message": None, "retry_count": 0, "max_retries": 3,
                "throttle_level": 0, "next_run_at": None, "lease_owner": None,
                "lease_expires_at": None, "evidence_json": None, "created_at": now, "updated_at": now,
            }
            return job, True

    def get_job(self, job_id: int) -> dict | None:
        self._ensure_ready()
        from sqlalchemy import text

        with self._engine_or_raise().connect() as conn:
            row = conn.execute(
                text(f"SELECT {self._JOB_COLUMNS} FROM asset_download_jobs WHERE id = :id"),
                {"id": job_id},
            ).first()
        return self._row_to_job(row) if row else None

    def list_jobs(self, status: str | None = None) -> list[dict]:
        self._ensure_ready()
        from sqlalchemy import text

        sql = f"SELECT {self._JOB_COLUMNS} FROM asset_download_jobs"
        params: dict[str, Any] = {}
        if status:
            sql += " WHERE status = :s"
            params["s"] = status
        sql += " ORDER BY id"
        with self._engine_or_raise().connect() as conn:
            rows = conn.execute(text(sql), params).all()
        return [self._row_to_job(r) for r in rows]

    def claim_next(self, worker_id: str, lease_minutes: int, blocked_platforms: tuple[str, ...] = ()) -> dict | None:
        self._ensure_ready()
        from sqlalchemy import text

        now = _iso_now()
        lease_exp = _add_minutes_iso(lease_minutes)
        blocked = list(blocked_platforms or ())
        sql = (
            f"SELECT {self._JOB_COLUMNS} FROM asset_download_jobs "
            "WHERE (status = 'queued' AND (next_run_at IS NULL OR next_run_at <= :now)) "
            "   OR (status = 'running' AND lease_expires_at < :now) "
            "   OR (status = 'running' AND lease_owner = :w AND lease_expires_at >= :now) "
        )
        params: dict[str, Any] = {"now": now, "w": worker_id}
        if blocked:
            sql += " AND source_platform NOT IN :blocked "
            params["blocked"] = tuple(blocked)
        sql += "ORDER BY id LIMIT 1"
        with self._engine_or_raise().begin() as conn:
            row = conn.execute(text(sql), params).first()
            if row is None:
                return None
            job = self._row_to_job(row)
            conn.execute(
                text(
                    "UPDATE asset_download_jobs SET status = 'running', lease_owner = :w, "
                    "lease_expires_at = :exp, updated_at = :now WHERE id = :id"
                ),
                {"w": worker_id, "exp": lease_exp, "now": now, "id": job["id"]},
            )
        job["status"] = "running"
        job["lease_owner"] = worker_id
        job["lease_expires_at"] = lease_exp
        job["updated_at"] = now
        return job

    def release_claim(self, job_id: int) -> bool:
        self._ensure_ready()
        from sqlalchemy import text

        now = _iso_now()
        with self._engine_or_raise().begin() as conn:
            r = conn.execute(
                text(
                    "UPDATE asset_download_jobs SET status = 'queued', lease_owner = NULL, "
                    "lease_expires_at = NULL, updated_at = :now WHERE id = :id AND status = 'running'"
                ),
                {"now": now, "id": job_id},
            )
            return r.rowcount > 0

    def finish_success(self, job_id: int, file_path: str, md5: str, size: int, evidence: dict) -> None:
        self._ensure_ready()
        from sqlalchemy import text

        now = _iso_now()
        payload = {"file_path": file_path, "md5": md5, "size": size, **evidence}
        with self._engine_or_raise().begin() as conn:
            conn.execute(
                text(
                    "UPDATE asset_download_jobs SET status = 'success', error_code = NULL, "
                    "error_message = NULL, retry_count = 0, throttle_level = 0, next_run_at = NULL, "
                    "lease_owner = NULL, lease_expires_at = NULL, evidence_json = :ev, updated_at = :now "
                    "WHERE id = :id"
                ),
                {"ev": json.dumps(payload, ensure_ascii=False), "now": now, "id": job_id},
            )

    def finish_failure(
        self,
        job_id: int,
        error_code: str,
        retry_count: int,
        next_run_at: str | None,
        throttle_level: int,
        evidence: dict,
        status: str = "queued",
    ) -> None:
        self._ensure_ready()
        from sqlalchemy import text

        now = _iso_now()
        with self._engine_or_raise().begin() as conn:
            conn.execute(
                text(
                    "UPDATE asset_download_jobs SET status = :s, error_code = :ec, "
                    "error_message = :em, retry_count = :rc, throttle_level = :tl, next_run_at = :nra, "
                    "lease_owner = NULL, lease_expires_at = NULL, evidence_json = :ev, updated_at = :now "
                    "WHERE id = :id"
                ),
                {
                    "s": status, "ec": error_code, "em": _truncate(str(evidence.get("message", "")), 500),
                    "rc": retry_count, "tl": throttle_level, "nra": next_run_at,
                    "ev": json.dumps(evidence, ensure_ascii=False), "now": now, "id": job_id,
                },
            )

    def retry_job(self, job_id: int) -> bool:
        self._ensure_ready()
        from sqlalchemy import text

        now = _iso_now()
        with self._engine_or_raise().begin() as conn:
            r = conn.execute(
                text(
                    "UPDATE asset_download_jobs SET status = 'queued', error_code = NULL, "
                    "error_message = NULL, retry_count = 0, throttle_level = 0, next_run_at = NULL, "
                    "lease_owner = NULL, lease_expires_at = NULL, updated_at = :now WHERE id = :id"
                ),
                {"now": now, "id": job_id},
            )
            return r.rowcount > 0

    # -- 熔断账本（asset_sources.risk_control）------------------------------
    def source_risk_control(self, platform: str) -> int:
        self._ensure_ready()
        from sqlalchemy import text

        with self._engine_or_raise().connect() as conn:
            row = conn.execute(
                text("SELECT risk_control FROM asset_sources WHERE source_platform = :p LIMIT 1"),
                {"p": platform},
            ).first()
        return int(row[0]) if row else 0

    def set_source_risk_control(self, platform: str, level: int) -> None:
        self._ensure_ready()
        from sqlalchemy import text

        now = _iso_now()
        with self._engine_or_raise().begin() as conn:
            r = conn.execute(
                text(
                    "UPDATE asset_sources SET risk_control = :l, updated_at = :now "
                    "WHERE source_platform = :p"
                ),
                {"l": level, "now": now, "p": platform},
            )
            if r.rowcount == 0:
                # 源账本尚无该平台行：用合成 source_key 占位（UNIQUE(source_platform, source_key)）
                # 注意：NOT NULL 列需显式提供（ORM default 为客户端默认，无 server_default）
                conn.execute(
                    text(
                        "INSERT INTO asset_sources "
                        "(source_platform, source_key, risk_control, throttle_level, consecutive_failures, idle_runs, created_at, updated_at) "
                        "VALUES (:p, '__circuit_breaker__', :l, 0, 0, 0, :now, :now)"
                    ),
                    {"p": platform, "l": level, "now": now},
                )


# ---------------------------------------------------------------------------
# DownloadWorker：领任务 → 下载 → 校验 → 存存储 → MD5 → 记账（失败退避/熔断）
# ---------------------------------------------------------------------------
class DownloadWorker:
    def __init__(
        self,
        repo: DownloadJobRepo,
        storage: Storage,
        config: Any,
        worker_id: str | None = None,
        backoff_map: dict[str, float] | None = None,
        default_backoff_seconds: float | None = None,
        breaker_cooldown_seconds: float | None = None,
        timeout_seconds: float | None = None,
        extra_headers: dict[str, str] | None = None,
    ):
        self.repo = repo
        self.storage = storage
        self.config = config
        self.worker_id = worker_id or _resolve_worker_id()
        self.backoff_map = backoff_map or RETRY_BACKOFF_SECONDS
        self.default_backoff_seconds = default_backoff_seconds or DEFAULT_BACKOFF_SECONDS
        self.timeout_seconds = timeout_seconds or getattr(config.download, "timeout_seconds", 30.0)
        self.breaker_cooldown_seconds = breaker_cooldown_seconds or getattr(
            config.download, "circuit_breaker_cooldown_seconds", 300.0
        )
        self.extra_headers = dict(extra_headers or {})
        self._failures: dict[str, int] = {}
        self._cooldown_until: dict[str, float] = {}
        self.running = False
        self.last_run_stats: dict[str, Any] = {}

    # -- 熔断辅助 ----------------------------------------------------------
    def _risk_control(self, platform: str) -> int:
        getter = getattr(self.repo, "source_risk_control", None)
        if getter is not None:
            try:
                return int(getter(platform) or 0)
            except Exception:
                return 0
        return 1 if self._failures.get(platform, 0) >= self._breaker_threshold() else 0

    def _breaker_threshold(self) -> int:
        return int(getattr(self.config.download, "circuit_breaker_failures", 2) or 2)

    def _set_risk_control(self, platform: str, level: int) -> None:
        setter = getattr(self.repo, "set_source_risk_control", None)
        if setter is not None:
            try:
                setter(platform, level)
            except Exception as e:  # 持久化失败不阻断下载主流程
                log.warning("写 asset_sources.risk_control 失败 platform=%s level=%s err=%s", platform, level, e)

    def _platform_blocked(self, platform: str) -> bool:
        """熔断冷却期内该平台暂停（冷却结束自动放行探针）。"""
        if self._risk_control(platform) <= 0:
            return False
        return time.time() < self._cooldown_until.get(platform, 0.0)

    def _on_failure_platform(self, platform: str) -> None:
        """熔断计数：连续失败 ≥ 阈值 → risk_control=1 + 冷却（探针恢复）。"""
        self._failures[platform] = self._failures.get(platform, 0) + 1
        if self._failures[platform] >= self._breaker_threshold():
            self._set_risk_control(platform, 1)
            self._cooldown_until[platform] = time.time() + self.breaker_cooldown_seconds
            log.warning(
                "熔断：platform=%s 连续失败 %d 次 → risk_control=1（%ss 后探针恢复）",
                platform, self._failures[platform], self.breaker_cooldown_seconds,
            )

    def _on_success(self, platform: str) -> None:
        if self._failures.get(platform, 0) >= self._breaker_threshold() or self._risk_control(platform) > 0:
            self._set_risk_control(platform, 0)
            log.info("熔断恢复：platform=%s 探针成功 → risk_control=0", platform)
        self._failures[platform] = 0
        self._cooldown_until.pop(platform, None)

    # -- 主循环 ------------------------------------------------------------
    def _claim(self) -> dict | None:
        lease_minutes = int(getattr(self.config.download, "lease_minutes", 45) or 45)
        return self.repo.claim_next(self.worker_id, lease_minutes)

    def run_once(self, max_jobs: int | None = None) -> dict[str, Any]:
        """单轮：领任务处理（默认至多 concurrency 个）。返回统计 dict。"""
        stats: dict[str, Any] = {
            "claimed": 0, "succeeded": 0, "failed": 0, "skipped": 0,
            "paused_platforms": [], "worker_id": self.worker_id,
        }
        limit = max_jobs if max_jobs is not None else int(getattr(self.config.download, "concurrency", 3) or 3)
        attempts = 0
        max_attempts = max(limit * 3 + 5, 10)  # 防无限循环（熔断放回场景）
        while attempts < max_attempts and stats["claimed"] < limit:
            attempts += 1
            job = self._claim()
            if job is None:
                break
            stats["claimed"] += 1
            if self._platform_blocked(job["source_platform"]):
                # 熔断冷却期：放回队列，跳过（探针在冷却结束后自动放行）
                self.repo.release_claim(job["id"])
                stats["skipped"] += 1
                p = job["source_platform"]
                if p not in stats["paused_platforms"]:
                    stats["paused_platforms"].append(p)
                continue
            outcome = self._process(job)
            stats[outcome] += 1
        self.last_run_stats = stats
        return stats

    def run_forever(self, interval_seconds: float = 1.0, stop_event: threading.Event | None = None) -> None:
        self.running = True
        try:
            while not (stop_event and stop_event.is_set()):
                try:
                    self.run_once()
                except Exception:
                    log.exception("worker 单轮异常（继续下一轮）")
                time.sleep(interval_seconds)
        finally:
            self.running = False

    def _process(self, job: dict) -> str:
        """处理单个任务：返回 "succeeded" / "failed"。"""
        job_id = job["id"]
        platform = job["source_platform"]
        tmp_dir = Path(tempfile.gettempdir()) / "materials-dl" / self.worker_id
        tmp_dir.mkdir(parents=True, exist_ok=True)
        ext = _guess_ext(job.get("source_url", ""), job.get("job_type", "video"))
        dest = tmp_dir / f"{job_id}{ext}.part"  # 按 job_id 固定：失败保留，下次续传
        try:
            result = fetch_file(
                job["source_url"], dest, resume=True,
                timeout=self.timeout_seconds, extra_headers=self.extra_headers,
            )
            size = result["size"]
            if size > HARD_MAX_SIZE_BYTES:
                log.warning(
                    "素材超过硬规格上限 %d 字节（P-007 预警，仅提示）：job=%s size=%d",
                    HARD_MAX_SIZE_BYTES, job_id, size,
                )
            asset_type = job.get("job_type") or "video"
            key = self.storage.key_for(asset_type, f"{job_id}{ext}")
            self.storage.put_file(key, dest)
            md5 = compute_md5(dest)
            evidence = {
                "ok": True, "url": redact_url(job["source_url"]), "http_status": 200,
                "size": size, "resumed": result["resumed"], "storage_key": key,
                "md5": md5, "worker_id": self.worker_id, "message": "下载成功",
            }
            self.repo.finish_success(job_id, file_path=key, md5=md5, size=size, evidence=evidence)
            dest.unlink(missing_ok=True)  # 成功入库后清理 .part
            self._on_success(platform)
            log.info("下载成功 job=%s platform=%s key=%s md5=%s size=%d", job_id, platform, key, md5, size)
            return "succeeded"
        except DownloadError as e:
            return self._on_failure(job, e)
        except Exception as e:  # 存储/环境等未分类错误
            return self._on_failure(job, DownloadError(UNEXPECTED, f"{e.__class__.__name__}: {e}"))

    def _on_failure(self, job: dict, err: DownloadError) -> str:
        job_id = job["id"]
        platform = job["source_platform"]
        code = err.error_code
        retry_count = int(job.get("retry_count") or 0) + 1
        throttle = min(int(job.get("throttle_level") or 0) + 1, THROTTLE_MAX_LEVEL)
        max_retries = int(job.get("max_retries") or 3)
        self._on_failure_platform(platform)
        evidence: dict[str, Any] = {
            "ok": False, "url": redact_url(job["source_url"]), "error_code": code,
            "message": _truncate(err.message, 500), "worker_id": self.worker_id,
        }
        if err.http_status:
            evidence["http_status"] = err.http_status
        if err.evidence:
            evidence["detail"] = err.evidence
        if code in _MANUAL_ERROR_CODES:
            # P-002：人工接管，不自动续跑（断点续跑由人工登录后 retry 触发）
            self.repo.finish_failure(job_id, code, retry_count, None, throttle, evidence, status="blocked")
            log.warning("任务转人工接管：job=%s platform=%s code=%s", job_id, platform, code)
            return "failed"
        if retry_count >= max_retries:
            self.repo.finish_failure(job_id, code, retry_count, None, throttle, evidence, status="failed")
            log.error("任务重试耗尽：job=%s platform=%s code=%s retry=%d", job_id, platform, code, retry_count)
            return "failed"
        next_run_at = compute_next_run_at(code, throttle, self.backoff_map, self.default_backoff_seconds)
        self.repo.finish_failure(job_id, code, retry_count, next_run_at, throttle, evidence)
        log.warning(
            "下载失败可重试：job=%s platform=%s code=%s retry=%d/%d next=%s",
            job_id, platform, code, retry_count, max_retries, next_run_at,
        )
        return "failed"


# ---------------------------------------------------------------------------
# DownloaderService：集成入口（供 HTTP API 与 CLI 使用）
# ---------------------------------------------------------------------------
class DownloaderService:
    def __init__(self, repo: DownloadJobRepo, storage: Storage | None = None, config: Any = None, worker: DownloadWorker | None = None):
        self.config = config or load_config()
        self.storage = storage or LocalStorage(self.config.storage_dir)
        self.repo = repo
        self.worker = worker or DownloadWorker(repo, self.storage, self.config)
        self.started_at = time.time()
        self._worker_thread: threading.Thread | None = None

    # -- 任务账本（透传 repo）-----------------------------------------------
    def enqueue_job(self, source_platform: str, source_url: str, job_type: str, priority: int = 0) -> tuple[dict, bool]:
        return self.repo.enqueue(source_platform, source_url, job_type, priority)

    def get_job(self, job_id: int) -> dict | None:
        return self.repo.get_job(job_id)

    def list_jobs(self, status: str | None = None) -> list[dict]:
        return self.repo.list_jobs(status)

    def retry_job(self, job_id: int) -> bool:
        return self.repo.retry_job(job_id)

    # -- 运行 ---------------------------------------------------------------
    def run_once(self, max_jobs: int | None = None) -> dict[str, Any]:
        return self.worker.run_once(max_jobs)

    def start_worker_loop(self, interval_seconds: float = 1.0) -> None:
        if self._worker_thread and self._worker_thread.is_alive():
            return
        self._worker_thread = threading.Thread(
            target=lambda: self.worker.run_forever(interval_seconds=interval_seconds),
            name="materials-download-worker", daemon=True,
        )
        self._worker_thread.start()

    def health(self) -> dict[str, Any]:
        return {
            "worker_id": self.worker.worker_id,
            "worker_running": self.worker.running,
            "last_run": self.worker.last_run_stats,
            "uptime_seconds": round(time.time() - self.started_at, 1),
            "repo": type(self.repo).__name__,
            "storage": type(self.storage).__name__,
        }
