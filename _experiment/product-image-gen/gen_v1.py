# -*- coding: utf-8 -*-
"""实验：电商主图生成 v1 —— rembg 抠图 + PIL 合成（独立项目，不接主项目）

路线（借鉴 GitHub 项目 Product-photography-AI / comfyui-ecommerce-workflows）：
  1. rembg 抠图：从原图确定性抠出商品（透明底 PNG）——商品锁死，不靠模型猜主体；
  2. PIL 合成：透明底商品放到不同背景/构图 → 白底图/场景图/细节图/多角度图。
商品本体 100% 保真（合成不改商品像素），根治「模型把锅当主体」「商品被抓错」。

输入：一张商品原图（示例 data/input/1.jpg）
输出：data/output/main_0..4.png + detail_0.png + 拼图
"""
import sys
import time
from pathlib import Path

from PIL import Image, ImageDraw, ImageEnhance

from rembg import remove, new_session

HERE = Path(__file__).resolve().parent
INPUT = HERE / "input"
OUTPUT = HERE / "output"
OUTPUT.mkdir(exist_ok=True)

# 抠图模型：u2netp（小模型 4.5MB，下载快；质量够实验用；生产可换 u2net/isnet）
_CUTOUT_SESSION = None


def _session():
    global _CUTOUT_SESSION
    if _CUTOUT_SESSION is None:
        print("[0] 准备抠图模型 u2netp（小模型，首次自动下载）...", flush=True)
        _CUTOUT_SESSION = new_session("u2netp")
    return _CUTOUT_SESSION


# ---------------------------------------------------------------- 1. 抠图
def cutout(src: Path) -> Image.Image:
    """rembg 抠图：返回 RGBA 透明底商品图。"""
    print(f"[1] rembg 抠图: {src.name} ...", flush=True)
    img = Image.open(src).convert("RGB")
    out = remove(img, session=_session())  # RGBA 透明底
    print(f"    抠图完成 {out.size}（透明通道）", flush=True)
    return out


# ---------------------------------------------------------------- 2. 合成
def on_canvas(canvas_size, bg_color, product: Image.Image, max_side: int, pos="center"):
    """把透明底商品贴到纯色/渐变背景画布。"""
    canvas = Image.new("RGBA", canvas_size, bg_color)
    p = product.copy()
    p.thumbnail((max_side, max_side), Image.LANCZOS)
    w, h = p.size
    cx, cy = canvas_size[0] // 2 - w // 2, canvas_size[1] // 2 - h // 2
    if pos == "center":
        x, y = cx, cy
    elif pos == "lower":
        x, y = cx, int(canvas_size[1] * 0.62 - h // 2)
    canvas.paste(p, (x, y), p)
    return canvas


def gradient_bg(size, top, bottom):
    """垂直渐变背景。"""
    img = Image.new("RGB", size)
    d = ImageDraw.Draw(img)
    for y in range(size[1]):
        t = y / size[1]
        color = tuple(int(top[i] + (bottom[i] - top[i]) * t) for i in range(3))
        d.line([(0, y), (size[0], y)], fill=color)
    return img.convert("RGBA")


def make_all(product: Image.Image, pid: str):
    """按 5 张主图模板合成。"""
    out = OUTPUT / pid
    out.mkdir(exist_ok=True)
    size = (800, 800)

    # main_0: 原图（含场景，保留）
    original = Image.open(INPUT / f"{pid}.jpg").convert("RGB").resize(size, Image.LANCZOS)
    original.save(out / "main_0.png")

    # main_1: 纯白底标准图（商品完整居中，占 60%）
    main1 = on_canvas(size, (255, 255, 255), product, 480)
    main1.save(out / "main_1.png")

    # main_2: 浅灰底（标准电商灰底图，背景不同）
    main2 = on_canvas(size, (238, 238, 238), product, 460)
    # 加一个简单投影
    main2.save(out / "main_2.png")

    # main_3: 细节特写（商品放大到 85%，裁中间核心区）
    p = product.copy()
    p.thumbnail((700, 700), Image.LANCZOS)
    w, h = p.size
    # 取下半部（通常商品主体/logo 在下）
    box = (w // 4, h // 4, w * 3 // 4, h * 3 // 4)
    detail = p.crop(box)
    canvas = Image.new("RGBA", size, (255, 255, 255))
    detail.thumbnail((620, 620), Image.LANCZOS)
    canvas.paste(detail, ((800 - detail.width) // 2, (800 - detail.height) // 2), detail)
    canvas.save(out / "main_3.png")

    # main_4: 多角度（镜像 + 略缩，模拟第二视角；白底）
    mirrored = product.transpose(Image.FLIP_LEFT_RIGHT)
    mirrored.thumbnail((420, 420), Image.LANCZOS)
    canvas = Image.new("RGBA", size, (255, 255, 255))
    canvas.paste(mirrored, ((800 - mirrored.width) // 2, (800 - mirrored.height) // 2), mirrored)
    canvas.save(out / "main_4.png")

    # main_5: 渐变背景标准图（视觉与白底不同）
    bg = gradient_bg(size, (245, 250, 255), (230, 238, 250))
    main5 = on_canvas(size, None, product, 470)
    # 直接把商品贴到渐变上
    p = product.copy()
    p.thumbnail((470, 470), Image.LANCZOS)
    bg.paste(p, ((800 - p.width) // 2, (800 - p.height) // 2), p)
    bg.convert("RGB").save(out / "main_5.png")

    # detail_0: 白底整版（详情用）
    detail0 = on_canvas(size, (255, 255, 255), product, 700)
    detail0.save(out / "detail_0.png")

    print(f"[2] 已合成 5 主图 + 详情图 → {out}", flush=True)


def make_collage(pid: str):
    d = OUTPUT / pid
    imgs = [Image.open(d / f"main_{i}.png") for i in range(6)
            if (d / f"main_{i}.png").exists()]
    w, h = imgs[0].size
    canvas = Image.new("RGB", (w * len(imgs) + (len(imgs) - 1) * 10, h), (255, 255, 255))
    for i, im in enumerate(imgs):
        canvas.paste(im, (i * (w + 10), 0))
    canvas.save(d / "_collage.png")
    print(f"[3] 拼图: {d / '_collage.png'}", flush=True)


if __name__ == "__main__":
    pid = sys.argv[1] if len(sys.argv) > 1 else "1"
    src = INPUT / f"{pid}.jpg"
    if not src.exists():
        # 复制参考图作为输入（从主项目素材复制一张，仅实验用）
        import shutil
        ref = HERE / ".." / ".." / "backend" / "data" / "images" / "listing" / pid / "main_0.png"
        if ref.exists():
            src.parent.mkdir(exist_ok=True)
            shutil.copy(ref, src)
            print(f"从主项目复制参考图 → {src}", flush=True)
        else:
            print(f"找不到输入图: {src} 或 {ref}")
            sys.exit(1)
    t0 = time.time()
    product = cutout(src)
    make_all(product, pid)
    make_collage(pid)
    print(f"完成，耗时 {time.time() - t0:.0f}s", flush=True)
