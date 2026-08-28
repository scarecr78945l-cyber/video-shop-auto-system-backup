"""M5 自动小店投放（商品托管）· 投放设置（托管两步之②）执行层（v0.3）。

覆盖「投放设置」全部动作（08 文档四②/四③）：
  1. 目标三选一：成交ROI / 净成交ROI（秒退不扣费）/ 商品成交（target_type=roi/net_roi/goods）；
  2. 目标 ROI 填值：系统推荐优先、可配置覆盖（target_roi_override）；
  3. 素材绑定：evaluation 优选顺序 高效(efficient) > 潜力(potential) > 探索期(exploring)，
     且只选 upload_status == "approved"（审核通过）的素材（10 文档：审核不通过/源文件损坏
     投放时不支持选择）；
  4. 提交与页面校验：余额不足 / 素材未过审 → blocked + 人工接管（error_code 复用 09 码表
     PLATFORM_REJECT）。

本文件全部基于 PageOps 抽象接口（interfaces.py）+ ShopAdsUiConfig 配置驱动
（ui_config.py，选择器 key 化，改版只改配置不崩代码 P-003）；fixtures 阶段由本文件内
独立实现的 MockSettingsPage 承载行为，不触碰真实浏览器；真实 Playwright 适配器后续
接入时本模块接口不变。

口径（data-audit DA-001）：金额一律「分」（int），ROI 为浮点倍数（不走分）；
枚举英文（中文仅注释/展示映射）；错误码复用 09 码表。
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Iterable

from .interfaces import PageOps
from .ui_config import ShopAdsUiConfig

# ---------------------------------------------------------------- 常量

# 素材 evaluation 优选优先级：高效 > 潜力 > 探索期（数字越小越优先）。
# 与 M2 共口径（exploring/efficient/potential）；未知标签按最低优先级兜底，不排除。
_EVALUATION_PRIORITY: dict[str, int] = {
    "efficient": 0,   # 高效
    "potential": 1,   # 潜力
    "exploring": 2,   # 探索期
}
_EVALUATION_FALLBACK_PRIORITY = 3

# 目标三选一：英文枚举 → ui_config 选择器 key（中文映射：roi=成交ROI / net_roi=净成交ROI / goods=商品成交）
_TARGET_SELECTOR_KEYS: dict[str, str] = {
    "roi": "settings_target_roi",
    "net_roi": "settings_target_net_roi",
    "goods": "settings_target_goods",
}
_TARGET_LABELS: dict[str, str] = {
    "roi": "成交ROI",
    "net_roi": "净成交ROI",
    "goods": "商品成交",
}

# 页面校验反馈关键词（08 文档四③：余额不足/素材未过审 → blocked + 人工接管）
_BALANCE_KEYWORDS = ("余额不足",)
_MATERIAL_KEYWORDS = (
    "素材未过审",
    "素材未通过审核",
    "素材审核不通过",
    "素材未审核通过",
    "素材不可投放",
)


@dataclass
class SubmitResult:
    """提交校验结果：passed=False 时 blocked_reason 给出人工接管原因（中文，展示用）。"""

    passed: bool
    blocked_reason: str = ""
    error_code: str = ""


# ---------------------------------------------------------------- 素材优选（纯函数）
def pick_materials(materials: list[dict], limit: int = 3) -> list[dict]:
    """素材优选：只选审核通过（upload_status=="approved"）素材，按 evaluation 优先级
    高效(efficient) > 潜力(potential) > 探索期(exploring) 排序取前 limit。

    同级别按可选字段 (impressions, gmv) 降序稳定排序（缺失/None 视为 0，排同级别末尾）；
    返回保持输入 dict 的字段结构（同引用，不裁剪不复制）。
    审核不通过（rejected）/源文件损坏（corrupt）/审核中（reviewing）等一律排除
    （10 文档：审核不通过或源文件损坏的素材投放时不支持选择）。
    """
    limit = 3 if limit is None else limit
    if limit <= 0:
        return []
    approved = [m for m in materials if m.get("upload_status") == "approved"]
    return sorted(approved, key=_material_sort_key)[:limit]


def _material_sort_key(m: dict) -> tuple:
    """排序键：(优先级升序, 曝光降序, 成交降序)。缺失曝光/成交 → 0（排同级末尾）。"""
    evaluation = m.get("evaluation")
    priority = _EVALUATION_PRIORITY.get(evaluation, _EVALUATION_FALLBACK_PRIORITY)
    impressions = m.get("impressions")
    gmv = m.get("gmv")
    imp = impressions if isinstance(impressions, (int, float)) else 0
    gm = gmv if isinstance(gmv, (int, float)) else 0
    return (priority, -imp, -gm)


# ---------------------------------------------------------------- 提交校验（纯函数）
def validate_submit(
    balance_fen: int,
    min_balance_fen: int,
    materials_ok: bool,
    budget_state: dict | None = None,
) -> SubmitResult:
    """提交前校验（08 文档四③ / 止损规则表 S5/S7）：余额不足、素材不可用、预算超限 → blocked。

    budget_state 由预算硬约束（S7）上游计算后传入，约定形状：
        {"over_limit": bool, "rule": str, ...}   # over_limit=True 表示任一预算超限
    检查优先级：余额 > 素材 > 预算（同时命中时上报优先级最高的一项原因）。
    """
    if balance_fen < min_balance_fen:
        return SubmitResult(passed=False, blocked_reason="余额不足", error_code="PLATFORM_REJECT")
    if not materials_ok:
        return SubmitResult(passed=False, blocked_reason="素材未过审/不可投放", error_code="PLATFORM_REJECT")
    if budget_state and budget_state.get("over_limit"):
        return SubmitResult(passed=False, blocked_reason="预算超限", error_code="PLATFORM_REJECT")
    return SubmitResult(passed=True)


def _parse_banner_error(text: str) -> SubmitResult:
    """解析页面校验反馈文本为 SubmitResult（关键词匹配，命中即 blocked=PLATFORM_REJECT）。"""
    if any(k in text for k in _BALANCE_KEYWORDS):
        return SubmitResult(passed=False, blocked_reason="余额不足", error_code="PLATFORM_REJECT")
    if any(k in text for k in _MATERIAL_KEYWORDS):
        return SubmitResult(passed=False, blocked_reason="素材未过审/不可投放", error_code="PLATFORM_REJECT")
    # 其他平台驳回文本：原样截断上报（PLATFORM_REJECT，记录原因转人工）
    return SubmitResult(passed=False, blocked_reason=text.strip()[:100], error_code="PLATFORM_REJECT")


# ---------------------------------------------------------------- 投放设置表单
class SettingsForm:
    """投放设置表单（托管两步之②）：目标三选一 / ROI 填值 / 素材绑定 / 提交校验。

    全部操作经 PageOps 抽象接口 + ui_config 选择器 key 完成，fixtures 阶段可注入
    MockSettingsPage 离线驱动；显式等待（wait_for）由上层执行器编排负责，本表单
    按「元素已就绪」假设操作。
    """

    def __init__(
        self,
        page: PageOps,
        ui_config: ShopAdsUiConfig,
        target_roi_override: float | None = None,
    ):
        self.page: PageOps = page
        self.ui: ShopAdsUiConfig = ui_config
        self.target_roi_override: float | None = target_roi_override  # 可配置覆盖（优先于系统推荐）
        self.evidence: list[dict] = []  # 操作留痕：{op, selector, ms(耗时), ts(UTC), ...}

    # ------------------------------------------------------------ 内部工具
    def _selector(self, key: str) -> str:
        """取配置选择器；未配置（空串）抛 RuntimeError（fixtures 阶段需注入选择器值）。"""
        selector = getattr(self.ui.selectors, key, "")
        if not selector:
            raise RuntimeError(f"UI 选择器未配置: {key}（fixtures 阶段测试需注入选择器值）")
        return selector

    def _record(self, op: str, selector: str, start: float, **extra: Any) -> None:
        self.evidence.append(
            {
                "op": op,
                "selector": selector,
                "ms": round((time.perf_counter() - start) * 1000, 2),
                "ts": datetime.now(timezone.utc).isoformat(),
                **extra,
            }
        )

    # ------------------------------------------------------------ ① 目标三选一
    def choose_target(self, target_type: str) -> None:
        """点击目标单选：target_type ∈ {"roi","net_roi","goods"}。

        中文映射（展示用）：roi=成交ROI / net_roi=净成交ROI（秒退不扣费）/ goods=商品成交。
        """
        if target_type not in _TARGET_SELECTOR_KEYS:
            raise ValueError(f"未知目标类型: {target_type!r}（可选 roi/net_roi/goods）")
        key = _TARGET_SELECTOR_KEYS[target_type]
        selector = self._selector(key)
        start = time.perf_counter()
        self.page.click(selector)
        self._record(
            "click", selector, start, target=target_type, label=_TARGET_LABELS[target_type]
        )

    # ------------------------------------------------------------ ② ROI 填值
    def fill_roi(self, roi: float) -> None:
        """填目标 ROI 输入框（两位小数格式化，如 2.00）。

        合理性校验：roi ≤ 0 抛 ValueError（高于类目上限由调用方按类目控制，本层只做 >0 校验）。
        """
        if roi <= 0:
            raise ValueError(f"目标 ROI 必须 > 0，收到 {roi!r}")
        selector = self._selector("settings_roi_input")
        value = f"{roi:.2f}"
        start = time.perf_counter()
        self.page.fill(selector, value)
        self._record("fill", selector, start, value=value)

    def read_recommended_roi(self) -> float | None:
        """读页面系统推荐 ROI（settings_roi_recommended）；未配置/无元素/解析失败 → None。"""
        selector = self.ui.selectors.settings_roi_recommended
        if not selector or not self.page.exists(selector):
            return None
        raw = self.page.read_text(selector).strip()
        if not raw:
            return None
        try:
            return float(raw)
        except ValueError:
            return None

    def resolve_roi(self, recommended_roi: float | None) -> float:
        """目标 ROI 取值策略（08 文档四②）：可配置覆盖优先，否则系统推荐值；两者皆无抛 ValueError。"""
        if self.target_roi_override is not None:
            return float(self.target_roi_override)
        if recommended_roi is not None:
            return float(recommended_roi)
        raise ValueError("无可用目标 ROI：系统推荐缺失且未配置覆盖值")

    # ------------------------------------------------------------ ③ 素材绑定
    def bind_materials(self, material_ids: list[str]) -> None:
        """按素材行勾选（settings_material_checkbox 模板，{mid} 占位 material_id）；空列表抛 ValueError。"""
        if not material_ids:
            raise ValueError("素材列表为空：至少绑定 1 个素材（含视频号形象）")
        template = self._selector("settings_material_checkbox")
        start = time.perf_counter()
        for mid in material_ids:
            selector = template.format(mid=mid)
            self.page.click(selector)
            self._record("click", selector, start, mid=mid)
        self._record("bind", template, start, material_ids=list(material_ids))

    # ------------------------------------------------------------ ④ 提交与页面校验
    def submit(self) -> SubmitResult:
        """点提交 → 读 settings_error_banner：有错误文本 → 解析为 blocked；无 → passed。

        选择器未配置/读取失败 → 抛 RuntimeError（TIMEOUT 语义，由上层映射为
        error_code=TIMEOUT 人工接管）；页面无 banner 元素视为无校验失败。
        """
        submit_sel = self._selector("settings_submit")
        start = time.perf_counter()
        self.page.click(submit_sel)
        self._record("click", submit_sel, start, step="submit")

        banner_sel = self.ui.selectors.settings_error_banner
        if not banner_sel:
            raise RuntimeError(
                "读取页面校验反馈超时（TIMEOUT 语义）：settings_error_banner 选择器未配置"
            )
        if not self.page.exists(banner_sel):
            self._record("read", banner_sel, start, note="no_error_banner")
            return SubmitResult(passed=True)
        try:
            text = self.page.read_text(banner_sel).strip()
        except Exception as exc:  # noqa: BLE001 —— 读取失败按 TIMEOUT 语义抛给上层映射
            raise RuntimeError(f"读取页面校验反馈失败（TIMEOUT 语义）：{exc}") from exc
        self._record("read", banner_sel, start, text=text[:80])
        if not text:
            return SubmitResult(passed=True)
        return _parse_banner_error(text)


# ---------------------------------------------------------------- Mock 页面（fixtures）
_MISSING_ALL = "<all>"  # 哨兵：scenario="missing_element" 时任何选择器均视为缺失


class MockSettingsPage:
    """实现 PageOps Protocol 的假页面（投放设置页 fixtures 模拟）。

    与 executor 子代理的 MockPageOps 相互独立（并行解耦，不 import）。
    脚本化场景（scenario）：
      - "happy"：全部操作成功；error banner 文本为空 → submit 通过；
      - "error_banner"：banner 预设校验失败文案（默认"余额不足"，可用 banner_text 覆盖，
        也可用 set_text(selector, text) 精确指定）→ submit 返回 blocked；
      - "missing_element"：所有选择器操作抛 RuntimeError（模拟页面未加载/page_changed），
        或通过 missing=[...] 精确指定缺失选择器。

    记录 operations 操作历史（op/selector/value/ms）与 click 次数/fill 值供测试断言；
    查询方法（exists/read_text/read_attr/count）不写入 operations。
    """

    _DEFAULT_BANNER_TEXT: dict[str, str] = {"error_banner": "余额不足"}

    def __init__(
        self,
        scenario: str = "happy",
        missing: Iterable[str] | None = None,
        banner_text: str = "",
    ):
        if scenario not in ("happy", "error_banner", "missing_element"):
            raise ValueError(f"未知场景: {scenario!r}（可选 happy/error_banner/missing_element）")
        self.scenario: str = scenario
        self._missing: set[str] = set(missing) if missing is not None else set()
        if scenario == "missing_element" and not self._missing:
            self._missing.add(_MISSING_ALL)
        if scenario == "error_banner" and not banner_text:
            banner_text = self._DEFAULT_BANNER_TEXT["error_banner"]
        self._banner_text: str = banner_text

        self.operations: list[dict] = []  # 操作历史（动作类 op）
        self._clicks: dict[str, int] = {}
        self._fills: dict[str, str] = {}
        self._options: dict[str, str] = {}
        self._texts: dict[str, str] = {}
        self._attrs: dict[tuple, Any] = {}
        self._counts: dict[str, int] = {}
        self._screenshots: list[str] = []
        self.url: str = ""
        self.closed: bool = False

    # ------------------------------------------------------------ 场景控制
    def set_text(self, selector: str, text: str) -> "MockSettingsPage":
        self._texts[selector] = text
        return self

    def set_attr(self, selector: str, attr: str, value: Any) -> "MockSettingsPage":
        self._attrs[(selector, attr)] = value
        return self

    def set_count(self, selector: str, n: int) -> "MockSettingsPage":
        self._counts[selector] = n
        return self

    def click_count(self, selector: str) -> int:
        return self._clicks.get(selector, 0)

    def fill_value(self, selector: str) -> str | None:
        return self._fills.get(selector)

    def option_value(self, selector: str) -> str | None:
        return self._options.get(selector)

    def _require(self, selector: str) -> None:
        if _MISSING_ALL in self._missing or selector in self._missing:
            raise RuntimeError(
                f"[MockSettingsPage] 元素缺失（模拟 page_changed/元素不存在）: {selector!r}"
            )

    def _record(self, op: str, selector: str, **extra: Any) -> None:
        self.operations.append({"op": op, "selector": selector, **extra})

    # ------------------------------------------------------------ PageOps 实现
    def goto(self, url: str) -> None:
        self.url = url
        self._record("goto", url)

    def wait_for(self, selector: str, timeout_ms: int = 15000) -> None:
        self._require(selector)
        self._record("wait_for", selector, timeout_ms=timeout_ms)

    def click(self, selector: str) -> None:
        self._require(selector)
        self._clicks[selector] = self._clicks.get(selector, 0) + 1
        self._record("click", selector)

    def fill(self, selector: str, value: str) -> None:
        self._require(selector)
        self._fills[selector] = value
        self._record("fill", selector, value=value)

    def select_option(self, selector: str, value: str) -> None:
        self._require(selector)
        self._options[selector] = value
        self._record("select_option", selector, value=value)

    def read_text(self, selector: str) -> str:
        self._require(selector)
        if selector in self._texts:
            return self._texts[selector]
        if self._banner_text and "banner" in selector.lower():
            return self._banner_text
        return ""

    def read_attr(self, selector: str, attr: str) -> str | None:
        self._require(selector)
        value = self._attrs.get((selector, attr))
        return str(value) if value is not None else None

    def exists(self, selector: str) -> bool:
        return not (_MISSING_ALL in self._missing or selector in self._missing)

    def count(self, selector: str) -> int:
        if _MISSING_ALL in self._missing or selector in self._missing:
            return 0  # 真实 DOM 语义：元素缺失 count=0
        return self._counts.get(selector, 0)

    def screenshot(self, path: str) -> str:
        self._screenshots.append(path)
        self._record("screenshot", path)
        return path

    def close(self) -> None:
        self.closed = True
        self._record("close", "")


__all__ = [
    "MockSettingsPage",
    "SettingsForm",
    "SubmitResult",
    "pick_materials",
    "validate_submit",
]
