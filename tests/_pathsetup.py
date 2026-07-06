import os
import sys

_APP_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'backend', 'app')
if _APP_DIR not in sys.path:
    sys.path.insert(0, _APP_DIR)
