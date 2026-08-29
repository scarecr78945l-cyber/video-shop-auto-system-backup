"""M2 素材模块 · 归档能力测试（P2-5 旧系统 product-image-archive 思路落地）。

覆盖：
- derive_product_key：淘宝 id / 1688 offer / 普通 web URL（去 query）/ 空 URL；
- repo.list_assets 新增 source_url_contains 过滤（product 维度查询，向后兼容）；
- MaterialArchiver.list_product_assets：product 维度列出（空子串防全表误扫）；
- build_manifest：sha256 正确（对齐 P2-4 清单机制）；文件缺失 error 标注不中断；
- archive_product_assets：复制落盘 / 幂等（二次调用 skipped）/ content_mismatch
  不覆盖 / MANIFEST.json UTF-8 无 BOM 写入；
- P2-1 fixtures 回归样本去重：dup_a vs dup_b 判重；dup_a vs noise 不判重。
全程零外网零登录态零 ffmpeg（R-M2-17）；临时 SQLite + 临时存储目录。
"""

import hashlib
import json

import pytest

from materials.archive import ARCHIVE_TOOL_VERSION, MaterialArchiver, derive_product_key
from materials.dedup import hamming_distance, image_phash, is_duplicate
from materials.repo import AssetRepo
from materials.storage import LocalStorage


# ---------------------------------------------------------------- product_key 派生
@pytest.mark.parametrize(
    "url,expected",
    [
        ("https://item.taobao.com/item.htm?id=123456&spm=a21n57", "taobao:123456"),
        ("https://detail.tmall.com/item.htm?id=888&skuId=9", "taobao:888"),
        ("https://detail.1688.com/offer/123456789.html?spm=a26352", "1688:123456789"),
        ("https://detail.1688.com/offer/42.html", "1688:42"),
        ("https://example.com/shop/goods?from=1", "web:https://example.com/shop/goods"),
        ("https://example.com/shop/goods/", "web:https://example.com/shop/goods"),
        ("", "unknown"),
        (None, "unknown"),
    ],
)
def test_derive_product_key(url, expected):
    assert derive_product_key(url) == expected


# ---------------------------------------------------------------- fixtures 样本
@pytest.fixture()
def sample_dir(cfg_materials):
    return cfg_materials.fixtures_dir / "materials" / "samples"


def _sample_phash(sample_dir, name):
    return image_phash(str(sample_dir / name))


def test_fixture_samples_dup_regression(sample_dir):
    """P2-1：合成回归样本去重口径（dup_a vs dup_b 判重；dup_a vs noise 不判重）。"""
    a = _sample_phash(sample_dir, "dup_a.png")
    b = _sample_phash(sample_dir, "dup_b.png")
    noise = _sample_phash(sample_dir, "noise.png")
    assert is_duplicate(hamming_distance(a, b)) is True      # 同语义缩放变体 → 判重
    assert is_duplicate(hamming_distance(a, noise)) is False  # 噪声异图 → 不判重


# ---------------------------------------------------------------- 归档查询（repo 扩展）
def _put_asset(repo, storage, *, source_url, key, data, source_platform="淘宝", **over):
    storage.put(key, data)
    base = dict(
        asset_type="image",
        source_platform=source_platform,
        source_url=source_url,
        md5=hashlib.md5(data).hexdigest(),
        phash="f" * 16,  # 每资产唯一（调用方覆盖）
        file_path=key,
        size=len(data),
        compliance_status="passed",
    )
    base.update(over)
    return repo.create_asset(**base)


def make_archiver(db_materials, cfg_materials):
    storage = LocalStorage(cfg_materials.storage_dir)
    repo = AssetRepo(db_materials)
    return repo, storage, MaterialArchiver(repo, storage=storage, config=cfg_materials)


def test_repo_list_assets_source_url_contains(db_materials, cfg_materials):
    repo, storage, _ = make_archiver(db_materials, cfg_materials)
    _put_asset(repo, storage, source_url="https://item.taobao.com/item.htm?id=111&x=1",
               key="images/2025/a.png", data=b"aaa", phash="1" * 16)
    _put_asset(repo, storage, source_url="https://item.taobao.com/item.htm?id=222&x=1",
               key="images/2025/b.png", data=b"bbb", phash="2" * 16)
    _put_asset(repo, storage, source_url="https://detail.1688.com/offer/333.html",
               key="images/2025/c.png", data=b"ccc", phash="3" * 16, source_platform="1688")
    # product 维度：id=111 只命中第一条；其他过滤参数照常叠加
    assert [a["id"] for a in repo.list_assets(source_url_contains="id=111")] == [1]
    assert len(repo.list_assets(source_url_contains="offer/333", source_platform="1688")) == 1
    assert len(repo.list_assets(source_url_contains="offer/333", source_platform="淘宝")) == 0
    # 空子串不过滤（等价未传）；不带过滤全部返回
    assert len(repo.list_assets(source_url_contains="")) == 3


