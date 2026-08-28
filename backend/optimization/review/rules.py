"""M3 自动素材优化模块 · 审核闸门（review）第一步：规则预审（子代理-D · v1.0）。

对齐 06 文档第四节「审核闸门」第 1 步与 10 文档第三节「内容合规」：
复用 ``optimization.compliance.check_text``（供应链词/广告禁用词/品牌词/功效词/禁售词），
再叠加素材专用规则——按目标类型收集素材文本字段后逐字段预审：

- copywrite：内容（content/title）合规；
- video    ：字幕（subtitles）/角标（badges）/口播（voiceover）文本合规；
- image    ：生图提示词（prompts）与文件名（file_path 取 basename）合规。

任何字段命中任一违禁词 → rejected（命中词列表留证据）；全部干净 → passed。
本模块零网络、零 API Key、零跨库访问（只读 import 公共骨架 compliance）。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from ..compliance import check_text
from ..config import M3Config, load_config

# 素材专用规则标签（可解释性：每条规则名进入结果 rules 列表）
RULE_VIDEO = "video:字幕/角标文本合规"
RULE_IMAGE = "image:提示词与文件名合规"
RULE_COPY = "copywrite:内容合规"
RULE_BASE = "compliance.check_text"


def _as_text_list(value: Any) -> list[str]:
    """把 str / list[str] 统一成去空字符串列表。"""
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    return [str(v) for v in value if str(v or "").strip()]


def _collect_text_fields(material: dict[str, Any], target_type: str) -> dict[str, str]:
    """按目标类型收集需要预审的文本字段（字段名 → 文本）。

    target_type 已归一化小写；未知类型走通用字段（content/title/prompts/file_name）。
    """
    fields: dict[str, str] = {}

    def add(name: str, text: Any) -> None:
        t = str(text or "").strip()
        if t:
            fields[name] = t

    if target_type in ("copywrite", "copywriting"):
        add("content", material.get("content"))
        add("title", material.get("title"))
    elif target_type == "video":
        for i, s in enumerate(_as_text_list(material.get("subtitles"))):
            add(f"subtitle[{i}]", s)
        for i, s in enumerate(_as_text_list(material.get("badges"))):
            add(f"badge[{i}]", s)
        add("voiceover", material.get("voiceover"))
        add("content", material.get("content"))
    elif target_type == "image":
        for i, s in enumerate(_as_text_list(material.get("prompts"))):
            add(f"prompt[{i}]", s)
        fp = material.get("file_path") or material.get("file_name") or ""
        if fp:
            add("file_name", Path(str(fp)).name)
        add("content", material.get("content"))
    else:
        add("content", material.get("content"))
        add("title", material.get("title"))
        for i, s in enumerate(_as_text_list(material.get("prompts"))):
            add(f"prompt[{i}]", s)
        fp = material.get("file_path") or material.get("file_name") or ""
        if fp:
            add("file_name", Path(str(fp)).name)
    return fields


def _material_rules(target_type: str) -> list[str]:
    if target_type in ("copywrite", "copywriting"):
        return [RULE_COPY]
    if target_type == "video":
        return [RULE_VIDEO]
    if target_type == "image":
        return [RULE_IMAGE]
    return []


def _dedupe(items: list[str]) -> list[str]:
    seen: list[str] = []
    for it in items:
        if it not in seen:
            seen.append(it)
    return seen


class MaterialRules:
    """规则预审器：素材对象 dict → 预审结果（passed/rejected + 命中词列表）。

    构造注入 config（默认 load_config()），零副作用；check 为纯函数式评估。
    """

    def __init__(self, config: Optional[M3Config] = None):
        self.config: M3Config = config or load_config()

    def check(self, material: dict[str, Any], target_type: str = "") -> dict[str, Any]:
        """执行规则预审。

        material: 素材对象 dict（含 content/subtitles/badges/prompts/file_path 等文本字段）。
        target_type: video/image/copywrite；缺省时回退 material['target_type']。
        返回：{"passed","result","hits","fields","target_type","texts_checked","rules"}。
        """
        tt = str(
            target_type or material.get("target_type") or material.get("type") or ""
        ).strip().lower()
        fields = _collect_text_fields(material, tt)

        hits_by_field: dict[str, list[str]] = {}
        for field, text in fields.items():
            field_hits = check_text(text)
            if field_hits:
                hits_by_field[field] = field_hits

        hits = _dedupe([h for hs in hits_by_field.values() for h in hs])
        passed = not hits
        return {
            "passed": passed,
            "result": "pass" if passed else "reject",
            "hits": hits,
            "fields": hits_by_field,
            "target_type": tt or "unknown",
            "texts_checked": len(fields),
            "rules": [RULE_BASE] + _material_rules(tt),
        }


def run_rule_precheck(
    material: dict[str, Any],
    target_type: str = "",
    config: Optional[M3Config] = None,
) -> dict[str, Any]:
    """模块级便捷入口：规则预审。"""
    return MaterialRules(config).check(material, target_type)
