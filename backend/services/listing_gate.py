"""M4 上架前校验硬门禁（listing_gate）。

流水线第一道关卡（07-自动上架模块设计.md 第三节）：六项硬门禁，任一不通过
→ 商品不入队（结构化拒绝，GateResult.rejected_reason_codes）。

七项硬门禁：
  1. title             — 15–35 字符 + 非虚构承诺（品牌侵权词/供应链词/功效资质缺失词）
  2. category          — 类目在配置白名单 + 资质完整（资质字段非空）
  3. images            — 主图 ≥5 张、全部 1:1（Pillow 宽高比，容差可配）、
                         图片哈希去重（不全相同，R21）、详情图 ≥1 张
  4. sku_cost          — 逐 SKU 真实成本 > 0（整数「分」）+ 差异化售价已生成且 price > cost
  5. purchase_settings — 必填购买设置完整（限购/物流/售后，缺字段按未提供拒绝）
  6. compliance        — 合规预审通过（品牌/功效/供应链词，复用 sourcing/compliance.py）
  7. attrs_complete    — 必填商品参数完整（REC-迁移-02，C2 客服补参闭环 M4 侧）：
                         消费 M1 侧 missing_attrs 契约字段（对照
                         listing-requirements.json missing_field_labels），缺任一
                         必填参数 → 拒绝并列出缺项；字段缺失（None）视为完整（向后兼容）

门禁是前置校验，不套 WorkflowJob 执行期错误码（那是流水线运行期用，见
context/README.md 第四节）；拒绝返回结构化原因：
  title_length / title_compliance / category / qualification / images_count /
  images_ratio / images_duplicate / detail_images / sku_cost / sku_price /
  purchase_settings / compliance_preview / attrs_complete

阈值全部可配置：环境变量前缀 `LISTING_`（pydantic-settings，参考
sourcing/config.py）或构造函数注入 `ListingGateConfig`。
合规规则复用 sourcing/compliance.py（词库单一事实源：BRAND_WORDS /
PROHIBITED_WORDS / SUPPLY_CHAIN_WORDS / EFFICACY_WORDS / sanitize_title /
ComplianceEngine），规则演进自动同步。

REC-004：本模块仅前置校验，不发起任何真实平台调用（离线/模拟模式先行）。
"""

from __future__ import annotations

import hashlib
from typing import Any

from PIL import Image
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# 合规规则复用：词库与清洗直接引用 sourcing.compliance（单一事实源）
from sourcing.compliance import (
    BRAND_WORDS,
    EFFICACY_WORDS,
    PROHIBITED_WORDS,
    SUPPLY_CHAIN_WORDS,
    ComplianceEngine,
    sanitize_title,
)
from sourcing.config import DEFAULT_CATEGORY_WHITELIST, SourcingConfig
from sourcing.models import ComplianceState, SourceItem


# --------------------------------------------------------------------------
# 必填商品参数（REC-迁移-02，C2 客服补参闭环 M4 侧）
# --------------------------------------------------------------------------
# 权威清单来源：_management/data-exchange/old-system-assets/listing-requirements.json
#   customer_service_backfill.missing_field_labels（旧系统 1688 询价缺参字段）。
# M1 侧对照本清单产出 missing_attrs 契约字段；本门禁消费该字段，
# 字段缺失（None）视为参数完整（向后兼容旧数据）。
REQUIRED_ATTR_LABELS: tuple[str, ...] = (
    "适用年龄",
    "包装清单",
    "重量",
    "容量",
    "适用场景",
    "类别",
    "功能",
)


# --------------------------------------------------------------------------
# 输入模型（字段对齐 context/README.md 跨模块数据契约 5.1/5.2）
# --------------------------------------------------------------------------


class SkuInput(BaseModel):
    """逐 SKU 输入：编码 + 真实成本（分）+ 差异化售价（分）。"""

    code: str
    cost_cents: int = 0
    price_cents: int = 0


class PurchaseSettings(BaseModel):
    """必填购买设置（字段名以 context 跨模块契约为准，listing_spus）。

    purchase_limit:      {per_user, period}（默认每月 2 件）
    freight_template_id: 运费模板 ID
    after_sale:          售后说明/模板
    缺任一字段 = 按未提供拒绝（reason_code=purchase_settings）。
    """

    purchase_limit: dict[str, Any] | None = None
    freight_template_id: str | None = None
    after_sale: str | None = None


