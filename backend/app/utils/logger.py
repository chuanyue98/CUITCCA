import logging

# 创建一个名为 "customer_logger" 的日志记录器
customer_logger = logging.getLogger("customer_logger")
customer_logger.setLevel(logging.INFO)

# 创建一个 StreamHandler
stream_handler = logging.StreamHandler()

# 设置日志记录器的处理器为 StreamHandler
customer_logger.addHandler(stream_handler)

# 设置 StreamHandler 的格式化器为内置的 ColoredFormatter
stream_handler.setFormatter(logging.Formatter('\033[1;34mCustomer - %(asctime)s - %(levelname)s - %(message)s\033[0m'))
