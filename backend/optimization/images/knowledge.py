"""REC-融合 P1-4：主图方法论知识库（旧系统 douyin_main_image_learning 配置化）。

用户付费学习资料（9 组 jpg）转文档/策略配置（REC-融合-04：仅内部策略参考，
不直接进商品图）：
- knowledge.json 配置：主图模板 / 文案公式 / 配色规则 / 布局要点；
- planner 生成策略时可读取（prompt 增强 / 模板选择）；
- 纯读取模块，无副作用。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

_DEFAULT_PATH = Path(__file__).parent / "knowledge.json"


class ImageKnowledge:
    """主图方法论知识库（JSON 配置加载一次）。"""

    def __init__(self, path: Path | str = _DEFAULT_PATH) -> None:
        self.path = Path(path)
        self._data: dict[str, Any] = {}
        if self.path.exists():
            self._data = json.loads(self.path.read_text(encoding="utf-8"))

    def templates(self) -> list[dict]:
        return list(self._data.get("main_image_templates", []))

    def copywriting_formulas(self) -> list[dict]:
        return list(self._data.get("copywriting_formulas", []))

    def color_rules(self) -> list[dict]:
        return list(self._data.get("color_rules", []))

    def layout_notes(self) -> list[str]:
        return list(self._data.get("layout_notes", []))

    def pick_template(self, index: int = 0) -> Optional[dict]:
        tpls = self.templates()
        return tpls[index % len(tpls)] if tpls else None

    def prompt_hint(self, max_notes: int = 3) -> str:
        """生成给 planner 的策略提示（组合模板+公式+配色，供生图 prompt 增强）。"""
        parts: list[str] = []
        tpl = self.pick_template(0)
        if tpl:
            parts.append(f"构图: {tpl['name']}（{tpl['desc']}）")
        formula = (self.copywriting_formulas() or [{}])[0]
        if formula.get("formula"):
            parts.append(f"文案: {formula['formula']}")
        for rule in self.color_rules()[:2]:
            parts.append(f"配色: {rule['rule']}")
        for note in self.layout_notes()[:max_notes]:
            parts.append(f"布局: {note}")
        return "；".join(parts)
