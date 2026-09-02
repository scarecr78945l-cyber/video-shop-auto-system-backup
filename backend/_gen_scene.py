# -*- coding: utf-8 -*-
"""P-044-D：优化场景方向（非重构抠图）——重生成 #1 main_2/3/4/5（用后即删）

用户指正：优化不是重构，单产品白底图没有吸引力。
修正：保留原场景（锅刷刷锅），增强动作/氛围/光影/卖点，画面有内容。
main_1 保留为唯一白底标准图。
"""
import time
from pathlib import Path

from PIL import Image

from optimization.images.openai_provider import OpenAIImg2ImgProvider

OUT = Path("data/images/listing")

NO_TEXT = (
    "画面中绝对禁止出现任何文字、横幅、水印、logo、图标、数字、标语、促销语、角标或文字框。"
)

PROMPTS = {
    2: (
        "参考图是不锈钢锅刷正在清洁蜂窝纹不粘炒锅。优化这张使用场景图："
        "保留锅刷在锅内刷洗的动作与生活感，增强厨房真实氛围（水槽/灶台/水汽），"
        "光线明亮自然，锅面反光有质感，主体清晰为焦点，背景虚化浅景深，"
        "构图饱满有吸引力，电商使用场景主图风格。"
        + NO_TEXT
    ),
    3: (
        "参考图是不锈钢锅刷清洁蜂窝纹不粘炒锅。优化成功效卖点图："
        "突出刷洗瞬间的视觉冲击——锅面残留油污与水珠、刷毛扫过的痕迹、"
        "蜂窝纹理清晰可见，不锈钢质感明亮，画面有动感与清洁前后对比暗示，"
        "主体占画面70%以上，光影对比强，电商卖点主图风格。"
        + NO_TEXT
    ),
    4: (
        "参考图是不锈钢锅刷清洁蜂窝纹不粘炒锅。优化成细节品质图："
        "特写锅刷刷毛的材质与不锈钢手柄的金属光泽，同时展现锅面蜂窝纹理的细节反光，"
        "微距质感，做工精细，背景极简虚化，电商细节品质主图风格。"
        + NO_TEXT
    ),
    5: (
        "参考图是不锈钢锅刷清洁蜂窝纹不粘炒锅。优化成对比展示图："
        "左侧展示使用前的油污锅面，右侧展示使用后光亮的蜂窝纹锅面，"
        "锅刷放在中间作为工具，画面干净利落，对比鲜明，白或浅色背景，"
        "电商对比展示主图风格。"
        + NO_TEXT
    ),
}


def main():
    provider = OpenAIImg2ImgProvider()
    pid = 1
    ref = OUT / str(pid) / "main_0.png"
    print(f"=== #{pid} 优化场景版 main_2/3/4/5 ===", flush=True)
    for no in [2, 3, 4, 5]:
        try:
            draft = provider.generate(
                reference_image=ref, prompt=PROMPTS[no],
                product_id=pid, image_type="main", variant_no=no,
            )
            src = Path(draft.file_path)
            img = Image.open(src).convert("RGB").resize((800, 800), Image.LANCZOS)
            img.save(OUT / str(pid) / f"main_{no}.png")
            src.unlink(missing_ok=True)
            print(f"  main_{no} ✓", flush=True)
        except Exception as e:
            print(f"  main_{no} ✗ {type(e).__name__} {str(e)[:80]}", flush=True)
        time.sleep(1)

    # 拼图
    imgs = [Image.open(OUT / str(pid) / f"main_{i}.png") for i in range(5)
            if (OUT / str(pid) / f"main_{i}.png").exists()]
    w, h = imgs[0].size
    canvas = Image.new("RGB", (w * 5 + 40, h), (255, 255, 255))
    for i, im in enumerate(imgs):
        canvas.paste(im, (i * (w + 10), 0))
    canvas.save("_collage_1_scene.png")
    print("拼图: _collage_1_scene.png", flush=True)


if __name__ == "__main__":
    main()
