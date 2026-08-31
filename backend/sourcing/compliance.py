"""合规过滤（复用/演进半成品 compliance.py）。

三态：hard_reject（品牌侵权/禁售词/功效资质缺失）直接拒；
candidate 进池；manual_review 人工确认（类目不在白名单、疑似功效词等）。

类目白名单改为配置项：`category_whitelist`（默认 9 类），
后台可通过 app_config 表增删，运行时优先级高于 config 默认值。
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from .config import SourcingConfig
from .models import ComplianceResult, ComplianceState, SourceItem

# 品牌侵权词（示例清单，生产按商标库扩充）
BRAND_WORDS = [
    "耐克", "nike", "阿迪达斯", "adidas", "三叶草", "香奈儿", "chanel",
    "路易威登", "louis vuitton", "lv", "古驰", "gucci", "爱马仕", "hermes",
    "迪奥", "dior", "普拉达", "prada", "苹果", "apple 官方", "华为官方",
    "小米官方", "迪士尼", "disney", "泡泡玛特", "乐高", "lego",
]

# 禁售词（平台禁售/管控商品）
PROHIBITED_WORDS = [
    "烟草", "香烟", "电子烟", "酒", "白酒", "处方药", "医疗器械",
    "枪支", "管制刀具", "违禁", "走私", "发票", "代开发票", "pos机",
    "假一赔十需要", "翻新机", "水货", "高仿", "原单", "尾单", "剪标",
    "赌博", "彩票", "博彩", "保健品", "减肥药", "伟哥", "三无",
]

# 功效资质缺失（无资质不得宣称）
EFFICACY_WORDS = [
    "治疗", "治愈", "根治", "药效", "医用", "消炎", "杀菌99", "抑菌99",
    "抗癌", "降血糖", "降血压", "防脱发", "生发", "美白祛斑", "祛皱",
    "瘦身", "丰胸", "壮阳", "助眠", "抗衰老", "婴儿专用", "孕妇专用",
]

# 供应链词（来源不洁/无品牌授权）
SUPPLY_CHAIN_WORDS = ["一件代发", "批发", "供应商", "1688", "厂家直销", "代发"]

# 品牌/功效等词的清洗规则（sanitize_marketplace_sku_name）
BRAND_CLEAN_RE = re.compile(
    r"(官方旗舰店|旗舰店|官方|正品|同款|爆款|热卖|热销|新款|2024|2025|"
    r"包邮|秒杀|清仓|特价|直降|优惠|券后|活动价|"
    r"耐克|nike|阿迪|adidas|香奈儿|chanel|古驰|gucci|迪奥|dior)", re.IGNORECASE
)
PAREN_RE = re.compile(r"[（(][^（）()]*[）)]")
MULTI_SPACE_RE = re.compile(r"\s+")


def sanitize_title(title: str) -> str:
    """清洗商品标题：去品牌词/「同款」/「官方旗舰」/功效词/营销词。"""
    t = PAREN_RE.sub(" ", title or "")
    t = BRAND_CLEAN_RE.sub(" ", t)
    for w in EFFICACY_WORDS:
        t = t.replace(w, " ")
    t = MULTI_SPACE_RE.sub(" ", t).strip(" -–—_")
    return t


def _match_any(words: list[str], title_lower: str) -> list[str]:
    return [w for w in words if w.lower() in title_lower]


# ===== REC-迁移-01（C1）：鞋服/包类硬拦词表（旧系统 SOURCING_HARD_BLOCK_POLICY）=====
# 语义：命中 apparel_terms / bag_terms（且不在 safe_*_context_terms 豁免）
# → 鞋服/包类必淘汰（hard_reject）；豁免如 衣架/洗衣机/收纳/垃圾袋/保鲜袋/快递袋 等。
_DEFAULT_HARD_BLOCK_PATH = Path(__file__).parent / "data" / "hard_block_policy.json"


class HardBlockPolicy:
    """旧系统硬拦策略的配置化载体（REC-迁移-01：词表进 JSON 配置，不硬编码）。

    P-031（2026-08-31 用户裁定「只找白名单里的品」）：接入 permanent_exclusion_terms
    （食品/饮品/贵金属/图书等永久排除词）——命中即 hard_reject，双保险兜底类目解析漏网。
    """

    def __init__(self, path: Path | str = _DEFAULT_HARD_BLOCK_PATH) -> None:
        self.path = Path(path)
        self.apparel_terms: list[str] = []
        self.safe_apparel_terms: list[str] = []
        self.bag_terms: list[str] = []
        self.safe_bag_terms: list[str] = []
        self.permanent_exclusion_terms: list[str] = []
        self.safe_permanent_context_terms: list[str] = []
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            return
        raw = json.loads(self.path.read_text(encoding="utf-8"))
        self.apparel_terms = list(raw.get("apparel_terms", []) or [])
        self.safe_apparel_terms = list(raw.get("safe_apparel_context_terms", []) or [])
        self.bag_terms = list(raw.get("bag_terms", []) or [])
        self.safe_bag_terms = list(raw.get("safe_bag_context_terms", []) or [])
        self.permanent_exclusion_terms = list(raw.get("permanent_exclusion_terms", []) or [])
        self.safe_permanent_context_terms = list(
            raw.get("safe_permanent_context_terms", []) or []
        )

    def apparel_hit(self, title_lower: str) -> list[str]:
        hits = _match_any(self.apparel_terms, title_lower)
        if hits:
            safe = _match_any(self.safe_apparel_terms, title_lower)
            if safe:
                return []  # 安全上下文豁免（衣架/洗衣机/收纳/客服等）
        return hits

    def bag_hit(self, title_lower: str) -> list[str]:
        hits = _match_any(self.bag_terms, title_lower)
        if hits:
            safe = _match_any(self.safe_bag_terms, title_lower)
            if safe:
                return []  # 安全上下文豁免（垃圾袋/收纳袋/保鲜袋等）
        return hits

    def permanent_hit(self, title_lower: str) -> list[str]:
        """永久排除词命中（P-031：食品/饮品/贵金属/图书等，用户裁定不做）。

        安全上下文豁免（safe_permanent_context_terms）：「食品」在「食品保鲜袋/食品级
        保鲜膜/食品收纳盒」中是材质/用途描述（厨房用品可做），不判为食品商品。
        """
        hits = _match_any(self.permanent_exclusion_terms, title_lower)
        if hits:
            safe = _match_any(self.safe_permanent_context_terms, title_lower)
            if safe:
                return []  # 安全上下文豁免（保鲜袋/收纳/食品级等材质描述）
        return hits

    def blocked_terms(self, title_lower: str) -> list[str]:
        return self.apparel_hit(title_lower) + self.bag_hit(title_lower)


class ComplianceEngine:
    def __init__(self, config: SourcingConfig, category_whitelist: list[str] | None = None):
        self.config = config
        # 白名单优先级：调用方传入（app_config 读取结果）> config 默认
        self.whitelist = (
            category_whitelist if category_whitelist is not None
            else config.category_whitelist
        )
        # REC-迁移-01：硬拦词表（C1），配置化可关
        self.hard_block = (
            HardBlockPolicy(config.hard_block_policy_path)
            if config.hard_block_policy_enabled
            else None
        )

    def evaluate(self, item: SourceItem) -> ComplianceResult:
        title = item.title or ""
        lower = title.lower()
        reasons: list[str] = []
        matched: list[str] = []

        # REC-迁移-01（C1）：鞋服/包类硬拦（命中 + 非安全上下文 → hard_reject）
        if self.hard_block is not None:
            blocked = self.hard_block.blocked_terms(lower)
            if blocked:
                matched += blocked
                return ComplianceResult(
                    state=ComplianceState.HARD_REJECT,
                    reasons=[f"鞋服/包类硬拦词: {'/'.join(blocked[:5])}"],
                    matched_rules=matched,
                )

        # P-031（用户裁定「只找白名单里的品」）：永久排除词（食品/饮品/贵金属/图书等）
        # 命中 → hard_reject（先于类目映射：防「酸奶」被「健身」映射到户外运动漏网等）
        if self.hard_block is not None:
            permanent = self.hard_block.permanent_hit(lower)
            if permanent:
                matched += permanent
                return ComplianceResult(
                    state=ComplianceState.HARD_REJECT,
                    reasons=[f"永久排除类目词（用户裁定不做）: {'/'.join(permanent[:5])}"],
                    matched_rules=matched,
                )

        hits = _match_any(PROHIBITED_WORDS, lower)
        if hits:
            matched += hits
            return ComplianceResult(
                state=ComplianceState.HARD_REJECT,
                reasons=[f"禁售词: {'/'.join(hits[:5])}"],
                matched_rules=matched,
            )

        hits = _match_any(BRAND_WORDS, lower)
        if hits:
            matched += hits
            return ComplianceResult(
                state=ComplianceState.HARD_REJECT,
                reasons=[f"品牌侵权词: {'/'.join(hits[:5])}"],
                matched_rules=matched,
            )

        hits = _match_any(SUPPLY_CHAIN_WORDS, lower)
        if hits:
            matched += hits
            reasons.append(f"供应链词: {'/'.join(hits[:5])}")

        hits = _match_any(EFFICACY_WORDS, lower)
        if hits:
            matched += hits
            reasons.append(f"功效词(缺资质): {'/'.join(hits[:5])}")

        sanitized = sanitize_title(title)
        if len(sanitized) < 2:
            return ComplianceResult(
                state=ComplianceState.HARD_REJECT,
                reasons=["清洗后标题为空，无法上架"],
                sanitized_title=sanitized,
                matched_rules=matched,
            )

        # P-031：类目标注（采集源未带类目时按标题推断白名单类目）+ 白名单强制
        # 用户裁定「只找白名单里的品，其他的不要找」——类目空/不在白名单 → hard_reject
        #（原 manual_review 语义升级为硬拒；白名单 9 类见 config.category_whitelist）
        category = (item.category or "").strip()
        if self.config.category_whitelist_enabled and self.whitelist:
            if not category:
                from .category_map import infer_category

                category = infer_category(title) or ""
            if not category:
                matched.append("类目未标注")
                return ComplianceResult(
                    state=ComplianceState.HARD_REJECT,
                    reasons=["类目无法映射到白名单 9 类（用户裁定只找白名单内的品）"],
                    sanitized_title=sanitized,
                    category=category,
                    matched_rules=matched,
                )
            if not any(cat in category for cat in self.whitelist):
                matched.append(f"类目不在白名单:{category}")
                return ComplianceResult(
                    state=ComplianceState.HARD_REJECT,
                    reasons=[f"类目「{category}」不在白名单 9 类（用户裁定只找白名单内的品）"],
                    sanitized_title=sanitized,
                    category=category,
                    matched_rules=matched,
                )

        # 功效词但未到 hard_reject 阈值 → manual_review
        if any(w in matched for w in EFFICACY_WORDS):
            reasons.append("含功效表述，需人工确认资质后放行")

        state = ComplianceState.MANUAL_REVIEW if reasons else ComplianceState.CANDIDATE
        return ComplianceResult(
            state=state,
            reasons=reasons,
            sanitized_title=sanitized,
            category=category,
            matched_rules=matched,
        )
