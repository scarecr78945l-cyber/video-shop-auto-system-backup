# -*- coding: utf-8 -*-
"""补 #1 main_4/5 严格版（用后即删）"""
import time
from pathlib import Path

from PIL import Image

from optimization.images.openai_provider import OpenAIImg2ImgProvider

OUT = Path("data/images/listing")
NO_TEXT = (
    "，画面中绝对禁止出现任何文字、横幅、水印、logo、图标、数字、标语、促销语、"
    "角标或文字框，只输出纯商品画面"
)
P4 = "将参考图中的商品以斜侧俯拍的不同角度展示，商品完整可见，纯白背景，电商多角度主图，保留商品原貌" + NO_TEXT
P5 = "将参考图中的商品居中展示，底部加简洁浅灰色阴影，纯白背景，电商标准主图（构图与白底图不同），保留商品原貌" + NO_TEXT

provider = OpenAIImg2ImgProvider()
pid = 1
ref = OUT / str(pid) / "main_0.png"

for no, prompt in [(4, P4), (5, P5)]:
    try:
        draft = provider.generate(
            reference_image=ref, prompt=prompt,
            product_id=pid, image_type="main", variant_no=no,
        )
        src = Path(draft.file_path)
        img = Image.open(src).convert("RGB").resize((800, 800), Image.LANCZOS)
        img.save(OUT / str(pid) / f"main_{no}.png")
        src.unlink(missing_ok=True)
        print(f"main_{no} ✓")
    except Exception as e:
        print(f"main_{no} ✗ {type(e).__name__} {str(e)[:80]}")
    time.sleep(1)
