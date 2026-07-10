import logging
from logging.handlers import RotatingFileHandler
import os

from configs.load_env import reload_env_variables

reload_env_variables()

from configs.load_env import LOG_PATH

if not os.path.exists(LOG_PATH):
    os.makedirs(LOG_PATH)

customer_logger = logging.getLogger("customer_logger")
customer_logger.setLevel(logging.INFO)

stream_handler = logging.StreamHandler()
customer_logger.addHandler(stream_handler)
stream_handler.setFormatter(logging.Formatter('\033[1;34mCustomer - %(asctime)s - %(levelname)s - %(message)s\033[0m'))

error_logger = logging.getLogger('error_logger')
error_logger.setLevel(logging.ERROR)

log_file = os.path.join(LOG_PATH, 'error.log')
file_handler = RotatingFileHandler(log_file, maxBytes=10*1024*1024, backupCount=5, encoding='utf-8')
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
file_handler.setFormatter(formatter)
error_logger.addHandler(file_handler)

query_logger = logging.getLogger('query_logger')
query_logger.setLevel(logging.INFO)

log_file = os.path.join(LOG_PATH, 'query.log')
file_handler = RotatingFileHandler(log_file, maxBytes=10*1024*1024, backupCount=5, encoding='utf-8')
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
file_handler.setFormatter(formatter)
query_logger.addHandler(file_handler)
