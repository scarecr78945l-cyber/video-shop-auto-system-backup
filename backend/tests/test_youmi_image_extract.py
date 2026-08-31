"""A6 有米云图片提取收敛测试（v1.1 迭代，零浏览器零登录态）。

背景（S3c 真实采集结论，selector-log.md 第 2 节）：有米云 `_extract_images`
在真实页面 **imgs=0**——商品图疑似 lazy 加载（src 为 data:/blob: 占位符、data-src
非 http / 相对路径），旧实现 `src or data-src` 的 or 短路导致 data-src 永不读取；
fixtures 中带 image_urls 的样本与真实行为不一致（R-25 漂移点）。

本文件用 fake locator/img 覆盖纯逻辑，不依赖 Playwright：
- lazy 属性提取命中（data-src / data-original / data-lazy-src / srcset 取首个候选）；
- blob:/data: 过滤（含 data: SVG 内嵌 http 命名空间不误收）；
- 空图集兜底（列容器未命中 → 回退行内 img；全空 → []）；
- 收窄到商品列容器（title_cell 内 img 优先，排除非商品图）。
"""

import pytest

from sourcing.collectors.youmi import LAZY_IMG_ATTRS, _first_http_url, YoumiCollector
from sourcing.config import load_config


# --------------------------------------------------------------------------- fakes


class FakeImg:
    """模拟 Playwright ElementHandle：get_attribute 按属性字典返回。"""

    def __init__(self, attrs):
        self._attrs = attrs

    def get_attribute(self, name):
        return self._attrs.get(name)


class FakeBg:
    """模拟 .ys-bg-img 元素：style 属性内联 background-image（P-033）。"""

    def __init__(self, style_attr, computed=None):
        self._style = style_attr
        self._computed = computed if computed is not None else style_attr

    def get_attribute(self, name):
        if name == "style":
            return self._style
        return None

    def evaluate(self, js):
        return self._computed


class FakeImgLocator:
    def __init__(self, imgs):
        self._imgs = imgs

    def all(self):
        return list(self._imgs)


class FakeTd:
    def __init__(self, imgs, bgs=None):
        self._imgs = imgs
        self._bgs = bgs or []

    def locator(self, sel):
        if sel == "img":
            return FakeImgLocator(self._imgs)
        if sel == ".ys-bg-img":
            return FakeImgLocator(self._bgs)
        raise AssertionError(f"unexpected selector: {sel!r}")


class FakeTdLocator:
    def __init__(self, cell_imgs, cell_bgs=None):
        self._cell_imgs = cell_imgs  # list[list[FakeImg]]
        self._cell_bgs = cell_bgs or [[] for _ in cell_imgs]  # list[list[FakeBg]]

    def nth(self, i):
        imgs = self._cell_imgs[i] if 0 <= i < len(self._cell_imgs) else []
        bgs = self._cell_bgs[i] if 0 <= i < len(self._cell_bgs) else []
        return FakeTd(imgs, bgs)


class FakeRow:
    """模拟 Playwright Locator：locator("td") 按列取图，locator("img") 行内全图。"""

    def __init__(self, cell_imgs, row_imgs=None, cell_bgs=None, row_bgs=None):
        self._cell_imgs = cell_imgs
        self._row_imgs = (
            list(row_imgs) if row_imgs is not None else [i for c in cell_imgs for i in c]
        )
        self._cell_bgs = cell_bgs or [[] for _ in cell_imgs]
        self._row_bgs = (
            list(row_bgs)
            if row_bgs is not None
            else [b for c in self._cell_bgs for b in c]
        )

    def locator(self, sel):
        if sel == "td":
            return FakeTdLocator(self._cell_imgs, self._cell_bgs)
        if sel == "img":
            return FakeImgLocator(self._row_imgs)
        if sel == ".ys-bg-img":
            return FakeImgLocator(self._row_bgs)
        raise AssertionError(f"unexpected selector: {sel!r}")


class BrokenRow:
    """任何 locator 调用都抛异常（防御性兜底测试）。"""

    def locator(self, sel):
        raise RuntimeError("boom")


# --------------------------------------------------------- _first_http_url 纯逻辑


def test_youmi_first_http_src_placeholder_then_data_src():
    """src 为 data: 占位符 → 跳过，继续读 data-src（旧实现 or 短路的根因场景）。"""
    assert _first_http_url({"src": "data:image/gif;base64,R0lGODlhAQAB"}) == ""
    assert (
        _first_http_url(
            {"src": "data:image/gif;base64,R0lGODlhAQAB", "data-src": "https://cdn.example.com/p1.jpg"}
        )
        == "https://cdn.example.com/p1.jpg"
    )


