"""M2 自动收集素材模块 · 素材标签化与内容合规预审（子代理 B4-1）。

标签化（generate_tags）：平台标签 / 达人标签 / 类目提示标签 / 标题关键词提取
（去标点 → 截断 → 去重保序，总数上限 max_tags 可配，默认 8）；
标题为空不崩（只产出平台/达人/类目标签或空列表）。

内容合规预审（MaterialCompliance，R-M2-19 / R-M2-18）：
- ★词库单一事实源 = sourcing.compliance（BRAND_WORDS / PROHIBITED_WORDS /
  EFFICACY_WORDS / SUPPLY_CHAIN_WORDS），**只 import 引用，不复制词表**；
- 判定铁律（优先级：禁售 > 品牌 > 供应链 > 功效，取最严重者定 result/check_type）：
  - 禁售词命中 → reject（check_type=prohibited_word，平台禁售管控）
  - 品牌词命中 → reject（check_type=brand_word，品牌侵权）
  - 供应链词命中 → reject（check_type=supply_chain_word，R-M2-19 铁律）
  - 功效词命中 → review（check_type=efficacy_word，需资质，人工闸门）
  - 均未命中 → pass（check_type=content_precheck，整体预审通过）

证据留痕（evaluate_and_record）：check_material → repo.record_compliance_check
落 asset_compliance_checks（check_type / result / hit_words_json / note，note 含
命中理由 + 二创义务 derivation_note + 来源平台上下文），asset_items.compliance_status
由 repo 同步（pass→passed / reject→rejected / review 不动保持 pending）。

拒审下架（mark_platform_rejected，R-M2-20）：调用 repo.mark_disabled 置
upload_status=disabled（幂等），并在 asset_uploads 留 status=disabled 台账证据。
"""

from __future__ import annotations

import re
from typing import Any, Optional

from .config import MaterialsConfig, load_config

# ---------------------------------------------------------------------------
# ★ 词库单一事实源：只读复用 sourcing.compliance（禁复制词表）
# ---------------------------------------------------------------------------
from sourcing.compliance import (  # noqa: E402  sourcing 包由 tests/conftest 挂入 sys.path
    BRAND_WORDS,
    EFFICACY_WORDS,
    PROHIBITED_WORDS,
    SUPPLY_CHAIN_WORDS,
)

# 检查类型枚举（对齐 database/README.md asset_compliance_checks.check_type 口径）
CHECK_TYPE_SUPPLY_CHAIN = "supply_chain_word"
CHECK_TYPE_BRAND = "brand_word"
CHECK_TYPE_EFFICACY = "efficacy_word"
CHECK_TYPE_PROHIBITED = "prohibited_word"
CHECK_TYPE_PRE_CHECK = "content_precheck"  # 整体预审通过（无命中）用

# 平台标签映射（source_platform → 标签；未知/空平台不产出平台标签）
PLATFORM_TAGS: dict[str, str] = {
    "视频号": "视频号素材",
    "抖音": "抖音素材",
    "快手": "快手素材",
    "小红书": "小红书素材",
    "淘宝": "淘宝素材",
    "1688": "1688素材",
    "考古加": "考古加素材",
    "有米云": "有米云素材",
}

# 标题关键词提取：非单词字符（含中文/英文标点、空白）一律切分；保留 CJK/字母/数字块
_TITLE_SPLIT_RE = re.compile(r"[^\w]+", re.UNICODE)
# 单个关键词片段长度上限（过长的整句标题截断，避免整句入标签）
_MAX_KEYWORD_LEN = 12
# 达人标签长度上限（昵称可能很长）
_MAX_AUTHOR_TAG_LEN = 30

_default_config: Optional[MaterialsConfig] = None


def _default_cfg() -> MaterialsConfig:
    """进程内缓存一份默认配置（惰性加载，测试可显式传 config 覆盖）。"""
    global _default_config
    if _default_config is None:
        _default_config = load_config()
    return _default_config


