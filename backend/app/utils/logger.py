import logging
import os

from configs import ERRORLOG_PATH

# 创建一个名为 "customer_logger" 的日志记录器
customer_logger = logging.getLogger("customer_logger")
customer_logger.setLevel(logging.INFO)

# 创建一个 StreamHandler
stream_handler = logging.StreamHandler()

# 设置日志记录器的处理器为 StreamHandler
customer_logger.addHandler(stream_handler)

# 设置 StreamHandler 的格式化器为内置的 ColoredFormatter
stream_handler.setFormatter(logging.Formatter('\033[1;34mCustomer - %(asctime)s - %(levelname)s - %(message)s\033[0m'))

# 创建error_logger对象
error_logger = logging.getLogger('error_logger')
error_logger.setLevel(logging.ERROR)

# 创建文件处理程序
log_file = os.path.join(ERRORLOG_PATH, 'error.log')
file_handler = logging.FileHandler(log_file,encoding='utf-8')

# 设置日志格式
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
file_handler.setFormatter(formatter)

# 将文件处理程序添加到logger
error_logger.addHandler(file_handler)






# 创建error_logger对象
query_logger = logging.getLogger('query_logger')
query_logger.setLevel(logging.INFO)

# 创建文件处理程序
log_file = os.path.join(ERRORLOG_PATH, 'query.log')
file_handler = logging.FileHandler(log_file,encoding='utf-8')

# 设置日志格式
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
file_handler.setFormatter(formatter)

# 将文件处理程序添加到logger
query_logger.addHandler(file_handler)
