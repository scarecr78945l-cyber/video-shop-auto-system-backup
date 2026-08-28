"""M3 主图/详情图管线 · Wan 生图 Provider（WanImageProvider）。

对齐方案文档 06 第二节与 context/README 外部契约（WAN_API_KEY）：
- 在线模式：调用 Wan（通义万相）文生图；封装错误分类 ——
  RATE_LIMIT(429) → 180s 退避重试、TIMEOUT/服务端 5xx → 退避重试、
  4xx → 直接返回错误码；重试上限 config.llm.max_retries（默认 2）；
  传输函数可注入（测试用，不真跑网络，逻辑可测）；
- 离线模式（无 WAN_API_KEY）：Pillow 生成占位图 ——
  主图 800x800（1:1）、详情图 750x1000（3:4）；
  保存到 data/optimization/images/（不存在则创建），记录宽高与 dHash；
- 密钥只读环境变量 WAN_API_KEY（config.llm.wan_env），不落库不落日志。
"""

from __future__ import annotations

import base64
import colorsys
import io
import json
import os
import time
import urllib.request
from pathlib import Path
from typing import Any, Callable, Optional

from PIL import Image

from ..config import M3Config, load_config
from ..models import ImageDraft, ImagePlan
from .quality_gate import phash_dhash

WAN_URL = (
    "https://dashscope.aliyuncs.com/api/v1/services/aigc/text2image/image-synthesis"
)
WAN_MODEL = "wanx-v1"
RATE_LIMIT_BACKOFF_SECONDS = 180  # 429 退避（context/README 契约）

PostFn = Callable[[str, dict[str, str], dict[str, Any], float], tuple[int, str]]
SleepFn = Callable[[float], None]

MAIN_SIZE = (800, 800)      # 主图 1:1
DETAIL_SIZE = (750, 1000)   # 详情图 3:4（亦兼容 800x800）


class WanImageError(Exception):
    """生图失败（复用宪法错误码：RATE_LIMIT/TIMEOUT/PLATFORM_REJECT/UNEXPECTED）。"""

    def __init__(self, error_code: str, message: str = ""):
        super().__init__(message or error_code)
        self.error_code = error_code


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


def _hsv_to_rgb(h: float, s: float, v: float) -> tuple[int, int, int]:
    r, g, b = colorsys.hsv_to_rgb((h % 360) / 360.0, s, v)
    return int(r * 255), int(g * 255), int(b * 255)


