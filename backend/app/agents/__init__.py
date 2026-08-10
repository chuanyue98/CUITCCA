"""Agent 层：工具注册表 + FunctionAgent 编排。

- ``agents.registry``：通用的工具注册/查找/启停容器（``ToolRegistry``）。
- ``agents.tools``：这个项目真实具备的工具实现（知识库检索/目录/按来源取
  原文/当前日期时间），以及把它们灌进注册表的 ``register_default_tools``。
- ``agents.agent_workflow``：把工具注册表接到 ``FunctionAgent`` 上，做多轮
  工具调用编排 + 护栏（轮次上限、超时、引用约束、降级路径）。跟
  ``handlers/qa_workflow.py`` 的 ``QAWorkflow`` 是并存关系，不是替代——两者
  的分工论证见 ``agents/agent_workflow.py`` 模块 docstring。

对外主要用这几个：``agents.agent_workflow.run_agent()``/
``stream_agent_events()`` 跑一次问答，``agents.tools.get_default_registry()``
拿到默认工具集，``agents.registry.ToolRegistry``/``ToolSpec`` 自己搭一份
不一样的工具子集（比如测试里只挂一两个假工具）。
"""
