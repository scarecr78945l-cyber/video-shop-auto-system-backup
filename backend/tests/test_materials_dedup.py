"""M2 素材模块 · 双去重器测试（R-M2-11）。

覆盖：
- MD5：同文件两次一致 / 分块实现与参考一致 / 不同文件不同；
- 图片 phash：与 sourcing/dedup.py 口径逐位一致；同图不同压缩/缩放 → 距离 ≤ 阈值判重；
  随机噪声异图 → 不判重；阈值 8/9 边界；
- 视频关键帧：MockFrameExtractor 注入固定帧 → phash 正确；FFmpegFrameExtractor
  在 ffmpeg 缺失时 raise 且错误信息清晰（skipif 保护）；全程零真实 ffmpeg 依赖；
- DedupService 集成：临时 SQLite（cfg_materials/db_materials fixtures）注册指纹后
  二次检查判重复；claim_and_register 冲突抛 DuplicateAssetError；并发认领语义。
"""

import hashlib
import json
import os
import shutil

import pytest
from PIL import Image, ImageDraw
from sqlalchemy import select

from materials import tables as T
from materials.dedup import (
    DedupService,
    FFmpegFrameExtractor,
    FFmpegNotFoundError,
    MockFrameExtractor,
    compute_md5,
    hamming_distance,
    image_phash,
    is_duplicate,
    parse_video_phash_value,
    video_phash,
)
from materials.models import iso_now
from materials.repo import AssetRepo, DuplicateAssetError


# ---------------------------------------------------------------- 测试图生成
def _complex_image(size=(128, 128)) -> Image.Image:
    """低频结构丰富的测试图（渐变 + 几何色块），跨压缩/缩放 phash 稳定（实测距离 0）。"""
    img = Image.new("RGB", size)
    d = ImageDraw.Draw(img)
    for x in range(size[0]):
        c = int(255 * x / size[0])
        d.line([(x, 0), (x, size[1])], fill=(c, 120, 60))
    d.ellipse([20, 20, 80, 80], fill=(30, 30, 200))
    d.rectangle([60, 60, 110, 110], fill=(220, 220, 30))
    return img


def _noise_image(size=(128, 128)) -> Image.Image:
    """随机噪声图：与复杂图 phash 距离实测 ~30（> 8），作「不同图」对照组。"""
    return Image.effect_noise(size, 120).convert("RGB")


def _save(img: Image.Image, path, fmt="PNG", **kw) -> str:
    img.save(str(path), format=fmt, **kw)
    return str(path)


def _mock_frames() -> list[Image.Image]:
    return [_complex_image((64, 64)), _complex_image((80, 80)), _complex_image((96, 96))]


def _flip_bits(hex_str: str, k: int) -> str:
    """翻转 16 位 hex 串的低 k 个 bit → 与原串汉明距离恰为 k。"""
    v = int(hex_str, 16)
    for i in range(k):
        v ^= 1 << i
    return f"{v:016x}"


def base_image_like(**over) -> dict:
    data = dict(
        asset_type="image",
        source_platform="抖音",
        source_url="https://example.com/i.jpg",
        source_author="达人B",
        md5="0" * 32,
        phash="0" * 16,
        file_path="images/2025/x.png",
        size=1024,
    )
    data.update(over)
    return data


def base_video_like(**over) -> dict:
    data = dict(
        asset_type="video",
        source_platform="视频号",
        source_url="https://example.com/v.mp4",
        source_author="达人A",
        md5="1" * 32,
        phash="[]",
        file_path="videos/2025/x.mp4",
        duration=15,
        resolution="720x1280",
        size=2048,
    )
    data.update(over)
    return data


# ---------------------------------------------------------------- MD5
def test_compute_md5_stable_lowercase_hex(tmp_path):
    p = tmp_path / "a.bin"
    p.write_bytes(b"materials dedup md5 payload" * 100)
    m1 = compute_md5(str(p))
    m2 = compute_md5(str(p))
    assert m1 == m2                                   # 同文件两次一致
    assert len(m1) == 32
    assert m1 == m1.lower()                           # 32 位小写 hex
    assert set(m1) <= set("0123456789abcdef")


