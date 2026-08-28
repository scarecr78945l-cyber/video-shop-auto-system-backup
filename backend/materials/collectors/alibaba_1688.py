"""1688 商品视频与同款图采集器（子代理 B2'；同构于 TaobaoReferencesCollector，context 2.3）。

- fixtures 离线模式（默认，config.alibaba.fixtures_mode=True）：读
  backend/fixtures/materials/alibaba_1688.json，零登录态零网络（R-M2-17）；
- source_platform 口径（context 1.1）：**"1688"**；
- auto 模式（骨架）：Playwright 共享 Chrome（CDP，config.alibaba.cdp_port），
  选择器从 config.alibaba.selectors 读取；真实浏览器链路未验证不实现细节（抛 NotImplementedError）；
- 降级（R-M2-08）/ page_changed（P-003）/ 错误分类 与 taobao_refs.py 完全同口径
  （复用 _RefsCollectorBase 公共实现）。
"""

from __future__ import annotations

from .taobao_refs import _RefsCollectorBase

__all__ = ["AlibabaCollector"]


class AlibabaCollector(_RefsCollectorBase):
    """1688 商品视频与同款图采集器（context/README.md 2.3；source_platform="1688"）。"""

    source_platform = "1688"
    platform_key = "alibaba"
    fixtures_filename = "alibaba_1688.json"
    config_attr = "alibaba"
