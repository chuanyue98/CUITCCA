import logging
import os
from logging.handlers import RotatingFileHandler

from configs.load_env import LOG_PATH, reload_env_variables

reload_env_variables()

if not os.path.exists(LOG_PATH):
    os.makedirs(LOG_PATH)

customer_logger = logging.getLogger("customer")
customer_logger.setLevel(logging.INFO)
customer_handler = RotatingFileHandler(
    os.path.join(LOG_PATH, 'customer.log'), maxBytes=2*1024*1024, backupCount=3, encoding='utf-8'
)
customer_handler.setFormatter(logging.Formatter('%(asctime)s - %(message)s'))
customer_logger.addHandler(customer_handler)

query_logger = logging.getLogger("query")
query_logger.setLevel(logging.INFO)
query_handler = RotatingFileHandler(
    os.path.join(LOG_PATH, 'query.log'), maxBytes=2*1024*1024, backupCount=3, encoding='utf-8'
)
query_handler.setFormatter(logging.Formatter('%(asctime)s - %(message)s'))
query_logger.addHandler(query_handler)

error_logger = logging.getLogger("error")
error_logger.setLevel(logging.ERROR)
error_handler = RotatingFileHandler(
    os.path.join(LOG_PATH, 'error.log'), maxBytes=2*1024*1024, backupCount=3, encoding='utf-8'
)
error_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
error_logger.addHandler(error_handler)

# 审计日志：独立 logger，级别 INFO，记录安全相关事件
audit_logger = logging.getLogger("audit")
audit_logger.setLevel(logging.INFO)
audit_handler = RotatingFileHandler(
    os.path.join(LOG_PATH, 'audit.log'), maxBytes=2*1024*1024, backupCount=5, encoding='utf-8'
)
audit_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
audit_logger.addHandler(audit_handler)
