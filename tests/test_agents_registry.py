"""backend/app/agents/registry.py 的测试。

覆盖：
1. ToolSpec 必须提供 fn/async_fn 之一，否则构造时报错。
2. ToolSpec.to_function_tool() 产出的 FunctionTool 名字/描述正确。
3. ToolRegistry：注册、重复注册报错、按名字取（未知名字报错）、
   list_names（默认全部 / only_enabled 过滤）、enable/disable/is_enabled。
4. build_tools()：names=None 时只取启用的工具；显式传 names 时忽略 enabled
   状态，精确按名字取。
"""
import pytest
from agents.registry import ToolRegistry, ToolSpec

import tests._pathsetup  # noqa: F401


def _noop() -> str:
    return "ok"


async def _anoop() -> str:
    return "ok"


# ── ToolSpec ─────────────────────────────────────────────────────────


def test_tool_spec_requires_fn_or_async_fn():
    with pytest.raises(ValueError, match="必须提供 fn 或 async_fn"):
        ToolSpec(name="broken", description="desc")


def test_tool_spec_accepts_sync_fn():
    spec = ToolSpec(name="sync_tool", description="desc", fn=_noop)
    tool = spec.to_function_tool()
    assert tool.metadata.get_name() == "sync_tool"
    assert tool.metadata.description == "desc"


def test_tool_spec_accepts_async_fn():
    spec = ToolSpec(name="async_tool", description="desc", async_fn=_anoop)
    tool = spec.to_function_tool()
    assert tool.metadata.get_name() == "async_tool"


# ── ToolRegistry: register/get ──────────────────────────────────────


def test_register_and_get():
    registry = ToolRegistry()
    spec = ToolSpec(name="t1", description="d1", fn=_noop)
    registry.register(spec)
    assert registry.get("t1") is spec


def test_register_duplicate_name_raises():
    registry = ToolRegistry()
    registry.register(ToolSpec(name="t1", description="d1", fn=_noop))
    with pytest.raises(ValueError, match="已经注册过"):
        registry.register(ToolSpec(name="t1", description="d2", fn=_noop))


def test_get_unknown_tool_raises_with_registered_names():
    registry = ToolRegistry()
    registry.register(ToolSpec(name="t1", description="d1", fn=_noop))
    with pytest.raises(KeyError, match="t1"):
        registry.get("does_not_exist")


def test_default_enabled_true():
    registry = ToolRegistry()
    registry.register(ToolSpec(name="t1", description="d1", fn=_noop))
    assert registry.is_enabled("t1") is True


def test_register_with_enabled_false():
    registry = ToolRegistry()
    registry.register(ToolSpec(name="t1", description="d1", fn=_noop), enabled=False)
    assert registry.is_enabled("t1") is False


# ── ToolRegistry: list_names ─────────────────────────────────────────


def _make_registry_with_one_disabled() -> ToolRegistry:
    registry = ToolRegistry()
    registry.register(ToolSpec(name="a", description="d", fn=_noop))
    registry.register(ToolSpec(name="b", description="d", fn=_noop), enabled=False)
    return registry


def test_list_names_returns_all_by_default():
    registry = _make_registry_with_one_disabled()
    assert registry.list_names() == ["a", "b"]


def test_list_names_only_enabled_filters_out_disabled():
    registry = _make_registry_with_one_disabled()
    assert registry.list_names(only_enabled=True) == ["a"]


def test_is_enabled_unknown_tool_raises():
    registry = ToolRegistry()
    with pytest.raises(KeyError):
        registry.is_enabled("nope")


# ── ToolRegistry: enable/disable ────────────────────────────────────


def test_disable_then_enable_round_trips():
    registry = ToolRegistry()
    registry.register(ToolSpec(name="a", description="d", fn=_noop))

    registry.disable("a")
    assert registry.is_enabled("a") is False
    assert registry.list_names(only_enabled=True) == []

    registry.enable("a")
    assert registry.is_enabled("a") is True
    assert registry.list_names(only_enabled=True) == ["a"]


def test_set_enabled_unknown_tool_raises():
    registry = ToolRegistry()
    with pytest.raises(KeyError):
        registry.set_enabled("nope", True)


# ── ToolRegistry: build_tools ───────────────────────────────────────


def test_build_tools_default_uses_only_enabled():
    registry = _make_registry_with_one_disabled()
    tools = registry.build_tools()
    assert [t.metadata.get_name() for t in tools] == ["a"]


def test_build_tools_explicit_names_ignores_enabled_flag():
    """显式传 names 时应该忽略全局 enable/disable 状态——调用方明确要什么
    就是什么，不应该被别处的全局开关意外影响（见 registry.py 的 docstring）。"""
    registry = _make_registry_with_one_disabled()
    tools = registry.build_tools(names=["b"])
    assert [t.metadata.get_name() for t in tools] == ["b"]


def test_build_tools_empty_registry_returns_empty_list():
    registry = ToolRegistry()
    assert registry.build_tools() == []
