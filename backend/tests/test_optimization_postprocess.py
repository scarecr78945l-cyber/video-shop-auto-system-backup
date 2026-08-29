"""REC-融合 P1-3：主图后处理避坑 fixtures 测试。

旧系统 image_generation 像素级函数迁移验证：
① strip_forbidden_text_regions 边缘裁剪（尺寸变小）
② crop_away_supplier_bands 裁水印条（低纹理带检测）
③ cover_suspicious_text_bands 遮瑕（边缘覆盖）
④ photo_saturation_score 评分（鲜艳图 > 灰图）
⑤ palette 主色提取（数量与类型正确）
⑥ 图片不存在抛 ImageNotFoundError
"""

import PIL.Image as PILImage

from optimization.images.postprocess import (
    ImageNotFoundError,
    cover_suspicious_text_bands,
    crop_away_supplier_bands,
    palette,
    photo_saturation_score,
    strip_forbidden_text_regions,
)


def _solid(w: int = 100, h: int = 100, rgb=(200, 60, 60)) -> PILImage.Image:
    img = PILImage.new("RGB", (w, h), rgb)
    return img


def test_strip_crops_edges():
    """① 边缘裁剪后尺寸变小。"""
    img = _solid(200, 200)
    out = strip_forbidden_text_regions(img)
    assert out.size == (168, 168)  # 每边去 8% = 16px


def test_crop_supplier_bands():
    """② 上下纯色带被裁掉。"""
    img = _solid(100, 100, (255, 255, 255))  # 全白 → 上下带均为低纹理
    out = crop_away_supplier_bands(img, band_ratio=0.05)
    assert out.size[1] < 100  # 高度变小（带被裁）


def test_crop_keeps_textured_image():
    """纯色带检测不误伤正常图（渐变/有内容图带不被裁）。"""
    img = PILImage.new("L", (100, 100))
    for x in range(100):
        for y in range(100):
            img.putpixel((x, y), (x * 2 + y) % 256)
    rgb = img.convert("RGB")
    out = crop_away_supplier_bands(rgb, band_ratio=0.05)
    assert out.size[1] == 100  # 未被裁


def test_cover_suspicious_bands():
    """③ 边缘覆盖为纯色块。"""
    img = _solid(100, 100, (10, 200, 10))
    out = cover_suspicious_text_bands(img)
    # 顶部像素被覆盖为白色
    assert out.getpixel((50, 0)) == (255, 255, 255)


def test_saturation_score():
    """④ 鲜艳图评分高于灰图。"""
    vivid = _solid(100, 100, (255, 0, 0))
    gray = _solid(100, 100, (128, 128, 128))
    assert photo_saturation_score(vivid) > photo_saturation_score(gray)


def test_palette_extracts_colors():
    """⑤ 主色提取：数量正确且为 RGB 三元组。"""
    img = _solid(100, 100, (30, 40, 50))
    colors = palette(img, n=3)
    assert 1 <= len(colors) <= 3
    for c in colors:
        assert len(c) == 3
        assert all(0 <= v <= 255 for v in c)


def test_missing_image_raises():
    """⑥ 图片不存在抛 ImageNotFoundError。"""
    try:
        strip_forbidden_text_regions("no/such/file.png")
        assert False, "应抛 ImageNotFoundError"
    except ImageNotFoundError:
        pass
