"""M3 自动素材优化模块 · A/B 优化闭环子包（子代理-E · v1.0 集成任务 2）。

对齐 06 文档第五节「A/B 优化闭环」：同一商品 ≥2 版素材 → 投放数据回写
evaluation → 素材评分排序（高效 > 潜力 > 探索期）→ 模板参数按类目重训练。

- ``scoring.py``   素材评分 ``score = roi_weight*roi_score + ctr_weight*ctr_score
                   + diag_weight*diag_score``（权重/饱和点配置化；无数据 → 0 分）；
- ``evaluate.py``  evaluation 标签计算（高效/潜力/探索期，阈值配置化）+
                   EvaluationRepo.upsert 幂等回写（(variant_id, report_date) 唯一）+
                   stale 标记（无新数据）；
- ``ranking.py``   素材排序（evaluation 序 → score 降序，稳定），供 M5 投放绑定选择，
                   输出 ``[(variant_id, platform_material_id, evaluation, score)]``；
- ``variants.py``  ≥2 版素材管理：版本清单 / 版本间差异摘要 / 不足 2 版提示；
- ``retrain.py``   模板参数按类目重训练：统计平均 ROI/CTR/样本数 → 更新
                   opt_templates.stats_json 与 opt_category_memory.template_stats_json；
                   样本不足（<5）不更新。

纪律：只读使用公共骨架（config/db/tables/models/repo/compliance）与三路子包
（copywriting/images/video），不修改任何既有文件；密钥只出现环境变量名。
"""

from __future__ import annotations

from .scoring import (
    DEFAULT_CTR_SCORE_CAP,
    DEFAULT_CTR_WEIGHT,
    DEFAULT_DIAG_WEIGHT,
    DEFAULT_ROI_SCORE_CAP,
    DEFAULT_ROI_WEIGHT,
    MaterialScorer,
    ScoringPolicy,
    compute_score,
    ctr_of,
    ctr_score,
    diag_score,
    roi_score,
)
from .evaluate import (
    EVALUATION_VALUES,
    EXPLORATION,
    HIGH_EFFICIENCY,
    POTENTIAL,
    EvaluationPolicy,
    EvaluationService,
    label_for,
)
from .ranking import EVALUATION_ORDER, MaterialRanker
from .variants import AB_MIN_VARIANTS, PARAM_DIFF_FIELDS, VariantManager
from .retrain import (
    DEFAULT_MIN_SAMPLES,
    RetrainPolicy,
    TemplateRetrainer,
    base_template_id,
)

__all__ = [
    # scoring
    "ScoringPolicy",
    "MaterialScorer",
    "compute_score",
    "ctr_of",
    "roi_score",
    "ctr_score",
    "diag_score",
    "DEFAULT_ROI_WEIGHT",
    "DEFAULT_CTR_WEIGHT",
    "DEFAULT_DIAG_WEIGHT",
    "DEFAULT_ROI_SCORE_CAP",
    "DEFAULT_CTR_SCORE_CAP",
    # evaluate
    "EvaluationPolicy",
    "EvaluationService",
    "label_for",
    "HIGH_EFFICIENCY",
    "POTENTIAL",
    "EXPLORATION",
    "EVALUATION_VALUES",
    # ranking
    "MaterialRanker",
    "EVALUATION_ORDER",
    # variants
    "VariantManager",
    "AB_MIN_VARIANTS",
    "PARAM_DIFF_FIELDS",
    # retrain
    "RetrainPolicy",
    "TemplateRetrainer",
    "base_template_id",
    "DEFAULT_MIN_SAMPLES",
]
