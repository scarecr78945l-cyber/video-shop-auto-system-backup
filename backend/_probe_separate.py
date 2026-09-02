# -*- coding: utf-8 -*-
"""P-044-A：强分离 prompt 测试——只保留商品单品，去场景/锅/手，纯白底（用后即删）"""
import os
from pathlib import Path

from PIL import Image

from optimization.images.openai_provider import OpenAIImg2ImgProvider

OUT = Path("data/images/listing")
PROBE = Path("data/images/_tmp")

PROMPTS = {
    "a1": (
        "图中只有一个不锈钢锅刷单品，位于黑色的锅内。"
        "请把不锈钢锅刷（金属手柄+黑色刷毛）单独提取出来，作为唯一的商品主体，"
        "完全去除黑色的锅、手、水槽、桌面以及所有其他物体和环境。"
        "主体居中放在纯白色背景上，占画面60%，电商白底商品图，"
        "细节清晰，无阴影之外的装饰，无文字无水印。"
    ),
    "a2": (
        "只保留图片中央的不锈钢刷，剪掉其他一切（黑色锅、手、背景全部移除），"
        "纯白色背景，商品单独居中，高清产品展示图。"
    ),
}

provider = OpenAIImg2ImgProvider()
pid = 1
ref = OUT / str(pid) / "main_0.png"

for name, prompt in PROMPTS.items():
    print(f"=== prompt {name} ===")
    try:
        draft = provider.generate(
            reference_image=ref, prompt=prompt,
            product_id=pid, image_type="probe", variant_no=0,
        )
        src = Path(draft.file_path)
        img = Image.open(src).convert("RGB").resize((800, 800), Image.LANCZOS)
        out = PROBE / f"probe_{name}.png"
        img.save(out)
        src.unlink(missing_ok=True)
        print(f"  已生成 {out}")
    except Exception as e:
        print(f"  ✗ {type(e).__name__} {str(e)[:100]}")
