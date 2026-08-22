import logging
import os
from logging.handlers import RotatingFileHandler

# 属性访问而不是 from...import：reload 后 from-import 的旧绑定感知不到
# 新的 LOG_PATH（handlers 在 import 时配置一次，这里至少保证读的是 reload
# 之后的值）。见 tests/test_load_env_binding_hygiene.py 的守卫说明。
import configs.load_env as load_env

load_env.reload_env_variables()

if not os.path.exists(load_env.LOG_PATH):
    os.makedirs(load_env.LOG_PATH)

customer_logger = logging.getLogger("customer")
customer_logger.setLevel(logging.INFO)
customer_handler = RotatingFileHandler(
    os.path.join(load_env.LOG_PATH, 'customer.log'), maxBytes=2*1024*1024, backupCount=3, encoding='utf-8'
)
customer_handler.setFormatter(logging.Formatter('%(asctime)s - %(message)s'))
customer_logger.addHandler(customer_handler)

query_logger = logging.getLogger("query")
query_logger.setLevel(logging.INFO)
query_handler = RotatingFileHandler(
    os.path.join(load_env.LOG_PATH, 'query.log'), maxBytes=2*1024*1024, backupCount=3, encoding='utf-8'
)
query_handler.setFormatter(logging.Formatter('%(asctime)s - %(message)s'))
query_logger.addHandler(query_handler)

error_logger = logging.getLogger("error")
error_logger.setLevel(logging.ERROR)
error_handler = RotatingFileHandler(
    os.path.join(load_env.LOG_PATH, 'error.log'), maxBytes=2*1024*1024, backupCount=3, encoding='utf-8'
)
error_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
error_logger.addHandler(error_handler)

# 审计日志：独立 logger，级别 INFO，记录安全相关事件
audit_logger = logging.getLogger("audit")
audit_logger.setLevel(logging.INFO)
audit_handler = RotatingFileHandler(
    os.path.join(load_env.LOG_PATH, 'audit.log'), maxBytes=2*1024*1024, backupCount=5, encoding='utf-8'
)
audit_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
audit_logger.addHandler(audit_handler)
