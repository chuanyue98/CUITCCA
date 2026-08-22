"""router/ 子模块的独立加载器：绕过 sys.modules 缓存，返回全新模块实例。

router/__init__.py 已是空壳（不再拖起 HuggingFace embeddings 的重型导入
链），所以"轻量导入"本身不再是问题；但部分测试还需要**全新实例**来隔离
模块级会话状态（graph.py 的 _chat_histories、query 结果缓存等）——不同
测试文件经常复用同样的 session_id 字面量，共享 sys.modules 里的规范实例
会互相读到对方残留的状态。需要隔离的测试用本加载器；只需要路由对象、
不碰模块级状态的测试直接 `from router import xxx` 即可。
"""
import importlib.util
import os

_APP_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'backend', 'app')

_load_count = 0


def load_router_module(subpath: str):
    """加载 backend/app/router/<subpath>（如 'graph.py'）为一个独立的新模块实例。"""
    global _load_count
    _load_count += 1
    # 每次调用用不重复的模块名，保证实例之间（以及与 sys.modules 里的规范
    # 实例之间）互不共享模块级状态。
    unique_name = f'_router_standalone_{_load_count}_{os.path.basename(subpath).replace(".", "_")}'
    spec = importlib.util.spec_from_file_location(
        unique_name, os.path.join(_APP_DIR, 'router', subpath)
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