def test_compute_md5_chunked_matches_reference(tmp_path):
    # 跨 1 MiB 块边界的大文件：分块实现与一次性 hashlib 参考一致
    big = tmp_path / "big.bin"
    data = os.urandom((1 << 20) + 17)
    big.write_bytes(data)
    assert compute_md5(str(big)) == hashlib.md5(data).hexdigest()


def test_compute_md5_different_files_differ(tmp_path):
    a = tmp_path / "a.bin"
    a.write_bytes(b"payload A")
    b = tmp_path / "b.bin"
    b.write_bytes(b"payload B")
    assert compute_md5(str(a)) != compute_md5(str(b))


# ---------------------------------------------------------------- 汉明距离 / 阈值
def test_hamming_distance_bitwise():
    assert hamming_distance("0f0f0f0f0f0f0f00", "0f0f0f0f0f0f0f00") == 0
    assert hamming_distance("0f0f0f0f0f0f0f00", "0f0f0f0f0f0f0f01") == 1
    assert hamming_distance("ffffffffffffffff", "0000000000000000") == 64
    # 兼容带帧标识前缀 "{index}:{hex}"
    assert hamming_distance("0:0f0f0f0f0f0f0f00", "0f0f0f0f0f0f0f01") == 1


def test_is_duplicate_threshold_boundary():
    # 默认阈值 8（config.dedup.phash_hamming_threshold）：距离 8 判重、9 不判重
    assert is_duplicate(8) is True
    assert is_duplicate(9) is False
    assert is_duplicate(0) is True
    assert is_duplicate(7) is True
    # 显式覆盖阈值
    assert is_duplicate(4, threshold=4) is True
    assert is_duplicate(5, threshold=4) is False


# ---------------------------------------------------------------- 图片 phash
def test_image_phash_matches_sourcing_implementation(tmp_path):
    from sourcing.dedup import phash_from_bytes, phash_hex

    p = _save(_complex_image(), tmp_path / "a.png")
    expected = phash_hex(phash_from_bytes(open(p, "rb").read()))
    assert image_phash(p) == expected                       # 路径输入与 sourcing 口径逐位一致
    assert image_phash(_complex_image()) == expected        # PIL 输入同一管线（PNG 无损字节）
    assert len(expected) == 16


def test_image_phash_same_image_variants_duplicate(tmp_path):
    base = _complex_image()
    variants = [
        _save(base, tmp_path / "a.png"),
        _save(base, tmp_path / "b.jpg", fmt="JPEG", quality=85),
        _save(base, tmp_path / "c.jpg", fmt="JPEG", quality=30),
        _save(base.resize((64, 64)), tmp_path / "d.png"),
        _save(base.resize((256, 256)), tmp_path / "e.png"),
    ]
    ph = image_phash(variants[0])
    for v in variants[1:]:
        d = hamming_distance(ph, image_phash(v))
        assert d <= 8, f"同图变体距离应 ≤ 8，实际 {d}"
        assert is_duplicate(d) is True


def test_image_phash_different_image_not_duplicate(tmp_path):
    p1 = _save(_complex_image(), tmp_path / "a.png")
    p2 = _save(_noise_image(), tmp_path / "noise.png")
    d = hamming_distance(image_phash(p1), image_phash(p2))
    assert d > 8, f"异图距离应 > 8，实际 {d}"
    assert is_duplicate(d) is False


# ---------------------------------------------------------------- 视频关键帧（零真实 ffmpeg）
def test_video_phash_with_mock_extractor(tmp_path):
    frames = _mock_frames()
    ex = MockFrameExtractor(frames)
    vp = video_phash(str(tmp_path / "fake.mp4"), ex)
    expected = [image_phash(f) for f in frames]
    assert vp["frames"] == expected                        # 逐帧 phash 正确
    assert vp["combined"] == json.dumps(expected, ensure_ascii=False)  # JSON 数组（含帧标识：下标=首/中/尾）
    assert parse_video_phash_value(vp["combined"]) == expected


def test_mock_extractor_respects_n():
    frames = _mock_frames()
    assert len(MockFrameExtractor(frames).extract_frames("x.mp4", n=2)) == 2
    assert len(MockFrameExtractor(frames).extract_frames("x.mp4", n=5)) == 3  # 帧不足取全部


