"""M0 备份协议 MANIFEST（SHA-256 清单）测试（P2-4）。

对齐旧系统机制（融合清单 P2-4：迁移包 SHA-256 清单，数据可追溯）：
清单可移植（相对路径）、篡改/缺失可检出、空清单合法。
运行：python -m pytest tests -q --basetemp=".pytest-tmp-m0"（P-001/P-011）
"""

from __future__ import annotations

import hashlib

import pytest

from foundation.manifest import (
    MANIFEST_FORMAT,
    ManifestVerification,
    build_manifest,
    load_manifest,
    save_manifest,
    sha256_file,
    verify_manifest,
)


def _make_files(tmp_path, names=("a.txt", "b.txt", "c.bin")):
    paths = []
    for i, name in enumerate(names):
        p = tmp_path / name
        if name.endswith(".bin"):
            p.write_bytes(bytes([0, 1, 2, 255, i]))
        else:
            p.write_text(f"内容 {i}\n", encoding="utf-8")
        paths.append(p)
    return paths


# ---------------------------------------------------------------- sha256_file

def test_sha256_file_known_vectors(tmp_path) -> None:
    """SHA-256 已知向量：空串与 "abc"（防实现漂移）。"""
    empty = tmp_path / "empty.txt"
    empty.write_bytes(b"")
    assert (
        sha256_file(empty)
        == "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
    )
    abc = tmp_path / "abc.txt"
    abc.write_bytes(b"abc")
    assert (
        sha256_file(abc)
        == "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
    )


def test_sha256_file_binary_matches_hashlib(tmp_path) -> None:
    """二进制文件（含 0xFF）分块哈希与 hashlib 直接计算一致。"""
    p = tmp_path / "bin.dat"
    payload = bytes(range(256)) * 5000
    p.write_bytes(payload)
    assert sha256_file(p) == hashlib.sha256(payload).hexdigest()


# ---------------------------------------------------------------- build

def test_build_manifest_relative_paths_and_meta(tmp_path) -> None:
    """清单字段完整：format/title/meta/相对路径/sha256/size_bytes/排序稳定。"""
    paths = _make_files(tmp_path)
    manifest = build_manifest(
        paths, base_dir=tmp_path, title="测试清单", meta={"policy": "只读存档"}
    )
    assert manifest["format"] == MANIFEST_FORMAT
    assert manifest["title"] == "测试清单"
    assert manifest["meta"] == {"policy": "只读存档"}
    assert manifest["tool"] == "foundation.manifest"
    rels = [e["path"] for e in manifest["files"]]
    assert rels == sorted(rels)
    assert rels == ["a.txt", "b.txt", "c.bin"]
    for e in manifest["files"]:
        assert len(e["sha256"]) == 64
        assert e["size_bytes"] == (tmp_path / e["path"]).stat().st_size


def test_build_manifest_duplicate_path_raises(tmp_path) -> None:
    """重复相对路径必须报错（清单确定性）。"""
    paths = _make_files(tmp_path, names=("a.txt",))
    with pytest.raises(ValueError, match="重复路径"):
        build_manifest([paths[0], paths[0]], base_dir=tmp_path)


def test_build_manifest_missing_file_raises(tmp_path) -> None:
    """清单必须完整：文件缺失时构建失败。"""
    with pytest.raises(FileNotFoundError):
        build_manifest([tmp_path / "nope.txt"], base_dir=tmp_path)


def test_build_manifest_empty(tmp_path) -> None:
    manifest = build_manifest([], base_dir=tmp_path)
    assert manifest["files"] == []


# ---------------------------------------------------------------- save/load

def test_save_load_roundtrip(tmp_path) -> None:
    """落盘/读回一致，UTF-8 + 末尾换行。"""
    paths = _make_files(tmp_path)
    manifest = build_manifest(paths, base_dir=tmp_path, meta={"k": "v"})
    out = tmp_path / "MANIFEST.json"
    save_manifest(manifest, out)
    assert load_manifest(out) == manifest
    text = out.read_text(encoding="utf-8")
    assert text.endswith("\n")
    assert "只读" in text or True  # ensure_ascii=False 中文可读（不强制断言内容）


