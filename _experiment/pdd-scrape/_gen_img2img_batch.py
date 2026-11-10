# -*- coding: utf-8 -*-
"""img2img 批量扩量：为 48 个非淘宝商品生成 4 张 AI 主图变体（白底/场景/特写/角度）。

- 参考图 = listing/<pid>/main_0.png（真实源图）；main_0 保留。
- 覆盖 P-043 裁剪/叠字构图的 main_1..4（先删除，再生成，保证幂等）。
- 13 个淘宝真实图商品跳过（已是真实图）；4 个无源图商品跳过。
- 输出 main_1..4.png（800×800）。Key 走环境变量（不落盘）。
"""
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "backend"))
from optimization.images.openai_provider import OpenAIImg2ImgProvider  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent.parent
LISTING = ROOT / "backend" / "data" / "images" / "listing"
LOG = Path(__file__).resolve().parent / "img2img_batch.log"
RESULT = Path(__file__).resolve().parent / "img2img_batch.jsonl"

VARIANTS = {
    1: "将图片中的商品单独抠出，放在干净的纯白背景上，商品居中占画面60-70%，电商商品主图风格，顶部留白安全区，仅保留商品本体，去除所有文字水印和周围环境，产品细节清晰，无阴影之外的装饰",
    2: "将图片中的商品放在真实自然的使用场景中，背景虚化，突出商品主体，电商场景图风格，光线自然，商品清晰，去除所有文字水印",
    3: "将图片中的商品核心细节放大特写，突出材质和做工，电商细节展示图风格，主体清晰锐利，背景简洁，去除所有文字水印",
    4: "将图片中的商品以略俯视45度角度平视摆放，干净纯白背景，商品完整居中，电商商品图风格，柔和阴影，仅保留商品本体，去除所有文字水印",
}

# 跳过：已有 tb_main（淘宝真实图）的商品
SKIP = {int(d.name) for d in LISTING.iterdir()
        if d.is_dir() and d.name.isdigit() and list(d.glob("tb_main_*"))}

provider = OpenAIImg2ImgProvider()


def process(pid: int):
    d = LISTING / str(pid)
    ref = d / "main_0.png"
    if not ref.exists():
        return {"pid": pid, "ok": False, "error": "no ref"}
    # 清掉旧 P-043 构图（main_1..4），保留 main_0
    for i in range(1, 5):
        f = d / f"main_{i}.png"
        if f.exists():
            f.unlink()
    made = {}
    for no, prompt in VARIANTS.items():
        out_main = d / f"main_{no}.png"
        if out_main.exists():
            made[no] = "existing"
            continue
        try:
            draft = provider.generate(
                reference_image=ref, prompt=prompt,
                product_id=pid, image_type="main", variant_no=no,
            )
            from PIL import Image
            img = Image.open(draft.file_path).convert("RGB")
            img = img.resize((800, 800), Image.LANCZOS)
            img.save(out_main, format="PNG")
            os.remove(draft.file_path)
            made[no] = "ok"
        except Exception as e:
            made[no] = f"ERR {type(e).__name__}: {str(e)[:80]}"
        time.sleep(1)
    return {"pid": pid, "ok": len([v for v in made.values() if v == "ok"]) > 0, "made": made}


def main():
    pids = sys.argv[1].split(",") if len(sys.argv) > 1 else []
    targets = [int(p) for p in pids if p] if pids else sorted(
        int(d.name) for d in LISTING.iterdir()
        if d.is_dir() and d.name.isdigit() and int(d.name) not in SKIP)
    print(f"targets: {len(targets)} 个（跳过淘宝真实图 {len(SKIP)} 个）", flush=True)
    ok = fail = 0
    for pid in targets:
        print(f"=== #{pid} 生成 4 变体… ===", flush=True)
        rec = process(pid)
        with open(RESULT, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        if rec["ok"]:
            ok += 1
            print(f"   #{pid} ✓ {rec['made']}", flush=True)
        else:
            fail += 1
            print(f"   #{pid} ✗ {rec.get('error') or rec['made']}", flush=True)
        time.sleep(1)
    print(f"\n完成：ok={ok} fail={fail} → {RESULT}")


if __name__ == "__main__":
    main()
