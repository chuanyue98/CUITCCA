"""礼貌抓取的两个基础机制：请求间隔限速、失败重试退避。

拆成独立、不依赖 httpx 具体类型的小模块，是为了能脱离网络单测——限速逻辑
测的是"时间间隔"，重试逻辑测的是"第 N 次才成功时的调用次数与退避时长"，两者
都可以用普通函数/fake 时钟验证，不需要真的发请求。
"""
from __future__ import annotations

import random
import threading
import time
from collections.abc import Callable


class IntervalRateLimiter:
    """全局请求间隔限速器：保证连续两次 ``wait()`` 返回之间至少间隔
    ``interval_seconds``。用一把锁保护"上次请求时间"这个共享状态，天然对
    多线程并发抓取安全（配合 ``max_concurrency`` 的线程池使用）。

    没有用更复杂的令牌桶，是因为这里的诉求只是"别把对方服务器打太快"，不需要
    支持突发流量——固定间隔比令牌桶更容易讲清楚"这是什么策略"，符合"礼貌抓取"
    这个目标本身应该朴素、可解释。
    """

    def __init__(self, interval_seconds: float, sleep: Callable[[float], None] = time.sleep):
        self._interval = max(0.0, interval_seconds)
        self._sleep = sleep
        self._lock = threading.Lock()
        self._last_request_at: float | None = None
        self._clock: Callable[[], float] = time.monotonic

    def wait(self) -> None:
        """阻塞到可以发起下一次请求为止。"""
        with self._lock:
            now = self._clock()
            if self._last_request_at is not None:
                elapsed = now - self._last_request_at
                remaining = self._interval - elapsed
                if remaining > 0:
                    self._sleep(remaining)
                    now = self._clock()
            self._last_request_at = now


class RetryExhaustedError(RuntimeError):
    """重试次数用尽后仍未成功，携带最后一次的原始异常，方便调用方打印诊断
    信息而不是只看到一个模糊的"重试失败"。"""

    def __init__(self, attempts: int, last_error: BaseException):
        super().__init__(f"重试 {attempts} 次后仍然失败: {type(last_error).__name__}: {last_error}")
        self.attempts = attempts
        self.last_error = last_error


def call_with_retry[T](
    func: Callable[[], T],
    *,
    max_retries: int,
    backoff_seconds: float,
    retry_on: tuple[type[BaseException], ...],
    sleep: Callable[[float], None] = time.sleep,
    jitter: float = 0.2,
) -> T:
    """指数退避重试。第 1 次失败等 ``backoff_seconds``，第 2 次等
    ``backoff_seconds * 2``，以此类推；加一点随机抖动（``jitter`` 比例）避免
    多个失败请求同步重试造成新的瞬时压力（"惊群"）。

    :param max_retries: 除首次尝试外的最大重试次数。``max_retries=3`` 意味着
        总共最多尝试 4 次。
    :param retry_on: 只对这些异常类型重试，其他异常直接向上抛——不能把
        "调用方代码本身写错了"也当成"网络抖动"来重试。
    """
    attempt = 0
    last_error: BaseException | None = None
    while attempt <= max_retries:
        try:
            return func()
        except retry_on as e:  # type: ignore[misc]
            last_error = e
            attempt += 1
            if attempt > max_retries:
                break
            delay = backoff_seconds * (2 ** (attempt - 1))
            delay += random.uniform(0, delay * jitter)
            sleep(delay)
    assert last_error is not None  # 循环至少跑一次，失败时 last_error 必被赋值
    raise RetryExhaustedError(attempts=attempt, last_error=last_error)
