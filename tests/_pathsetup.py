import logging
import os
import sys
import warnings

_APP_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'backend', 'app')
if _APP_DIR not in sys.path:
    sys.path.insert(0, _APP_DIR)

sys.path.insert(0, os.path.join(_APP_DIR, 'utils'))

warnings.filterwarnings(
    'ignore',
    message='Using `httpx` with `starlette.testclient` is deprecated',
    category=Warning,
)

import configs.load_env as _load_env  # noqa: E402
_load_env.reload_env_variables()

_cust_logger = logging.getLogger('customer_logger')
for _h in list(_cust_logger.handlers):
    if isinstance(_h, logging.StreamHandler):
        _cust_logger.removeHandler(_h)
        _h.close()
