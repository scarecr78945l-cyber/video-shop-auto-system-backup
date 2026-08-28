"""M3 主图/详情图管线 · 质量门禁（image_quality_gate）。

对齐方案文档 06 第二节与 context/README 数据字典：
- 分辨率/比例：主图 1:1、最小边 ≥ config.image.min_edge_px（默认 800）；
  详情图 750x1000（3:4）或 800x800（1:1）均放行，比例落在 [0.70, 1.05]；
- 完整性：Pillow 可打开、非空白（灰度标准差过小判近纯色图）；
- 感知哈希：**Pillow 自实现 dHash / aHash**（无第三方依赖，requirements.txt 仅 Pillow），
  汉明距离 ≤ config.image.phash_hamming_threshold（默认 8）判同图；
- 主图 5 张出现相似对 → 打回重生成（regenerate_until_ok，≤ config.image.max_regenerate=2），
  超限标记失败。

返回 models.QualityVerdict（image_id / ok / score / issues）。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Optional

from PIL import Image, ImageStat

from ..config import M3Config, load_config
from ..models import ImagePlan, QualityVerdict


# ---------- 感知哈希（Pillow 自实现，无第三方依赖） ----------

def phash_dhash(file_path: str | Path) -> str:
    """dHash：缩放 9x8 灰度，比较相邻像素亮度序，64 bit → 16 位 hex。

    对全局颜色偏移鲁棒、对布局变化敏感，适合「同图 vs 不同构图」判定。
    """
    img = Image.open(file_path).convert("L").resize((9, 8), Image.Resampling.LANCZOS)
    bits: list[str] = []
    px = img.load()
    for y in range(8):
        for x in range(8):
            bits.append("1" if px[x, y] > px[x + 1, y] else "0")
    return hex(int("".join(bits), 2))[2:].zfill(16)


def phash_ahash(file_path: str | Path) -> str:
    """aHash：缩放 8x8 灰度，与均值比较，64 bit → 16 位 hex。"""
    img = Image.open(file_path).convert("L").resize((8, 8), Image.Resampling.LANCZOS)
    pixels = list(img.getdata())
    avg = sum(pixels) / len(pixels)
    bits = "".join("1" if p > avg else "0" for p in pixels)
    return hex(int(bits, 2))[2:].zfill(16)


def hamming_distance(hex_a: str, hex_b: str) -> int:
    """两个 16 位 hex 感知哈希的汉明距离（相异 bit 数）。"""
    if not hex_a or not hex_b:
        return 64
    xor = int(hex_a, 16) ^ int(hex_b, 16)
    return bin(xor).count("1")


# ---------- 门禁 ----------

class ImageQualityGate:
    """单图检查 + 批次相似度判定。"""

    def __init__(self, config: Optional[M3Config] = None):
        self.config: M3Config = config or load_config()

    # -- 单图 --

    def inspect(self, image_id: str, file_path: str | Path,
                image_type: str = "main") -> QualityVerdict:
        """单张图片质量检查：完整性 / 分辨率 / 比例 / 空白。"""
        cfg = self.config.image
        issues: list[str] = []
        try:
            img = Image.open(file_path)
            img.load()
        except Exception as exc:  # 无法打开/损坏
            return QualityVerdict(
                image_id=image_id, ok=False, score=0.0,
                issues=[f"无法打开或图片损坏: {type(exc).__name__}"],
            )

        w, h = img.size
        min_edge = min(w, h)
        if min_edge < cfg.min_edge_px:
            issues.append(
                f"分辨率不足：最小边 {min_edge}px < {cfg.min_edge_px}px（{w}x{h}）"
            )

        ratio = w / h if h else 0.0
        if image_type == "main":
            if abs(ratio - 1.0) > 0.01:
                issues.append(f"主图非 1:1：{w}x{h}（ratio={ratio:.3f}）")
        else:  # detail：允许 1:1（800x800）或 3:4（750x1000）
            if not (0.70 <= ratio <= 1.05):
                issues.append(f"详情图比例异常：{w}x{h}（ratio={ratio:.3f}）")

        try:
            stat = ImageStat.Stat(img.convert("L"))
            if stat.stddev[0] < 5.0:
                issues.append("疑似空白/近纯色图（亮度标准差过小）")
        except Exception:
            issues.append("图像统计失败")

        score = max(0.0, 100.0 - 30.0 * len(issues))
        return QualityVerdict(
            image_id=image_id, ok=not issues,
            score=round(score, 1), issues=issues,
        )

    def phash_of(self, file_path: str | Path) -> str:
        """dHash（主图去重/相似判定用）。"""
        return phash_dhash(file_path)

    # -- 批次 --

    def gate_batch(self, items: list[dict[str, Any]],
                   image_type: str = "main") -> dict[str, Any]:
        """批次门禁：逐张检查 + 主图两两 phash 相似判定。

        items: [{"image_id": ..., "file_path": ...}, ...]
        返回 {"verdicts", "phashes", "similar_pairs", "threshold", "ok"}
        """
        cfg = self.config.image
        verdicts = [self.inspect(it["image_id"], it["file_path"], image_type)
                    for it in items]
        phashes = {it["image_id"]: self.phash_of(it["file_path"]) for it in items}

        similar_pairs: list[dict[str, Any]] = []
        if image_type == "main":
            ids = [it["image_id"] for it in items]
            for i in range(len(ids)):
                for j in range(i + 1, len(ids)):
                    d = hamming_distance(phashes[ids[i]], phashes[ids[j]])
                    if d <= cfg.phash_hamming_threshold:
                        similar_pairs.append(
                            {"a": ids[i], "b": ids[j], "hamming": d}
                        )

        ok = all(v.ok for v in verdicts) and not similar_pairs
        return {
            "verdicts": verdicts,
            "phashes": phashes,
            "similar_pairs": similar_pairs,
            "threshold": cfg.phash_hamming_threshold,
            "ok": ok,
        }


# ---------- 打回重生成编排 ----------

def regenerate_until_ok(
    gate: ImageQualityGate,
    generate_one: Callable[[int], Any],
    plan: ImagePlan,
    product: dict[str, Any],
    batch_id: str,
    max_regenerate: Optional[int] = None,
    image_type: Optional[str] = None,
) -> dict[str, Any]:
    """批次生成 + 门禁循环：不达标打回重生成，超限标记失败。

    generate_one(variant_no) -> ImageDraft（由调用方注入，离线=占位图 / 在线=API）。
    max_regenerate 默认 config.image.max_regenerate（=2）。
    返回 {"drafts", "gate", "attempts", "ok", "failed"}。
    """
    image_type = image_type or plan.image_type
    max_r = (gate.config.image.max_regenerate
             if max_regenerate is None else max_regenerate)
    count = len(plan.prompts)

    def _run() -> tuple[list[Any], dict[str, Any]]:
        drafts = [generate_one(v) for v in range(1, count + 1)]
        for d in drafts:
            d.batch_id = batch_id
        items = [
            {"image_id": f"{batch_id}_{v}", "file_path": d.file_path}
            for v, d in enumerate(drafts, 1)
        ]
        return drafts, gate.gate_batch(items, image_type)

    drafts, result = _run()
    attempts = 0
    while not result["ok"] and attempts < max_r:
        attempts += 1
        drafts, result = _run()

    return {
        "drafts": drafts,
        "gate": result,
        "attempts": attempts,
        "ok": result["ok"],
        "failed": not result["ok"],
    }
