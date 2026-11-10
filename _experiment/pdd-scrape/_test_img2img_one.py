# -*- coding: utf-8 -*-
"""img2img 单商品验证：pid 47 白底变体（验证端点/Key/输出链路）。"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "backend"))
from optimization.images.openai_provider import OpenAIImg2ImgProvider  # noqa: E402

pid = sys.argv[1] if len(sys.argv) > 1 else "47"
OUT = Path("backend/data/images/listing") / pid
ref = OUT / "main_0.png"
print("ref:", ref, ref.exists())
provider = OpenAIImg2ImgProvider()
print("base:", provider.base_url, "| model:", provider.model, "| key set:", bool(provider.key))
draft = provider.generate(
    reference_image=ref,
    prompt="将图片中的商品单独抠出，放在干净的纯白背景上，商品居中占画面60-70%，电商商品主图风格，顶部留白安全区，仅保留商品本体，去除所有文字水印和周围环境，产品细节清晰，无阴影之外的装饰",
    product_id=pid, image_type="main", variant_no=99,
)
print("draft:", draft.file_path)
from PIL import Image
im = Image.open(draft.file_path)
print("size:", im.size)
im.resize((800, 800), Image.LANCZOS).save(OUT / "_validate_white.png", format="PNG")
print("saved", OUT / "_validate_white.png")
