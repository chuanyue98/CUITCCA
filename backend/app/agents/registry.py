"""工具注册表：把"有哪些工具"和"工具具体怎么实现""要不要暴露给某个 Agent"
这几件事拆开，互不牵连。

## 为什么不直接在 ``agent_workflow.py`` 里手写一个工具列表

最直接的做法是 ``FunctionAgent(tools=[tool_a, tool_b, ...])`` 硬编码一份列表。
问题是这个项目已经有"同一套能力、不同端点想暴露不同子集"的真实需求——比如
未来如果要做一个"只允许检索、不允许写操作"的只读端点，或者调试时想单独
挂载某一个工具排查问题，硬编码列表意味着每次都要去改编排代码本身。

拆成 ``ToolRegistry``（通用的注册/查找/启停容器，不知道任何具体工具长什么
样）+ ``tools.py``（具体工具实现，只管"这个工具怎么做"，不管"谁会用到我"）
之后：加一个新工具只需要在 ``tools.py`` 写一个函数、调一次
``registry.register()``，这个文件的逻辑完全不用动；某个端点想要一个工具子集
只需要在调用 ``build_tools(names=[...])`` 时传自己要的名字，不用碰全局启停
状态。

## enable/disable vs. 显式传 names

两种"选工具"的方式都留着，因为语义不一样：
- ``enable``/``disable`` 改的是"这个工具默认要不要出现"，影响所有不显式指定
  ``names`` 的调用方——用于运维场景（比如某个工具依赖的外部服务挂了，运维
  操作一次全局禁用，不用逐个端点改代码）。
- ``build_tools(names=[...])`` 显式传名字时**忽略** enabled 状态，按名字精确
  取——调用方明确知道自己要什么就是什么，不应该被别处的全局开关意外影响。
"""
from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from llama_index.core.tools import FunctionTool

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ToolSpec:
    """一个工具的注册信息：名字、描述、实现函数。

    ``description`` 是模型选择要不要调用这个工具的**唯一依据**（模型看不到
    函数体、看不到这份代码里的中文注释），写得含糊模型就会选错工具或者传错
    参数——这份描述在 ``agents/tools.py`` 里逐条写得比较长，就是因为这个。

    ``fn``/``async_fn`` 至少提供一个，语义跟 ``FunctionTool.from_defaults``
    完全一致（同步函数传 ``fn``，协程函数传 ``async_fn``）；本项目的工具实现
    全是协程（都要访问 retriever/Chroma），所以 ``tools.py`` 里清一色用
    ``async_fn``，但注册表本身不假设这一点，留着 ``fn`` 是为了不把这个类
    做窄。
    """

    name: str
    description: str
    fn: Callable[..., Any] | None = None
    async_fn: Callable[..., Awaitable[Any]] | None = None
    fn_schema: type | None = None

    def __post_init__(self) -> None:
        if self.fn is None and self.async_fn is None:
            raise ValueError(f"工具 {self.name!r} 必须提供 fn 或 async_fn 之一")

    def to_function_tool(self) -> FunctionTool:
        return FunctionTool.from_defaults(
            fn=self.fn,
            async_fn=self.async_fn,
            name=self.name,
            description=self.description,
            fn_schema=self.fn_schema,
        )


class ToolRegistry:
    """工具的注册 / 查找 / 启停容器。不知道、也不应该知道任何具体工具的实现
    细节——具体工具在 ``agents/tools.py``，通过 ``register_default_tools()``
    灌进来。"""

    def __init__(self) -> None:
        self._specs: dict[str, ToolSpec] = {}
        self._enabled: dict[str, bool] = {}

    def register(self, spec: ToolSpec, *, enabled: bool = True) -> None:
        if spec.name in self._specs:
            raise ValueError(f"工具 {spec.name!r} 已经注册过，不能重复注册")
        self._specs[spec.name] = spec
        self._enabled[spec.name] = enabled
        logger.debug("registered tool %r (enabled=%s)", spec.name, enabled)

    def get(self, name: str) -> ToolSpec:
        try:
            return self._specs[name]
        except KeyError:
            raise KeyError(f"未知工具: {name!r}，已注册的工具: {sorted(self._specs)}") from None

    def list_names(self, *, only_enabled: bool = False) -> list[str]:
        if only_enabled:
            return sorted(name for name, is_enabled in self._enabled.items() if is_enabled)
        return sorted(self._specs)

    def is_enabled(self, name: str) -> bool:
        if name not in self._specs:
            raise KeyError(f"未知工具: {name!r}")
        return self._enabled[name]

    def set_enabled(self, name: str, enabled: bool) -> None:
        if name not in self._specs:
            raise KeyError(f"未知工具: {name!r}")
        self._enabled[name] = enabled

    def enable(self, name: str) -> None:
        self.set_enabled(name, True)

    def disable(self, name: str) -> None:
        self.set_enabled(name, False)

    def build_tools(self, names: list[str] | None = None) -> list[FunctionTool]:
        """构造一批可以直接塞给 ``FunctionAgent(tools=...)`` 的 ``FunctionTool``。

        ``names=None``：取当前所有"启用"的工具（默认行为，运维靠
        enable/disable 控制）。显式传 ``names`` 时按名字精确取，忽略 enabled
        状态——见类 docstring 里两种选择方式的语义区分。
        """
        selected = self.list_names(only_enabled=True) if names is None else names
        return [self.get(name).to_function_tool() for name in selected]
