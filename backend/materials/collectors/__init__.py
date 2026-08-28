"""M2 采集器侧封装包（collectors）。

当前交付：TikTokDownloader 二次封装（抖音/快手/小红书批量下载 CLI 封装）。
- 仅覆盖抖音/快手/小红书（R-M2-04）；视频号不在本封装范围（R-M2-05，自研采集器批次 3）。
- 外部 CLI 子进程 + 超时 + 输出解析 + 错误分类（对齐 downloader.py 码表）；
  与下载中台解耦：本封装只产出文件清单，任务账本由中台/上层管理。
- 零真实二进制依赖：开发/CI 全走 fake CLI fixtures（R-M2-17）。
"""

from __future__ import annotations

from .tiktok_wrapper import TikTokDownloaderCLI, TikTokDownloaderError  # noqa: F401

__all__ = ["TikTokDownloaderCLI", "TikTokDownloaderError"]
