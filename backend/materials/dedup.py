"""M2 自动收集素材模块 · 双去重器（R-M2-11）。

入库门禁 = 三级去重：
  1. 文件 MD5 精确判重（入库前必查；转码/加水印会变 → 依赖 phash 近似兜底）；
  2. 视频关键帧 phash 近似判重（首/中/尾 3 帧，任意帧汉明距离 ≤ 阈值 → 疑似重复）；
  3. 图片整图 phash 近似判重（复用 sourcing/dedup.py 的 image_phash 口径，跨模块一致）。

与 AssetRepo 指纹认领集成：claim_and_register 走 create_asset 的
「先落 asset 取 id → 同一事务内认领 md5 + {asset_type}_phash → 冲突整体回滚并抛
DuplicateAssetError」语义（防并发重复入库，冲突不静默吞，由上层转重复标记）。

指纹存储格式（对齐 context/README.md 1.2 与 database/README.md DDL）：
  - md5          : 32 位小写 hex
  - image_phash  : 16 位小写 hex（整图 DCT phash）
  - video_phash  : JSON 数组字符串（["帧0hex","帧1hex","帧2hex"]），
                   数组下标 = 帧序号（首/中/尾）即帧标识（DDL「phash 含帧标识」）；
                   检查器读取兼容 "{index}:{hex}" 与纯 hex（前向兼容）。

视频关键帧抽取可插拔（本机 ffmpeg 未安装，测试零真实 ffmpeg 依赖，R-M2-15/R-M2-17）：
  FrameExtractor（抽象）→ FFmpegFrameExtractor（真实实现，缺失 raise 清晰错误）
                        → MockFrameExtractor（测试注入固定帧）。
"""

from __future__ import annotations

import hashlib
import io
import json
import os
import re
import shutil
import subprocess
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Optional

from PIL import Image
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import tables as T
from .config import MaterialsConfig
from .db import Database
from .repo import AssetRepo, DuplicateAssetError  # noqa: F401  （重导出，供上层统一从此模块导入）

# 文件 MD5 分块大小（大文件流式读取，不整读入内存）
MD5_CHUNK_SIZE: int = 1 << 20  # 1 MiB

# 32 位小写 hex 判定（check_* 的 path_or_md5 二义消解：是 md5 字符串而非文件路径）
_MD5_RE = re.compile(r"^[0-9a-f]{32}$")


# =====================================================================
# 视频关键帧抽取抽象（可插拔）
# =====================================================================
class FrameExtractor(ABC):
    """视频关键帧抽取抽象：真实实现 FFmpegFrameExtractor / 测试实现 MockFrameExtractor。"""

    @abstractmethod
    def extract_frames(self, video_path: str, n: int = 3) -> list[Image.Image]:
        """抽取 n 帧（默认首/中/尾 3 帧），返回 PIL.Image 列表。"""


class FFmpegNotFoundError(RuntimeError):
    """ffmpeg 缺失：无法抽取视频关键帧（错误信息含安装/配置指引，R-M2-15 不静默）。"""


class FrameExtractionError(RuntimeError):
    """ffmpeg 存在但抽帧失败（非零退出 / 超时 / 无帧输出）。"""


