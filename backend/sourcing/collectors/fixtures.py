"""离线 fixtures 采集器：从本地 JSON 样本回放数据，零登录态零网络。

fixtures 目录结构（SOURCING_FIXTURES_DIR 可改，默认 backend/fixtures）：
  youmi.json            {board: [item, ...]}  有米云商品榜
  opportunities.json    {board: [item, ...]}  视频号商机中心
  doudian.json          {board: [item, ...]}  抖店电商罗盘
  alibaba_quotes.json   {platform_item_id: [quote, ...]}  1688 询价
  taobao_references.json {platform_item_id: {images:[...], ...}}
  ad_snapshots.json     {category: {roi: float, sales: float}}  投放转化回流
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..config import SourcingConfig
from ..models import Quote, SourceItem
from .base import Collector, QuoteCollector

FIXTURE_FILES = {
    "youmi": "youmi.json",
    "opportunities": "opportunities.json",
    "doudian": "doudian.json",
    "alibaba": "alibaba_quotes.json",
    "taobao": "taobao_references.json",
    "ad_snapshots": "ad_snapshots.json",
}

YOUMI_BOARDS = ["商品榜"]
OPPORTUNITY_BOARDS = ["机会品"]
DOUDIAN_BOARDS = ["商品榜", "飙升榜"]


def _load(path: Path) -> Any:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


class FixtureCollector(Collector):
    """从 fixtures JSON 回放榜单数据。"""

    source = ""
    default_boards: list[str] = []

    def __init__(self, source: str, config: SourcingConfig):
        self.source = source
        self.default_boards = {
            "youmi": YOUMI_BOARDS,
            "opportunities": OPPORTUNITY_BOARDS,
            "doudian": DOUDIAN_BOARDS,
        }[source]
        super().__init__(getattr(config, source))
        self.config_all = config
        self._cache: dict[str, dict[str, list[dict]]] = {}

    def _data(self) -> dict[str, list[dict]]:
        if self.source not in self._cache:
            self._cache[self.source] = _load(
                self.config_all.fixtures_dir / FIXTURE_FILES[self.source]
            )
        return self._cache[self.source]

    def collect_board(self, board: str, limit: int = 200) -> list[SourceItem]:
        rows = self._data().get(board, [])
        items: list[SourceItem] = []
        for i, row in enumerate(rows[:limit], start=1):
            row = dict(row)
            row.setdefault("platform_item_id", f"{self.source}-{board}-{i}")
            items.append(
                SourceItem(
                    source=self.source,
                    board=board,
                    platform_item_id=str(row["platform_item_id"]),
                    title=str(row.get("title", "")),
                    price=float(row.get("price", 0) or 0),
                    sales=int(row.get("sales", 0) or 0),
                    rank=int(row.get("rank", 0) or 0),
                    category=str(row.get("category", "")),
                    image_urls=list(row.get("image_urls", [])),
                    raw=row,
                )
            )
        return items

    def probe(self) -> bool:
        return self.source in self._data() or self._data() is not None


class FixtureQuoteCollector(QuoteCollector):
    """从 fixtures 回放 1688 询价 / 淘宝参考。"""

    source = ""

    def __init__(self, source: str, config: SourcingConfig):
        self.source = source
        self.config_all = config
        super().__init__(getattr(config, source))
        self._quotes: dict[str, list[dict]] = _load(
            config.fixtures_dir / FIXTURE_FILES["alibaba"]
        )
        self._taobao: dict[str, dict] = _load(
            config.fixtures_dir / FIXTURE_FILES["taobao"]
        )

    def quote(self, item: SourceItem) -> list[object]:
        if self.source == "alibaba":
            return [Quote(**q) for q in self._quotes.get(item.platform_item_id, [])]
        # taobao 参考素材：返回 URL 列表（后续素材模块消费）
        ref = self._taobao.get(item.platform_item_id, {})
        images = ref.get("images", [])
        return [{"kind": "reference_images", "urls": images}] if images else []


def load_ad_snapshots(config: SourcingConfig) -> dict[str, dict[str, float]]:
    """读取投放转化回流样本：{category: {roi, sales}}。"""
    data = _load(config.fixtures_dir / FIXTURE_FILES["ad_snapshots"])
    return {k: {"roi": float(v.get("roi", 0)), "sales": float(v.get("sales", 0))} for k, v in data.items()}