def test_youmi_first_http_other_lazy_attrs():
    """data-original / data-lazy-src / data-lazy 优先级依次生效。"""
    assert _first_http_url({"data-original": "https://cdn.example.com/p2.jpg"}) == "https://cdn.example.com/p2.jpg"
    assert _first_http_url({"data-lazy-src": "https://cdn.example.com/p3.jpg"}) == "https://cdn.example.com/p3.jpg"
    assert _first_http_url({"data-lazy": "https://cdn.example.com/p4.jpg"}) == "https://cdn.example.com/p4.jpg"


def test_youmi_first_http_srcset_takes_first_candidate():
    """srcset 多个候选 → 取第一个 http 候选（1x 优先）。"""
    assert (
        _first_http_url({"srcset": "https://cdn.example.com/p5_200.jpg 1x, https://cdn.example.com/p5_400.jpg 2x"})
        == "https://cdn.example.com/p5_200.jpg"
    )
    # src 为占位、srcset 为真实候选 → srcset 命中
    assert (
        _first_http_url(
            {
                "src": "data:image/gif;base64,R0lGODlhAQAB",
                "srcset": "https://cdn.example.com/p5_200.jpg 1x, https://cdn.example.com/p5_400.jpg 2x",
            }
        )
        == "https://cdn.example.com/p5_200.jpg"
    )


def test_youmi_first_http_rejects_blob_data_relative():
    """blob:/data:/相对路径/protocol-relative 一律过滤，只收 http(s)。"""
    assert _first_http_url({"src": "blob:https://console.youshu.youcloud.com/abcd"}) == ""
    assert _first_http_url({"data-src": "data:image/png;base64,xxx"}) == ""
    assert _first_http_url({"src": "/static/img/thumb.jpg"}) == ""
    assert _first_http_url({"data-src": "//img.example.com/thumb.jpg"}) == ""
    # data: SVG 可能内嵌 http 命名空间，按前缀整值跳过（不扫描内嵌 http）
    svg = 'data:image/svg+xml;utf8,<svg xmlns="http://www.w3.org/2000/svg"><rect/></svg>'
    assert _first_http_url({"src": svg}) == ""


def test_youmi_first_http_priority_and_empty():
    """优先级：src > data-src；全空/未知键 → 空串。"""
    assert (
        _first_http_url({"src": "https://cdn.example.com/a.jpg", "data-src": "https://cdn.example.com/b.jpg"})
        == "https://cdn.example.com/a.jpg"
    )
    assert _first_http_url({}) == ""
    assert _first_http_url({"data-original": "  "}) == ""


# ------------------------------------------------------------------- _extract_images


def test_youmi_extract_lazy_images_from_title_cell():
    """行内 img src 为 data: 占位 → 用 data-src / srcset 命中真实 http URL。"""
    img = FakeImg(
        {
            "src": "data:image/gif;base64,R0lGODlhAQAB",
            "data-src": "https://cdn.example.com/ym-001.jpg",
        }
    )
    row = FakeRow([[FakeImg({})], [img]])
    assert YoumiCollector._extract_images(row, title_cell=1) == ["https://cdn.example.com/ym-001.jpg"]


def test_youmi_extract_srcset_candidate():
    """srcset 图片属性命中首个候选。"""
    img = FakeImg({"srcset": "https://cdn.example.com/ym-002_200.jpg 1x, https://cdn.example.com/ym-002_400.jpg 2x"})
    row = FakeRow([[img]])
    assert YoumiCollector._extract_images(row, title_cell=0) == ["https://cdn.example.com/ym-002_200.jpg"]


def test_youmi_extract_blob_data_only_returns_empty():
    """整行只有 blob:/data: 占位图 → 空列表（不误收，也不抛错）。"""
    row = FakeRow(
        [
            [FakeImg({"src": "blob:https://console.youshu.youcloud.com/abcd"})],
            [FakeImg({"data-src": "data:image/png;base64,xxx"})],
        ]
    )
    assert YoumiCollector._extract_images(row, title_cell=1) == []


def test_youmi_extract_narrows_to_title_cell_excludes_logo():
    """收窄：title_cell=1 只取商品列图片，排除列 0 的 logo/排名图。"""
    logo = FakeImg({"src": "https://cdn.example.com/logo.png"})
    product = FakeImg({"data-src": "https://cdn.example.com/ym-003.jpg"})
    row = FakeRow([[logo], [product], [FakeImg({"src": "https://cdn.example.com/badge.png"})]])
    assert YoumiCollector._extract_images(row, title_cell=1) == ["https://cdn.example.com/ym-003.jpg"]


def test_youmi_extract_empty_title_cell_falls_back_to_row_imgs():
    """防御：商品列无图（页面改版/结构差异）→ 回退行内 img，保持旧版行为。"""
    img = FakeImg({"data-original": "https://cdn.example.com/ym-004.jpg"})
    row = FakeRow([[FakeImg({})], [img]])
    assert YoumiCollector._extract_images(row, title_cell=1) == ["https://cdn.example.com/ym-004.jpg"]


