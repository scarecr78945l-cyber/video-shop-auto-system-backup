"""REC-融合 P1-4：主图方法论知识库 fixtures 测试。

旧系统 douyin_main_image_learning 配置化验证：
① JSON 配置加载（模板/公式/配色/布局）
② pick_template 循环选择
③ prompt_hint 组合策略提示
④ 配置缺失路径返回空（不崩）
"""

from optimization.images.knowledge import ImageKnowledge


def test_load_sections():
    """① 四类知识配置加载。"""
    kb = ImageKnowledge()
    assert len(kb.templates()) >= 4
    assert len(kb.copywriting_formulas()) >= 3
    assert len(kb.color_rules()) >= 3
    assert len(kb.layout_notes()) >= 4


def test_pick_template_cycle():
    """② pick_template 循环选择。"""
    kb = ImageKnowledge()
    t0 = kb.pick_template(0)
    t1 = kb.pick_template(1)
    assert t0 is not None and t1 is not None
    assert t0["id"] != t1["id"]
    assert kb.pick_template(99) is not None  # 循环


def test_prompt_hint_composes():
    """③ prompt_hint 组合策略提示（含构图/文案/配色/布局）。"""
    kb = ImageKnowledge()
    hint = kb.prompt_hint()
    assert "构图" in hint
    assert "文案" in hint
    assert "配色" in hint


def test_missing_path_returns_empty(tmp_path):
    """④ 配置缺失返回空（不崩）。"""
    kb = ImageKnowledge(tmp_path / "no.json")
    assert kb.templates() == []
    assert kb.prompt_hint() == ""