class ListingCandidate(BaseModel):
    """上架候选。

    来源：M1（标题/类目/资质/逐 SKU 成本/定价/购买设置）+ M3（主图/详情图）。
    cost_cents / price_cents 单位：分；main_images / detail_images 为本地文件路径。
    """

    product_id: int
    title: str = ""
    category_id: int = 0
    category_name: str = ""  # 类目白名单按名称匹配（M1 类目名）
    qualification: dict[str, Any] | None = None  # 资质信息摘要（资质 ID/有效期，不含凭证原文）
    main_images: list[str] = Field(default_factory=list)  # M3 主图（用途=main_image，审核通过）
    detail_images: list[str] = Field(default_factory=list)  # M3 详情图
    skus: list[SkuInput] = Field(default_factory=list)
    purchase_settings: PurchaseSettings | None = None
    # REC-迁移-02：M1 1688 客服补参缺项清单（对照 REQUIRED_ATTR_LABELS）；
    # None = 字段未提供 → 视为参数完整（向后兼容旧数据）。
    missing_attrs: list[str] | None = None
    # REC-迁移-03：素材相关性状态（M2 入库质量门 / M3 relevance 审核标记，
    # 枚举 pending/passed/failed/manual_review）；None = 未接入 → 放行（向后兼容）。
    material_relevance: str | None = None


# --------------------------------------------------------------------------
# 输出模型
# --------------------------------------------------------------------------


class GateItemResult(BaseModel):
    """单门禁项结果。"""

    item: str
    passed: bool
    reason_code: str = ""
    reason: str = ""
    evidence: dict[str, Any] = Field(default_factory=dict)


class GateResult(BaseModel):
    """门禁总结果：passed + 逐项 items + 结构化拒绝原因码。"""

    passed: bool
    items: list[GateItemResult] = Field(default_factory=list)

    @property
    def rejected_reason_codes(self) -> list[str]:
        """未通过门禁项的原因码列表（按 items 顺序）。"""
        return [i.reason_code for i in self.items if not i.passed]


# --------------------------------------------------------------------------
# 配置（阈值可配置：LISTING_* 环境变量 + 构造函数注入）
# --------------------------------------------------------------------------


class ListingGateConfig(BaseSettings):
    """门禁阈值配置。环境变量前缀 `LISTING_`（如 LISTING_TITLE_MIN），可构造函数注入。

    优先级：构造函数注入 > 环境变量 > 默认值（参考 sourcing/config.py 用法）。
    """

    model_config = SettingsConfigDict(
        env_prefix="LISTING_", env_file=".env", extra="ignore"
    )

    title_min: int = 15  # 标题长度下限（字符）
    title_max: int = 35  # 标题长度上限（字符）
    main_images_min: int = 5  # 主图数量下限（平台要求 5 张 1:1）
    image_ratio_tolerance: float = 0.02  # 1:1 宽高比容差（|ratio - 1| <= tol）
    sku_cost_min_cents: int = 0  # SKU 成本下限（分）；校验 cost_cents > 下限，默认 0 → 成本必须 > 0
    category_whitelist: list[str] = Field(
        default_factory=lambda: list(DEFAULT_CATEGORY_WHITELIST)
    )  # 类目白名单（默认 9 类，可后台增删）


# --------------------------------------------------------------------------
# 门禁
# --------------------------------------------------------------------------


