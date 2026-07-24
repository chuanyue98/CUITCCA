import asyncio
from collections import defaultdict

# 存储访问信息的字典
access_stats = {
    "total_visits": 0,
    "ip_count": 0,
    "user_visits": defaultdict(int),
    "endpoint_visits": defaultdict(int)
}

# 访问统计的异步锁，放在这里避免 router/manage.py 从 main.py 导入造成的循环依赖
access_stats_lock = asyncio.Lock()


if __name__ == '__main__':
    print(access_stats)
