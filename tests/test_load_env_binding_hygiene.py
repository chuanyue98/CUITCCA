"""守卫测试：禁止用 ``from configs.load_env import X`` 绑定**可热重载**的配置值。

``reload_env_variables()`` 改的是 configs.load_env 模块内的变量；
from-import 在导入时就把值拷贝进当前模块，之后 .env 的变化（在线改 LLM
配置、调 COOKIE_*、改路径）永远感知不到。历史上多个文件踩过这个坑，
qa_workflow / hybrid_retriever / vector_store 的注释都在解释正确写法。
本测试用 AST 扫描 backend/app 全目录，规则：

- 可重载值（从 reload_env_variables 的 global 语句自动推导，新增配置自动
  纳入监管）：只允许 ``import configs.load_env as load_env`` + 使用处
  ``load_env.X`` 属性访问；
- 静态常量白名单（PROJECT_ROOT / ENV_PATH / MAX_FILE_SIZE /
  ALLOWED_EXTENSIONS / reload_env_variables 函数本身）：from-import 无害；
- configs 包（__init__.py）不得再导出任何 load_env 名字（再导出=又一份
  过时绑定的别名，见 configs/__init__.py 的 docstring）。
"""
import ast
import os
import unittest

import tests._pathsetup  # noqa: F401  (adds backend/app to sys.path)

_APP_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'backend', 'app')

# import 时刻就固定、reload_env_variables() 不会重赋的常量与函数。
STATIC_ALLOWLIST = frozenset({
    'PROJECT_ROOT',
    'ENV_PATH',
    'MAX_FILE_SIZE',
    'ALLOWED_EXTENSIONS',
    'reload_env_variables',
})


def _reloadable_names() -> set[str]:
    """从 configs/load_env.py 的 reload_env_variables() 函数体里收集
    global 语句声明的名字——这就是"会被热重载重新赋值"的集合。"""
    load_env_path = os.path.join(_APP_DIR, 'configs', 'load_env.py')
    with open(load_env_path, encoding='utf-8') as f:
        tree = ast.parse(f.read())
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == 'reload_env_variables':
            return {n for stmt in node.body if isinstance(stmt, ast.Global) for n in stmt.names}
    raise AssertionError('configs/load_env.py 里找不到 reload_env_variables()，守卫测试需要更新')


class LoadEnvBindingHygieneTest(unittest.TestCase):
    def test_no_from_import_of_reloadable_values(self):
        dynamic = _reloadable_names()
        offenders = []
        for dirpath, _dirnames, filenames in os.walk(_APP_DIR):
            for filename in filenames:
                if not filename.endswith('.py') or filename == 'load_env.py':
                    continue
                path = os.path.join(dirpath, filename)
                rel = os.path.relpath(path, _APP_DIR)
                with open(path, encoding='utf-8') as f:
                    tree = ast.parse(f.read())
                for node in ast.walk(tree):
                    if not isinstance(node, ast.ImportFrom):
                        continue
                    module = node.module or ''
                    if module not in ('configs.load_env', 'load_env'):
                        continue
                    for alias in node.names:
                        if alias.name in dynamic:
                            offenders.append(f'{rel}:{node.lineno} from-import 了可重载值 {alias.name}')
        self.assertEqual(
            offenders, [],
            '可热重载的配置值必须用 `import configs.load_env as load_env` + '
            '调用处 load_env.X 属性访问（from-import 是 import 时刻的过时快照）:\n'
            + '\n'.join(offenders),
        )

    def test_static_allowlist_actually_static(self):
        """白名单里的名字不能同时出现在 reload 的 global 列表里——否则它
        根本不是静态的，白名单本身就把守卫打穿了。"""
        dynamic = _reloadable_names()
        polluted = STATIC_ALLOWLIST & dynamic
        self.assertEqual(polluted, set(), f'白名单里的名字其实是可重载的: {polluted}')

    def test_configs_package_does_not_reexport_load_env(self):
        init_path = os.path.join(_APP_DIR, 'configs', '__init__.py')
        with open(init_path, encoding='utf-8') as f:
            tree = ast.parse(f.read())
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and (node.module or '').endswith('load_env'):
                self.fail('configs/__init__.py 不得再导出 load_env 的名字（过时绑定别名）')


if __name__ == '__main__':
    unittest.main()
