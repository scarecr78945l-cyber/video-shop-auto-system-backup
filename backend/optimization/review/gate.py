"""M3 自动素材优化模块 · 审核闸门（review）编排器 ReviewGate（子代理-D · v1.0）。

对齐 06 文档第四节「审核闸门（素材进投放/上架前必经）」：
素材按序过三道闸——① 规则预审（rules.py，compliance 复用）→ ② 素材评估
（evaluate.py，平台智能诊断回读 fixtures 模拟）→ ③ 人工复核抽检（manual.py，
配置化百分比 + 高风险类目强制）。每道闸的结果写 ``opt_review_records``
（gate_type=rule/evaluate/manual，result=pass/reject/manual_review，
reasons_json 留证据，reviewer=system）。

短路语义（素材不进入下一道闸，避免无效评估/抽检）：
- 规则预审 rejected → 最终 rejected（stage=rule），仅落 1 条记录；
- 素材评估 reject（待优化）→ 最终 rejected（stage=evaluate），落 rule+evaluate 2 条；
- 人工抽检抽中 → 最终 manual_review（stage=manual），落 3 条（manual=manual_review）；
- 全部放行 → 最终 passed（stage=manual），落 3 条（manual=pass）。

批量入口 ``run_batch`` 单批 ≤50（P-006 批量错峰），超限抛 ValueError。
db 缺省 → 内存库（不触碰本模块真实 m3-optimization.db）。
"""

from __future__ import annotations

from typing import Any, Optional

from sqlalchemy import select

from .. import tables
from ..config import M3Config, load_config
from ..db import Database
from ..repo import new_id
from .evaluate import MaterialEvaluator
from .manual import ManualSampler
from .relevance import (
    MULTI_STYLE_MANUAL_NOTE,
    VERDICT_TO_RESULT,
    RelevanceJudge,
    RelevanceJudgeError,
    StyleClusterer,
    build_frame_sampler,
    build_relevance_judge,
)
from .rules import MaterialRules

MAX_BATCH_SIZE = 50          # ≤50/批（P-006：批量错峰防风控）

# 最终结论码
FINAL_PASSED = "passed"
FINAL_REJECTED = "rejected"
FINAL_MANUAL_REVIEW = "manual_review"

# relevance 相关性门（REC-迁移-03 C3）专用常量
GATE_TYPE_RELEVANCE = "relevance"       # opt_review_records.gate_type
RELEVANCE_TARGET_TYPE = "material"      # 相关性门 target_type（M2 素材）


class ReviewRecordRepo:
    """审核记录落库（opt_review_records，仅本模块库；幂等新增）。"""

    def __init__(self, db: Database):
        self.db = db

    def add(self, record: dict[str, Any]) -> str:
        review_id = new_id("rv")
        with self.db.session() as s:
            s.add(tables.OptReviewRecord(
                review_id=review_id,
                target_type=str(record["target_type"]),
                target_id=str(record["target_id"]),
                gate_type=str(record["gate_type"]),
                result=str(record["result"]),
                reasons_json=dict(record.get("reasons_json") or {}),
                reviewer=str(record.get("reviewer") or "system"),
            ))
        return review_id

    def list_by_target(self, target_type: str, target_id: str) -> list[dict[str, Any]]:
        with self.db.session() as s:
            rows = s.execute(
                select(tables.OptReviewRecord)
                .where(
                    tables.OptReviewRecord.target_type == target_type,
                    tables.OptReviewRecord.target_id == target_id,
                )
                .order_by(tables.OptReviewRecord.created_at)
            ).scalars().all()
            return [
                {
                    "review_id": r.review_id,
                    "target_type": r.target_type,
                    "target_id": r.target_id,
                    "gate_type": r.gate_type,
                    "result": r.result,
                    "reasons_json": r.reasons_json or {},
                    "reviewer": r.reviewer,
                }
                for r in rows
            ]


