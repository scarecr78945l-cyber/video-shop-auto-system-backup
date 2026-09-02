# -*- coding: utf-8 -*-
"""P-045 接入：把淘宝以图搜款下载的高清同款图（tb_main_*）规范化为主项目
listing/<pid>/main_0..4.png（800×800 1:1 PNG），替换 P-043/P-044 构图变体。
无 tb_main 的商品保留原图并登记。运行后跑 _verify_gate_65.py 复核门禁。

用法：python _integrate_real_images.py [--dry-run]
"""
import argparse
import sys
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent.parent
LISTING = ROOT / "backend" / "data" / "images" / "listing"

Image.MAX_IMAGE_PIXELS = None


MIN_EDGE = 400  # 真实图最小边长（过滤 210px 图标等低质图）


def norm_edge(src: Path) -> int:
    try:
        return min(Image.open(src).size)
    except Exception:
        return 0


def to_square_png(src: Path, dest: Path, size: int = 800):
    im = Image.open(src).convert("RGB")  # PIL 按内容嗅探格式（alicdn 常返回 webp 字节）
    w, h = im.size
    side = min(w, h)
    left = (w - side) // 2
    top = (h - side) // 2
    im = im.crop((left, top, left + side, top + side)).resize((size, size), Image.LANCZOS)
    im.save(dest, "PNG")
    return dest


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    promoted = []     # (pid, real_count, total_main)
    untouched = []    # pid with no usable real image
    for d in sorted([x for x in LISTING.iterdir() if x.is_dir() and x.name.isdigit()],
                    key=lambda x: int(x.name)):
        pid = int(d.name)
        real = [f for f in d.glob("tb_main_*") if norm_edge(f) >= MIN_EDGE]
        real_sorted = sorted(real, key=lambda f: f.stat().st_size, reverse=True)
        if not real_sorted:
            untouched.append(pid)
            continue
        chosen = real_sorted[:5]
        if args.dry_run:
            promoted.append((pid, len(chosen), 5))
            continue
        written = 0
        for i, f in enumerate(chosen):
            to_square_png(f, d / f"main_{i}.png")
            written += 1
        # 不足 5 张：用旧构图 main_* 补齐（仍满足门禁 5 张）
        for i in range(written, 5):
            old = d / f"main_{i}.png"
            if not old.exists():
                old = d / "main_0.png"  # 最后一招，仅极少数情况
            if old.exists():
                to_square_png(old, d / f"main_{i}.png")
        # 详情图：保留既有 detail_0.png；缺失则用最大真实图
        if not (d / "detail_0.png").exists():
            to_square_png(real_sorted[0], d / "detail_0.png")
        promoted.append((pid, written, 5))

    real_count = sum(p[1] for p in promoted)
    print(f"提升真实主图商品: {len(promoted)} 个，共写入真实主图 {real_count} 张（每商品补齐至 5 张）")
    for pid, n, _ in promoted[:20]:
        print(f"  #{pid}: 真实 {n} 张")
    if len(promoted) > 20:
        print(f"  …共 {len(promoted)} 个商品")
    if untouched:
        print(f"无可用真实图(保持原构图): {untouched}")


if __name__ == "__main__":
    main()