def test_parse_video_phash_value_formats():
    assert parse_video_phash_value('["aa","bb"]') == ["aa", "bb"]
    assert parse_video_phash_value("0:0f0f0f0f0f0f0f00") == ["0f0f0f0f0f0f0f00"]
    assert parse_video_phash_value("0f0f0f0f0f0f0f00") == ["0f0f0f0f0f0f0f00"]
    assert parse_video_phash_value("") == []
    assert parse_video_phash_value("not-json") == ["not-json"]


def _ffmpeg_available() -> bool:
    return shutil.which("ffmpeg") is not None


@pytest.mark.skipif(_ffmpeg_available(), reason="本机已安装 ffmpeg，缺失场景不适用")
def test_ffmpeg_extractor_raises_clear_error_when_missing():
    ex = FFmpegFrameExtractor()
    with pytest.raises(FFmpegNotFoundError) as ei:
        ex.extract_frames("whatever.mp4", n=1)
    msg = str(ei.value)
    assert "ffmpeg" in msg.lower()
    assert "MATERIALS_FFMPEG_PATH" in msg               # 错误信息含修复指引


def test_ffmpeg_extractor_raises_for_nonexistent_binary(tmp_path):
    ex = FFmpegFrameExtractor(ffmpeg_path=str(tmp_path / "no-ffmpeg.exe"))
    with pytest.raises(FFmpegNotFoundError) as ei:
        ex.extract_frames("whatever.mp4", n=1)
    assert "MATERIALS_FFMPEG_PATH" in str(ei.value)


# ---------------------------------------------------------------- DedupService 集成
def _service(db_materials) -> DedupService:
    return DedupService(db_materials)


def test_check_image_duplicate_by_md5(db_materials, tmp_path):
    svc = _service(db_materials)
    p = _save(_complex_image(), tmp_path / "a.png")
    md5 = compute_md5(p)
    ph = image_phash(p)
    aid = AssetRepo(db_materials).create_asset(**base_image_like(md5=md5, phash=ph, file_path=p))
    res = svc.check_image(p)
    assert res["is_duplicate"] is True
    assert res["reason"] == "md5"
    assert res["matched_fingerprint"]["fingerprint_type"] == "md5"
    assert res["matched_fingerprint"]["fingerprint_value"] == md5
    assert res["matched_fingerprint"]["asset_id"] == aid


def test_check_image_duplicate_by_phash_after_reencode(db_materials, tmp_path):
    """转码变体：MD5 已变（加水印/转码场景），整图 phash 近似判重（三级去重第 3 级）。"""
    svc = _service(db_materials)
    base = _complex_image()
    p1 = _save(base, tmp_path / "a.png")
    p2 = _save(base, tmp_path / "b.jpg", fmt="JPEG", quality=70)
    assert compute_md5(p1) != compute_md5(p2)
    md5_1, ph_1 = compute_md5(p1), image_phash(p1)
    aid = AssetRepo(db_materials).create_asset(**base_image_like(md5=md5_1, phash=ph_1, file_path=p1))
    res = svc.check_image(p2)
    assert res["is_duplicate"] is True
    assert res["reason"] == "image_phash"
    assert res["matched_fingerprint"]["fingerprint_type"] == "image_phash"
    assert res["matched_fingerprint"]["fingerprint_value"] == ph_1
    assert res["matched_fingerprint"]["asset_id"] == aid


def test_check_image_clean_returns_candidate_fingerprints(db_materials, tmp_path):
    svc = _service(db_materials)
    p1 = _save(_complex_image(), tmp_path / "a.png")
    p2 = _save(_noise_image(), tmp_path / "noise.png")
    AssetRepo(db_materials).create_asset(
        **base_image_like(md5=compute_md5(p1), phash=image_phash(p1), file_path=p1)
    )
    res = svc.check_image(p2)
    assert res["is_duplicate"] is False
    assert res["matched_fingerprint"] is None
    assert res["reason"] == "none"
    types = {f["fingerprint_type"] for f in res["fingerprints_registered"]}
    assert types == {"md5", "image_phash"}                # 候选指纹集合供 create_asset 入库存档