def test_youmi_extract_no_title_cell_uses_row_imgs():
    """title_cell=None（config columns 无 title）→ 行内全图（与旧版一致）。"""
    img = FakeImg({"data-src": "https://cdn.example.com/ym-005.jpg"})
    row = FakeRow([[img]])
    assert YoumiCollector._extract_images(row) == ["https://cdn.example.com/ym-005.jpg"]


def test_youmi_extract_dedup_and_cap():
    """去重 + 最多 4 张。"""
    imgs = [
        FakeImg({"data-src": f"https://cdn.example.com/dup-{i % 2}.jpg"}) for i in range(6)
    ]  # 6 张但只有 2 个唯一 URL
    assert len(YoumiCollector._extract_images(FakeRow([imgs]), title_cell=0)) == 2
    distinct = [FakeImg({"data-src": f"https://cdn.example.com/cap-{i}.jpg"}) for i in range(6)]
    assert len(YoumiCollector._extract_images(FakeRow([distinct]), title_cell=0)) == 4


def test_youmi_extract_never_raises_on_broken_row():
    """异常兜底：locator 抛错 → []，不阻断采集。"""
    assert YoumiCollector._extract_images(BrokenRow(), title_cell=0) == []
    assert YoumiCollector._extract_images(BrokenRow()) == []


def test_youmi_lazy_attrs_constant_order():
    """LAZY_IMG_ATTRS 顺序：src 优先于 data-src 等 lazy 属性。"""
    assert LAZY_IMG_ATTRS[0] == "src"
    assert "data-src" in LAZY_IMG_ATTRS and "srcset" in LAZY_IMG_ATTRS


# ------------------------------------------------------- P-033 background-image（有米云真实图载体）

BG_URL = "https://lp-ag-v2.umcdn.cn/4d00c059633d852632fb72f987b8bb7d/material.jpeg"
BG_STYLE = (
    f"background-color: rgb(255,255,255); width: 64px; height: 64px; "
    f'background-image: url("{BG_URL}?auth_key=abc");'
)


def test_youmi_bg_image_extract_from_style():
    """P-033：.ys-bg-img style 内联 background-image → 提取真实 URL。"""
    row = FakeRow([[FakeImg({})]], cell_bgs=[[FakeBg(BG_STYLE)]])
    assert YoumiCollector._extract_images(row, title_cell=0) == [BG_URL + "?auth_key=abc"]


def test_youmi_bg_preferred_over_img():
    """P-033：bg 命中优先于 img lazy 兜底（真实页面既有 bg 又有占位 img 时）。"""
    img = FakeImg({"src": "data:image/gif;base64,R0lGODlhAQAB"})
    row = FakeRow([[img]], cell_bgs=[[FakeBg(BG_STYLE)]])
    assert YoumiCollector._extract_images(row, title_cell=0) == [BG_URL + "?auth_key=abc"]


def test_youmi_bg_falls_back_to_computed_style():
    """P-033：style 属性无 url → getComputedStyle 兜底。"""
    bg = FakeBg("width: 64px;", computed=f'url("{BG_URL}?k=1")')
    row = FakeRow([[]], cell_bgs=[[bg]])
    assert YoumiCollector._extract_images(row, title_cell=0) == [BG_URL + "?k=1"]


def test_youmi_bg_missing_falls_back_to_img():
    """P-033：无 bg 元素 → 回退 img lazy 提取（旧行为不回归）。"""
    img = FakeImg({"data-src": "https://cdn.example.com/ym-bg-fallback.jpg"})
    row = FakeRow([[img]])
    assert YoumiCollector._extract_images(row, title_cell=0) == ["https://cdn.example.com/ym-bg-fallback.jpg"]


def test_youmi_bg_no_url_returns_empty():
    """P-033：bg style 无 http url（相对/data）→ 空（不误收）。"""
    bg = FakeBg("background-image: url('/local/img.png');")
    row = FakeRow([[]], cell_bgs=[[bg]])
    assert YoumiCollector._extract_images(row, title_cell=0) == []


# ------------------------------------------------------- A6 合并逻辑（不回归）

def test_a6_youmi_selector_merge_unchanged():
    """A6 不新增/不修改 youmi 选择器键：合并结果仍与默认一致（行为零变化）。"""
    from sourcing.collectors.youmi import DEFAULT_SELECTORS as YOUMI_DEFAULTS

    cfg = load_config()
    col = YoumiCollector(cfg.youmi)
    assert col.selectors == YOUMI_DEFAULTS
    # 显式核对关键键未被图片收敛改动
    assert col.selectors["row"] == ".el-table__body-wrapper tr"
    assert col.selectors["columns"] == {"rank": 0, "title": 1, "price": 5, "sales": 7}