def _match_words(words: list[str], text_lower: str) -> list[str]:
    """返回 text_lower 中命中的词（原词序，去空；只做子串匹配，不改词表）。"""
    return [w for w in words if w and w.lower() in text_lower]


# ---------------------------------------------------------------------------
# 标签生成
# ---------------------------------------------------------------------------
def _extract_title_keywords(title: str, stopwords: set[str]) -> list[str]:
    """标题关键词提取：去标点切分 → 过滤停用词/过短片段 → 超长截断 → 去重保序。"""
    out: list[str] = []
    seen: set[str] = set()
    for seg in _TITLE_SPLIT_RE.split(title or ""):
        seg = seg.strip()
        if not seg:
            continue
        if seg.lower() in stopwords:
            continue
        if len(seg) < 2:
            continue
        seg = seg[:_MAX_KEYWORD_LEN]
        if seg in seen:
            continue
        seen.add(seg)
        out.append(seg)
    return out


def generate_tags(
    source_platform: Optional[str] = None,
    source_author: Optional[str] = None,
    title: Optional[str] = None,
    category_hint: Optional[str] = None,
    max_tags: Optional[int] = None,
    config: Optional[MaterialsConfig] = None,
) -> list[str]:
    """生成素材标签（平台/达人/类目/标题关键词），去重保序，总数上限 max_tags。

    - source_platform：来源平台 → 平台标签（如「视频号素材」；未知平台原样保留；
      None/空 → 不产出平台标签）；
    - source_author：达人昵称 → 达人标签（原样，截断 30 字）；
    - category_hint：类目提示（如「美妆」）→ 类目标签；
    - title：标题关键词提取（去标点/停用词/截断/去重）；None/空 → 跳过不崩；
    - max_tags：标签总数上限，None → 取 config.tagger.max_tags（默认 8）；
    - config：显式配置（测试注入）；None → 进程内默认配置。
    返回去重有序列表。
    """
    cfg = config or _default_cfg()
    limit = max_tags if max_tags is not None else cfg.tagger.max_tags
    stopwords = set(cfg.tagger.tag_keyword_stopwords)

    tags: list[str] = []
    plat_tag = PLATFORM_TAGS.get((source_platform or "").strip(), "")
    if source_platform and not plat_tag:
        plat_tag = source_platform  # 未知平台原样作为标签
    if plat_tag:
        tags.append(plat_tag)

    author = (source_author or "").strip()
    if author:
        tags.append(author[:_MAX_AUTHOR_TAG_LEN])

    hint = (category_hint or "").strip()
    if hint:
        tags.append(hint[:_MAX_KEYWORD_LEN])

    tags.extend(_extract_title_keywords(title, stopwords))

    # 去重保序 + 截断
    seen: set[str] = set()
    out: list[str] = []
    for t in tags:
        if t and t not in seen:
            seen.add(t)
            out.append(t)
        if len(out) >= limit:
            break
    return out


