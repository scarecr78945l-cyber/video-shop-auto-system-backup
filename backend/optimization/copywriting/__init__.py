"""M3 文案管线 · 公共接口（copywriting，v0.2）。

四类文案生成能力 + 一个 LLM 客户端，供上层（pipeline / 其他模块）统一调用：

- ``TitleCleaner`` / ``clean_title``：标题机械清洗。唯一来源为淘宝原始标题
  （taobao_original_title），去标签/营销词/品牌词/供应链词/功效词/广告禁用词后
  按 15~35 字符策略：过短拒绝（不虚构卖点）、超长规则截断。
- ``ScriptGenerator`` / ``generate_script``：卖点口播稿。优先 DeepSeek 结构化输出，
  无 Key / 失败降级规则模板（仅拼接 sku_spec_json 真实字段，防虚假承诺），
  sku_basis 记录依据字段。
- ``AdBadgeGenerator`` / ``generate_ads`` / ``generate_badges``：投放文案/角标候选，
  每类 ≥ config.copywriting.ad_variants_min / badge_variants_min 套，候选间真实差异，
  合规预审必过。
- ``DeepSeekClient``：DeepSeek 结构化 JSON 客户端（response_format=json_object +
  Schema 校验 + 失败重试）；密钥只读环境变量 ``DEEPSEEK_API_KEY``，不落盘不落日志。

统一纪律（对齐 06/10 文档与宪法第 4.5 节）：产出必过
``optimization.compliance.check_text``；无 Key / 失败一律返回规则降级
（source="rule_fallback"），管线永不静默产出未过合规的文案。
"""

from __future__ import annotations

from .ads import AdBadgeGenerator, generate_ads, generate_badges
from .cleaner import TitleCleaner, clean_title
from .llm import DeepSeekClient
from .script import ScriptGenerator, generate_script

__all__ = [
    # 标题清洗
    "TitleCleaner",
    "clean_title",
    # 卖点口播稿
    "ScriptGenerator",
    "generate_script",
    # 投放文案 / 角标
    "AdBadgeGenerator",
    "generate_ads",
    "generate_badges",
    # LLM 客户端
    "DeepSeekClient",
]
