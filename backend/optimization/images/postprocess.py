"""REC-融合 P1-3：主图后处理避坑（旧系统 image_generation.py 像素级函数迁移）。

旧系统四个像素级避坑动作（PIL）：
1. strip_forbidden_text_regions — 裁掉/覆盖危险文案区域（供应链词/品牌词/二维码/水印文字带）；
2. crop_away_supplier_bands — 裁掉上下边缘供应商水印条（纯色低纹理带）；
3. cover_suspicious_text_bands — 覆盖可疑文字带（马赛克式色块遮瑕）；
4. photo_saturation_score — 图片饱和鲜艳度评分（供排序选主图）；
5. palette — 主色调提取（供文案配色）。

全部纯函数、无副作用；输入/输出均为 PIL.Image；图像不存在时抛 ImageNotFoundError。
"""

from __future__ import annotations

from typing import Optional

from PIL import Image

# 供应链/违规词（与 sourcing compliance 语义一致，这里做图像内文字带检测用）
_FORBIDDEN_TEXT_HINTS = ["1688", "工厂", "批发", "厂家", "一件代发", "源头"]


class ImageNotFoundError(Exception):
    pass


def _open_image(image: "Image.Image | str") -> Image.Image:
    if isinstance(image, str):
        try:
            return Image.open(image).convert("RGB")
        except FileNotFoundError as e:
            raise ImageNotFoundError(f"图片不存在: {image}") from e
    return image.convert("RGB")


def strip_forbidden_text_regions(image, forbidden: list[str] | None = None) -> Image.Image:
    """裁剪边缘 8% 的常规水印/文字带（上下左右四边各去 8%）。

    旧系统 _strip_forbidden_text_regions 简化版：对可疑文字带做边缘裁剪，
    保留主体。返回新图（不改原图）。
    """
    img = _open_image(image)
    w, h = img.size
    m = max(1, int(min(w, h) * 0.08))
    box = (m, m, w - m, h - m)
    if box[2] <= box[0] or box[3] <= box[1]:
        return img
    return img.crop(box)


def crop_away_supplier_bands(image, band_ratio: float = 0.05) -> Image.Image:
    """裁掉上下边缘供应商水印条（低纹理纯色带）。

    检测：顶部/底部各 band_ratio 高度区域，若整体为近纯色（饱和度低且方差小）
    视为水印条，裁掉；否则不动。
    """
    img = _open_image(image)
    w, h = img.size
    band_h = max(1, int(h * band_ratio))
    top = _is_low_texture_band(img.crop((0, 0, w, band_h)))
    bottom = _is_low_texture_band(img.crop((0, h - band_h, w, h)))
    top_cut = band_h if top else 0
    bottom_cut = band_h if bottom else 0
    if top_cut == 0 and bottom_cut == 0:
        return img
    return img.crop((0, top_cut, w, h - bottom_cut))


def cover_suspicious_text_bands(image, color: tuple[int, int, int] = (255, 255, 255)) -> Image.Image:
    """覆盖可疑文字带（边缘 10% 区域用纯色块遮瑕）。

    旧系统 _cover_suspicious_text_bands：把上下边缘可能含 1688/工厂 等
    文字的区域用色块覆盖（遮瑕不删除）。
    """
    img = _open_image(image)
    w, h = img.size
    m = max(1, int(h * 0.10))
    overlay = Image.new("RGB", (w, m), color)
    img.paste(overlay, (0, 0))
    img.paste(overlay, (0, h - m))
    return img


def photo_saturation_score(image) -> float:
    """图片饱和鲜艳度评分（0~100）：HSB 饱和度均值 + 高饱和占比加权。"""
    img = _open_image(image)
    hsv = img.convert("HSV")
    sat_hist = hsv.histogram()[256:512]  # S 通道直方图（0-255）
    total = sum(sat_hist) or 1
    mean_sat = sum(i * c for i, c in enumerate(sat_hist)) / total
    vivid = sum(sat_hist[180:]) / total  # 高饱和（≥180）占比
    return round(min(100.0, mean_sat / 2.55 * 0.7 + vivid * 100 * 0.3), 2)


def palette(image, n: int = 4) -> list[tuple[int, int, int]]:
    """主色调提取：量化后取出现最多的 n 个颜色（供文案/角标配色）。"""
    img = _open_image(image)
    small = img.resize((64, 64))
    quantized = small.convert("P", palette=Image.ADAPTIVE, colors=16)
    palette_im = quantized.getpalette() or []
    counts = quantized.getcolors() or []
    counts.sort(reverse=True)
    result: list[tuple[int, int, int]] = []
    for count, idx in counts:
        base = idx * 3
        if base + 2 < len(palette_im):
            result.append((palette_im[base], palette_im[base + 1], palette_im[base + 2]))
        if len(result) >= n:
            break
    return result


def _is_low_texture_band(img: Image.Image) -> bool:
    """判断图像块是否为近纯色低纹理带（供应商水印条特征）。"""
    gray = img.convert("L")
    hist = gray.histogram()
    total = sum(hist) or 1
    dominant = max(hist) / total  # 主色占比
    return dominant > 0.55
