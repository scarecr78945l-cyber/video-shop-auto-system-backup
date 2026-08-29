"""微信小店（视频号小店）OpenAPI 薄封装 —— M4 自动上架模块专用。

- 默认 mock 模式：全部内置 fixture，零网络。
- live 模式：TODO（待核对 T1：access_token 获取/缓存；T2：签名参数名官方契约）。
- 依赖：标准库 + requests + pydantic + pydantic-settings（backend/requirements.txt 已有）。
- 安全：任何日志绝不输出 secret / token / 完整 payload。
"""

import hashlib
import logging
import time

import requests  # live 模式预留（T1/T2 核对后接入）

from pydantic_settings import BaseSettings, SettingsConfigDict

_logger = logging.getLogger(__name__)

# WorkflowJob 统一错误码表（09 文档 8+1 码，对齐 M0 error_codes 权威码表 DA-008；
# 本模块不产出 INSUFFICIENT_REFERENCES / PAGE_CHANGED，但集合含全量以保证非法码归一正确）
ERROR_CODES = frozenset({
    "VERIFICATION_REQUIRED",
    "AUTH_REQUIRED",
    "RATE_LIMIT",
    "TIMEOUT",
    "NO_MATCH",
    "INSUFFICIENT_REFERENCES",
    "PLATFORM_REJECT",
    "UNEXPECTED",
    "PAGE_CHANGED",
})

# 重试退避（秒）：RATE_LIMIT=180 / TIMEOUT=60 / NO_MATCH=120 / INSUFFICIENT_REFERENCES=120 / 其余=60
_BACKOFF_SECONDS = {
    "RATE_LIMIT": 180.0,
    "TIMEOUT": 60.0,
    "NO_MATCH": 120.0,
    "INSUFFICIENT_REFERENCES": 120.0,
}
_DEFAULT_BACKOFF_SECONDS = 60.0

# 默认令牌桶参数：每接口 capacity=10，refill_rate=1.0/s
_DEFAULT_BUCKET_CAPACITY = 10.0
_DEFAULT_BUCKET_REFILL_RATE = 1.0

# 连续失败 >=2 次后熔断时长（秒）
_CIRCUIT_OPEN_SECONDS = 300.0


class WechatOpenApiConfig(BaseSettings):
    """微信小店 OpenAPI 配置。环境变量前缀 WECHAT_（如 WECHAT_APPID、WECHAT_MODE）。"""

    model_config = SettingsConfigDict(
        env_prefix="WECHAT_",
        env_file=".env",
        extra="ignore",
    )

    appid: str = ""
    secret: str = ""
    api_base: str = "https://api.weixin.qq.com"
    token_cache_path: str = ""
    mode: str = "mock"  # mock | live，默认 mock


class WechatApiError(Exception):
    """微信小店 OpenAPI 调用异常，error_code 限定 WorkflowJob 码表。"""

    def __init__(
        self,
        error_code: str,
        message: str = "",
        platform_code: str = "",
        evidence: dict | None = None,
    ):
        if error_code not in ERROR_CODES:
            error_code = "UNEXPECTED"
        super().__init__(message or error_code)
        self.error_code = error_code
        self.message = message
        self.platform_code = platform_code
        self.evidence = evidence or {}


class TokenBucket:
    """每接口令牌桶 + 熔断（连续失败 >=2 次熔断 300s）。"""

    def __init__(
        self,
        capacity: float,
        refill_rate: float,
        tokens: float | None = None,
    ):
        self.tokens: float = capacity if tokens is None else tokens
        self.capacity: float = capacity
        self.refill_rate: float = refill_rate  # 每秒补充
        self.consecutive_failures: int = 0
        self.circuit_open_until: float = 0.0
        self._last_refill: float = time.monotonic()

    def try_acquire(self, n: int = 1) -> bool:
        """按时间补充令牌后尝试取 n 个；熔断期内直接返回 False。"""
        now = time.monotonic()
        if now < self.circuit_open_until:
            return False
        elapsed = now - self._last_refill
        self._last_refill = now
        self.tokens = min(self.capacity, self.tokens + elapsed * self.refill_rate)
        if self.tokens >= n:
            self.tokens -= n
            return True
        return False

    def record_failure(self) -> None:
        self.consecutive_failures += 1
        if self.consecutive_failures >= 2:
            self.circuit_open_until = time.monotonic() + _CIRCUIT_OPEN_SECONDS

    def record_success(self) -> None:
        self.consecutive_failures = 0