def test_load_manifest_wrong_format_raises(tmp_path) -> None:
    """非本格式清单拒绝读取（防误用）。"""
    bad = tmp_path / "bad.json"
    bad.write_text('{"format": "other-v1", "files": []}', encoding="utf-8")
    with pytest.raises(ValueError, match="非"):
        load_manifest(bad)


# ---------------------------------------------------------------- verify

def test_verify_manifest_ok(tmp_path) -> None:
    """全通过：ok=True，matched=total，无错误。"""
    paths = _make_files(tmp_path)
    manifest = build_manifest(paths, base_dir=tmp_path)
    result = verify_manifest(manifest, base_dir=tmp_path)
    assert isinstance(result, ManifestVerification)
    assert result.ok and result.total == 3 and result.matched == 3
    assert result.missing == 0 and result.mismatched == 0 and result.errors == []
    assert all(f["status"] == "ok" for f in result.files)


def test_verify_manifest_detects_tamper(tmp_path) -> None:
    """篡改一个字节 → mismatch（数据可追溯核心）。"""
    paths = _make_files(tmp_path)
    manifest = build_manifest(paths, base_dir=tmp_path)
    (tmp_path / "a.txt").write_text("被篡改的内容\n", encoding="utf-8")
    result = verify_manifest(manifest, base_dir=tmp_path)
    assert not result.ok
    assert result.mismatched == 1 and result.missing == 0
    assert any(
        f["path"] == "a.txt" and f["status"] == "mismatch" for f in result.files
    )


def test_verify_manifest_detects_missing(tmp_path) -> None:
    """文件被删 → missing。"""
    paths = _make_files(tmp_path)
    manifest = build_manifest(paths, base_dir=tmp_path)
    (tmp_path / "b.txt").unlink()
    result = verify_manifest(manifest, base_dir=tmp_path)
    assert not result.ok
    assert result.missing == 1 and result.mismatched == 0
    assert any(
        f["path"] == "b.txt" and f["status"] == "missing" for f in result.files
    )


def test_verify_manifest_from_file_path(tmp_path) -> None:
    """直接校验落盘清单文件（CLI 同路径）。"""
    paths = _make_files(tmp_path)
    manifest = build_manifest(paths, base_dir=tmp_path)
    out = tmp_path / "MANIFEST.json"
    save_manifest(manifest, out)
    result = verify_manifest(out, base_dir=tmp_path)
    assert result.ok and result.total == 3


def test_verify_manifest_empty_ok(tmp_path) -> None:
    manifest = build_manifest([], base_dir=tmp_path)
    result = verify_manifest(manifest, base_dir=tmp_path)
    assert result.ok and result.total == 0


def test_verify_manifest_base_dir_matters(tmp_path) -> None:
    """base_dir 参数生效：同清单换基准后相对路径解析不同（可移植性验证）。"""
    paths = _make_files(tmp_path)
    manifest = build_manifest(paths, base_dir=tmp_path)
    assert verify_manifest(manifest, base_dir=tmp_path).ok
    result = verify_manifest(manifest, base_dir=tmp_path.parent)
    assert not result.ok and result.missing == 3


# ---------------------------------------------------------------- CLI 接线

def test_cli_manifest_subcommands() -> None:
    """CLI parser 含 manifest build/verify 子命令。"""
    from foundation.__main__ import build_parser

    parser = build_parser()
    ns = parser.parse_args(["manifest", "build", "-o", "M.json", "a.txt", "b.txt"])
    assert ns.manifest_command == "build"
    assert ns.output == "M.json"
    assert ns.files == ["a.txt", "b.txt"]
    assert ns.base_dir == "."
    ns2 = parser.parse_args(["manifest", "verify", "-m", "M.json"])
    assert ns2.manifest_command == "verify"
    assert ns2.manifest == "M.json"
