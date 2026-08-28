"""采集器基类：Collector / QuoteCollector / CollectorError。"""

from __future__ import annotations

from abc import ABC, abstractmethod

from ..config import CollectorConfig
from ..models import SourceItem

MAX_ITEMS_PER_BOARD = 200


class CollectorError(RuntimeError):
    """采集失败（限流/登录失效/页面改版等，交给调度器归类）。"""

    def __init__(self, message: str, error_code: str = "UNEXPECTED"):
        super().__init__(message)
        self.error_code = error_code


class Collector(ABC):
    """一个来源（平台）的采集器。"""

    source: str = ""
    default_boards: list[str] = []

    def __init__(self, config: CollectorConfig):
        self.config = config

    @property
    def enabled(self) -> bool:
        return self.config.enabled

    @property
    def boards(self) -> list[str]:
        if self.config.boards:
            return [b.name for b in self.config.boards if b.enabled]
        return self.default_boards

    @abstractmethod
    def collect_board(self, board: str, limit: int = MAX_ITEMS_PER_BOARD) -> list[SourceItem]:
        """采集单个榜单。失败抛 CollectorError（带 error_code 分类）。"""

    @abstractmethod
    def probe(self) -> bool:
        """探针板：熔断恢复时调用，检查平台是否可访问。"""

    def collect_all(self, limit: int = MAX_ITEMS_PER_BOARD) -> dict[str, list[SourceItem]]:
        out: dict[str, list[SourceItem]] = {}
        for board in self.boards:
            out[board] = self.collect_board(board, limit=limit)
        return out


class QuoteCollector(ABC):
    """询价采集器（1688 逐 SKU 真实询价 / 淘宝参考素材）。"""

    source: str = ""

    def __init__(self, config: CollectorConfig):
        self.config = config

    @abstractmethod
    def quote(self, item: SourceItem) -> list[object]:
        """对候选条目询价/查参考，返回 Quote / Reference 列表。"""
