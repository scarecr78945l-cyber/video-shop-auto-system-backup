"""M3 自动素材优化模块 · 审核闸门（review，子代理-D · v1.0 + 相关性门 v1.1）。

素材进投放/上架前的必经环节（对齐 06 文档第四节 + 迁移清单 C3）：
① 规则预审（rules.py，compliance 复用 + 素材专用规则）
② 素材评估（evaluate.py，平台智能诊断回读的本地确定性模拟）
③ 人工复核抽检（manual.py，配置化百分比 + 高风险类目强制）
ReviewGate（gate.py）依次编排三道闸并写 opt_review_records 留痕。

素材相关性门（REC-迁移-03 C3，v1.1）：
- relevance.py：Qwen-VL 前 15 秒抽帧相关性判定（接口抽象 + mock 判定器，
  环境就绪自动启用真实模式）+ 款式聚类（material_clustering 语义）；
- gate.py RelevanceGate：编排抽帧 → 判定 → 聚类 → 落 opt_review_records
  （gate_type=relevance；related→passed / unrelated→rejected /
  multi_style→manual_review 多款式需人工确认目标款）。

全部 fixtures 离线模式：零网络、零 API Key、零跨库访问；
只读使用公共骨架（config/db/tables/models/repo/compliance）。
"""

from __future__ import annotations

from .evaluate import (
    VERDICT_EXCELLENT,
    VERDICT_GOOD,
    VERDICT_NEEDS_OPTIMIZATION,
    MaterialEvaluator,
    evaluate_material,
)
from .gate import (
    FINAL_MANUAL_REVIEW,
    FINAL_PASSED,
    FINAL_REJECTED,
    GATE_TYPE_RELEVANCE,
    MAX_BATCH_SIZE,
    RELEVANCE_TARGET_TYPE,
    RelevanceGate,
    ReviewGate,
    ReviewRecordRepo,
)
from .manual import ManualSampler, should_manual_review
from .relevance import (
    FFmpegFrameSampler,
    FrameSampler,
    MockFrameSampler,
    MockRelevanceJudge,
    QwenVLRelevanceJudge,
    RelevanceJudge,
    RelevanceJudgeError,
    StyleClusterer,
    VERDICT_MULTI_STYLE,
    VERDICT_RELATED,
    VERDICT_TO_RESULT,
    VERDICT_UNRELATED,
    build_frame_sampler,
    build_relevance_judge,
    detect_qwen_vl,
    judge_relevance,
)
from .rules import (
    RULE_BASE,
    RULE_COPY,
    RULE_IMAGE,
    RULE_VIDEO,
    MaterialRules,
    run_rule_precheck,
)

__all__ = [
    # rules.py
    "MaterialRules",
    "run_rule_precheck",
    "RULE_BASE",
    "RULE_VIDEO",
    "RULE_IMAGE",
    "RULE_COPY",
    # evaluate.py
    "MaterialEvaluator",
    "evaluate_material",
    "VERDICT_EXCELLENT",
    "VERDICT_GOOD",
    "VERDICT_NEEDS_OPTIMIZATION",
    # manual.py
    "ManualSampler",
    "should_manual_review",
    # gate.py
    "ReviewGate",
    "ReviewRecordRepo",
    "MAX_BATCH_SIZE",
    "FINAL_PASSED",
    "FINAL_REJECTED",
    "FINAL_MANUAL_REVIEW",
    # relevance.py（REC-迁移-03 C3 相关性门）
    "RelevanceJudge",
    "MockRelevanceJudge",
    "QwenVLRelevanceJudge",
    "FrameSampler",
    "MockFrameSampler",
    "FFmpegFrameSampler",
    "StyleClusterer",
    "RelevanceJudgeError",
    "build_relevance_judge",
    "build_frame_sampler",
    "detect_qwen_vl",
    "judge_relevance",
    "VERDICT_RELATED",
    "VERDICT_UNRELATED",
    "VERDICT_MULTI_STYLE",
    "VERDICT_TO_RESULT",
    # gate.py 相关性门
    "RelevanceGate",
    "GATE_TYPE_RELEVANCE",
    "RELEVANCE_TARGET_TYPE",
]