class FFmpegFrameExtractor(FrameExtractor):
    """真实视频关键帧抽取：调用 ffmpeg 按时间点抽帧（-ss 快进 + image2pipe PPM 输出）。

    - 二进制解析顺序：构造参数 ffmpeg_path > 环境变量 MATERIALS_FFMPEG_PATH > PATH；
    - 抽帧时间点：ffprobe（或 ffmpeg -i 输出）探测时长后取首/中/尾均匀点；
      时长未知时退化为 首帧 + 尾帧（-ss 超界会钳制到 EOF）；
    - ffmpeg 缺失 / 路径不存在 → FFmpegNotFoundError（清晰错误）；
    - 抽帧失败 / 超时 / 无帧输出 → FrameExtractionError。
    """

    def __init__(self, ffmpeg_path: Optional[str] = None, timeout: float = 30.0):
        self._ffmpeg_path = (
            ffmpeg_path or os.environ.get("MATERIALS_FFMPEG_PATH") or shutil.which("ffmpeg")
        )
        self.timeout = timeout

    def _resolve_binary(self) -> str:
        if not self._ffmpeg_path:
            raise FFmpegNotFoundError(
                "ffmpeg 未安装或不在 PATH（无法抽取视频关键帧）。"
                "请安装 ffmpeg，或将可执行文件路径写入环境变量 MATERIALS_FFMPEG_PATH。"
            )
        return self._ffmpeg_path

    def _probe_duration(self, video_path: str) -> Optional[float]:
        """探测视频时长（秒）：ffprobe 优先，ffmpeg -i 输出解析兜底；失败返回 None。"""
        ffprobe = shutil.which("ffprobe")
        if ffprobe:
            try:
                proc = subprocess.run(
                    [
                        ffprobe, "-v", "error", "-show_entries", "format=duration",
                        "-of", "csv=p=0", video_path,
                    ],
                    capture_output=True, text=True, timeout=self.timeout,
                )
                if proc.returncode == 0 and proc.stdout.strip():
                    return float(proc.stdout.strip())
            except (OSError, ValueError, subprocess.SubprocessError):
                pass
        if self._ffmpeg_path:
            try:
                proc = subprocess.run(
                    [self._ffmpeg_path, "-hide_banner", "-i", video_path],
                    capture_output=True, text=True, timeout=self.timeout,
                )
                m = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", proc.stderr or "")
                if m:
                    h, mi, s = m.groups()
                    return int(h) * 3600 + int(mi) * 60 + float(s)
            except (OSError, ValueError, subprocess.SubprocessError):
                pass
        return None

    @staticmethod
    def _seek_times(duration: Optional[float], n: int) -> list[float]:
        """均匀取 n 个时间点（首/中/尾）。时长未知 → 首帧 + 尾帧（-ss 超界钳制 EOF）。"""
        if duration and duration > 0 and n > 1:
            eps = min(0.01, duration / 10)
            span = max(duration - eps, 0.0)
            return [round(span * i / (n - 1), 3) for i in range(n)]
        return [0.0] + [1e9] * (n - 1)

    def extract_frames(self, video_path: str, n: int = 3) -> list[Image.Image]:
        ffmpeg = self._resolve_binary()
        duration = self._probe_duration(video_path)
        frames: list[Image.Image] = []
        for t in self._seek_times(duration, n):
            cmd = [
                ffmpeg, "-hide_banner", "-loglevel", "error",
                "-ss", str(t), "-i", str(video_path),
                "-frames:v", "1", "-f", "image2pipe", "-vcodec", "ppm", "-",
            ]
            try:
                proc = subprocess.run(cmd, capture_output=True, timeout=self.timeout)
            except FileNotFoundError:
                raise FFmpegNotFoundError(
                    f"ffmpeg 不存在：{ffmpeg}（请安装或设置 MATERIALS_FFMPEG_PATH）"
                ) from None
            except subprocess.TimeoutExpired:
                raise FrameExtractionError(
                    f"ffmpeg 抽帧超时（>{self.timeout}s）：{video_path} @t={t}s"
                ) from None
            if proc.returncode != 0 or not proc.stdout:
                err = (proc.stderr or b"").decode("utf-8", "replace").strip()[-400:]
                raise FrameExtractionError(
                    f"ffmpeg 抽帧失败（exit={proc.returncode}）：{video_path} @t={t}s: {err}"
                )
            frames.append(Image.open(io.BytesIO(proc.stdout)).convert("RGB"))
        return frames


class MockFrameExtractor(FrameExtractor):
    """测试用固定帧抽取器：注入固定 PIL 帧，不依赖真实 ffmpeg（R-M2-17 零 ffmpeg 依赖）。"""

    def __init__(self, frames: list[Image.Image]):
        self.frames = list(frames)

    def extract_frames(self, video_path: str, n: int = 3) -> list[Image.Image]:
        return self.frames[:n]


