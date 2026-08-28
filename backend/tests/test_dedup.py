"""去重测试：属性指纹 / phash 相似合并 / 商品库判重。"""

from sourcing.config import SourcingConfig
from sourcing.dedup import DedupEngine, attribute_fingerprint, hamming, phash_from_bytes
from sourcing.models import SourceItem


def item(title: str, board: str = "机会品", source: str = "opportunities",
         phash: str = "0f0f0f0f0f0f0f00") -> SourceItem:
    return SourceItem(
        source=source, board=board, platform_item_id=f"{source}:{board}:{title[:8]}",
        title=title, category="收纳整理", image_urls=["https://img.example.com/x.jpg"],
        raw={"image_phash": phash},
    )


def engine(library=None):
    cfg = SourcingConfig()
    return DedupEngine(cfg, library_has=lambda fp, ph: (library or {}).get(fp, False))


def test_attribute_fingerprint_stable_and_brand_insensitive():
    a = attribute_fingerprint("免打孔卫生间置物架 浴室收纳架", "收纳整理")
    b = attribute_fingerprint("免打孔卫生间置物架 浴室收纳架", "收纳整理")
    c = attribute_fingerprint("免打孔卫生间置物架 浴室收纳架", "厨房用品")
    assert a == b
    assert a != c


def test_phash_hamming():
    assert hamming(0b0000, 0b0001) == 1
    assert hamming(0b1111, 0b0000) == 4


def test_phash_from_bytes_deterministic():
    from PIL import Image
    import io

    buf = io.BytesIO()
    Image.new("RGB", (64, 64), (200, 30, 30)).save(buf, format="PNG")
    p1 = phash_from_bytes(buf.getvalue())
    buf.seek(0)
    p2 = phash_from_bytes(buf.getvalue())
    assert p1 == p2


def test_same_title_same_phash_merges_across_boards():
    items = [
        item("免打孔卫生间置物架", board="销量榜"),
        item("免打孔卫生间置物架", board="商品热销"),
    ]
    results = engine().process(items)
    assert len(results) == 1
    assert len(results[0].merged) == 2  # 来源稳定性合并


def test_library_duplicate_detected():
    items = [item("免打孔卫生间置物架")]
    fp = attribute_fingerprint("免打孔卫生间置物架", "收纳整理")
    results = engine(library={fp: True}).process(items)
    assert results[0].is_duplicate
    assert results[0].duplicate_of == fp


def test_phash_similar_merge_different_titles():
    """属性指纹不同但图片 phash 相似（汉明≤8）→ 视为同款合并。"""
    items = [
        item("卫生间置物架 A", phash="0f0f0f0f0f0f0f00"),
        item("浴室收纳架 B", phash="0f0f0f0f0f0f0f01"),  # 汉明距离 1
    ]
    results = engine().process(items)
    assert len(results) == 1
