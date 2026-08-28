"""M3 视频二创流水线 · LLM 拆解层（子代理-C2 · v0.3）。

输入商品信息（product_id / 类目 / sku_spec_json）→ 输出卖点镜头 / 口播要点结构化列表，
供编排层（composer）按模板做片头卡点、中段混剪与字幕叠加（对齐 06 文档第一节）。

- LLM 优先：复用 ``copywriting.llm.DeepSeekClient`` 结构化 JSON 输出
  （response_format=json_object + JSON Schema 校验 + 失败重试 config.llm.max_retries 次）；
- 无 Key / 失败降级规则：仅按 sku_spec_json 真实字段切分要点
  （材质/容量/尺寸/颜色/数量/包装/产地，句式取自 copywriting.script._spec_facts），
  禁止来源未证实承诺（不编造赠品/效果/资质），source="rule_fallback"；
- 任何要点（LLM 或规则）产出后必过 ``optimization.compliance.check_text`` 预审，
  命中即剔除并留 meta 证据（llm_dropped / dropped）；全部命中或为空 → 规则兜底
  （通用安全要点），管线永不静默产出未过合规的拆解。

无明文密钥：密钥只读环境变量 DEEPSEEK_API_KEY（经 DeepSeekClient 处理），
本模块不读不写不落任何密钥。
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Optional

from ..compliance import check_text
from ..config import M3Config, load_config
from ..copywriting.llm import DeepSeekClient
from ..copywriting.script import _spec_facts

# 卖点拆解 JSON Schema（DeepSeekClient 轻量校验子集兼容：object/array/string/minLength）
BREAKDOWN_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "opening_hook": {"type": "string", "minLength": 1},
        "selling_shots": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "title": {"type": "string", "minLength": 1},
                    "shot": {"type": "string", "minLength": 1},
                },
                "required": ["title", "shot"],
            },
        },
        "voiceover_points": {
            "type": "array",
            "items": {"type": "string", "minLength": 1},
        },
    },
    "required": ["opening_hook", "selling_shots", "voiceover_points"],
}

SYSTEM_PROMPT = (
    "你是视频号小店带货视频二创拆解助手。"
    "只基于用户提供的商品类目与 SKU 真实规格/材质信息拆解，"
    "严禁虚构或夸大卖点：不得编造赠品、数量、效果、资质、品牌授权等任何"
    "来源未证实的信息。输出：opening_hook（片头钩子句，≤20 字）；"
    "selling_shots（卖点镜头列表，2~4 个，每项 title 为卖点名、shot 为画面描述）；"
    "voiceover_points（口播要点列表，2~4 条，每条 ≤30 字，用于字幕叠加）。"
)

# 规则降级：SKU 字段 → 镜头画面句式（仅当该字段在 sku_spec_json 中存在且非空时使用）
_FIELD_SHOT_TEMPLATES: dict[str, str] = {
    "材质": "近景展示{value}材质细节",
    "容量": "中景呈现{value}容量规格",
    "尺寸": "中景呈现{value}尺寸规格",
    "颜色": "多角度展示{value}配色",
    "数量": "展示{value}",
    "包装": "展示{value}细节",
    "产地": "展示{value}产地信息",
}

# 规则兜底（拆解全空/全部命中合规时使用，保证结构非空）
_EMPTY_SHOTS = [{"title": "商品", "shot": "全景展示商品外观"}]
_EMPTY_POINTS = ["实物规格请以商品详情页为准。"]


@dataclass
class VideoBreakdown:
    """视频二创拆解结果（卖点镜头 + 口播要点结构化列表）。"""

    product_id: str
    category: str = ""
    opening_hook: str = ""
    selling_shots: list[dict[str, str]] = field(default_factory=list)
    voiceover_points: list[str] = field(default_factory=list)
    source: str = "rule_fallback"          # llm / rule_fallback（降级标记）
    meta: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "product_id": self.product_id,
            "category": self.category,
            "opening_hook": self.opening_hook,
            "selling_shots": [dict(s) for s in self.selling_shots],
            "voiceover_points": list(self.voiceover_points),
            "source": self.source,
            "meta": dict(self.meta),
        }


def _clean_value(raw: Any) -> str:
    """SKU 字段值 → 展示串（list 转 / 连接）。"""
    if isinstance(raw, list):
        return "/".join(str(v) for v in raw)
    return str(raw)


class BreakdownGenerator:
    """视频二创拆解生成器（LLM 优先，规则降级，合规必过）。"""

    def __init__(self, config: Optional[M3Config] = None, llm: Optional[DeepSeekClient] = None):
        self.config = config or load_config()
        self.llm = llm or DeepSeekClient(self.config)

    # ---------- 主流程 ----------

    def generate(
        self,
        product_id: str,
        category: str = "",
        sku_spec: Optional[dict[str, Any]] = None,
    ) -> VideoBreakdown:
        """LLM 拆解；无 Key / 失败 / 全命中合规 → 规则降级（source="rule_fallback"）。"""
        meta: dict[str, Any] = {}

        if self.llm.has_key():
            out = self.llm.generate_structured(
                SYSTEM_PROMPT,
                self._user_message(category, sku_spec),
                BREAKDOWN_SCHEMA,
            )
            if out:
                shots, points, hook, dropped = self._clean_llm(out)
                if shots or points:
                    meta["llm_dropped"] = dropped
                    return VideoBreakdown(
                        product_id=product_id,
                        category=category,
                        opening_hook=hook,
                        selling_shots=shots,
                        voiceover_points=points,
                        source="llm",
                        meta=meta,
                    )
                meta["llm_rejected"] = (
                    "compliance_hits_all" if dropped else (self.llm.last_error or "empty_or_invalid")
                )
            else:
                meta["llm_rejected"] = self.llm.last_error or "empty_or_invalid"
        else:
            meta["llm_rejected"] = "no_api_key"

        return self._rule_breakdown(product_id, category, sku_spec, meta)

    # ---------- LLM 清洗（合规预审） ----------

    def _clean_llm(self, out: dict[str, Any]) -> tuple[list[dict], list[str], str, list[dict]]:
        """LLM 输出 → 合规通过的镜头/要点/钩子 + 被剔除清单（留证据）。"""
        shots: list[dict[str, str]] = []
        points: list[str] = []
        hook = ""
        dropped: list[dict[str, Any]] = []

        for it in out.get("selling_shots") or []:
            title = str(it.get("title", "")).strip()
            shot = str(it.get("shot", "")).strip()
            title_hits = check_text(title)
            shot_hits = check_text(shot)
            if shot and not shot_hits and not title_hits:
                shots.append({"title": title or "卖点", "shot": shot})
            else:
                dropped.append({
                    "kind": "shot", "title": title, "shot": shot,
                    "hits": title_hits + shot_hits,
                })

        for p in out.get("voiceover_points") or []:
            p = str(p).strip()
            hits = check_text(p)
            if p and not hits:
                points.append(p)
            else:
                dropped.append({"kind": "voiceover", "content": p, "hits": hits})

        hook = str(out.get("opening_hook", "")).strip()
        hook_hits = check_text(hook)
        if hook and hook_hits:
            dropped.append({"kind": "hook", "content": hook, "hits": hook_hits})
            hook = ""
        return shots, points, hook, dropped

    # ---------- 规则降级 ----------

    def _rule_breakdown(
        self,
        product_id: str,
        category: str,
        sku_spec: Optional[dict[str, Any]],
        meta: dict[str, Any],
    ) -> VideoBreakdown:
        """按 sku_spec_json 真实字段切分要点（无任何未证实承诺）。"""
        spec = sku_spec or {}
        facts, used = _spec_facts(spec)          # 复用 copywriting 句式（仅真实字段）
        label = (category or "").strip() or "好物"
        hook = f"这款{label}好物，值得一看"
        if check_text(hook):
            hook = "好物推荐，值得一看"

        shots: list[dict[str, str]] = []
        points: list[str] = []
        dropped: list[dict[str, Any]] = []
        for key in used:
            value = _clean_value(spec.get(key))
            if key == "数量" and str(spec.get("数量")).strip() in ("1", "1.0"):
                value = "单件装"
            tpl = _FIELD_SHOT_TEMPLATES.get(key, "展示{value}细节")
            shot = tpl.format(value=value)
            hits = check_text(shot)
            if not hits:
                shots.append({"title": key, "shot": shot})
            else:
                dropped.append({"kind": "shot", "field": key, "shot": shot, "hits": hits})

        for f in facts:
            hits = check_text(f)
            if not hits:
                points.append(f)
            else:
                dropped.append({"kind": "voiceover", "content": f, "hits": hits})

        if not shots and not points:
            shots = [dict(s) for s in _EMPTY_SHOTS]
            points = list(_EMPTY_POINTS)
            meta["empty_fallback"] = True

        meta["fallback"] = True
        meta["dropped"] = dropped
        return VideoBreakdown(
            product_id=product_id,
            category=category,
            opening_hook=hook,
            selling_shots=shots,
            voiceover_points=points,
            source="rule_fallback",
            meta=meta,
        )

    # ---------- 内部工具 ----------

    def _user_message(self, category: str, sku_spec: Optional[dict[str, Any]]) -> str:
        return (
            f"类目：{category or '未知'}\n"
            f"SKU 真实规格（JSON）：{json.dumps(sku_spec or {}, ensure_ascii=False)}\n"
            "请输出视频二创拆解。"
        )


def generate_breakdown(
    product_id: str,
    category: str = "",
    sku_spec: Optional[dict[str, Any]] = None,
    config: Optional[M3Config] = None,
) -> VideoBreakdown:
    """模块级便捷入口：卖点镜头/口播要点拆解（fixtures 离线可跑，无 Key 走规则）。"""
    return BreakdownGenerator(config).generate(product_id, category, sku_spec)