class WanImageProvider:
    """生图 Provider：在线走 Wan API，离线降级 Pillow 占位图。"""

    def __init__(
        self,
        config: Optional[M3Config] = None,
        out_dir: Optional[str | Path] = None,
        post: Optional[PostFn] = None,
        sleep_fn: Optional[SleepFn] = None,
        model: str = WAN_MODEL,
    ):
        self.config: M3Config = config or load_config()
        self.out_dir: Path = Path(out_dir) if out_dir is not None else (
            self.config.data_dir / "optimization" / "images"
        )
        self._post: PostFn = post or _default_post
        self._sleep_fn: SleepFn = sleep_fn or time.sleep
        self.model = model
        self.last_error: str = ""

    @property
    def key_env(self) -> str:
        return self.config.llm.wan_env

    def has_key(self) -> bool:
        return bool((os.environ.get(self.key_env) or "").strip())

    # ---------- 主入口 ----------

    def generate(
        self,
        product: dict[str, Any],
        plan: ImagePlan,
        variant_no: int = 1,
        on_error: str = "raise",
    ) -> ImageDraft:
        """生成单张图。离线（无 Key）→ 占位图；在线失败按 on_error 抛错或降级占位。"""
        image_type = plan.image_type
        product_id = product["product_id"]
        if not self.has_key():
            self.last_error = "no_api_key"
            return self._generate_placeholder(product, plan, variant_no)

        prompt = ""
        if plan.prompts:
            idx = max(0, min(variant_no - 1, len(plan.prompts) - 1))
            prompt = plan.prompts[idx]
        error_code, img_bytes = self._request_wan(prompt)
        if error_code is None and img_bytes:
            self.last_error = ""
            return self._save_image_bytes(
                img_bytes, image_type, product_id, variant_no
            )
        self.last_error = error_code or "UNEXPECTED"
        if on_error == "placeholder":
            return self._generate_placeholder(product, plan, variant_no)
        raise WanImageError(self.last_error, f"wan generate failed: {self.last_error}")

    # ---------- 在线路径（错误分类逻辑，可注入传输测试） ----------

    def _request_wan(self, prompt: str) -> tuple[Optional[str], Optional[bytes]]:
        """调用 Wan；返回 (error_code, image_bytes)。429→180s 退避重试；TIMEOUT 重试。"""
        if not prompt:
            return "empty_prompt", None
        payload: dict[str, Any] = {
            "model": self.model,
            "input": {"prompt": prompt},
            "parameters": {"size": "1024*1024", "n": 1},
        }
        headers = {
            "Content-Type": "application/json",
            "Authorization": "Bearer " + (os.environ.get(self.key_env) or "").strip(),
        }
        last_error: str = ""
        for _ in range(self.config.llm.max_retries + 1):
            try:
                status, body = self._post(
                    WAN_URL, headers, payload, self.config.llm.timeout_seconds
                )
            except TimeoutError:
                last_error = "TIMEOUT"
                self._sleep_fn(1.0)
                continue
            except Exception as exc:
                last_error = f"UNEXPECTED:{type(exc).__name__}"
                self._sleep_fn(1.0)
                continue
            if status == 429:  # RATE_LIMIT：180s 退避后重试
                last_error = "RATE_LIMIT"
                self._sleep_fn(RATE_LIMIT_BACKOFF_SECONDS)
                continue
            if status >= 500:  # 服务端错误：小退避重试
                last_error = f"http_{status}"
                self._sleep_fn(1.0)
                continue
            if status != 200:  # 4xx：不可恢复
                return f"PLATFORM_REJECT:http_{status}", None
            try:
                data = json.loads(body)
                b64 = data["output"]["results"][0].get("b64_json")
                if not b64:
                    return "bad_response", None
                return None, base64.b64decode(b64)
            except Exception:
                return "bad_response", None
        return last_error, None

    def _save_image_bytes(
        self, img_bytes: bytes, image_type: str, product_id: str, variant_no: int
    ) -> ImageDraft:
        """在线返回的图片字节落盘（Pillow 解码校验，记录宽高）。"""
        self.out_dir.mkdir(parents=True, exist_ok=True)
        try:
            img = Image.open(io.BytesIO(img_bytes))
            img.load()
        except Exception as exc:
            raise WanImageError("bad_response", f"解码生图结果失败: {type(exc).__name__}")
        path = self.out_dir / f"{image_type}_{product_id}_{variant_no}.png"
        img.save(path, format="PNG")
        return ImageDraft(
            batch_id="", product_id=product_id, image_type=image_type,
            variant_no=variant_no, file_path=str(path),
            phash=phash_dhash(path), width=img.width, height=img.height,
        )

    # ---------- 离线路径（Pillow 占位图） ----------

    def _generate_placeholder(
        self, product: dict[str, Any], plan: ImagePlan, variant_no: int
    ) -> ImageDraft:
        """fixtures 离线模式：Pillow 画占位图，保存并记录宽高/phash。"""
        self.out_dir.mkdir(parents=True, exist_ok=True)
        width, height = MAIN_SIZE if plan.image_type == "main" else DETAIL_SIZE
        img = self._draw_placeholder(width, height, variant_no, plan)
        path = self.out_dir / (
            f"{plan.image_type}_{product['product_id']}_{variant_no}.png"
        )
        img.save(path, format="PNG")
        return ImageDraft(
            batch_id="", product_id=product["product_id"],
            image_type=plan.image_type, variant_no=variant_no,
            file_path=str(path), phash=phash_dhash(path),
            width=width, height=height,
        )

    def _draw_placeholder(self, width: int, height: int, variant_no: int,
                          plan: ImagePlan):
        """每张占位图按 variant 差异化（色相/主体偏移/形状/角标位置），
        保证 5 张主图 dHash 两两汉明距离 > 8（不全相同）。"""
        from PIL import ImageDraw, ImageFont

        hue = (variant_no * 55) % 360
        img = Image.new("RGB", (width, height), _hsv_to_rgb(hue, 0.22, 0.98))
        draw = ImageDraw.Draw(img)

        # 主体偏移（每张不同）
        offsets = [(-0.10, 0.0), (0.12, -0.06), (-0.06, 0.10),
                   (0.08, 0.06), (-0.12, -0.10)]
        ox, oy = offsets[(variant_no - 1) % len(offsets)]
        cx, cy = width * (0.5 + ox), height * (0.5 + oy)
        bw, bh = int(width * 0.40), int(height * 0.26)
        body_color = _hsv_to_rgb((hue + 150) % 360, 0.55, 0.52)
        lid_color = _hsv_to_rgb((hue + 40) % 360, 0.6, 0.72)
        x0, y0, x1, y1 = cx - bw / 2, cy - bh / 2, cx + bw / 2, cy + bh / 2

        shape = (variant_no - 1) % 5
        if shape == 0:      # 圆角矩形杯身
            draw.rounded_rectangle([x0, y0, x1, y1],
                                   radius=max(8, min(bw, bh) // 6), fill=body_color)
            draw.ellipse([cx - bw / 3, y0 - bh * 0.35, cx + bw / 3, y0 + bh * 0.12],
                         fill=lid_color)
        elif shape == 1:    # 椭圆
            draw.ellipse([x0, y0, x1, y1], fill=body_color)
        elif shape == 2:    # 三角
            draw.polygon([(cx, y0 - bh * 0.2), (x0, y1), (x1, y1)], fill=body_color)
        elif shape == 3:    # 菱形
            draw.polygon([(cx, y0 - bh * 0.2), (x1, cy), (cx, y1 + bh * 0.2), (x0, cy)],
                         fill=body_color)
        else:               # 矩形
            draw.rectangle([x0, y0, x1, y1], fill=body_color)

        # 角标（角位循环 + 角标数量随 variant 变化）
        badge = int(min(width, height) * 0.10)
        positions = [(10, 10), (width - badge - 10, 10),
                     (10, height - badge - 10), (width - badge - 10, height - badge - 10)]
        bx, by = positions[variant_no % 4]
        for k in range(variant_no):
            draw.rectangle([bx + k * 4, by + k * 4, bx + badge + k * 4, by + badge + k * 4],
                           fill=_hsv_to_rgb((hue + 200 + k * 30) % 360, 0.65, 0.5))

        try:
            font = ImageFont.load_default()
        except Exception:
            font = None
        if font is not None:
            draw.text((int(width * 0.04), int(height * 0.82)),
                      f"SAMPLE-{variant_no} {width}x{height}", fill=(70, 70, 70), font=font)
            draw.text((int(width * 0.04), int(height * 0.90)),
                      plan.image_type.upper(), fill=(70, 70, 70), font=font)
        return img
