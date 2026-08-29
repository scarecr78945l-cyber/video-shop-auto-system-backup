"""REC-融合 P1-2：LLM prompt 模板库（旧系统 ai_generation.py 迁移）。

4 类任务模板（材质识别/标题/合规审核/客服）：
- 模板转 JSON 配置（backend/foundation/data/prompts.json），不硬编码；
- 温度 0.1–0.6、JSON 输出约定、前置语清理（旧系统 _chat_json 语义）；
- _chat_json 容错解析：剥离 markdown 代码块 → json.loads → 失败抛
  PromptRenderError（调用方降级规则库）。

用途：M3 copywriting（标题/口播稿）、M4 listing 识别 prompt、客服补参。
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Optional

_DEFAULT_PATH = Path(__file__).parent / "data" / "prompts.json"

# 任务温度（旧系统 ai_generation.py 语义：材质识别 0.1 / 标题 0.3 / 合规 0.2 / 客服 0.6）
DEFAULT_TEMPERATURES: dict[str, float] = {
    "material": 0.1,
    "title": 0.3,
    "compliance": 0.2,
    "customer_service": 0.6,
}

# 前置语清理（_chat_json 语义：剥离 Markdown 围栏与前后空白）
_CODE_BLOCK_RE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL)


class PromptRenderError(Exception):
    pass


class PromptLibrary:
    """JSON 配置化 prompt 模板库（加载一次，渲染幂等）。"""

    def __init__(self, path: Path | str = _DEFAULT_PATH) -> None:
        self.path = Path(path)
        self._templates: dict[str, dict[str, Any]] = {}
        self._load()

    def _load(self) -> None:
        if self.path.exists():
            self._templates = json.loads(self.path.read_text(encoding="utf-8"))

    def render(self, task: str, **kwargs: Any) -> str:
        """渲染模板：{placeholder} 替换；缺模板抛 PromptRenderError。"""
        template = self._templates.get(task)
        if not template:
            raise PromptRenderError(f"未知 prompt 任务: {task}")
        text = template["template"]
        for key, value in kwargs.items():
            text = text.replace("{" + key + "}", str(value))
        # 未替换占位符保留原样（提示调用方）
        return text

    def temperature(self, task: str) -> float:
        spec = self._templates.get(task) or {}
        return float(spec.get("temperature", DEFAULT_TEMPERATURES.get(task, 0.3)))

    def output_schema(self, task: str) -> dict:
        """任务声明的 JSON 输出结构（供结构化解析）。"""
        spec = self._templates.get(task) or {}
        return spec.get("output_schema", {})

    @staticmethod
    def parse_chat_json(text: str) -> Any:
        """_chat_json 容错解析：剥离代码块 → json.loads；失败抛 PromptRenderError。"""
        if not text or not text.strip():
            raise PromptRenderError("空响应")
        cleaned = text.strip()
        m = _CODE_BLOCK_RE.search(cleaned)
        if m:
            cleaned = m.group(1).strip()
        # 容错：截断到第一个 } 或 ]（模型偶发尾注）
        cleaned = cleaned.rstrip("` \n")
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            # 尝试截断修复
            for closer in ("}", "]"):
                idx = cleaned.rfind(closer)
                if idx > 0:
                    try:
                        return json.loads(cleaned[: idx + 1])
                    except json.JSONDecodeError:
                        continue
            raise PromptRenderError(f"JSON 解析失败: {text[:120]!r}")

    def list_tasks(self) -> list[str]:
        return sorted(self._templates.keys())
