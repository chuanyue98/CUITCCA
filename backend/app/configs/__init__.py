"""configs 包保持空壳：不做名字再导出。

原来这里 ``from .load_env import openai_api_key ...`` 把热重载变量复制成了
包级别名——``reload_env_variables()`` 只更新 configs.load_env 模块内的变量，
这些包级绑定永远停留在 import 时刻的旧值，且没有任何调用方在用（纯死代码，
还制造"configs.X 也有效"的错觉）。需要配置一律从 configs.load_env 取。
"""
