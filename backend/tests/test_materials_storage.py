"""materials.storage 单元测试：Local 读写删/分层键/不存在处理/MinIO 骨架。

纪律：pytest 一律带 --basetemp=".pytest-tmp"（P-001）；临时文件只放 tmp_path。
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from materials.storage import LocalStorage, MinIOStorage, Storage


def test_local_put_read(tmp_path):
    st = LocalStorage(tmp_path / "store")
    key = "video/202501/a.mp4"
    data = b"\x00\x01" * 100
    assert st.put(key, data) == key
    assert st.read(key) == data
    assert st.exists(key)
    # 自动 mkdir（按 asset_type/YYYYMM/ 分层）
    assert (tmp_path / "store" / "video" / "202501" / "a.mp4").is_file()


def test_local_put_file(tmp_path):
    st = LocalStorage(tmp_path / "store")
    src = tmp_path / "src.bin"
    src.write_bytes(b"hello storage")
    key = st.put_file("image/202502/b.jpg", src)
    assert key == "image/202502/b.jpg"
    assert st.read(key) == b"hello storage"
    assert (tmp_path / "store" / "image" / "202502" / "b.jpg").is_file()


def test_local_delete(tmp_path):
    st = LocalStorage(tmp_path / "store")
    st.put("video/202501/x.mp4", b"x")
    assert st.delete("video/202501/x.mp4") is True
    assert not st.exists("video/202501/x.mp4")
    # 不存在幂等返回 False（不抛异常）
    assert st.delete("video/202501/x.mp4") is False


def test_local_missing_handling(tmp_path):
    st = LocalStorage(tmp_path / "store")
    assert st.exists("video/209901/none.mp4") is False
    with pytest.raises(FileNotFoundError):
        st.read("video/209901/none.mp4")
    with pytest.raises(FileNotFoundError):
        st.stat("video/209901/none.mp4")


def test_local_stat(tmp_path):
    st = LocalStorage(tmp_path / "store")
    st.put("image/202503/c.png", b"12345")
    info = st.stat("image/202503/c.png")
    assert info["key"] == "image/202503/c.png"
    assert info["size"] == 5
    assert info["mtime"] > 0


def test_key_for_layering():
    st = LocalStorage(".")
    key = st.key_for("video", "clip.mp4")
    assert re.match(r"^video/\d{6}/clip\.mp4$", key)


def test_default_root_from_env(tmp_path, monkeypatch):
    monkeypatch.setenv("MATERIALS_STORAGE_DIR", str(tmp_path / "env-store"))
    st = LocalStorage()
    assert st.root == tmp_path / "env-store"


def test_default_root_fallback():
    # 未设置环境变量时默认 data/materials（相对路径）
    st = LocalStorage()
    assert st.root == Path("data/materials")


def test_path_traversal_guard(tmp_path):
    st = LocalStorage(tmp_path / "store")
    for evil in ("../../evil.txt", r"..\..\evil.txt", "/abs/evil.txt"):
        with pytest.raises(ValueError):
            st.put(evil, b"x")
    assert not st.exists("../../evil.txt")


def test_storage_abc():
    # 抽象基类不可直接实例化（必须有全部 IO 方法实现）
    with pytest.raises(TypeError):
        Storage()  # type: ignore[abstract]


def test_minio_construct_no_args():
    # 未配置任何凭据：构造不报错（R-M2-22 骨架约定）
    st = MinIOStorage()
    assert st.bucket == "materials"
    assert st.access_key is None and st.secret_key is None and st.endpoint is None


def test_minio_construct_env(monkeypatch):
    # 凭据只从环境变量读取（代码里只有变量名，P-004）
    monkeypatch.setenv("MATERIALS_MINIO_ENDPOINT", "http://localhost:9000")
    monkeypatch.setenv("MATERIALS_MINIO_ACCESS_KEY", "env-access")
    monkeypatch.setenv("MATERIALS_MINIO_SECRET_KEY", "env-secret")
    monkeypatch.setenv("MATERIALS_MINIO_BUCKET", "assets")
    st = MinIOStorage()
    assert st.endpoint == "http://localhost:9000"
    assert st.access_key == "env-access"
    assert st.secret_key == "env-secret"
    assert st.bucket == "assets"


def test_minio_is_storage_and_signature():
    # 接口签名与 Storage 一致：子类 + 全 IO 方法 NotImplementedError
    assert issubclass(MinIOStorage, Storage)
    assert issubclass(LocalStorage, Storage)
    st = MinIOStorage()
    for method, args in [
        ("put", ("k", b"x")),
        ("put_file", ("k", "some/path")),
        ("read", ("k",)),
        ("exists", ("k",)),
        ("delete", ("k",)),
        ("stat", ("k",)),
    ]:
        with pytest.raises(NotImplementedError):
            getattr(st, method)(*args)
    # key_for 是纯函数（非 IO），MinIO 同样可用，键格式一致
    key = st.key_for("video", "a.mp4")
    assert re.match(r"^video/\d{6}/a\.mp4$", key)
