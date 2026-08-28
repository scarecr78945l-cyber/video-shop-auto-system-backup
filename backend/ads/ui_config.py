"""M5 自动小店投放 · 托管 UI 页面契约（v0.3 执行层公共骨架）。

页面与选择器全部配置化（P-003/R3 防复发：投放后台改版只改配置不崩代码）。
真实选择器值待实机探针校准后填入（登录态/实机探针在总控待用户确认清单）；
fixtures 模拟阶段值可为空，由 Mock 页面承载行为。
表单位置：https://channels.weixin.qq.com/shop 后台「小店投放」入口（URL 模板待实机确认）。
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ShopAdsSelectors(BaseModel):
    """托管后台选择器集合（按页面分组，key 语义化）。

    fixtures 阶段全部允许为空字符串：Mock 页面不依赖真实选择器；
    实机校准后填入真实 CSS 选择器，代码零改动。
    """

    # ---- 托管首页 ----
    home_balance: str = ""               # 可用余额文本
    home_tab_counts: str = ""            # 已托管/托管中/待托管计数
    home_add_button: str = ""            # 「添加托管商品」按钮
    # ---- 添加托管商品页（两步之 ①）----
    add_product_row: str = ""            # 商品行（含 checkbox）
    add_product_checkbox: str = ""       # 商品勾选（行内）
    add_product_bucket: str = ""         # 分桶标签（机会品/热搜品/优质商品/潜力商品）
    add_product_next: str = ""           # 下一步（进入投放设置）
    add_product_count_hint: str = ""     # 已选数量提示（≤50/批上限校验）
    # ---- 投放设置页（两步之 ②）----
    settings_target_roi: str = ""        # 目标单选：成交ROI
    settings_target_net_roi: str = ""    # 目标单选：净成交ROI（秒退不扣费）
    settings_target_goods: str = ""      # 目标单选：商品成交
    settings_roi_input: str = ""         # 目标ROI 输入框
    settings_roi_recommended: str = ""   # 系统推荐 ROI（取推荐值来源）
    settings_material_row: str = ""      # 素材库行（勾选用）
    settings_material_checkbox: str = "" # 素材勾选（含视频号形象）
    settings_submit: str = ""            # 提交投放
    settings_error_banner: str = ""      # 页面校验反馈（余额不足/素材未过审）
    # ---- 投放管理列表（监控回读 v0.4 用，本任务仅预留）----
    list_row: str = ""                   # 投放列表行
    list_diagnosis: str = ""             # 智能诊断单元格
    list_impressions: str = ""           # 曝光单元格
    list_spend: str = ""                 # 花费单元格
    list_gmv: str = ""                   # 成交金额单元格
    list_subsidy: str = ""               # 平台补贴单元格
    list_ops: str = ""                   # 操作（查看详情/添加素材）


class ShopAdsPages(BaseModel):
    """托管后台页面 URL 模板（实机校准后填入；fixtures 用 file:// 或假地址）。"""

    home: str = ""
    add_product: str = ""
    settings: str = ""
    campaign_list: str = ""


class ShopAdsUiConfig(BaseModel):
    """v0.3 执行层 UI 配置：页面/选择器/节奏参数（ADS_ 前缀环境变量可覆盖）。"""

    pages: ShopAdsPages = Field(default_factory=ShopAdsPages)
    selectors: ShopAdsSelectors = Field(default_factory=ShopAdsSelectors)
    batch_size: int = 50                  # 单批托管上限（平台硬限 ≤50）
    item_interval_s: float = 2.0          # 单个商品操作间隔（防风控）
    page_timeout_ms: int = 15000          # 页面显式等待超时
    screenshot_dir: str = "data/ads/evidence"  # page_changed/失败证据截图目录
    page_signature: dict[str, str] = Field(default_factory=dict)  # 页面特征元素（page_changed 检测锚点）

    @property
    def selectors_map(self) -> dict[str, str]:
        return self.selectors.model_dump()

    def export_ui_facts(self) -> dict[str, Any]:
        """给证据 JSON / 探针脚本用的 UI 事实快照（不含任何凭证）。"""
        return {
            "pages": self.pages.model_dump(),
            "selectors": self.selectors.model_dump(),
            "batch_size": self.batch_size,
            "item_interval_s": self.item_interval_s,
            "page_timeout_ms": self.page_timeout_ms,
        }
