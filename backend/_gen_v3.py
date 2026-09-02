# -*- coding: utf-8 -*-
"""P-044-C：提示词模板版重生成 #1 的 5 张主图（用后即删）

- 点名商品：从标题清洗提取（如"不锈钢锅刷"）+ 参考图可见特征（黑色刷毛）
- 排除背景物：参考图中已知的容器/场景（如"黑色的锅"）
- 固定禁令：禁止文字/横幅/logo/图标/数字/标语
"""
import sys
import time
from pathlib import Path

from PIL import Image

from optimization.images.openai_provider import OpenAIImg2ImgProvider

OUT = Path("data/images/listing")
PROBE = Path("data/images/_tmp")

NO_TEXT = (
    "画面中绝对禁止出现任何文字、横幅、水印、logo、图标、数字、标语、促销语、"
    "角标或文字框，只输出纯商品画面。"
)


def build_prompts(item: str, exclude_hint: str) -> dict[int, str]:
    return {
        1: (
            f"将参考图中的【{item}】作为唯一商品主体提取，"
            f"完全移除图中其他所有物体（{exclude_hint}），"
            "商品居中放在纯白背景上占画面60-70%，正面平视构图，"
            "电商白底商品主图，商品本体完全保真（形状/颜色/材质/LOGO不变），细节清晰高清。"
            + NO_TEXT
        ),
        2: (
            f"将参考图中的【{item}】放入其真实典型使用场景（厨房水槽旁/灶台），"
            f"商品为唯一清晰焦点，完全移除{exclude_hint}，背景自然虚化浅景深，"
            "场景元素简洁不超过2个，光线自然，商品本体完全保真，细节清晰高清。"
            + NO_TEXT
        ),
        3: (
            f"将参考图中的【{item}】的核心细节部位局部放大特写，"
            "占画面70%以上，突出材质纹理与做工，背景纯白或极简虚化，"
            "微距质感，商品本体完全保真，细节清晰高清。"
            + NO_TEXT
        ),
        4: (
            f"将参考图中的【{item}】以斜侧45°俯拍视角展示，商品完整可见，"
            f"完全移除{exclude_hint}，纯白背景，电商多角度主图（构图与白底图明显不同），"
            "商品本体完全保真，细节清晰高清。"
            + NO_TEXT
        ),
        5: (
            f"将参考图中的【{item}】居中展示，底部加简洁浅灰投影，"
            f"完全移除{exclude_hint}，纯白背景，略微仰视，电商标准主图（与白底图、多角度图构图均不同），"
            "商品本体完全保真，细节清晰高清。"
            + NO_TEXT
        ),
    }


def main():
    # #1 锅刷：商品名 + 背景物提示（参考图是"锅刷放在蜂窝纹不粘炒锅里"）
    item = "黑色刷毛+不锈钢手柄的锅刷"
    exclude_hint = "黑色的蜂窝纹不粘炒锅、手、水槽、桌面、其他物体"
    prompts = build_prompts(item, exclude_hint)

    provider = OpenAIImg2ImgProvider()
    pid = 1
    ref = OUT / str(pid) / "main_0.png"
    print(f"=== #{pid} 提示词模板版 5 变体 ===", flush=True)
    for no in [1, 2, 3, 4, 5]:
        try:
            draft = provider.generate(
                reference_image=ref, prompt=prompts[no],
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

    # 拼图 + dhash
    imgs = [Image.open(OUT / str(pid) / f"main_{i}.png") for i in range(5)
            if (OUT / str(pid) / f"main_{i}.png").exists()]
    w, h = imgs[0].size
    canvas = Image.new("RGB", (w * 5 + 40, h), (255, 255, 255))
    for i, im in enumerate(imgs):
        canvas.paste(im, (i * (w + 10), 0))
    out = PROBE / "collage_1_v3.png"
    canvas.save(out)
    print(f"拼图: {out}", flush=True)


if __name__ == "__main__":
    main()