# =====================================================================
# 指纹计算
# =====================================================================
def compute_md5(path: str) -> str:
    """文件 MD5（32 位小写 hex）；大文件按 MD5_CHUNK_SIZE 分块流式读取。"""
    h = hashlib.md5()
    with open(path, "rb") as f:
        while True:
            chunk = f.read(MD5_CHUNK_SIZE)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def image_phash(path_or_pil) -> str:
    """整图感知哈希（16 位小写 hex）。

    与 sourcing/dedup.py 口径完全一致（R-M2-11 跨模块一致）：直接复用
    sourcing.dedup.phash_from_bytes（32x32 灰度 → 8x8 DCT 低频系数 → 中值二值化 → 64 位）
    与 phash_hex。输入：文件路径 或 PIL.Image（转 PNG 无损字节，与文件输入同一管线）。
    """
    from sourcing.dedup import phash_from_bytes, phash_hex

    if isinstance(path_or_pil, Image.Image):
        buf = io.BytesIO()
        path_or_pil.convert("RGB").save(buf, format="PNG")
        data = buf.getvalue()
    else:
        with open(str(path_or_pil), "rb") as f:
            data = f.read()
    return phash_hex(phash_from_bytes(data))


def video_phash(path: str, extractor: Optional[FrameExtractor] = None) -> dict:
    """视频关键帧感知哈希：抽首/中/尾 3 帧 → 逐帧 phash。

    返回 {"frames": [phash...], "combined": JSON 数组字符串}：
      - frames  : 每帧 16 位小写 hex（顺序 = 首/中/尾）；
      - combined: 供 asset_items.phash 与 video_phash 指纹存储的 JSON 数组
                  （数组下标 = 帧序号即帧标识，兼容 context 1.2 / DDL「phash 含帧标识」）。
    """
    extractor = extractor or FFmpegFrameExtractor()
    images = extractor.extract_frames(path, n=3)
    frames = [image_phash(img) for img in images]
    return {"frames": frames, "combined": json.dumps(frames, ensure_ascii=False)}


def parse_video_phash_value(value: str) -> list[str]:
    """解析存储的视频 phash 指纹值 → 帧 hex 列表。

    兼容三种格式：
      - JSON 数组字符串（本模块 create_asset / claim_and_register 写入的 combined）；
      - "{index}:{hex}"（带帧标识的单帧）；
      - 纯 hex（单帧）。
    """
    v = (value or "").strip()
    if not v:
        return []
    if v.startswith("["):
        try:
            data = json.loads(v)
        except ValueError:
            data = None
        if isinstance(data, list):
            return [str(x) for x in data]
    if ":" in v:
        return [v.rsplit(":", 1)[1]]
    return [v]


# =====================================================================
# 汉明距离与阈值判定
# =====================================================================
def _hex_to_int(value: str) -> int:
    v = (value or "").strip()
    if ":" in v:
        v = v.rsplit(":", 1)[1]
    return int(v, 16) if v else 0


def hamming_distance(a: str, b: str) -> int:
    """两个 16 位 hex phash 串的汉明距离（按位比较）。

    兼容 "{index}:{hex}" 前缀（自动剥离）；长度不同按前导零对齐（int 对齐）。
    """
    return bin(_hex_to_int(a) ^ _hex_to_int(b)).count("1")


def _default_threshold() -> int:
    from .config import load_config

    return load_config().dedup.phash_hamming_threshold


def is_duplicate(distance: int, threshold: Optional[int] = None) -> bool:
    """汉明距离 ≤ 阈值 → 疑似重复。阈值默认取 config.dedup.phash_hamming_threshold（默认 8）。"""
    if threshold is None:
        threshold = _default_threshold()
    return distance <= threshold