def test_list_product_assets_empty_guard(db_materials, cfg_materials):
    _, _, archiver = make_archiver(db_materials, cfg_materials)
    assert archiver.list_product_assets("") == []       # 空子串防全表误扫
    assert archiver.list_product_assets("   ") == []


# ---------------------------------------------------------------- 清单（build_manifest）
def test_build_manifest_sha256_and_missing_file(db_materials, cfg_materials):
    repo, storage, archiver = make_archiver(db_materials, cfg_materials)
    data = b"payload-bytes-123"
    aid = _put_asset(repo, storage, source_url="https://item.taobao.com/item.htm?id=9",
                     key="images/2025/x.png", data=data, phash="a" * 16)
    asset = repo.get_asset(aid)
    manifest = archiver.build_manifest([asset])
    assert manifest["tool"] == ARCHIVE_TOOL_VERSION
    assert manifest["entry_count"] == 1
    entry = manifest["entries"][0]
    assert entry["asset_id"] == aid
    assert entry["sha256"] == hashlib.sha256(data).hexdigest()
    # 文件缺失 → error 标注，不中断
    missing = dict(asset, file_path="images/2025/not-exist.png")
    m2 = archiver.build_manifest([missing])
    assert m2["entries"][0]["sha256"] is None
    assert m2["entries"][0]["error"].startswith("read_failed:")
    # 空列表 → 空清单不报错
    assert archiver.build_manifest([])["entry_count"] == 0


# ---------------------------------------------------------------- 归档（archive_product_assets）
def test_archive_product_assets_copy_idempotent_and_mismatch(db_materials, cfg_materials, tmp_path):
    repo, storage, archiver = make_archiver(db_materials, cfg_materials)
    a1 = _put_asset(repo, storage, source_url="https://item.taobao.com/item.htm?id=77",
                    key="images/2025/a.png", data=b"content-A", phash="b" * 16)
    a2 = _put_asset(repo, storage, source_url="https://item.taobao.com/item.htm?id=77&p=2",
                    key="images/2025/b.png", data=b"content-B", phash="c" * 16)
    assets = [repo.get_asset(a1), repo.get_asset(a2)]

    out = tmp_path / "archives"
    r1 = archiver.archive_product_assets(assets, out)
    assert r1["product_key"] == "taobao:77"
    assert r1["total"] == 2 and r1["archived"] == 2 and r1["skipped"] == 0 and r1["errors"] == []
    # Windows 路径安全：目录名冒号替换为 _（P2-5 集成测试修正）
    dest = tmp_path / "archives" / "taobao_77"
    assert (dest / "1.png").read_bytes() == b"content-A"
    assert (dest / "2.png").read_bytes() == b"content-B"
    assert (dest / "MANIFEST.json").exists()

    # 幂等：二次归档全部 skipped
    r2 = archiver.archive_product_assets(assets, out)
    assert r2["archived"] == 0 and r2["skipped"] == 2 and r2["errors"] == []

    # content_mismatch：目标文件被外部篡改 → error 不覆盖
    (dest / "1.png").write_bytes(b"tampered!")
    r3 = archiver.archive_product_assets(assets, out)
    assert r3["archived"] == 0 and r3["skipped"] == 1
    assert any(e["asset_id"] == a1 and e["error"] == "content_mismatch" for e in r3["errors"])
    assert (dest / "1.png").read_bytes() == b"tampered!"  # 未被覆盖

    # MANIFEST.json：UTF-8 无 BOM + 条目数正确
    raw = (dest / "MANIFEST.json").read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf")
    manifest = json.loads(raw.decode("utf-8"))
    assert manifest["entry_count"] == 2
    assert {e["asset_id"] for e in manifest["entries"]} == {a1, a2}

    # 空素材 → 不写清单
    r4 = archiver.archive_product_assets([], out, product_key="taobao:0")
    assert r4["total"] == 0 and r4["manifest_path"] is None


def test_archive_product_assets_missing_source(db_materials, cfg_materials, tmp_path):
    repo, storage, archiver = make_archiver(db_materials, cfg_materials)
    aid = _put_asset(repo, storage, source_url="https://detail.1688.com/offer/55.html",
                     key="images/2025/x.png", data=b"x", phash="d" * 16)
    asset = dict(repo.get_asset(aid), file_path="images/2025/gone.png")
    r = archiver.archive_product_assets([asset], tmp_path / "archives")
    assert r["product_key"] == "1688:55"
    assert r["archived"] == 0
    assert any(e["asset_id"] == aid and e["error"].startswith("source_read_failed") for e in r["errors"])