def test_check_image_md5_only_mode(db_materials):
    svc = _service(db_materials)
    md5 = "0123456789abcdef0123456789abcdef"
    AssetRepo(db_materials).create_asset(
        **base_image_like(md5=md5, phash="0" * 16, file_path="images/x.png", size=100)
    )
    res = svc.check_image(md5)                            # 纯 md5 输入（无文件）
    assert res["is_duplicate"] is True
    assert res["reason"] == "md5"
    res2 = svc.check_image("fedcba9876543210fedcba9876543210")  # 未注册 md5
    assert res2["is_duplicate"] is False
    assert res2["reason"] == "no_file"


def test_check_video_duplicate_by_keyframe_phash(db_materials, tmp_path):
    """转码变体视频：MD5 已变，首/中/尾关键帧 phash 近似判重（三级去重第 2 级）。"""
    svc = _service(db_materials)
    ex = MockFrameExtractor(_mock_frames())
    v1 = tmp_path / "v1.mp4"
    v1.write_bytes(b"video bytes one")
    v2 = tmp_path / "v2.mp4"
    v2.write_bytes(b"video bytes two")
    assert compute_md5(str(v1)) != compute_md5(str(v2))
    vp = video_phash(str(v1), ex)
    aid = AssetRepo(db_materials).create_asset(
        **base_video_like(md5=compute_md5(str(v1)), phash=vp["combined"], file_path=str(v1))
    )
    res = svc.check_video(str(v2), extractor=ex)
    assert res["is_duplicate"] is True
    assert res["reason"] == "video_phash"
    assert res["matched_fingerprint"]["fingerprint_type"] == "video_phash"
    assert res["matched_fingerprint"]["asset_id"] == aid
    # 库中 video_phash 指纹值 = JSON 数组（数组下标 = 首/中/尾帧标识）
    assert parse_video_phash_value(res["matched_fingerprint"]["fingerprint_value"]) == vp["frames"]


def test_check_video_duplicate_by_md5(db_materials, tmp_path):
    svc = _service(db_materials)
    v1 = tmp_path / "v1.mp4"
    v1.write_bytes(b"video bytes one")
    AssetRepo(db_materials).create_asset(
        **base_video_like(md5=compute_md5(str(v1)), phash="[]", file_path=str(v1))
    )
    res = svc.check_video(str(v1), extractor=MockFrameExtractor(_mock_frames()))
    assert res["is_duplicate"] is True
    assert res["reason"] == "md5"


# ---------------------------------------------------------------- claim_and_register（认领 + 入库）
def test_claim_and_register_image_flow(db_materials, tmp_path):
    svc = _service(db_materials)
    p = _save(_complex_image(), tmp_path / "a.png")
    keys, created = svc.claim_and_register(
        asset_type="image",
        file_path=p,
        source_platform="抖音",
        source_url="https://example.com/i.jpg",
    )
    assert created > 0
    assert {k["fingerprint_type"] for k in keys} == {"md5", "image_phash"}
    assert len(keys) == 2
    with db_materials.session() as s:
        rows = s.execute(select(T.AssetDedupFingerprint)).scalars().all()
        assert len(rows) == 2                      # md5 + image_phash 均已注册
    res = svc.check_image(p)                       # 注册后二次检查 → 重复
    assert res["is_duplicate"] is True
    assert res["reason"] == "md5"
    assert res["matched_fingerprint"]["asset_id"] == created


def test_claim_and_register_conflict_raises_duplicate(db_materials, tmp_path):
    svc = _service(db_materials)
    p = _save(_complex_image(), tmp_path / "a.png")
    svc.claim_and_register(
        asset_type="image", file_path=p, source_platform="抖音", source_url="https://example.com/i.jpg"
    )
    # 同文件再次入库 → md5 认领冲突（事务回滚，重复不入库，不静默吞）
    with pytest.raises(DuplicateAssetError) as ei:
        svc.claim_and_register(
            asset_type="image", file_path=p, source_platform="抖音", source_url="https://example.com/i.jpg"
        )
    assert ei.value.fingerprint_type == "md5"
    # 转码变体：md5 不同但 phash 近似 → image_phash 认领冲突
    q = _save(Image.open(p), tmp_path / "b.jpg", fmt="JPEG", quality=60)
    assert compute_md5(q) != compute_md5(p)
    with pytest.raises(DuplicateAssetError) as ei2:
        svc.claim_and_register(
            asset_type="image", file_path=q, source_platform="抖音", source_url="https://example.com/i2.jpg"
        )
    assert ei2.value.fingerprint_type == "image_phash"
    # 重复素材全程未入库
    assert len(AssetRepo(db_materials).list_assets()) == 1


