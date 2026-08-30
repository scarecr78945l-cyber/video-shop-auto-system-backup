"""M6 v1.2：M3 生图产物媒体预览端点测试（/api/optimization/media/{id}）。"""

from pathlib import Path

import pytest
from PIL import Image

from api_testing import login, make_client


@pytest.fixture()
def client(tmp_path):
    client, services, creds, _ = make_client(tmp_path)
    with client:
        yield client, services, creds


def _make_png(tmp_path: Path, name: str = "img.png") -> Path:
    p = tmp_path / name
    Image.new("RGB", (10, 10), (200, 60, 60)).save(p, format="PNG")
    return p


def test_media_preview_ok(client, tmp_path):
    """① 有效 OptImage → 200 图片流。"""
    c, services, creds = client
    login(c, creds)
    from optimization.tables import OptImage

    png = _make_png(tmp_path)
    with services.m3_db.session() as s:
        s.add(OptImage(
            image_id="img-001", batch_id="batch-1", product_id="p1",
            image_type="main", variant_no=1, file_path=str(png),
        ))
    c, _, _ = client
    resp = c.get("/api/optimization/media/img-001")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("image/png")
    assert resp.content[:8] == b"\x89PNG\r\n\x1a\n"  # PNG 魔数


def test_media_preview_not_found(client):
    """② 不存在的 image_id → 404。"""
    c, _, creds = client
    login(c, creds)
    resp = c.get("/api/optimization/media/nope")
    assert resp.status_code == 404


def test_media_preview_path_traversal_blocked(client, tmp_path):
    """③ 路径穿越（file_path 含 ..）→ 404 拒绝。"""
    c, services, creds = client
    login(c, creds)
    from optimization.tables import OptImage

    with services.m3_db.session() as s:
        s.add(OptImage(
            image_id="img-evil", batch_id="batch-1", product_id="p1",
            image_type="main", variant_no=1,
            file_path=str(tmp_path / ".." / ".." / ".." / "etc" / "passwd"),
        ))
    c, _, _ = client
    resp = c.get("/api/optimization/media/img-evil")
    assert resp.status_code == 404


def test_media_preview_relative_blocked(client, tmp_path):
    """④ 非绝对路径 → 404。"""
    c, services, creds = client
    login(c, creds)
    from optimization.tables import OptImage

    with services.m3_db.session() as s:
        s.add(OptImage(
            image_id="img-rel", batch_id="batch-1", product_id="p1",
            image_type="main", variant_no=1, file_path="relative/path.png",
        ))
    c, _, _ = client
    resp = c.get("/api/optimization/media/img-rel")
    assert resp.status_code == 404
