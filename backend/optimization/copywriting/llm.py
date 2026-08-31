"""M3 文案管线 · DeepSeek LLM 客户端（结构化 JSON 输出）。

纪律（对齐宪法第 4.5 节 / 10 文档第六节）：
- 密钥只读环境变量 ``DEEPSEEK_API_KEY``（经 ``os.environ`` 取值），
  任何文件（代码/md/日志/JSON）绝不写明文密钥；
- 结构化输出：``response_format=json_object`` + 系统提示内嵌 JSON Schema，
  返回后做轻量 Schema 校验（不依赖 jsonschema 第三方包）；
- 失败重试 ``config.llm.max_retries`` 次（网络/超时/5xx/429/无效 JSON/结构不符）；
  超时 ``config.llm.timeout_seconds``；
- 无 Key 或最终失败一律返回 ``None``，由调用方降级规则模板（source="rule_fallback"）。
"""

from __future__ import annotations

import json
import os
import urllib.request
from typing import Any, Callable, Optional

from ..config import M3Config, load_config

DEEPSEEK_URL = "https://api.deepseek.com/chat/completions"
DEEPSEEK_MODEL = "deepseek-chat"
# 第三方兼容服务商接入（OpenAI 兼容 /chat/completions）：
#   LLM_BASE_URL 覆盖接口地址（如 OpenRouter/硅基流动/中转，形如 https://…/v1）
#   LLM_MODEL    覆盖模型名（如 deepseek-chat / deepseek-v3 / 任意兼容模型）
def _base_url() -> str:
    url = (os.environ.get("LLM_BASE_URL") or "").strip() or DEEPSEEK_URL
    # 兼容两种写法：完整 /chat/completions URL，或 v1 根地址（自动拼接）
    if not url.rstrip("/").endswith("/chat/completions"):
        url = url.rstrip("/") + "/chat/completions"
    return url


def _model_name(default: str) -> str:
    return (os.environ.get("LLM_MODEL") or "").strip() or default

# 传输函数签名：(url, headers, payload, timeout) -> (status_code, body_str)
PostFn = Callable[[str, dict[str, str], dict[str, Any], float], tuple[int, str]]


def _default_post(
    url: str,
    headers: dict[str, str],
    payload: dict[str, Any],
    timeout: float,
) -> tuple[int, str]:
    """默认 HTTP 传输：标准库 urllib（避免第三方依赖）。"""
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return int(resp.status), resp.read().decode("utf-8")


def _strip_code_fence(text: str) -> str:
    """去掉模型偶发的 ```json ... ``` 围栏。"""
    t = (text or "").strip()
    if t.startswith("```"):
        t = t.split("\n", 1)[-1] if "\n" in t else t[3:]
    if t.endswith("```"):
        t = t[:-3]
    return t.strip()


def _validate_schema(data: Any, schema: dict[str, Any]) -> bool:
    """轻量 JSON Schema 校验（仅支持本管线用到的 object/array/string/int 子集）。"""
    stype = schema.get("type")
    if stype == "object":
        if not isinstance(data, dict):
            return False
        for req in schema.get("required", []):
            if req not in data:
                return False
        for key, prop in schema.get("properties", {}).items():
            if key in data and not _validate_schema(data[key], prop):
                return False
        return True
    if stype == "array":
        if not isinstance(data, list):
            return False
        items = schema.get("items", {})
        return all(_validate_schema(it, items) for it in data)
    if stype == "string":
        if not isinstance(data, str):
            return False
        return len(data) >= int(schema.get("minLength", 0))
    if stype == "integer":
        return isinstance(data, int) and not isinstance(data, bool)
    if stype == "number":
        return isinstance(data, (int, float)) and not isinstance(data, bool)
    if stype == "boolean":
        return isinstance(data, bool)
    return True


class DeepSeekClient:
    """DeepSeek 结构化输出客户端。

    ``post`` 参数可注入自定义传输（测试用），默认标准库 urllib。
    密钥始终经 ``os.environ`` 读取，实例不保存、不落盘、不落日志。
    """

    def __init__(
        self,
        config: Optional[M3Config] = None,
        post: Optional[PostFn] = None,
        model: Optional[str] = None,
    ):
        self.config = config or load_config()
        self._post = post or _default_post
        # 模型名：构造参数 > 环境变量 LLM_MODEL > 默认 deepseek-chat
        self.model = model or _model_name(DEEPSEEK_MODEL)
        self.last_error: str = ""  # 最近一次失败原因（不含密钥），供调用方记录

    # ---------- 密钥 ----------

    @property
    def key_env(self) -> str:
        return self.config.llm.deepseek_env

    def has_key(self) -> bool:
        """是否有可用密钥（只读环境变量，无则走规则降级）。"""
        return bool((os.environ.get(self.key_env) or "").strip())

    # ---------- 结构化生成 ----------

    def generate_structured(
        self,
        system: str,
        user: str,
        schema: dict[str, Any],
        *,
        max_tokens: int = 2048,
        temperature: float = 0.7,
    ) -> Optional[dict[str, Any]]:
        """请求结构化 JSON 输出；成功返回解析后的 dict，失败返回 None。

        重试语义：``max_retries + 1`` 次总尝试（默认 3 次）；
        仅网络/超时/5xx/429/无效 JSON/结构不符 这类可恢复失败触发重试。
        """
        if not self.has_key():
            self.last_error = "no_api_key"
            return None

        schema_note = (
            "你必须只输出一个符合以下 JSON Schema 的 JSON 对象，"
            "不要输出任何额外文字：\n" + json.dumps(schema, ensure_ascii=False)
        )
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system + "\n" + schema_note},
                {"role": "user", "content": user},
            ],
            "response_format": {"type": "json_object"},
            "max_tokens": max_tokens,
            "temperature": temperature,
            "stream": False,
        }
        headers = {
            "Content-Type": "application/json",
            "Authorization": "Bearer " + (os.environ.get(self.key_env) or "").strip(),
        }

        last_error = ""
        for _ in range(self.config.llm.max_retries + 1):
            try:
                status, body = self._post(
                    _base_url(), headers, payload, self.config.llm.timeout_seconds
                )
            except Exception as exc:  # 网络/连接/超时：可恢复，重试
                last_error = f"transport:{type(exc).__name__}"
                continue
            if status == 429 or status >= 500:  # 限流/服务端：可恢复，重试
                last_error = f"http_{status}"
                continue
            if status != 200:
                last_error = f"http_{status}"
                continue
            try:
                data = json.loads(body)
                content = _strip_code_fence(data["choices"][0]["message"]["content"])
                parsed = json.loads(content)
            except Exception:
                last_error = "bad_response_json"
                continue
            if not _validate_schema(parsed, schema):
                last_error = "schema_mismatch"
                continue
            self.last_error = ""
            return parsed

        self.last_error = last_error
        return None
