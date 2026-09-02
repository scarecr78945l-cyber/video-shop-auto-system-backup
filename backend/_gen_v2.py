# -*- coding: utf-8 -*-
"""P-044-A 全量：5 变体强分离 prompt（通用词，参考图中商品），覆盖全部 pool 商品（用后即删）"""
import sys
import time
from pathlib import Path

from PIL import Image

from optimization.images.openai_provider import OpenAIImg2ImgProvider

OUT = Path("data/images/listing")

# 通用 prompt（不写死商品名，模型从参考图理解「图中商品」）
VARIANTS = {
    1: "将参考图中的商品单独提取为唯一主体，完全移除背景中其他所有物体（锅/手/水槽/桌面等），商品居中放在纯白背景上占画面60%，电商白底商品主图，无文字无水印，细节清晰，保留商品原貌",
    2: "将参考图中的商品放入对应真实使用场景：以商品实际用途为场景（如厨房/浴室/桌面），商品为清晰焦点，背景自然虚化，电商场景主图，无文字无水印，保留商品原貌",
    3: "将参考图中的商品核心细节局部放大特写，突出材质与做工细节，背景纯白或极简虚化，电商细节展示图，无文字无水印，保留商品原貌",
    4: "将参考图中的商品以不同角度展示：斜侧俯拍视角，商品完整可见，纯白背景，电商多角度主图，无文字无水印，保留商品原貌",
    5: "将参考图中的商品居中展示，底部加入简洁浅灰色阴影，纯白背景，电商标准主图，构图与白底图不同，无文字无水印，保留商品原貌",
}


def gen_product(pid: int, provider, ref: Path, only: set[int] | None = None):
    made = 0
    for no, prompt in VARIANTS.items():
        if only and no not in only:
            continue
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
    dirs = sorted([d for d in OUT.iterdir() if d.is_dir() and (d / "main_0.png").exists()])
    print(f"处理 {len(dirs)} 商品", flush=True)
    ok = 0
    for d in dirs:
        ok += gen_product(int(d.name), provider, d / "main_0.png")
        time.sleep(1)
    print(f"\n完成：新增/刷新 {ok} 张变体", flush=True)


if __name__ == "__main__":
    main()
