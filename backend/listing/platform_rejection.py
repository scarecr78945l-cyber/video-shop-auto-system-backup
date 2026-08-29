"""M4 自动上架：平台拒审处理（驳回原因分类 + 自动修复候选 + 二次门禁）。

对应 07-自动上架模块设计.md 与 _management/modules/m4-listing/context/README.md
第二节状态机：platform_auditing → rejected（平台驳回）→ retry_candidate | manual。

职责（本文件只做拒审决策与留痕，不发起任何真实平台调用，REC-004）：
  1. 驳回原因原文按关键词表分类（优先级顺序，命中即分类，未命中 → other）；
  2. 按分类生成自动修复候选（改标题/重传主图/重传详情图/改价/补资质）；
  3. RejectionHandler.handle：有修复候选 → 迁移 retry_candidate（修复后重提），
     无候选 → 迁移 manual（人工介入）；同时写 listing_audit_records 一条审核记录；
  4. RejectionHandler.requalify：二次门禁——仅 retry_candidate 任务可重提，
     复用 backend/services/listing_gate.ListingGate 全量校验，passed 才放行。

依赖注入风格与 P3 一致：repo / state_machine 构造注入（gate 可选注入，默认自建），
便于测试。禁止改动 listing 包既有文件；本模块只读引用 repo/tables/state_machine 与
services.listing_gate。
"""

from __future__ import annotations

import json
import uuid
from typing import Any

from pydantic import BaseModel, Field

from services.listing_gate import ListingCandidate, ListingGate

from .models import utcnow_iso
from .repo import ListingRepo
from .state_machine import ListingStateMachine
from .tables import ListingAuditRecordRow

# 拒审分类枚举（平台审核拒绝原因的语义归类）
REJECT_CATEGORIES = (
    "title",
    "category",
    "qualification",
    "image",
    "price",
    "content_compliance",
    "other",
)

# 分类关键词表：驳回原因原文子串匹配，命中即分类；按字典顺序（优先级）逐类检查，
# 先命中的分类优先（如「标题类目错误」→ title，而非 category）。
REJECT_KEYWORDS: dict[str, tuple[str, ...]] = {
    "title": ("标题",),
    "category": ("类目", "分类"),
    "qualification": ("资质", "证件", "许可证", "品牌授权"),
    "image": ("图片", "主图", "详情图", "素材"),
    "price": ("价格", "售价", "定价", "低价"),
    "content_compliance": ("品牌", "功效", "夸大", "虚假", "违规", "禁售", "违禁词"),
}

# 可自动修复的分类（系统侧自动整改即可重提；qualification 需人工提供证件 → 不算自动可修）
_AUTO_FIXABLE_CATEGORIES = frozenset({"title", "image", "price"})


def classify_reject_reason(reject_reason: str) -> str:
    """按关键词表对驳回原因原文分类（优先级顺序，命中即返回；均未命中 → other）。"""
    for category in REJECT_CATEGORIES:
        if category == "other":
            continue
        keywords = REJECT_KEYWORDS.get(category, ())
        if any(kw in (reject_reason or "") for kw in keywords):
            return category
    return "other"


def _build_fix_candidates(category: str, reason: str) -> list["RejectFixCandidate"]:
    """按分类生成修复候选（category/content_compliance/other 无候选 → 空列表）。

    image 分支：reason 含「详情图」只给详情图候选，含「主图」只给主图候选，
    否则（含「图片/素材」或未细分）两者都给。
    """
    if category == "title":
        return [RejectFixCandidate(action="改标题", gate_required=True)]
    if category == "image":
        has_main = "主图" in (reason or "")
        has_detail = "详情图" in (reason or "")
        if has_detail and not has_main:
            return [RejectFixCandidate(action="重传详情图", gate_required=True)]
        if has_main and not has_detail:
            return [RejectFixCandidate(action="重传主图", gate_required=True)]
        return [
            RejectFixCandidate(action="重传主图", gate_required=True),
            RejectFixCandidate(action="重传详情图", gate_required=True),
        ]
    if category == "price":
        return [RejectFixCandidate(action="改价", gate_required=True)]
    if category == "qualification":
        # 补资质通常需人工提供证件：gate_required=False，二次门禁通过后仍需人工填资质
        return [RejectFixCandidate(action="补资质", gate_required=False)]
    return []


class RejectFixCandidate(BaseModel):
    """单条自动修复候选：动作 + 参数 + 是否需二次门禁。"""

    action: str  # 改标题 / 重传主图 / 重传详情图 / 补资质 / 改价
    param: dict[str, Any] = Field(default_factory=dict)
    gate_required: bool = False


class RejectionAnalysis(BaseModel):
    """拒审分析结果：分类 + 修复候选 + 自动可修 + 是否需重提。"""

    category: str
    reject_reason: str
    fix_candidates: list[RejectFixCandidate] = Field(default_factory=list)
    auto_fixable: bool = False  # 系统侧可自动整改（title/image/price）；qualification 需人工证件
    resubmit_required: bool = False  # 修复后需重提（二次门禁标志）


