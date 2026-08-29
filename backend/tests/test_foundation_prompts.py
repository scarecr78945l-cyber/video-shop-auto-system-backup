"""REC-融合 P1-2：LLM prompt 模板库 fixtures 测试。

旧系统 ai_generation.py 迁移验证：
① 模板 JSON 配置加载（4 类任务）+ 渲染占位符替换
② 温度配置（材质 0.1 / 客服 0.6）
③ _chat_json 容错解析（代码块剥离 / 尾注截断）
④ 未知任务抛 PromptRenderError
"""

import pytest

from foundation.prompts import PromptLibrary, PromptRenderError


@pytest.fixture()
def lib() -> PromptLibrary:
    return PromptLibrary()


def test_load_four_tasks(lib):
    """① 4 类任务模板加载。"""
    tasks = lib.list_tasks()
    assert set(tasks) == {"material", "title", "compliance", "customer_service"}


def test_render_placeholder(lib):
    """渲染占位符替换。"""
    out = lib.render("title", raw_title="夏季连衣裙 女装 官方旗舰店", category="服饰配件")
    assert "夏季连衣裙 女装 官方旗舰店" in out
    assert "服饰配件" in out


def test_temperature_config(lib):
    """② 温度配置。"""
    assert lib.temperature("material") == 0.1
    assert lib.temperature("customer_service") == 0.6
    assert lib.temperature("title") == 0.3


def test_parse_chat_json_codeblock(lib):
    """③ 代码块剥离解析。"""
    raw = '```json\n{"title": "你好"}\n```'
    assert lib.parse_chat_json(raw) == {"title": "你好"}


def test_parse_chat_json_trailing(lib):
    """③ 尾注截断容错。"""
    raw = '{"title": "你好"} 以上是结果'
    assert lib.parse_chat_json(raw) == {"title": "你好"}


def test_parse_chat_json_invalid_raises(lib):
    """③ 非法 JSON 抛 PromptRenderError。"""
    with pytest.raises(PromptRenderError):
        lib.parse_chat_json("not json at all")


def test_unknown_task_raises(lib):
    """④ 未知任务抛 PromptRenderError。"""
    with pytest.raises(PromptRenderError):
        lib.render("no_such_task")


def test_output_schema(lib):
    """输出结构声明存在。"""
    schema = lib.output_schema("title")
    assert schema.get("title") == "str"
