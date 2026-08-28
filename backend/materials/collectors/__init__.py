"""M2 采集器侧封装包（collectors）。

当前交付：
- TikTokDownloader 二次封装（抖音/快手/小红书批量下载 CLI 封装，R-M2-04/R-M2-05）；
- BoardImageCache 榜单图缓存（有米云 youmi 已打通；考古加 kaogujia 预留，多源接口化，R-M2-09）。
- 外部 CLI 子进程 + 超时 + 输出解析 + 错误分类（对齐 downloader.py 码表）；
  与下载中台解耦：本封装只产出文件清单，任务账本由中台/上层管理。
- 零真实二进制依赖：开发/CI 全走 fake CLI fixtures（R-M2-17）。
"""

from __future__ import annotations

from .board_image_cache import BoardImageCache  # noqa: F401
from .tiktok_wrapper import TikTokDownloaderCLI, TikTokDownloaderError  # noqa: F401
from .wechat_video import WechatVideoCollector, WechatVideoError  # noqa: F401
from .signer import SignatureProvider, MockSignatureProvider, RealSignatureProvider  # noqa: F401

__all__ = [
    "BoardImageCache",
    "TikTokDownloaderCLI",
    "TikTokDownloaderError",
    "WechatVideoCollector",
    "WechatVideoError",
    "SignatureProvider",
    "MockSignatureProvider",
    "RealSignatureProvider",
]