class WechatOpenApiAdapter:
    """微信小店 OpenAPI 薄封装主类（mock 模式零网络）。"""

    def __init__(self, config: WechatOpenApiConfig | None = None, **overrides):
        self.config = config or WechatOpenApiConfig(**overrides)
        self._buckets: dict[str, TokenBucket] = {}

    # ---------- 基础能力 ----------

    def _sign(self, payload: dict) -> dict:
        """占位签名：按 key 排序的 "k=v" 以 & 连接 + 拼接 secret 后做 sha256。

        签名参数名以官方契约为准，当前为占位实现（待核对 T2）。
        """
        timestamp = int(time.time())
        normalized = "&".join(f"{k}={v}" for k, v in sorted(payload.items()))
        normalized += self.config.secret
        sign = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
        return {"timestamp": timestamp, "sign": sign}

    def _get_token(self) -> str:
        """mock 模式返回固定 token；live 模式 TODO（待核对 T1）。"""
        if self.config.mode == "mock":
            return "mock-token"
        # TODO(T1): live 模式 access_token 获取与 token_cache_path 缓存，待核对官方契约
        raise WechatApiError("UNEXPECTED", "live mode token acquisition not implemented yet")

    def _backoff_delay(self, error_code: str) -> float:
        return _BACKOFF_SECONDS.get(error_code, _DEFAULT_BACKOFF_SECONDS)

    def _log_call(self, api: str, task_id: str, error_code: str) -> None:
        # 脱敏日志：只输出 api / task_id / error_code，绝不输出 secret / token / 完整 payload
        _logger.info(
            "wechat_openapi call api=%s task_id=%s error_code=%s",
            api,
            task_id or "-",
            error_code,
        )

    # ---------- 核心调用 ----------

    def _call(
        self,
        api: str,
        biz: dict | None = None,
        task_id: str = "",
        retry: int = 3,
    ) -> dict:
        biz = biz or {}

        if self.config.mode != "mock":
            # TODO(T1/T2): live 模式：token 获取 -> 签名 -> requests 调用 -> 错误映射，待核对官方契约
            raise WechatApiError(
                "UNEXPECTED",
                "live mode not implemented yet",
                evidence={"api": api},
            )

        bucket = self._buckets.setdefault(
            api,
            TokenBucket(
                capacity=_DEFAULT_BUCKET_CAPACITY,
                refill_rate=_DEFAULT_BUCKET_REFILL_RATE,
            ),
        )
        if not bucket.try_acquire():
            self._log_call(api, task_id, "RATE_LIMIT")
            raise WechatApiError(
                "RATE_LIMIT",
                message=f"token bucket exhausted for api '{api}'",
                evidence={"api": api},
            )

        last_error: WechatApiError | None = None
        for attempt in range(1, retry + 1):
            try:
                result = self._mock_dispatch(api, biz)
                bucket.record_success()
                self._log_call(api, task_id, "OK")
                return result
            except WechatApiError as exc:
                last_error = exc
                bucket.record_failure()
                self._log_call(api, task_id, exc.error_code)
                if attempt < retry:
                    time.sleep(self._backoff_delay(exc.error_code))
        raise last_error  # retry>=1 时循环内必已赋值

    # ---------- mock fixture ----------

    def _mock_dispatch(self, api: str, biz: dict) -> dict:
        """mock 模式内置 fixture；金额字段一律 int（分）。"""
        if api == "create_spu":
            return {"spu_id": "mock_spu_" + str(biz.get("title", ""))[:8]}
        if api == "update_spu":
            return {"ok": True}
        if api == "create_skus":
            return {"sku_ids": [f"mock_sku_{i}" for i in range(len(biz.get("skus", [])))]}
        if api in ("update_stock", "update_price"):
            return {"ok": True}
        if api == "upload_image":
            digest = hashlib.sha256(str(biz.get("file_path", "")).encode("utf-8")).hexdigest()
            return {"media_id": "mock_media_" + digest[:8]}
        if api == "submit_audit":
            return {"audit_id": "mock_audit_" + str(biz.get("spu_id", ""))[-8:]}
        if api == "query_audit_status":
            return {"audit_status": "pass", "reject_reason": ""}
        if api == "get_product_link":
            return {
                "product_link": "https://channels.weixin.qq.com/shop/goods/"
                + str(biz.get("spu_id", ""))
            }
        raise WechatApiError("UNEXPECTED", f"unknown api {api}")

    # ---------- 业务方法（task_id 一律透传 _call） ----------

    def create_spu(
        self,
        title: str,
        category_id: int,
        qualification: dict | None,
        freight_template_id: int,
        purchase_limit: int,
        task_id: str = "",
    ) -> dict:
        biz = {
            "title": title,
            "category_id": category_id,
            "qualification": qualification,
            "freight_template_id": freight_template_id,
            "purchase_limit": purchase_limit,
            "task_id": task_id,
        }
        return self._call("create_spu", biz, task_id=task_id)

    def update_spu(self, spu_id: str, task_id: str = "", **fields) -> dict:
        biz = {"spu_id": spu_id, "task_id": task_id, **fields}
        return self._call("update_spu", biz, task_id=task_id)

    def create_skus(self, spu_id: str, skus: list[dict], task_id: str = "") -> dict:
        biz = {"spu_id": spu_id, "skus": skus, "task_id": task_id}
        return self._call("create_skus", biz, task_id=task_id)

    def update_stock(self, sku_id: str, stock: int, task_id: str = "") -> dict:
        biz = {"sku_id": sku_id, "stock": stock, "task_id": task_id}
        return self._call("update_stock", biz, task_id=task_id)

    def update_price(self, sku_id: str, price_cents: int, task_id: str = "") -> dict:
        # 金额字段一律 int（分）
        biz = {"sku_id": sku_id, "price_cents": int(price_cents), "task_id": task_id}
        return self._call("update_price", biz, task_id=task_id)

    def upload_image(self, file_path: str, usage: str, task_id: str = "") -> dict:
        biz = {"file_path": file_path, "usage": usage, "task_id": task_id}
        return self._call("upload_image", biz, task_id=task_id)

    def submit_audit(self, spu_id: str, media_ids: list[str], task_id: str = "") -> dict:
        biz = {"spu_id": spu_id, "media_ids": media_ids, "task_id": task_id}
        return self._call("submit_audit", biz, task_id=task_id)

    def query_audit_status(self, audit_id: str, task_id: str = "") -> dict:
        biz = {"audit_id": audit_id, "task_id": task_id}
        return self._call("query_audit_status", biz, task_id=task_id)

    def get_product_link(self, spu_id: str, task_id: str = "") -> dict:
        biz = {"spu_id": spu_id, "task_id": task_id}
        return self._call("get_product_link", biz, task_id=task_id)