class RejectionResult(BaseModel):
    """拒审处理结果：去向（retry_candidate | manual）+ 完整分析。"""

    task_id: str
    category: str
    action: str  # "retry_candidate" | "manual"
    analysis: RejectionAnalysis


class RejectionHandler:
    """平台拒审处理：分类 → 修复候选 → 状态迁移 + 审核记录落库 → 二次门禁。"""

    def __init__(
        self,
        repo: ListingRepo,
        state_machine: ListingStateMachine,
        gate: ListingGate | None = None,
    ):
        self.repo = repo
        self.state_machine = state_machine
        self.gate = gate or ListingGate()

    # ------------------------------------------------------------ 分析

    def analyze(self, reject_reason: str) -> RejectionAnalysis:
        """驳回原因分类 + 生成修复候选 + 自动可修/需重提判定。"""
        category = classify_reject_reason(reject_reason)
        candidates = _build_fix_candidates(category, reject_reason)
        return RejectionAnalysis(
            category=category,
            reject_reason=reject_reason,
            fix_candidates=candidates,
            auto_fixable=category in _AUTO_FIXABLE_CATEGORIES,
            # 有修复候选 → 修复后需重提（走二次门禁）；无候选 → 人工处理不重提
            resubmit_required=bool(candidates),
        )

    # ------------------------------------------------------------ 拒审处理

    def handle(
        self, task, reject_reason: str, force_manual: bool = False
    ) -> RejectionResult:
        """拒审决策并落地：

        - 有修复候选 → state_machine.transition(task, "retry_candidate", ...)
          （qualification 亦走 retry_candidate：门禁通过后人工补资质再重提）；
        - 无修复候选 → transition(task, "manual", ...)（人工介入）；
        - force_manual=True（REC-融合 P0-1：该类目拒审率/连续图片拒审超阈值）
          → 即使有修复候选也强制转 manual（人工复核兜底，防自动重提循环）；
        - 迁移证据带 reject_reason_code=分类码，并写 listing_audit_records 一条记录。
        要求 task 已处于 rejected（平台驳回后由调用方先迁移），否则 transition 抛
        IllegalTransitionError（与状态机契约一致）。
        """
        analysis = self.analyze(reject_reason)
        if force_manual:
            action = "manual"
        else:
            action = "retry_candidate" if analysis.fix_candidates else "manual"
        evidence: dict[str, Any] = {"reject_reason_code": analysis.category}
        if force_manual:
            evidence["manual_reason"] = "category_manual_review"
        self.state_machine.transition(task, action, evidence=evidence)
        self._record_audit(task, analysis, action)
        return RejectionResult(
            task_id=task.task_id,
            category=analysis.category,
            action=action,
            analysis=analysis,
        )

    def _record_audit(
        self, task, analysis: RejectionAnalysis, action: str
    ) -> None:
        """写 listing_audit_records 一条（repo 无 audit 专用方法，直接走本模块库 session）。"""
        fix_candidate_json = (
            json.dumps(
                [c.model_dump() for c in analysis.fix_candidates],
                ensure_ascii=False,
            )
            if analysis.fix_candidates
            else None
        )
        # audit_id 派生自 platform_spu_id（无则回退 task_id），加随机后缀保证
        # UNIQUE(task_id, audit_id) 可容纳同一任务多次拒审记录
        audit_id = f"REJ:{task.platform_spu_id or task.task_id}:{uuid.uuid4().hex[:8]}"
        with self.repo.database.session() as session:
            session.add(
                ListingAuditRecordRow(
                    task_id=task.task_id,
                    audit_id=audit_id,
                    submit_at=utcnow_iso(),
                    last_query_at=None,
                    audit_status="rejected",
                    reject_reason=analysis.reject_reason,
                    reject_category=analysis.category,
                    fix_candidate=fix_candidate_json,
                    resubmit_required=1 if analysis.resubmit_required else 0,
                    evidence=json.dumps(
                        {
                            "reject_reason_code": analysis.category,
                            "action": action,
                            "auto_fixable": analysis.auto_fixable,
                        },
                        ensure_ascii=False,
                    ),
                )
            )

    # ------------------------------------------------------------ 二次门禁

    def requalify(self, task, candidate: ListingCandidate) -> bool:
        """二次门禁：仅 retry_candidate 任务可重提。

        用 ListingGate 对候选执行全量门禁，passed 才返回 True；未通过（或任务不在
        retry_candidate）返回 False，且不迁移任务状态（重提动作由调用方在通过后
        执行 retry_candidate→creating）。
        """
        if task.status != "retry_candidate":
            return False
        result = self.gate.evaluate(candidate)
        passed = result.passed
        self.repo.append_op_log(
            task_id=task.task_id,
            api="requalify_gate",
            direction="evaluate",
            payload_digest="",  # 门禁评估不涉及请求体，无敏感值
            evidence_json=json.dumps(
                {
                    "passed": passed,
                    "rejected_reason_codes": result.rejected_reason_codes,
                },
                ensure_ascii=False,
            ),
        )
        return passed
