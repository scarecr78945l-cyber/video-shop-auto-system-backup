"""视频号直链签名器（signer）——接口化可替换（R-M2-03）。

分层契约（_management/modules/m2-materials/context/README.md 2.2）：
- 页面层（Playwright 共享浏览器）负责拿视频 id 与作者信息；
- 直链解析层通过 SignatureProvider 注入请求头/查询参数后拿直链；
- 签名算法随平台版本变化 → 只改本文件/替换实现，不崩采集器（R-M2-03）。

纪律（宪法第 4/11 节 + P-004 + R-M2-03）：
- 禁止在代码/文档/日志中写死真实签名算法与明文密钥（凭据一律走环境变量）；
- RealSignatureProvider 在「共享浏览器登录态 + 抓包校准」完成前必须明确报错，
  不允许留假算法（验收标准第 3 条）。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class SignatureProvider(ABC):
    """直链签名器接口：给定请求上下文，返回需注入的请求头与查询参数。

    sign() 统一返回结构（两个键恒存在，值可为空 dict）：
    - "headers": 随下载/页面请求注入的请求头（如 referer / user-agent / 自定义签名头）；
    - "query":   追加到目标 URL 的查询参数（如签名参数）。

    签名算法变化时只需替换/修改 SignatureProvider 实现（signer 接口化可替换），
    采集器代码无需改动。
    """

    @abstractmethod
    def sign(self, params: dict[str, Any], url: str) -> dict[str, Any]:
        """对给定请求签名。

        :param params: 请求上下文（如 {"video_id": ...}，须为可序列化 JSON）
        :param url: 目标直链/接口 URL（签名可能需要基于它计算）
        :return: {"headers": {...}, "query": {...}}
        """
        raise NotImplementedError


class MockSignatureProvider(SignatureProvider):
    """fixtures/测试用签名器：返回构造时配置的固定签名值（可配置）。

    用于离线全链路验证 signer 注入链路（验收标准第 3 条）：
    resolve_direct_url 注入后结果包含本签名器的固定值。
    """

    def __init__(
        self,
        fixed_query: dict[str, Any] | None = None,
        fixed_headers: dict[str, Any] | None = None,
    ):
        self.fixed_query = dict(fixed_query or {})
        self.fixed_headers = dict(fixed_headers or {})

    def sign(self, params: dict[str, Any], url: str) -> dict[str, Any]:
        # 固定值签名：忽略 params/url（mock 语义），返回可配置的固定注入内容
        return {"headers": dict(self.fixed_headers), "query": dict(self.fixed_query)}


class RealSignatureProvider(SignatureProvider):
    """真实视频号签名器（骨架，未实现）。

    R-M2-03 纪律：签名算法必须基于「共享浏览器登录态 + 抓包校准」实现；
    校准完成前 sign() 一律 raise NotImplementedError（明确报错，不留假算法）。
    构造函数接收配置（预留）：校准后实现可读取签名所需配置（如算法版本/开关），
    凭据只走环境变量（P-004），禁止把明文密钥写进代码/文档/日志。
    """

    def __init__(self, config: Any | None = None):
        # config 预留：校准后实现读取（本骨架不读取任何真实凭据，不实现任何算法）
        self.config = config

    def sign(self, params: dict[str, Any], url: str) -> dict[str, Any]:
        raise NotImplementedError(
            "RealSignatureProvider 未实现：需共享浏览器登录态 + 抓包校准"
            "（_management/modules/m2-materials/risks.md R-M2-03；pitfall-log P-002/P-003）。"
            "校准完成前请用 MockSignatureProvider 或 fixtures 模式；"
            "实现时只改本文件（signer 接口化可替换，不崩采集器）。"
        )
