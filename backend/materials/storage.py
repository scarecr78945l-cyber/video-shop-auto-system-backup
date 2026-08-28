"""素材存储抽象：Storage ABC / LocalStorage / MinIOStorage 骨架。

R-M2-22（MinIO 暂缺）：v0.1 只落本地目录，file_path 语义统一为「存储键」；
M4 里程碑随全局迁移对象存储时新增 MinIOStorage 完整实现，配置切一行即可。

- 键分层：asset_type/YYYYMM/<filename>（自动 mkdir；key_for 为纯函数，Local/MinIO 共用）
- LocalStorage 防路径穿越（key 必须落在根目录内）
- MinIO 凭据只从环境变量 MATERIALS_MINIO_* 读取或构造参数显式注入，
  代码里只有变量名、绝不写死/不写明文（P-004 / 宪法第 5 节）
- MinIOStorage 为骨架：构造不报错（未配置也可实例化），IO 方法明确 NotImplementedError
"""

from __future__ import annotations

import os
import re
import shutil
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Union

PathLike = Union[str, Path]

DEFAULT_STORAGE_DIR = "data/materials"


def _month_key() -> str:
    """UTC 当前月份键（YYYYMM），素材按月份分层归档。"""
    return datetime.now(timezone.utc).strftime("%Y%m")


class Storage(ABC):
    """存储抽象基类。所有路径语义为相对存储键（key），对接 MinIO 后键不变。

    实现子类必须提供 put/put_file/read/exists/delete/stat；
    key_for 为纯函数，由基类统一实现（Local 与 MinIO 键格式一致）。
    """

    def key_for(self, asset_type: str, filename: str) -> str:
        """按 asset_type/YYYYMM/ 分层生成存储键。"""
        return f"{asset_type}/{_month_key()}/{filename}"

    @abstractmethod
    def put(self, key: str, data: bytes) -> str:
        """写入字节数据，返回存储键。"""

    @abstractmethod
    def put_file(self, key: str, src_path: PathLike) -> str:
        """把本地文件复制进存储，返回存储键。"""

    @abstractmethod
    def read(self, key: str) -> bytes:
        """读取字节；键不存在抛 FileNotFoundError。"""

    @abstractmethod
    def exists(self, key: str) -> bool:
        """键是否存在。"""

    @abstractmethod
    def delete(self, key: str) -> bool:
        """删除；键不存在返回 False（幂等）。"""

    @abstractmethod
    def stat(self, key: str) -> dict[str, Any]:
        """元信息（key/size/mtime）；键不存在抛 FileNotFoundError。"""


class LocalStorage(Storage):
    """本地目录存储（默认根目录 = MATERIALS_STORAGE_DIR 或 data/materials）。"""

    def __init__(self, root_dir: PathLike | None = None):
        if root_dir is None:
            root_dir = os.environ.get("MATERIALS_STORAGE_DIR") or DEFAULT_STORAGE_DIR
        self.root = Path(root_dir)

    def _resolve(self, key: str) -> Path:
        key = str(key)
        if key.startswith("/") or key.startswith("\\"):
            raise ValueError(f"非法存储键（不允许绝对路径）: {key!r}")
        if re.match(r"^[A-Za-z]:", key):
            raise ValueError(f"非法存储键（不允许盘符路径）: {key!r}")
        key = key.replace("\\", "/").strip("/")
        if not key or key in (".", "..") or "/../" in f"/{key}/" or key.startswith("../"):
            raise ValueError(f"非法存储键: {key!r}")
        p = (self.root / key).resolve()
        root = self.root.resolve()
        if p != root and root not in p.parents:
            raise ValueError(f"存储键越出根目录: {key!r}")
        return p

    def put(self, key: str, data: bytes) -> str:
        p = self._resolve(key)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)
        return key

    def put_file(self, key: str, src_path: PathLike) -> str:
        p = self._resolve(key)
        p.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(str(src_path), str(p))
        return key

    def read(self, key: str) -> bytes:
        return self._resolve(key).read_bytes()

    def exists(self, key: str) -> bool:
        try:
            return self._resolve(key).is_file()
        except ValueError:
            return False

    def delete(self, key: str) -> bool:
        try:
            p = self._resolve(key)
        except ValueError:
            return False
        if not p.is_file():
            return False
        p.unlink()
        return True

    def stat(self, key: str) -> dict[str, Any]:
        p = self._resolve(key)
        st = p.stat()
        return {
            "key": key,
            "size": st.st_size,
            "mtime": st.st_mtime,
        }


class MinIOStorage(Storage):
    """MinIO 骨架（M4 里程碑接入对象存储，R-M2-22）。

    构造只接受参数或环境变量（MATERIALS_MINIO_ENDPOINT / MATERIALS_MINIO_ACCESS_KEY /
    MATERIALS_MINIO_SECRET_KEY / MATERIALS_MINIO_BUCKET），值一律不写死在代码里；
    未配置时构造不报错（方便测试与未接 MinIO 环境），IO 方法明确 NotImplementedError。
    接口签名与 Storage 完全一致（key_for 为纯函数，直接可用）。
    """

    def __init__(
        self,
        endpoint: str | None = None,
        access_key: str | None = None,
        secret_key: str | None = None,
        bucket: str | None = None,
    ):
        self.endpoint = endpoint or os.environ.get("MATERIALS_MINIO_ENDPOINT")
        self.access_key = access_key or os.environ.get("MATERIALS_MINIO_ACCESS_KEY")
        self.secret_key = secret_key or os.environ.get("MATERIALS_MINIO_SECRET_KEY")
        self.bucket = bucket or os.environ.get("MATERIALS_MINIO_BUCKET", "materials")

    def _unavailable(self, method: str) -> NotImplementedError:
        return NotImplementedError(
            f"MinIOStorage.{method} 将在 M4 里程碑随全局迁移接入（R-M2-22）；"
            "当前阶段请使用 LocalStorage"
        )

    def put(self, key: str, data: bytes) -> str:
        raise self._unavailable("put")

    def put_file(self, key: str, src_path: PathLike) -> str:
        raise self._unavailable("put_file")

    def read(self, key: str) -> bytes:
        raise self._unavailable("read")

    def exists(self, key: str) -> bool:
        raise self._unavailable("exists")

    def delete(self, key: str) -> bool:
        raise self._unavailable("delete")

    def stat(self, key: str) -> dict[str, Any]:
        raise self._unavailable("stat")
