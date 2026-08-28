"""临时探测脚本（验证 phash 距离后即删，不入交付）。"""
import io
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PIL import Image, ImageDraw

from materials.dedup import hamming_distance, image_phash


def complex_v(size=(128, 128)):
    img = Image.new("RGB", size)
    d = ImageDraw.Draw(img)
    for x in range(size[0]):
        c = int(255 * x / size[0])
        d.line([(x, 0), (x, size[1])], fill=(c, 120, 60))
    d.ellipse([20, 20, 80, 80], fill=(30, 30, 200))
    d.rectangle([60, 60, 110, 110], fill=(220, 220, 30))
    return img


def complex_h(size=(128, 128)):
    img = Image.new("RGB", size)
    d = ImageDraw.Draw(img)
    for y in range(size[1]):
        c = int(255 * y / size[1])
        d.line([(0, y), (size[0], y)], fill=(c, 120, 60))
    d.ellipse([20, 20, 80, 80], fill=(30, 30, 200))
    d.rectangle([60, 60, 110, 110], fill=(220, 220, 30))
    return img


def to_bytes(img, fmt, **kw):
    buf = io.BytesIO()
    img.save(buf, format=fmt, **kw)
    return buf.getvalue()


base = complex_v()
png = to_bytes(base, "PNG")
ph = image_phash(Image.open(io.BytesIO(png)))
print("png phash:", ph)
for name, data in [
    ("jpeg85", to_bytes(base, "JPEG", quality=85)),
    ("jpeg30", to_bytes(base, "JPEG", quality=30)),
    ("scale64", to_bytes(base.resize((64, 64)), "PNG")),
    ("scale256", to_bytes(base.resize((256, 256)), "PNG")),
]:
    d = hamming_distance(ph, image_phash(Image.open(io.BytesIO(data))))
    print(f"{name}: dist={d} dup={d <= 8}")

other = image_phash(Image.open(io.BytesIO(to_bytes(complex_h(), "PNG"))))
d2 = hamming_distance(ph, other)
print(f"horizontal-gradient variant: dist={d2} dup={d2 <= 8}")

solid = Image.new("RGB", (64, 64), (200, 30, 30))
print("solid phash:", image_phash(solid))

# path vs PIL consistency
import tempfile
p = os.path.join(tempfile.mkdtemp(), "a.png")
base.save(p, format="PNG")
print("path==pil:", image_phash(p) == image_phash(base))
