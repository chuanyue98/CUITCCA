"""evals/ 评测脚本包。

存在这个 __init__.py 是为了让 evals._common 既能被脚本直接运行
（`uv run python evals/run_retrieval_eval.py`）时用 sys.path hack 导入，
也能被 tests/test_evals_smoke.py 用普通的 `import evals.xxx` 方式导入。
"""
