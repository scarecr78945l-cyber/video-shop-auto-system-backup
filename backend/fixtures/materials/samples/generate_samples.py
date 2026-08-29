"""M2 素材 fixtures 回归样本生成脚本（P2-1）。

可复现：直接运行 `python fixtures/materials/samples/generate_samples.py`，
输出到本目录（UTF-8 无 BOM；PNG 均为小体积合成图，零外网零登录态）：
- dup_a.png   复杂图（渐变 + 几何色块，低频结构丰富，phash 稳定）
- dup_b.png   dup_a 的缩放变体（同语义不同像素 → 与 dup_a phash 距离小，应判重）
- noise.png   随机噪声图（与 dup_a 距离大，应不判重）
- rel_a.png   相关性判定样本 A（合成「商品主图」结构）
- rel_b.png   相关性判定样本 B（同商品另一视角变体，供相关性门 fixtures 链路演示；
              真实相关性判定由 M3/C3 Qwen-VL 执行，真实 183 图资产待总控提取后放 real/）

用途：去重回归（image_phash 判定）、归档/相关性判定 fixtures 链路（R-M2-17）。
对齐 test_materials_dedup.py 的 _complex_image/_noise_image 构造口径。
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

HERE = Path(__file__).resolve().parent


def _complex(size: tuple[int, int] = (96, 96)) -> Image.Image:
    """渐变 + 几何色块（对齐 dedup 测试 _complex_image 口径）。"""
    img = Image.new("RGB", size)
    d = ImageDraw.Draw(img)
    for x in range(size[0]):
        c = int(255 * x / size[0])
        d.line([(x, 0), (x, size[1])], fill=(c, 120, 60))
    d.ellipse([20, 20, 60, 60], fill=(30, 30, 200))
    d.rectangle([50, 50, 90, 90], fill=(220, 220, 30))
    return img


def _noise(size: tuple[int, int] = (96, 96)) -> Image.Image:
    """随机噪声（与复杂图 phash 距离大，作「不同图」对照组）。"""
    return Image.effect_noise(size, 120).convert("RGB")


def main() -> None:
    dup_a = _complex()
    dup_b = dup_a.resize((80, 80)).resize((96, 96))  # 同语义缩放变体
    noise = _noise()
    rel_a = _complex((96, 96))
    rel_b = rel_a.transpose(Image.FLIP_LEFT_RIGHT).resize((90, 90)).resize((96, 96))

    targets = {
        "dup_a.png": dup_a,
        "dup_b.png": dup_b,
        "noise.png": noise,
        "rel_a.png": rel_a,
        "rel_b.png": rel_b,
    }
    for name, img in targets.items():
        img.save(str(HERE / name), format="PNG")
        print(f"wrote {HERE / name}")


if __name__ == "__main__":
    main()