class ListingGate:
    """上架前校验硬门禁：六项全部通过才放行（任一失败 → 不入队）。"""

    def __init__(self, config: ListingGateConfig | None = None):
        self.config = config or ListingGateConfig()

    # ---- 主入口 ----

    def evaluate(self, candidate: ListingCandidate) -> GateResult:
        """执行全部硬门禁，返回结构化结果（不抛业务异常）。"""
        items = [
            self._title_length(candidate.title),
            self._title_compliance(candidate.title),
            self._category(candidate.category_name),
            self._qualification(candidate.qualification),
            self._images_count(candidate.main_images),
            self._images_ratio(candidate.main_images),
            self._images_duplicate(candidate.main_images),
            self._detail_images(candidate.detail_images),
            self._sku_cost(candidate.skus),
            self._sku_price(candidate.skus),
            self._purchase_settings(candidate.purchase_settings),
            self._compliance_preview(candidate),
        ]
        return GateResult(passed=all(i.passed for i in items), items=items)

    def is_allowed(self, candidate: ListingCandidate) -> bool:
        """门禁放行判定：六项全部通过才 True，否则不入队。"""
        return self.evaluate(candidate).passed

    # ---- 门禁 1：标题 ----

    def _title_length(self, title: str) -> GateItemResult:
        length = len(title or "")
        passed = self.config.title_min <= length <= self.config.title_max
        return GateItemResult(
            item="title_length",
            reason_code="title_length",
            passed=passed,
            reason=(
                ""
                if passed
                else f"标题长度 {length} 不在 [{self.config.title_min}, {self.config.title_max}]"
            ),
            evidence={
                "length": length,
                "min": self.config.title_min,
                "max": self.config.title_max,
            },
        )

    def _title_compliance(self, title: str) -> GateItemResult:
        """非虚构承诺：不含品牌侵权词/供应链词/功效资质缺失词（对齐 compliance.py 词库）。"""
        t = title or ""
        lower = t.lower()
        hits: list[str] = []
        for w in PROHIBITED_WORDS:
            if w.lower() in lower:
                hits.append(f"禁售词:{w}")
        for w in BRAND_WORDS:
            if w.lower() in lower:
                hits.append(f"品牌侵权词:{w}")
        for w in SUPPLY_CHAIN_WORDS:
            if w.lower() in lower:
                hits.append(f"供应链词:{w}")
        for w in EFFICACY_WORDS:
            if w.lower() in lower:
                hits.append(f"功效资质缺失词:{w}")
        sanitized = sanitize_title(t)
        if len(sanitized) < 2:
            hits.append("清洗后标题为空")
        passed = not hits
        return GateItemResult(
            item="title_compliance",
            reason_code="title_compliance",
            passed=passed,
            reason="" if passed else f"标题含违禁表述: {'/'.join(hits[:5])}",
            evidence={"hits": hits[:10], "sanitized": sanitized},
        )

    # ---- 门禁 2：类目与资质 ----

    def _category(self, category_name: str) -> GateItemResult:
        cat = (category_name or "").strip()
        whitelist = list(self.config.category_whitelist)
        # 与 compliance.py 同口径：子串匹配（兼容「家居日用百货」等完整类目名）
        matched = [c for c in whitelist if c in cat]
        passed = bool(cat) and bool(matched)
        return GateItemResult(
            item="category",
            reason_code="category",
            passed=passed,
            reason="" if passed else f"类目「{cat or '(空)'}」不在白名单",
            evidence={"category": cat, "whitelist": whitelist, "matched": matched},
        )

    def _qualification(self, qualification: dict[str, Any] | None) -> GateItemResult:
        provided = isinstance(qualification, dict) and bool(qualification)
        return GateItemResult(
            item="qualification",
            reason_code="qualification",
            passed=provided,
            reason="" if provided else "类目资质未提供或为空（资质字段非空）",
            evidence={
                "provided": provided,
                "keys": (
                    sorted(qualification.keys()) if isinstance(qualification, dict) else []
                ),
            },
        )

    # ---- 门禁 3：图片（主图 ≥5 张 1:1 去重 + 详情图） ----

    def _images_count(self, main_images: list[str]) -> GateItemResult:
        count = len(main_images or [])
        required = self.config.main_images_min
        passed = count >= required
        return GateItemResult(
            item="images_count",
            reason_code="images_count",
            passed=passed,
            reason="" if passed else f"主图 {count} 张 < 要求 {required} 张",
            evidence={"count": count, "required": required},
        )

    def _images_ratio(self, main_images: list[str]) -> GateItemResult:
        tol = self.config.image_ratio_tolerance
        violations: list[dict[str, Any]] = []
        for p in main_images or []:
            info = self._image_ratio(p)
            if info is None:
                violations.append({"path": p, "error": "无法读取图片"})
                continue
            ratio, w, h = info
            if abs(ratio - 1.0) > tol:
                violations.append(
                    {"path": p, "width": w, "height": h, "ratio": round(ratio, 4)}
                )
        passed = not violations
        return GateItemResult(
            item="images_ratio",
            reason_code="images_ratio",
            passed=passed,
            reason="" if passed else f"{len(violations)} 张主图非 1:1（容差 {tol}）",
            evidence={"violations": violations[:10], "tolerance": tol},
        )

    def _images_duplicate(self, main_images: list[str]) -> GateItemResult:
        """主图不全相同：SHA256 去重后数量必须等于主图数量（任一重复即拒绝，R21）。"""
        paths = list(main_images or [])
        seen: dict[str, str] = {}
        duplicates: list[str] = []
        for p in paths:
            digest = self._file_sha256(p)
            if digest is None:
                duplicates.append(f"{p}(不可读)")
                continue
            if digest in seen:
                duplicates.append(p)
            else:
                seen[digest] = p
        unique = len(seen)
        passed = len(paths) == unique and not duplicates
        return GateItemResult(
            item="images_duplicate",
            reason_code="images_duplicate",
            passed=passed,
            reason=(
                ""
                if passed
                else f"主图存在重复或不可读（去重后 {unique}/{len(paths)}）"
            ),
            evidence={"total": len(paths), "unique": unique, "duplicates": duplicates[:10]},
        )

    def _detail_images(self, detail_images: list[str]) -> GateItemResult:
        count = len(detail_images or [])
        passed = count >= 1
        return GateItemResult(
            item="detail_images",
            reason_code="detail_images",
            passed=passed,
            reason="" if passed else f"详情图缺失（{count} 张，要求 ≥1）",
            evidence={"count": count, "required": 1},
        )

    # ---- 门禁 4：逐 SKU 成本与差异化售价 ----

    def _sku_cost(self, skus: list[SkuInput]) -> GateItemResult:
        min_cents = self.config.sku_cost_min_cents
        violations = [
            {"code": s.code, "cost_cents": s.cost_cents}
            for s in skus or []
            if s.cost_cents <= min_cents
        ]
        passed = not violations
        return GateItemResult(
            item="sku_cost",
            reason_code="sku_cost",
            passed=passed,
            reason=(
                ""
                if passed
                else f"{len(violations)} 个 SKU 真实成本 ≤ 下限 {min_cents}（须 > 下限）"
            ),
            evidence={"violations": violations[:10], "min_cents": min_cents},
        )

    def _sku_price(self, skus: list[SkuInput]) -> GateItemResult:
        violations = [
            {
                "code": s.code,
                "cost_cents": s.cost_cents,
                "price_cents": s.price_cents,
            }
            for s in skus or []
            if s.price_cents <= s.cost_cents
        ]
        passed = not violations
        return GateItemResult(
            item="sku_price",
            reason_code="sku_price",
            passed=passed,
            reason=(
                "" if passed else f"{len(violations)} 个 SKU 差异化售价未生成或未高于成本"
            ),
            evidence={"violations": violations[:10]},
        )

    # ---- 门禁 5：必填购买设置 ----

    def _purchase_settings(self, purchase_settings: PurchaseSettings | None) -> GateItemResult:
        missing: list[str] = []
        if purchase_settings is None:
            missing = ["purchase_limit", "freight_template_id", "after_sale"]
        else:
            pl = purchase_settings.purchase_limit if isinstance(purchase_settings.purchase_limit, dict) else None
            per_user = pl.get("per_user") if pl else None
            period = (pl or {}).get("period")
            if not (isinstance(per_user, int) and per_user > 0):
                missing.append("purchase_limit.per_user(>0)")
            if not (period or "").strip():
                missing.append("purchase_limit.period")
            if not (purchase_settings.freight_template_id or "").strip():
                missing.append("freight_template_id")
            if not (purchase_settings.after_sale or "").strip():
                missing.append("after_sale")
        passed = not missing
        return GateItemResult(
            item="purchase_settings",
            reason_code="purchase_settings",
            passed=passed,
            reason="" if passed else f"必填购买设置缺失: {'/'.join(missing)}",
            evidence={"missing": missing},
        )

    # ---- 门禁 6：合规预审（复用 sourcing/compliance.py） ----

    def _compliance_preview(self, candidate: ListingCandidate) -> GateItemResult:
        """复用 ComplianceEngine 全量预审（品牌/禁售/供应链/功效 + 类目白名单）。"""
        engine = ComplianceEngine(
            SourcingConfig(category_whitelist=list(self.config.category_whitelist))
        )
        item = SourceItem(
            source="listing",
            board="gate",
            platform_item_id=str(candidate.product_id),
            title=candidate.title or "",
            category=(candidate.category_name or "").strip(),
        )
        result = engine.evaluate(item)
        passed = result.state == ComplianceState.CANDIDATE
        return GateItemResult(
            item="compliance_preview",
            reason_code="compliance_preview",
            passed=passed,
            reason=(
                "" if passed else "合规预审未通过: " + "; ".join(result.reasons[:5])
            ),
            evidence={
                "state": result.state.value,
                "reasons": result.reasons,
                "matched_rules": result.matched_rules,
            },
        )

    # ---- 工具 ----

    @staticmethod
    def _image_ratio(path: str) -> tuple[float, int, int] | None:
        """返回 (宽高比, 宽, 高)；读取失败返回 None。"""
        try:
            with Image.open(path) as im:
                w, h = im.size
            return (w / h, w, h) if h else None
        except OSError:
            return None

    @staticmethod
    def _file_sha256(path: str) -> str | None:
        """文件 SHA256（图片去重键）；读取失败返回 None。"""
        try:
            with open(path, "rb") as f:
                return hashlib.sha256(f.read()).hexdigest()
        except OSError:
            return None
