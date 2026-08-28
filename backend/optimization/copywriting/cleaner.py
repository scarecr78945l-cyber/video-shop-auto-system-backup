"""M3 文案管线 · 标题机械清洗（cleaner）。

唯一来源：淘宝原始标题（taobao_original_title），**不虚构卖点**。
清洗链：
1. 去标签（【】/［］/[] 装饰性内容整体移除，留证据）；
2. 复用 ``sourcing.compliance.sanitize_title``（营销词/品牌词/「同款」/功效词/括号）；
3. 供应链词（1688/工厂/源头/厂家/批发/一件代发/代发 + 残留尾词 直发/直销）移除；
4. 广告禁用词残余（官方/旗舰店/代言/联名/正品/保真）移除；
5. 全角空格归一 + 相邻重复段去重；
6. 合规兜底循环（optimization.compliance.check_text 仍有命中 → 逐词移除）；
7. 长度策略（明确且可解释）：
   - 空 → 拒绝（无可用素材）；
   - <15 字符 → 拒绝（不虚构卖点，禁止拼接来源外文字）；
   - >35 字符 → 规则截断至 35（优先在空格边界断词），ok=True。

返回值 ``TitleCleanResult``（removed 证据 / reasons 全程留痕）。
"""

from __future__ import annotations

import re
from typing import Optional

from sourcing.compliance import (
    BRAND_WORDS,
    EFFICACY_WORDS,
    SUPPLY_CHAIN_WORDS,
    sanitize_title,
)

from ..compliance import (
    AD_BADGE_FORBIDDEN,
    SUPPLY_CHAIN_WORDS_EXTRA,
    check_text,
)
from ..config import M3Config, load_config
from ..models import TitleCleanResult

# ---------- 词表 ----------

# 营销词（检测用证据；实际删除由 sanitize_title + 本模块步骤完成）
MARKETING_WORDS = [
    "热卖", "热销", "爆款", "新款", "包邮", "秒杀", "清仓", "特价",
    "直降", "优惠", "券后", "活动价", "2025", "2024", "限时", "促销",
    "打折", "低价", "亏本", "赔钱", "超值", "划算", "狂欢", "返现",
]

# 品牌词（证据分类：官方旗舰店/旗舰店/官方 + sourcing 品牌词库）
BRAND_DETECT_WORDS = sorted(
    set(["官方旗舰店", "旗舰店", "官方"]) | set(BRAND_WORDS), key=len, reverse=True
)

# 广告禁用词（证据分类：同款/正品/代言/联名/保真，AD_BADGE_FORBIDDEN 子集）
AD_DETECT_WORDS = ["同款", "正品", "代言", "联名", "保真"]

# 供应链词（检测 + 删除共用；含 sourcing 与素材扩展，长词优先）
SUPPLY_WORDS = sorted(
    set(SUPPLY_CHAIN_WORDS) | set(SUPPLY_CHAIN_WORDS_EXTRA), key=len, reverse=True
)

# 供应链残留尾词（如「厂家直发」删「厂家」后残留的「直发」）
SUPPLY_FRAGMENTS = ["直发", "直销"]

BRACKET_RE = re.compile(r"[【\[［][^】\]］]*[】\]］]")
LEFT_BRACKET_RE = re.compile(r"[【\[［】\]］]")
SPACE_RE = re.compile(r"\s+")


def _dedupe(items: list[str]) -> list[str]:
    seen: list[str] = []
    for it in items:
        if it not in seen:
            seen.append(it)
    return seen


def _scan(raw: str, words: list[str]) -> list[str]:
    """在原文中命中词列表（保词表顺序、去重，供 removed 证据）。"""
    t = (raw or "").lower()
    return _dedupe([w for w in words if w and w.lower() in t])


def _dedupe_segments(text: str) -> str:
    """相邻重复段去重：「水杯 水杯」→「水杯」。"""
    parts = text.split(" ")
    out: list[str] = []
    for p in parts:
        if not p:
            continue
        if not out or out[-1] != p:
            out.append(p)
    return " ".join(out)