# =====================================================================
# 入库去重服务（与 AssetRepo 指纹认领集成）
# =====================================================================
class DedupService:
    """素材入库双去重服务（R-M2-11）：MD5 精确 + phash 近似，与 AssetRepo 指纹认领集成。

    返回结构统一（供 create_asset 入库存档）：
      {is_duplicate, matched_fingerprint, fingerprints_registered, reason}
        - is_duplicate            : 是否疑似重复
        - matched_fingerprint     : 命中的库中指纹行 dict（含 asset_id/hits），未命中 None
        - fingerprints_registered : check_* 为该素材携带的候选指纹集合（供上层注册/归档）；
                                    claim_and_register 为实际认领成功的指纹集合
        - reason                  : md5 | video_phash | image_phash | none | no_file
    """

    def __init__(self, db: Database, config: Optional[MaterialsConfig] = None):
        self.db = db
        self.config = config or db.config
        self.repo = AssetRepo(db)
        self.threshold = self.config.dedup.phash_hamming_threshold

    # ------------------------------------------------------------ 内部工具
    @staticmethod
    def _resolve_md5(path_or_md5: str) -> tuple[str, Optional[str]]:
        """path_or_md5 消歧：32 位 hex 且非现存路径 → 当作 md5 原样返回（无文件）；
        否则当作文件路径计算 md5。返回 (md5, path_or_None)。"""
        s = str(path_or_md5).strip()
        if _MD5_RE.match(s) and not Path(s).exists():
            return s, None
        return compute_md5(s), s

    @staticmethod
    def _fp_to_dict(row: T.AssetDedupFingerprint) -> dict[str, Any]:
        return {c.name: getattr(row, c.name) for c in T.AssetDedupFingerprint.__table__.columns}

    def _find_exact(
        self, session: Session, fingerprint_type: str, fingerprint_value: str
    ) -> Optional[dict[str, Any]]:
        """精确判重：同 (type, value) 指纹已注册 → 命中（MD5 或同值 phash）。"""
        row = session.execute(
            select(T.AssetDedupFingerprint).where(
                T.AssetDedupFingerprint.fingerprint_type == fingerprint_type,
                T.AssetDedupFingerprint.fingerprint_value == fingerprint_value,
            )
        ).scalar_one_or_none()
        return self._fp_to_dict(row) if row is not None else None

    def _find_approx(
        self, session: Session, fingerprint_type: str, candidate_frames: list[str]
    ) -> Optional[dict[str, Any]]:
        """近似判重：同类型指纹逐条比较，任一候选帧与任一所存帧汉明距离 ≤ 阈值 → 命中。"""
        rows = session.execute(
            select(T.AssetDedupFingerprint).where(
                T.AssetDedupFingerprint.fingerprint_type == fingerprint_type
            )
        ).scalars().all()
        for row in rows:
            stored_frames = parse_video_phash_value(row.fingerprint_value)
            for cand in candidate_frames:
                for stored in stored_frames:
                    if is_duplicate(hamming_distance(cand, stored), self.threshold):
                        return self._fp_to_dict(row)
        return None

    @staticmethod
    def _result(
        is_duplicate: bool,
        matched: Optional[dict[str, Any]],
        registered: list[dict[str, str]],
        reason: str,
    ) -> dict[str, Any]:
        return {
            "is_duplicate": is_duplicate,
            "matched_fingerprint": matched,
            "fingerprints_registered": registered,
            "reason": reason,
        }

    # ------------------------------------------------------------ 检查
    def check_image(self, path_or_md5: str) -> dict[str, Any]:
        """图片入库检查：MD5 精确 → image_phash 整图近似。

        path_or_md5 为 32 位 hex 且非现存路径时只做 MD5 精确检查（无文件无法算 phash，
        reason=no_file）。
        """
        md5, path = self._resolve_md5(path_or_md5)
        with self.db.session() as s:
            hit = self._find_exact(s, "md5", md5)
            if hit:
                return self._result(True, hit, [], "md5")
            if path is None:
                return self._result(False, None, [], "no_file")
            ph = image_phash(path)
            approx = self._find_approx(s, "image_phash", [ph])
            if approx:
                return self._result(True, approx, [], "image_phash")
            registered = [
                {"fingerprint_type": "md5", "fingerprint_value": md5},
                {"fingerprint_type": "image_phash", "fingerprint_value": ph},
            ]
            return self._result(False, None, registered, "none")

    def check_video(
        self, path_or_md5: str, extractor: Optional[FrameExtractor] = None
    ) -> dict[str, Any]:
        """视频入库检查：MD5 精确 → 关键帧 phash 近似（首/中/尾 3 帧，任意帧 ≤ 阈值）。

        extractor 默认 FFmpegFrameExtractor（真实环境需 ffmpeg；缺失抛 FFmpegNotFoundError）。
        """
        md5, path = self._resolve_md5(path_or_md5)
        with self.db.session() as s:
            hit = self._find_exact(s, "md5", md5)
            if hit:
                return self._result(True, hit, [], "md5")
            if path is None:
                return self._result(False, None, [], "no_file")
            vp = video_phash(path, extractor)
            approx = self._find_approx(s, "video_phash", vp["frames"])
            if approx:
                return self._result(True, approx, [], "video_phash")
            registered = [
                {"fingerprint_type": "md5", "fingerprint_value": md5},
                {"fingerprint_type": "video_phash", "fingerprint_value": vp["combined"]},
            ]
            return self._result(False, None, registered, "none")

    # ------------------------------------------------------------ 认领 + 注册 + 入库
    def claim_and_register(
        self,
        *,
        asset_type: str,
        file_path: str,
        source_platform: str,
        source_url: str,
        md5: Optional[str] = None,
        phash: Optional[str] = None,
        size: Optional[int] = None,
        extractor: Optional[FrameExtractor] = None,
        source_author: Optional[str] = None,
        duration: Optional[int] = None,
        resolution: Optional[str] = None,
        tags_json: Optional[str] = None,
        heat_score: Optional[float] = None,
        compliance_status: str = "pending",
        derivation_note: Optional[str] = None,
    ) -> tuple[list[dict[str, str]], int]:
        """认领并注册指纹 + 入库（与 AssetRepo.create_asset 同一事务语义）。

        流程：缺省指纹自动计算（md5 / 图片整图 phash / 视频关键帧 combined JSON）→
        create_asset 先落 asset 取 id，再同一事务认领 md5 + {asset_type}_phash；
        任一冲突 → DuplicateAssetError（事务整体回滚，由上层转重复标记，不静默吞）。

        返回 (fingerprint_keys, asset_id)：fingerprint_keys 为实际认领成功的
        [{"fingerprint_type", "fingerprint_value"}, ...]（与 check_* 的
        fingerprints_registered 同构，供入库存档）。
        """
        if md5 is None:
            md5 = compute_md5(file_path)
        if phash is None:
            if asset_type == "image":
                phash = image_phash(file_path)
            elif asset_type == "video":
                phash = video_phash(file_path, extractor)["combined"]
            else:
                raise ValueError(f"asset_type 必须是 'video' 或 'image'，收到 {asset_type!r}")
        if size is None:
            size = os.path.getsize(file_path)
        asset_id = self.repo.create_asset(
            asset_type=asset_type,
            source_platform=source_platform,
            source_url=source_url,
            source_author=source_author,
            md5=md5,
            phash=phash,
            file_path=file_path,
            duration=duration,
            resolution=resolution,
            size=size,
            tags_json=tags_json,
            heat_score=heat_score,
            compliance_status=compliance_status,
            derivation_note=derivation_note,
        )
        keys = [
            {"fingerprint_type": "md5", "fingerprint_value": md5},
            {"fingerprint_type": f"{asset_type}_phash", "fingerprint_value": phash},
        ]
        return keys, asset_id
