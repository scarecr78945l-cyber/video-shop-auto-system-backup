"""去重：image_phash + source_core_attributes_hash + 来源稳定性合并。

对应方案文档 04：去重（image_phash + source_core_attributes_hash + 来源稳定性）。
同款判定：同一商品指纹（属性哈希）或 phash 汉明距离 ≤ 阈值 → 合并/判重；
多榜/多源出现 → 合并为同一候选并加分（来源稳定性）。
"""

from __future__ import annotations

import hashlib
import io
import math
from dataclasses import dataclass
from typing import Callable, Optional

from .compliance import sanitize_title
from .config import SourcingConfig
from .models import SourceItem

# phash 计算函数：输入图像字节 -> 64 位 int；离线 fixture 模式可注入
PhashFn = Callable[[bytes], int]


def attribute_fingerprint(
    title: str, category: str, salt: str = "sourcing.v1"
) -> str:
    """source_core_attributes_hash：清洗后标题核心词 + 类目 的 SHA-256。"""
    clean = sanitize_title(title)
    # 取核心属性词：按长度过滤的切分词，弱化营销词影响
    tokens = [t for t in clean.replace("/", " ").replace(",", " ").split() if len(t) >= 2]
    tokens.sort()
    core = "|".join(tokens) + f"|{category.strip()}"
    return hashlib.sha256(f"{salt}::{core}".encode("utf-8")).hexdigest()


# ---------------------------------------------------------------- pHash
def _dct_1d(x: list[float]) -> list[float]:
    n = len(x)
    out = []
    c0 = math.sqrt(1.0 / n)
    for k in range(n):
        if k == 0:
            out.append(c0 * sum(x))
            continue
        ck = math.sqrt(2.0 / n)
        s = sum(v * math.cos(math.pi * k * (2 * i + 1) / (2 * n)) for i, v in enumerate(x))
        out.append(ck * s)
    return out


def phash_from_bytes(data: bytes, size: int = 32) -> int:
    """DCT 感知哈希：32x32 灰度 → 8x8 低频系数 → 按中值二值化 → 64 位 int。"""
    from PIL import Image

    img = Image.open(io.BytesIO(data)).convert("L").resize((size, size), Image.LANCZOS)
    px = list(img.tobytes())  # L 模式 0-255 字节
    rows = [_dct_1d([float(v) for v in px[r * size:(r + 1) * size]]) for r in range(size)]
    cols = [
        [_dct_1d([rows[r][c] for r in range(size)])[c2] for c2 in range(8)]
        for c in range(8)
    ]
    # cols[c][c2] = (c 列的 DCT 结果) 取前 8 个系数
    low = []
    for c in range(8):
        low.extend(cols[c])
    median = sorted(low)[len(low) // 2]
    bits = 0
    for i, v in enumerate(low):
        if v >= median:
            bits |= 1 << i
    return bits


def hamming(a: int, b: int) -> int:
    return bin(a ^ b).count("1")


def phash_hex(ph: int) -> str:
    return f"{ph:016x}"


@dataclass
class DedupResult:
    """合并/判重结果。"""

    merged: list[SourceItem]  # 合并后的条目（同一候选的全部来源）
    fingerprint: str
    image_phash: str
    is_duplicate: bool = False  # 与商品库已有商品重复
    duplicate_of: Optional[str] = None  # 库中已有指纹


class DedupEngine:
    def __init__(
        self,
        config: SourcingConfig,
        phash_fn: Optional[PhashFn] = None,
        library_has: Optional[Callable[[str, str], bool]] = None,
    ):
        """library_has(fingerprint, image_phash_hex) -> 是否已存在于商品库。"""
        self.config = config
        self.phash_fn = phash_fn or phash_from_bytes
        self.library_has = library_has or (lambda fp, ph: False)

    def _phash_for(self, item: SourceItem) -> str:
        raw_ph = item.raw.get("image_phash")
        if raw_ph:
            return str(raw_ph)
        url = next(iter(item.image_urls), None)
        if url:
            try:
                import requests

                resp = requests.get(url, timeout=10)
                if resp.status_code == 200:
                    return phash_hex(self.phash_fn(resp.content))
            except Exception:
                pass
        return ""

    def process(self, items: list[SourceItem]) -> list[DedupResult]:
        """同源内合并（同一商品多榜单/多来源），再对商品库判重。"""
        # 1) 按属性指纹分组（弱同款）
        groups: dict[str, list[SourceItem]] = {}
        phash_by_item: dict[str, str] = {}
        for it in items:
            fp = attribute_fingerprint(it.title, it.category, self.config.dedup.attribute_hash_salt)
            groups.setdefault(fp, []).append(it)
            phash_by_item[it.core_key] = self._phash_for(it)

        results: list[DedupResult] = []
        seen_ph: list[tuple[str, str]] = []  # (fingerprint, phash_hex)
        for fp, group in groups.items():
            group.sort(key=lambda x: x.rank or 0)
            phash = ""
            for it in group:
                p = phash_by_item.get(it.core_key, "")
                if p:
                    phash = p
                    break
            # 2) 图片 phash 相似合并（跨属性组撞图视为同款）
            dup_of: Optional[str] = None
            if phash:
                for other_fp, other_ph in seen_ph:
                    if other_ph and hamming(int(phash, 16), int(other_ph, 16)) <= self.config.dedup.phash_hamming_threshold:
                        dup_of = other_fp
                        break
            if dup_of:
                # 合并进已存在结果
                target = next(r for r in results if r.fingerprint == dup_of)
                target.merged.extend(group)
                continue
            seen_ph.append((fp, phash))
            results.append(DedupResult(merged=group, fingerprint=fp, image_phash=phash))

        # 3) 对商品库判重（库中有属性指纹或 phash 命中 → duplicate）
        for r in results:
            r.is_duplicate = self.library_has(r.fingerprint, r.image_phash)
            if r.is_duplicate:
                r.duplicate_of = r.fingerprint
        return results