class TitleCleaner:
    """标题机械清洗器（规则优先，无需 LLM）。"""

    def __init__(self, config: Optional[M3Config] = None):
        self.config = config or load_config()

    # ---------- 主流程 ----------

    def clean(self, original: str) -> TitleCleanResult:
        cfg = self.config.copywriting
        raw = original or ""
        reasons: list[str] = []
        removed: dict[str, list[str]] = {
            "标签": [],
            "营销词": [],
            "品牌词": [],
            "广告禁用词": [],
            "供应链词": [],
            "功效词": [],
        }

        # 0. 证据：在原始标题上扫描各词类命中（删除前留痕）
        removed["标签"] = _dedupe(BRACKET_RE.findall(raw))
        removed["营销词"] = _scan(raw, MARKETING_WORDS)
        removed["品牌词"] = _scan(raw, BRAND_DETECT_WORDS)
        removed["广告禁用词"] = _scan(raw, AD_DETECT_WORDS)
        removed["供应链词"] = _scan(raw, SUPPLY_WORDS)
        removed["功效词"] = _scan(raw, EFFICACY_WORDS)

        # 1. 去标签（装饰性内容整体移除）
        t = BRACKET_RE.sub(" ", raw)
        # 2. 复用 sourcing 机械清洗（营销词/品牌词/「同款」/功效词/括号）
        t = sanitize_title(t)
        # 3. 供应链词 + 残留尾词移除
        for w in SUPPLY_WORDS:
            t = t.replace(w, " ")
        for w in SUPPLY_FRAGMENTS:
            t = t.replace(w, " ")
        # 4. 广告禁用词残余（官方/旗舰店/代言/联名/正品/保真）
        for w in AD_BADGE_FORBIDDEN:
            t = t.replace(w, " ")
        # 5. 残余括号字符 + 空白归一
        t = LEFT_BRACKET_RE.sub(" ", t)
        t = SPACE_RE.sub(" ", t).strip(" -–—_|·")
        # 6. 相邻重复段去重
        t = _dedupe_segments(t)
        # 7. 合规兜底：仍有命中词 → 逐词移除（保证零命中）
        t = self._strip_hits(t)

        char_len = len(t)
        title_min, title_max = cfg.title_min_chars, cfg.title_max_chars

        # 8. 长度策略（拒绝或规则截断，均记录原因）
        if not t:
            reasons.append("清洗后为空：原始标题无可用素材，拒绝生成（不虚构卖点）")
            return TitleCleanResult(
                original=raw, title="", char_len=0, ok=False,
                reasons=reasons, removed=removed,
            )
        if char_len < title_min:
            reasons.append(
                f"清洗后仅 {char_len} 字符（要求 {title_min}–{title_max}），"
                f"不足下限：不虚构卖点、不拼接来源外文字，拒绝生成"
            )
            return TitleCleanResult(
                original=raw, title=t, char_len=char_len, ok=False,
                reasons=reasons, removed=removed,
            )
        if char_len > title_max:
            t = self._truncate(t, title_min, title_max)
            reasons.append(
                f"清洗后原 {char_len} 字符超出上限 {title_max}，按规则截断至 {len(t)} 字符"
            )
            char_len = len(t)
        reasons.append(f"清洗完成：{char_len} 字符（{title_min}–{title_max} 合规区间）")
        return TitleCleanResult(
            original=raw, title=t, char_len=char_len, ok=True,
            reasons=reasons, removed=removed,
        )

    # ---------- 内部工具 ----------

    def _strip_hits(self, text: str) -> str:
        """合规兜底：check_text 命中词逐词移除，直到零命中或文本耗尽。"""
        t = text
        for _ in range(20):  # 防死循环上限
            hits = check_text(t)
            if not hits:
                break
            t_next = t
            for hit in hits:
                word = hit.split(":", 1)[-1]
                t_next = t_next.replace(word, " ")
            t_next = SPACE_RE.sub(" ", t_next).strip(" -–—_|·")
            if t_next == t:  # 无进展则停，避免死循环
                break
            t = t_next
        return t

    def _truncate(self, text: str, title_min: int, title_max: int) -> str:
        """超长截断：优先在空格边界断词；边界导致 < 下限时按硬上限截断。"""
        t = text
        if " " in t:
            cut = t.rfind(" ", 0, title_max + 1)
            if cut > title_min:
                t = t[:cut]
            else:
                t = t[:title_max]
        else:
            t = t[:title_max]
        return t.rstrip(" -–—_|·").strip()


def clean_title(original: str, config: Optional[M3Config] = None) -> TitleCleanResult:
    """模块级便捷入口。"""
    return TitleCleaner(config).clean(original)
