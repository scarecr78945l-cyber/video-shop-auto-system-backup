"""M3 文案管线 · 卖点口播稿生成（script）。

- 输入：product_id / 类目 / sku_spec_json（1688 SKU 真实规格/材质）；
- 优先 DeepSeek 结构化输出（JSON Schema，失败重试 config.llm.max_retries 次）；
- 无 Key / 失败 → 降级规则模板：**仅拼接 sku_spec_json 真实字段**
  （材质/容量/尺寸/颜色/数量/包装/产地）到句式库，禁止来源未证实承诺
  （如「送 200 木棍」须所选 SKU 明确支持，本管线不生成任何赠品/效果承诺）；
- 结果必过 ``optimization.compliance.check_text``（命中即整体弃用 LLM 内容转规则）。

返回 ``CopywriteDraft``（copy_type="script"，sku_basis 记录依据字段，防虚假承诺审计）。
"""

from __future__ import annotations

import json
from typing import Any, Optional

from ..compliance import check_text
from ..config import M3Config, load_config
from ..models import CopywriteDraft
from .llm import DeepSeekClient

SCRIPT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "content": {"type": "string", "minLength": 20},
        "selling_points": {
            "type": "array",
            "items": {"type": "string", "minLength": 1},
        },
    },
    "required": ["content", "selling_points"],
}

SYSTEM_PROMPT = (
    "你是视频号小店带货口播稿撰写助手。"
    "口播稿必须只基于用户提供的 SKU 真实规格/材质信息编写，"
    "严禁虚构或夸大卖点：不得编造赠品、数量、效果、资质、品牌授权等任何"
    "来源未证实的信息。内容需口语化、自然，适合口播，长度 60~160 字。"
)

# 字段 → 句式（仅当该字段在 sku_spec_json 中存在且非空时使用）
_FIELD_ORDER = ["材质", "容量", "尺寸", "颜色", "数量", "包装", "产地"]


def _spec_facts(sku_spec: Optional[dict[str, Any]]) -> tuple[list[str], list[str]]:
    """从 sku_spec_json 提取真实规格句与使用字段（防虚假承诺依据）。"""
    spec = sku_spec or {}
    facts: list[str] = []
    used: list[str] = []
    for key in _FIELD_ORDER:
        val = spec.get(key)
        if val in (None, "", [], {}):
            continue
        if key == "颜色":
            colors = val if isinstance(val, list) else [val]
            seg = "颜色有" + "/".join(str(c) for c in colors) + "可选"
        elif key == "数量":
            n = str(val).strip()
            seg = "单件装" if n in ("1", "1.0") else f"{val}件装"
        elif key == "材质":
            seg = f"甄选{val}材质"
        elif key == "包装":
            seg = f"{val}发货"
        else:  # 容量/尺寸/产地
            seg = f"{key}{val}"
        facts.append(seg)
        used.append(key)
    return facts, used


class ScriptGenerator:
    """卖点口播稿生成器（LLM 优先，规则降级）。"""

    def __init__(
        self,
        config: Optional[M3Config] = None,
        llm: Optional[DeepSeekClient] = None,
    ):
        self.config = config or load_config()
        self.llm = llm or DeepSeekClient(self.config)

    # ---------- 主流程 ----------

    def generate(
        self,
        product_id: str,
        category: str = "",
        sku_spec: Optional[dict[str, Any]] = None,
    ) -> CopywriteDraft:
        facts, used = _spec_facts(sku_spec)
        meta: dict[str, Any] = {}

        llm_content: Optional[str] = None
        if self.llm.has_key():
            out = self.llm.generate_structured(
                SYSTEM_PROMPT,
                self._user_message(category, sku_spec),
                SCRIPT_SCHEMA,
            )
            if out and str(out.get("content", "")).strip():
                content = str(out["content"]).strip()
                if not check_text(content):
                    llm_content = content
                else:
                    meta["llm_rejected"] = "compliance_hits"
            else:
                meta["llm_rejected"] = self.llm.last_error or "empty_or_invalid"

        if llm_content:
            content = llm_content
            source = "llm"
        else:
            content = self._rule_script(category, facts)
            source = "rule_fallback"
            meta["fallback"] = True

        hits = check_text(content)
        return CopywriteDraft(
            product_id=product_id,
            copy_type="script",
            content=content,
            variant_no=1,
            char_len=len(content),
            sku_basis={
                "used_fields": used,
                "spec": dict(sku_spec or {}),
                "meta": meta,
            },
            compliance_hits=hits,
            passed=not hits,
            source=source,
        )

    # ---------- 内部工具 ----------

    def _user_message(self, category: str, sku_spec: Optional[dict[str, Any]]) -> str:
        return (
            f"类目：{category or '未知'}\n"
            f"SKU 真实规格（JSON）：{__import__('json').dumps(sku_spec or {}, ensure_ascii=False)}\n"
            "请输出口播稿。"
        )

    def _rule_script(self, category: str, facts: list[str]) -> str:
        """规则降级：仅拼接真实规格字段到句式库，无任何未证实承诺。"""
        label = (category or "").strip()
        brief = f"{label}好物" if label else "这款好物"
        head = f"今天给大家带来一款{brief}——"
        body = "，".join(facts) + "。" if facts else "实物规格请以商品详情页为准。"
        tail = "喜欢的朋友可以放心入手，有需要的欢迎下单。"
        return head + body + tail


def generate_script(
    product_id: str,
    category: str = "",
    sku_spec: Optional[dict[str, Any]] = None,
    config: Optional[M3Config] = None,
) -> CopywriteDraft:
    """模块级便捷入口。"""
    return ScriptGenerator(config).generate(product_id, category, sku_spec)
