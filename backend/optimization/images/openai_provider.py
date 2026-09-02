"""OpenAI 兼容 img2img 生图 Provider（P-044，2026-09-01 接入用户提供的生图模型）。

- 端点：`IMG_API_BASE`（默认 http://192.168.31.12:51000/v1）+ `IMG_API_KEY` + `IMG_MODEL`（默认 gpt-image-2）
- 能力：**图生图**（/v1/images/edits，multipart：image 参考图 + prompt）——商品本体保真，
  白底/场景/特写等变体由 prompt 控制（P-043 教训：不做同图缩放糊弄，真实变体）。
- 输出：b64_json → 落盘 PNG，记录宽高/phash。
- 错误分类：429→RATE_LIMIT 退避、5xx/TIMEOUT→退避重试、4xx→PLATFORM_REJECT、解析失败→bad_response。
- 密钥只读环境变量，不落库不落日志。
"""

from __future__ import annotations

import base64
import io
import json
import os
import time
import uuid
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Callable, Optional

from PIL import Image

from .provider import DETAIL_SIZE, MAIN_SIZE, phash_dhash
from ..models import ImageDraft

IMG_BASE_DEFAULT = "http://192.168.31.12:51000/v1"
IMG_MODEL_DEFAULT = "gpt-image-2"
RATE_LIMIT_BACKOFF_SECONDS = 180


class OpenAIImgError(Exception):
    def __init__(self, error_code: str, message: str = ""):
        super().__init__(message or error_code)
        self.error_code = error_code


def _default_post(url: str, headers: dict, body: bytes, timeout: float) -> tuple[int, str]:
    req = urllib.request.Request(url, data=body, headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return int(resp.status), resp.read().decode("utf-8")


class OpenAIImg2ImgProvider:
    """图生图 Provider：参考商品图 → 指定变体（白底/场景/特写…），商品本体保真。"""

    def __init__(
        self,
        base_url: str = "",
        model: str = "",
        out_dir: Optional[str | Path] = None,
        post: Optional[Callable[[str, dict, bytes, float], tuple[int, str]]] = None,
        sleep_fn: Optional[Callable[[float], None]] = None,
    ):
        self.base_url = (base_url or os.environ.get("IMG_API_BASE") or IMG_BASE_DEFAULT).rstrip("/")
        self.model = model or os.environ.get("IMG_MODEL") or IMG_MODEL_DEFAULT
        self.key = (os.environ.get("IMG_API_KEY") or "").strip()
        self.out_dir = Path(out_dir) if out_dir is not None else Path("data/images/listing")
        self._post = post or _default_post
        self._sleep_fn = sleep_fn or time.sleep
        self.last_error = ""

    def has_key(self) -> bool:
        return bool(self.key)

    # ---------- 主入口 ----------
    def generate(
        self,
        reference_image: str | Path,
        prompt: str,
        product_id: int | str,
        image_type: str = "main",
        variant_no: int = 0,
        size: str = "1024x1024",
        max_retries: int = 2,
    ) -> ImageDraft:
        """图生图：参考图 + prompt → 变体图。失败抛 OpenAIImgError。"""
        if not self.has_key():
            raise OpenAIImgError("no_api_key", "IMG_API_KEY 未配置")
        ref = Path(reference_image)
        if not ref.exists():
            raise OpenAIImgError("no_reference", f"参考图不存在: {ref}")
        self.out_dir.mkdir(parents=True, exist_ok=True)

        last_error = ""
        for attempt in range(max_retries + 1):
            try:
                status, body = self._post_multipart(ref, prompt, size)
            except TimeoutError:
                last_error = "TIMEOUT"
                self._sleep_fn(1.0)
                continue
            except Exception as exc:
                last_error = f"UNEXPECTED:{type(exc).__name__}"
                self._sleep_fn(1.0)
                continue
            if status == 429:
                last_error = "RATE_LIMIT"
                self._sleep_fn(RATE_LIMIT_BACKOFF_SECONDS)
                continue
            if status >= 500:
                last_error = f"http_{status}"
                self._sleep_fn(1.0)
                continue
            if status != 200:
                self.last_error = f"PLATFORM_REJECT:http_{status}"
                raise OpenAIImgError(self.last_error, body[:300])
            try:
                data = json.loads(body)
                b64 = (data.get("data") or [{}])[0].get("b64_json", "")
                if not b64:
                    last_error = "bad_response"
                    continue
                img_bytes = base64.b64decode(b64)
                return self._save_image_bytes(img_bytes, product_id, image_type, variant_no)
            except Exception:
                last_error = "bad_response"
                continue
        self.last_error = last_error
        raise OpenAIImgError(last_error, "img2img generate failed")

    # ---------- multipart 请求 ----------
    def _post_multipart(self, ref: Path, prompt: str, size: str) -> tuple[int, str]:
        boundary = "----img2img" + uuid.uuid4().hex
        parts: list[bytes] = []
        fields = {
            "model": self.model,
            "prompt": prompt,
            "size": size,
        }
        for name, value in fields.items():
            parts.append(
                f"--{boundary}\r\nContent-Disposition: form-data; name=\"{name}\"\r\n\r\n{value}\r\n".encode()
            )
        parts.append(
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"image\"; filename=\"{ref.name}\"\r\nContent-Type: image/png\r\n\r\n".encode()
        )
        parts.append(ref.read_bytes())
        parts.append(b"\r\n")
        parts.append(f"--{boundary}--\r\n".encode())
        body = b"".join(parts)
        headers = {
            "Authorization": f"Bearer {self.key}",
            "Content-Type": f"multipart/form-data; boundary={boundary}",
        }
        return self._post(self.base_url + "/images/edits", headers, body, 120)

    # ---------- 落盘 ----------
    def _save_image_bytes(
        self, img_bytes: bytes, product_id: int | str, image_type: str, variant_no: int
    ) -> ImageDraft:
        try:
            img = Image.open(io.BytesIO(img_bytes))
            img.load()
        except Exception as exc:
            raise OpenAIImgError("bad_response", f"解码失败: {type(exc).__name__}")
        path = self.out_dir / f"{image_type}_{product_id}_{variant_no}.png"
        img.save(path, format="PNG")
        return ImageDraft(
            batch_id="", product_id=str(product_id), image_type=image_type,
            variant_no=variant_no, file_path=str(path),
            phash=phash_dhash(path), width=img.width, height=img.height,
        )
