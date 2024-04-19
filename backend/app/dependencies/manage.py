from collections import defaultdict


# 存储访问信息的字典
access_stats = {
    "total_visits": 0,
    "ip_count": defaultdict(int),
    "user_visits": defaultdict(int),
    "endpoint_visits": defaultdict(int)
}


if __name__ == '__main__':
    print(access_stats)