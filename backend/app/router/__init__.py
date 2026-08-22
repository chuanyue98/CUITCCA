"""router 包保持空壳：不在这里急切 import 子模块。

原来顶部写着 ``from .graph import graph_app ...``，于是任何 ``import
router.xxx``——包括测试只想加载单个路由模块——都会连带执行 graph/index
的重型导入链（handlers → HuggingFace embeddings，慢且需要模型文件）。
应用入口（main.py）直接 ``from router.graph import graph_app`` 按需导入；
空 __init__ 让子模块可以独立、轻量地被导入。需要全新模块实例来隔离
模块级会话状态的测试用 tests/_router_loader.py。
"""