def test_claim_and_register_video_with_mock_extractor(db_materials, tmp_path):
    svc = _service(db_materials)
    v = tmp_path / "v.mp4"
    v.write_bytes(b"video bytes")
    ex = MockFrameExtractor(_mock_frames())
    keys, created = svc.claim_and_register(
        asset_type="video",
        file_path=str(v),
        source_platform="视频号",
        source_url="https://example.com/v.mp4",
        duration=15,
        resolution="720x1280",
        extractor=ex,
    )
    ph_key = next(k for k in keys if k["fingerprint_type"] == "video_phash")
    assert ph_key["fingerprint_value"].startswith("[")   # JSON 数组
    # mock 同帧变体视频（不同 md5）→ 关键帧 phash 判重
    v2 = tmp_path / "v2.mp4"
    v2.write_bytes(b"video bytes 2")
    res = svc.check_video(str(v2), extractor=ex)
    assert res["is_duplicate"] is True
    assert res["reason"] == "video_phash"
    assert res["matched_fingerprint"]["asset_id"] == created


def test_claim_fingerprint_concurrent_semantics(db_materials):
    """并发认领语义：同 (type, value) 首次 True、二次 False（幂等防并发重复入库）。"""
    repo = AssetRepo(db_materials)
    aid = repo.create_asset(**base_image_like(md5="a" * 32, phash="1" * 16))
    with db_materials.session() as s:
        assert AssetRepo.claim_fingerprint(s, "md5", "b" * 32, aid) is True
        assert AssetRepo.claim_fingerprint(s, "md5", "b" * 32, aid) is False


# ---------------------------------------------------------------- 服务级阈值边界（8/9）
def test_service_threshold_boundary_hit_at_8(db_materials):
    """库中注册距离恰为 8 的指纹 → 候选命中（阈值含等号，默认 8 生效）。"""
    svc = _service(db_materials)
    assert svc.threshold == 8
    base = "0f0f0f0f0f0f0f00"
    ph8 = _flip_bits(base, 8)
    ph9 = _flip_bits(base, 9)
    with db_materials.session() as s:
        asset = T.AssetItem(
            asset_type="image", source_platform="抖音", source_url="https://example.com/x.jpg",
            md5="a" * 32, phash=ph9, file_path="images/x.png", size=1,
        )
        s.add(asset)
        s.flush()
        s.add(T.AssetDedupFingerprint(
            fingerprint_type="image_phash", fingerprint_value=ph8,
            asset_id=asset.id, hits=1, claimed_at=iso_now(),
        ))
        s.add(T.AssetDedupFingerprint(
            fingerprint_type="image_phash", fingerprint_value=ph9,
            asset_id=asset.id, hits=1, claimed_at=iso_now(),
        ))
    with db_materials.session() as s:
        hit = svc._find_approx(s, "image_phash", [base])
        assert hit is not None
        assert hit["fingerprint_value"] == ph8   # 距离 8 → 命中（ph9 距离 9 不命中，顺序无关）


def test_service_threshold_boundary_no_hit_at_9(db_materials):
    """库中仅距离恰为 9 的指纹 → 候选不命中（阈值 8 不含 9）。"""
    svc = _service(db_materials)
    base = "0f0f0f0f0f0f0f00"
    ph9 = _flip_bits(base, 9)
    with db_materials.session() as s:
        asset = T.AssetItem(
            asset_type="image", source_platform="抖音", source_url="https://example.com/x.jpg",
            md5="a" * 32, phash=ph9, file_path="images/x.png", size=1,
        )
        s.add(asset)
        s.flush()
        s.add(T.AssetDedupFingerprint(
            fingerprint_type="image_phash", fingerprint_value=ph9,
            asset_id=asset.id, hits=1, claimed_at=iso_now(),
        ))
    with db_materials.session() as s:
        assert svc._find_approx(s, "image_phash", [base]) is None   # 距离 9 > 8 → 不命中
