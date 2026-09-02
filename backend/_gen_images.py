# -*- coding: utf-8 -*-
"""P-044 真实生图：img2img 生成商品主图变体（白底/场景/特写），覆盖 P-043 同图缺陷。

参考图 = data/images/listing/<pid>/main_0.png（已下载的真实商品图）。
变体：
  main_1 白底居中（抠商品放纯白背景，电商标准图）
  main_2 使用场景图（真实场景虚化）
  main_3 细节特写（放大核心卖点）
main_0 保留原图；main_4/详情图由后处理补（角标/灰底等）。
用法：python -X utf8 _gen_images.py [--limit N] [--start I]
"""
import sys
import time
from pathlib import Path

from PIL import Image

from optimization.images.openai_provider import OpenAIImg2ImgProvider

OUT = Path("data/images/listing")

LIMIT = 5
START = 0
if "--limit" in sys.argv:
    LIMIT = int(sys.argv[sys.argv.index("--limit") + 1])
if "--start" in sys.argv:
    START = int(sys.argv[sys.argv.index("--start") + 1])

VARIANTS = {
    1: "将图片中的商品单独抠出，放在干净的纯白背景上，商品居中占画面60-70%，电商商品主图风格，顶部留白安全区，仅保留商品本体，去除所有文字水印和周围环境，产品细节清晰，无阴影之外的装饰",
    2: "将图片中的商品放在真实自然的使用场景中，背景虚化，突出商品主体，电商场景图风格，光线自然，商品清晰，去除所有文字水印",
    3: "将图片中的商品核心细节放大特写，突出材质和做工，电商细节展示图风格，主体清晰锐利，背景简洁，去除所有文字水印",
}

provider = OpenAIImg2ImgProvider()


def process(pid: int):
    ref = OUT / str(pid) / "main_0.png"
    if not ref.exists():
        print(f"#{pid} 无参考图，跳过")
        return 0
    made = 0
    for no, prompt in VARIANTS.items():
        out_main = OUT / str(pid) / f"main_{no}.png"
        if out_main.exists():  # 幂等：已有则跳过
            made += 1
            continue
        try:
            draft = provider.generate(
                reference_image=ref, prompt=prompt,
                product_id=pid, image_type="main", variant_no=no,
            )
            # 模型输出 1254x1254 → 缩放到 800x800 1:1（统一规格，intake 消费）
            img = Image.open(draft.file_path).convert("RGB")
            img = img.resize((800, 800), Image.LANCZOS)
            img.save(out_main, format="PNG")
            import os
            os.remove(draft.file_path)
            print(f"  #{pid} main_{no} ✓ ({time.time():.0f}s)")
            made += 1
        except Exception as e:
            print(f"  #{pid} main_{no} ✗ {type(e).__name__} {str(e)[:80]}")
        time.sleep(1)  # 请求间隔（防限流）
    return made


def main():
    dirs = sorted([d for d in OUT.iterdir() if d.is_dir() and (d / "main_0.png").exists()])[START:START+LIMIT]
    print(f"处理 {len(dirs)} 个商品（{START}~{START+len(dirs)}）")
    ok = 0
    for d in dirs:
        ok += process(int(d.name))
        time.sleep(1)
    print(f"\n完成：生成 {ok} 张变体（{len(dirs)} 商品）")


if __name__ == "__main__":
    main()