# ---------------------------------------------------------------------------
# 内容合规预审
# ---------------------------------------------------------------------------
class MaterialCompliance:
    """素材内容预审（R-M2-19 供应链词泄漏 / 品牌侵权 / 功效资质 / 禁售词）。

    词库复用 sourcing.compliance（import 引用），判定结果三态：
    pass（可入库）/ reject（拒，留证据）/ review（人工复核，需资质）。
    """

    def __init__(self, config: Optional[MaterialsConfig] = None):
        self.config = config or _default_cfg()

    def check_material(
        self,
        title: str = "",
        extra_text: str = "",
        asset_type: Optional[str] = None,
    ) -> dict[str, Any]:
        """对标题 + 附加文本做四类词检查，返回判定结果。

        返回 dict：
        {
          "result": "pass" | "reject" | "review",
          "check_type": 主导检查类型（见模块常量 CHECK_TYPE_*），
          "hit_words": {"supply_chain_word": [...], "brand_word": [...],
                        "efficacy_word": [...], "prohibited_word": [...]},
          "reasons": [人类可读理由],
          "asset_type": 传入的 asset_type（仅上下文，不参与判定）,
        }
        优先级：禁售 > 品牌 > 供应链（均 reject）> 功效（review）> pass。
        """
        text = " ".join(filter(None, [title or "", extra_text or ""])).lower()
        hit_words: dict[str, list[str]] = {
            "supply_chain_word": _match_words(SUPPLY_CHAIN_WORDS, text),
            "brand_word": _match_words(BRAND_WORDS, text),
            "efficacy_word": _match_words(EFFICACY_WORDS, text),
            "prohibited_word": _match_words(PROHIBITED_WORDS, text),
        }

        reasons: list[str] = []
        result: str
        check_type: str

        if hit_words["prohibited_word"]:
            result, check_type = "reject", CHECK_TYPE_PROHIBITED
            reasons.append(f"禁售词: {'/'.join(hit_words['prohibited_word'][:5])}")
        elif hit_words["brand_word"]:
            result, check_type = "reject", CHECK_TYPE_BRAND
            reasons.append(f"品牌词(侵权风险): {'/'.join(hit_words['brand_word'][:5])}")
        elif hit_words["supply_chain_word"]:
            result, check_type = "reject", CHECK_TYPE_SUPPLY_CHAIN
            reasons.append(f"供应链词(泄漏风险): {'/'.join(hit_words['supply_chain_word'][:5])}")
        elif hit_words["efficacy_word"]:
            result, check_type = "review", CHECK_TYPE_EFFICACY
            reasons.append(f"功效词(需资质): {'/'.join(hit_words['efficacy_word'][:5])}")
        else:
            result, check_type = "pass", CHECK_TYPE_PRE_CHECK
            reasons.append("未命中供应链词/品牌词/功效词/禁售词")

        return {
            "result": result,
            "check_type": check_type,
            "hit_words": hit_words,
            "reasons": reasons,
            "asset_type": asset_type,
        }

    def evaluate_and_record(
        self,
        repo: Any,
        asset_id: int,
        title: str = "",
        extra_text: str = "",
        derivation_note: Optional[str] = None,
        source_platform: Optional[str] = None,
    ) -> dict[str, Any]:
        """预审 + 证据留痕：check_material → repo.record_compliance_check。

        落 asset_compliance_checks 一行（check_type / result / hit_words_json /
        note——note 含命中理由 + 二创义务 derivation_note + source_platform 上下文）；
        asset_items.compliance_status 由 repo 同步（pass→passed / reject→rejected /
        review 不动，保持 pending，语义按 repo 实现）。
        返回结果 dict（含 evidence 摘要）；资产不存在 → repo 抛 AssetNotFoundError。
        """
        check = self.check_material(title=title, extra_text=extra_text)

        note_parts = list(check["reasons"])
        if derivation_note:
            note_parts.append(f"derivation_note={derivation_note}")
        if source_platform:
            note_parts.append(f"source_platform={source_platform}")
        note = "; ".join(note_parts) if note_parts else None

        repo.record_compliance_check(
            asset_id,
            check_type=check["check_type"],
            result=check["result"],
            hit_words_json=check["hit_words"],
            note=note,
        )
        return {
            "asset_id": asset_id,
            "result": check["result"],
            "check_type": check["check_type"],
            "hit_words": check["hit_words"],
            "reasons": check["reasons"],
            "note": note,
        }

    def mark_platform_rejected(
        self, repo: Any, asset_id: int, reason: str
    ) -> dict[str, Any]:
        """平台拒审/源文件损坏 → upload_status=disabled（R-M2-20）。

        委托 repo.mark_disabled（幂等：已 disabled 重复调用直接返回，不重复记台账；
        资产不存在 → AssetNotFoundError）。返回标记结果摘要。
        """
        repo.mark_disabled(asset_id, reason)
        return {"asset_id": asset_id, "upload_status": "disabled", "reason": reason}
