# -*- coding: utf-8 -*-
"""P-044-B 验收：严格禁令版 5 变体生成（只跑 #1，用户验收通过后全量）

生图要求（定稿）：
- 5 张主图视觉明显不同（白底单品/场景/细节特写/多角度/标准图）
- 绝对禁止模型加任何文字/横幅/水印/logo/图标/数字/标语（第一红线）
- 商品本体保真
"""
import sys
import time
from pathlib import Path

from PIL import Image

from optimization.images.openai_provider import OpenAIImg2ImgProvider

OUT = Path("data/images/listing")
PROBE = Path("data/images/_tmp")

NO_TEXT = (
    "，画面中绝对禁止出现任何文字、横幅、水印、logo、图标、数字、标语、促销语、"
    "角标或文字框，只输出纯商品画面"
)

VARIANTS = {
    1: "将参考图中的商品单独提取为唯一主体，完全移除背景中其他所有物体（锅/手/水槽/桌面等），"
       "商品居中放在纯白背景上占画面60%，电商白底商品主图，保留商品原貌" + NO_TEXT,
    2: "将参考图中的商品放入对应真实使用场景（按商品实际用途，如厨房/浴室/桌面），"
       "商品为清晰焦点，背景自然虚化，电商场景主图，保留商品原貌" + NO_TEXT,
    3: "将参考图中的商品核心细节局部放大特写，突出材质与做工细节，"
       "背景纯白或极简虚化，电商细节展示图，保留商品原貌" + NO_TEXT,
    4: "将参考图中的商品以斜侧俯拍的不同角度展示，商品完整可见，纯白背景，"
       "电商多角度主图，保留商品原貌" + NO_TEXT,
    5: "将参考图中的商品居中展示，底部加简洁浅灰色阴影，纯白背景，"
       "电商标准主图（构图与白底图不同），保留商品原貌" + NO_TEXT,
}


def gen_product(pid: int, provider, ref: Path):
    made = 0
    for no, prompt in VARIANTS.items():
        try:
            draft = provider.generate(
                reference_image=ref, prompt=prompt,
                product_id=pid, image_type="main", variant_no=no,
            )
            src = Path(draft.file_path)
            img = Image.open(src).convert("RGB").resize((800, 800), Image.LANCZOS)
            img.save(OUT / str(pid) / f"main_{no}.png")
            src.unlink(missing_ok=True)
            made += 1
            print(f"  #{pid} main_{no} ✓", flush=True)
        except Exception as e:
            print(f"  #{pid} main_{no} ✗ {type(e).__name__} {str(e)[:80]}", flush=True)
        time.sleep(1)
    return made


def main():
    provider = OpenAIImg2ImgProvider()
    pid = 1
    ref = OUT / str(pid) / "main_0.png"
    print(f"=== 验收生成 #{pid} 5 变体 ===")
    gen_product(pid, provider, ref)
    # 拼图
    imgs = [Image.open(OUT / str(pid) / f"main_{i}.png") for i in range(5)
            if (OUT / str(pid) / f"main_{i}.png").exists()]
    w, h = imgs[0].size
    canvas = Image.new("RGB", (w * 5 + 40, h), (255, 255, 255))
    for i, im in enumerate(imgs):
        canvas.paste(im, (i * (w + 10), 0))
    out = PROBE / f"collage_{pid}_strict.png"
    canvas.save(out)
    print(f"拼图: {out}")


if __name__ == "__main__":
    main()