class ReviewGate:
    """审核闸门编排器：规则预审 → 素材评估 → 人工抽检，逐闸落库并返回最终结论。"""

    def __init__(
        self,
        config: Optional[M3Config] = None,
        db: Optional[Database] = None,
        rules: Optional[MaterialRules] = None,
        evaluator: Optional[MaterialEvaluator] = None,
        sampler: Optional[ManualSampler] = None,
    ):
        self.config = config or load_config()
        if db is None:
            db = Database(load_config(db_url="sqlite:///:memory:"))
            db.create_all()
        self.db = db
        self.rules = rules or MaterialRules(self.config)
        self.evaluator = evaluator or MaterialEvaluator(self.config)
        self.sampler = sampler or ManualSampler(self.config)
        self.repo = ReviewRecordRepo(db)

    # ---------------------------------------------------------------- 单条编排

    def run(
        self,
        target_type: str,
        target_id: str,
        material: dict[str, Any],
        category: str = "",
    ) -> dict[str, Any]:
        """单素材过闸。返回 {"target_type","target_id","category","rule","evaluate",
        "manual","final"}——final={"result","stage","review_id"}。"""
        target_type = str(target_type or "unknown")
        target_id = str(target_id)
        category = str(category or "")

        # ① 规则预审
        rule = self.rules.check(material, target_type)
        rule_record = self.repo.add({
            "target_type": target_type,
            "target_id": target_id,
            "gate_type": "rule",
            "result": rule["result"],
            "reasons_json": {
                "passed": rule["passed"],
                "hits": rule["hits"],
                "fields": rule["fields"],
                "rules": rule["rules"],
                "texts_checked": rule["texts_checked"],
            },
            "reviewer": "system",
        })
        if not rule["passed"]:
            return self._finish(
                target_type, target_id, category,
                result=FINAL_REJECTED, stage="rule", review_id=rule_record,
                rule={"passed": False, "hits": rule["hits"]},
                evaluate=None, manual=None,
            )

        # ② 素材评估（平台诊断回读 fixtures 模拟：material['platform_diagnosis'] 可选）
        ev = self.evaluator.evaluate(material, material.get("platform_diagnosis"))
        ev_record = self.repo.add({
            "target_type": target_type,
            "target_id": target_id,
            "gate_type": "evaluate",
            "result": ev["result"],
            "reasons_json": {
                "verdict": ev["verdict"],
                "label": ev["label"],
                "passed": ev["passed"],
                "optimization_items": ev["optimization_items"],
                "hard_failures": ev["hard_failures"],
                "soft_issues": ev["soft_issues"],
            },
            "reviewer": "system",
        })
        if not ev["passed"]:
            return self._finish(
                target_type, target_id, category,
                result=FINAL_REJECTED, stage="evaluate", review_id=ev_record,
                rule={"passed": True, "hits": []},
                evaluate={"verdict": ev["verdict"], "passed": False,
                          "optimization_items": ev["optimization_items"]},
                manual=None,
            )

        # ③ 人工复核抽检
        sampled = self.sampler.should_manual(target_id, category)
        manual_record = self.repo.add({
            "target_type": target_type,
            "target_id": target_id,
            "gate_type": "manual",
            "result": FINAL_MANUAL_REVIEW if sampled else "pass",
            "reasons_json": {
                "sampled": sampled,
                "sample_rate": self.sampler.sample_rate,
                "category": category,
                "high_risk": self.sampler.is_high_risk(category),
            },
            "reviewer": "system",
        })

        if sampled:
            return self._finish(
                target_type, target_id, category,
                result=FINAL_MANUAL_REVIEW, stage="manual", review_id=manual_record,
                rule={"passed": True, "hits": []},
                evaluate={"verdict": ev["verdict"], "passed": True,
                          "optimization_items": ev["optimization_items"]},
                manual={"sampled": True, "sample_rate": self.sampler.sample_rate,
                        "high_risk": self.sampler.is_high_risk(category)},
            )

        return self._finish(
            target_type, target_id, category,
            result=FINAL_PASSED, stage="manual", review_id=manual_record,
            rule={"passed": True, "hits": []},
            evaluate={"verdict": ev["verdict"], "passed": True,
                      "optimization_items": ev["optimization_items"]},
            manual={"sampled": False, "sample_rate": self.sampler.sample_rate,
                    "high_risk": self.sampler.is_high_risk(category)},
        )

    # ---------------------------------------------------------------- 批量入口

    def run_batch(self, items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """批量过闸（≤50/批，P-006 防风控；超限抛 ValueError 由调用方分批）。

        items: [{"target_type","target_id","material","category"}]。
        """
        items = list(items)
        if len(items) > MAX_BATCH_SIZE:
            raise ValueError(
                f"run_batch 单批最多 {MAX_BATCH_SIZE} 条，收到 {len(items)} 条（P-006 批量错峰）"
            )
        return [
            self.run(
                it["target_type"],
                it["target_id"],
                it["material"],
                it.get("category", ""),
            )
            for it in items
        ]

    # ---------------------------------------------------------------- 内部

    def _finish(
        self,
        target_type: str,
        target_id: str,
        category: str,
        *,
        result: str,
        stage: str,
        review_id: str,
        rule: Optional[dict[str, Any]],
        evaluate: Optional[dict[str, Any]],
        manual: Optional[dict[str, Any]],
    ) -> dict[str, Any]:
        return {
            "target_type": target_type,
            "target_id": target_id,
            "category": category,
            "rule": rule,
            "evaluate": evaluate,
            "manual": manual,
            "final": {"result": result, "stage": stage, "review_id": review_id},
        }


# ===========================================================================
# 素材相关性门（REC-迁移-03 C3：Qwen-VL 前 15 秒抽帧判定 + 款式聚类）
# ===========================================================================
class RelevanceGate:
    """素材相关性门编排器（复用本文件框架：ReviewRecordRepo / MAX_BATCH_SIZE / FINAL_*）。

    对齐迁移清单 C3：M2 采集入库后、进入询价/上架链前，判定素材与目标商品相关性——
    ① 前 15 秒抽帧（FrameSampler，mock 为 fixtures 描述 / 真实为 ffmpeg 抽帧图）
    → ② Qwen-VL 相关性判定（RelevanceJudge，无 Key 自动降级 mock 判定器）
    → ③ 款式聚类（StyleClusterer，material_clustering 语义：多款式必须人工确认目标款，
    禁止自动创建衍生商品）→ ④ 落 opt_review_records（gate_type=relevance）。

    判定三态 → 最终结论（与 M2 relevance_status / M4 候选池前置校验口径一致）：
    - related    → passed（放行，可进入询价/上架链）；
    - unrelated  → rejected（淘汰，不进入询价/上架链）；
    - multi_style→ manual_review（人工确认目标款，禁止自动创建衍生商品）。

    任一环节失败（抽帧/判定抛 RelevanceJudgeError）→ 结构化返回
    {"ok": False, "code": <error_code>, ...}，不向上抛出（R-M2-09 纪律）；
    db 缺省 → 内存库（不触碰本模块真实 m3-optimization.db）。
    """

    def __init__(
        self,
        config: Optional[M3Config] = None,
        db: Optional[Database] = None,
        judge: Optional[RelevanceJudge] = None,
        frame_sampler: Any = None,
        clusterer: Optional[StyleClusterer] = None,
    ):
        self.config = config or load_config()
        if db is None:
            db = Database(load_config(db_url="sqlite:///:memory:"))
            db.create_all()
        self.db = db
        # mode=auto 无 Key → build_* 自动返回 mock 组件（环境就绪自动启用真实模式）
        self.judge = judge or build_relevance_judge(self.config)
        self.frame_sampler = frame_sampler or build_frame_sampler(self.config)
        self.clusterer = clusterer or StyleClusterer()
        self.repo = ReviewRecordRepo(db)

    # ------------------------------------------------------------ 单素材判定

    def run(
        self,
        target_id: str,
        material: dict[str, Any],
        category: str = "",
    ) -> dict[str, Any]:
        """单素材过相关性门。

        target_id: M2 asset_id（字符串）；material: M2 素材 + 目标商品上下文
        （title/file_path/duration/target_product_title/style_hints/mock_verdict 等，
        契约见 _management/data-exchange/m2-m3-m4-relevance-gate.json）。
        返回 {"ok","target_id","category","verdict","style_count","styles","frames",
        "mode","final"}；final={"result","stage","review_id"}。
        """
        target_id = str(target_id)
        category = str(category or "")
        try:
            frames = self.frame_sampler.extract_frames(material)
            judgement = self.judge.judge(material, frames)
            clustering = self.clusterer.cluster(material, judgement)
        except RelevanceJudgeError as exc:
            # 抽帧/判定失败：结构化返回（不抛出），供 M2 门禁按错误码分类
            return {
                "ok": False,
                "code": exc.error_code,
                "reason": exc.message,
                "target_id": target_id,
                "category": category,
            }

        verdict = clustering["verdict"]
        result = VERDICT_TO_RESULT[verdict]
        final_result = {
            "pass": FINAL_PASSED,
            "reject": FINAL_REJECTED,
            "manual_review": FINAL_MANUAL_REVIEW,
        }[result]

        reasons: dict[str, Any] = {
            "verdict": verdict,
            "label": clustering.get("label", verdict),
            "judge_verdict": clustering.get("judge_verdict"),
            "confidence": float(judgement.get("confidence") or 1.0),
            "reason": str(judgement.get("reason") or ""),
            "mode": getattr(self.judge, "mode", "unknown"),
            "clustering": {
                "style_count": clustering["style_count"],
                "styles": clustering["styles"],
            },
            "frames": [
                {"at_seconds": f.get("at_seconds"), "description": f.get("description")}
                for f in frames
            ],
            "judge_evidence": judgement.get("evidence") or {},
            "category": category,
        }
        if verdict == "multi_style":
            reasons["manual_note"] = MULTI_STYLE_MANUAL_NOTE  # 08-17 收敛规则

        review_id = self.repo.add({
            "target_type": RELEVANCE_TARGET_TYPE,
            "target_id": target_id,
            "gate_type": GATE_TYPE_RELEVANCE,
            "result": result,
            "reasons_json": reasons,
            "reviewer": "system",
        })

        return {
            "ok": True,
            "target_id": target_id,
            "category": category,
            "verdict": verdict,
            "style_count": clustering["style_count"],
            "styles": clustering["styles"],
            "frames": reasons["frames"],
            "mode": reasons["mode"],
            "final": {"result": final_result, "stage": GATE_TYPE_RELEVANCE, "review_id": review_id},
        }

    # ------------------------------------------------------------ 批量入口

    def run_batch(self, items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """批量过相关性门（≤50/批，P-006 防风控；超限抛 ValueError 由调用方分批）。

        items: [{"target_id","material","category"}]。
        """
        items = list(items)
        if len(items) > MAX_BATCH_SIZE:
            raise ValueError(
                f"RelevanceGate.run_batch 单批最多 {MAX_BATCH_SIZE} 条，收到 {len(items)} 条"
                "（P-006 批量错峰）"
            )
        return [
            self.run(it["target_id"], it["material"], it.get("category", ""))
            for it in items
        ]
