"""
Token Bucket 限流器
支持 per-token 限流、滑动窗口、自动降级
"""

import time
import threading
from typing import Dict, Optional, Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from collections import defaultdict
import logging

logger = logging.getLogger(__name__)


@dataclass
class RateLimitConfig:
    """限流配置"""
    tokens_per_second: float = 2.0  # 每秒补充的 token 数
    max_tokens: int = 10  # 最大 token 数（突发容量）
    block_duration: int = 60  # 触发限流后锁定秒数
    enable_adaptive: bool = True  # 是否启用自适应（根据 429 响应调整）


class TokenBucket:
    """单 token 的限流桶"""

    def __init__(self, config: RateLimitConfig):
        self.config = config
        self.tokens = config.max_tokens
        self.last_update = time.monotonic()
        self.locked_until: Optional[float] = None  # 被锁定时的时间戳
        self.success_count = 0  # 成功计数（用于自适应）
        self.rate_limit_count = 0  # 限流计数

    def _refill(self):
        """补充 token"""
        now = time.monotonic()
        elapsed = now - self.last_update
        new_tokens = elapsed * self.config.tokens_per_second
        self.tokens = min(self.config.max_tokens, self.tokens + new_tokens)
        self.last_update = now

    def can_acquire(self) -> bool:
        """是否能获取一个 token"""
        self._refill()

        # 检查是否被锁定
        if self.locked_until and time.monotonic() < self.locked_until:
            return False

        return self.tokens >= 1

    def acquire(self, blocking: bool = False, timeout: float = None) -> bool:
        """
        获取 token
        
        Args:
            blocking: 是否阻塞等待
            timeout: 阻塞超时（秒）
        
        Returns:
            是否成功获取
        """
        start_time = time.monotonic()

        while True:
            self._refill()

            # 检查锁定
            if self.locked_until and time.monotonic() < self.locked_until:
                if not blocking:
                    return False
                remaining = self.locked_until - time.monotonic()
                if timeout and (time.monotonic() - start_time) >= timeout:
                    return False
                time.sleep(min(remaining, 0.1))
                continue

            if self.tokens >= 1:
                self.tokens -= 1
                self.success_count += 1
                return True

            if not blocking:
                return False

            if timeout and (time.monotonic() - start_time) >= timeout:
                return False

            # 等待 token 补充
            wait_time = (1 - self.tokens) / self.config.tokens_per_second
            if timeout:
                wait_time = min(wait_time, timeout - (time.monotonic() - start_time))
            time.sleep(max(0.01, wait_time))

    def trigger_rate_limit(self):
        """触发限流，增加锁定时间"""
        self.rate_limit_count += 1
        self.locked_until = time.monotonic() + self.config.block_duration
        logger.warning(f"Rate limit triggered, blocked for {self.config.block_duration}s")

    def adapt_rate(self, multiplier: float = 0.8):
        """
        自适应调整速率（根据 429 响应）
        
        Args:
            multiplier: 速率倍数（0.8 表示降低 20%）
        """
        if not self.config.enable_adaptive:
            return

        old_rate = self.config.tokens_per_second
        self.config.tokens_per_second = max(0.1, self.config.tokens_per_second * multiplier)
        self.config.max_tokens = max(1, int(self.config.max_tokens * multiplier))
        self.tokens = min(self.tokens, self.config.max_tokens)
        logger.info(f"Rate adapted: {old_rate:.2f} -> {self.config.tokens_per_second:.2f} tok/s")


class MultiTokenBucketRateLimiter:
    """
    多 Token Bucket 限流器
    
    特性：
    1. 支持多个 token（多账号）
    2. 滑动窗口统计
    3. 自适应速率调整
    4. 自动降级（触发限流后自动等待）
    """

    def __init__(self, default_config: RateLimitConfig = None):
        """
        Args:
            default_config: 默认限流配置
        """
        self.default_config = default_config or RateLimitConfig()
        self._buckets: Dict[str, TokenBucket] = {}
        self._lock = threading.Lock()
        self._stats = defaultdict(lambda: {"acquired": 0, "rejected": 0, "wait_time": 0.0})

    def _get_or_create_bucket(self, token: str) -> TokenBucket:
        """获取或创建 token bucket"""
        with self._lock:
            if token not in self._buckets:
                self._buckets[token] = TokenBucket(self.default_config)
            return self._buckets[token]

    def acquire(
        self,
        token: str,
        blocking: bool = True,
        timeout: float = 30.0
    ) -> bool:
        """
        获取限流许可
        
        Args:
            token: API token
            blocking: 是否阻塞
            timeout: 超时时间
        
        Returns:
            是否成功获取许可
        """
        bucket = self._get_or_create_bucket(token)
        start_time = time.monotonic()

        result = bucket.acquire(blocking=blocking, timeout=timeout)

        elapsed = time.monotonic() - start_time
        stat = self._stats[token]
        stat["acquired"] += 1 if result else 0
        stat["rejected"] += 0 if result else 1
        stat["wait_time"] += elapsed

        return result

    def wait_and_acquire(self, token: str, timeout: float = 60.0) -> bool:
        """
        等待并获取许可（自动等待直到可获取）
        
        Args:
            token: API token
            timeout: 最大等待时间
        
        Returns:
            是否成功
        """
        return self.acquire(token, blocking=True, timeout=timeout)

    def trigger_rate_limit(self, token: str):
        """
        通知限流发生（调用方在收到 429 时调用）
        
        Args:
            token: API token
        """
        bucket = self._get_or_create_bucket(token)
        bucket.trigger_rate_limit()

    def adapt_rate(self, token: str, multiplier: float = 0.8):
        """
        自适应调整速率
        
        Args:
            token: API token
            multiplier: 调整倍数
        """
        bucket = self._get_or_create_bucket(token)
        bucket.adapt_rate(multiplier)

    def get_stats(self, token: str = None) -> dict:
        """
        获取限流统计
        
        Args:
            token: specific token 或 None 获取全部
        
        Returns:
            统计信息
        """
        with self._lock:
            if token:
                return dict(self._stats[token])
            return {k: dict(v) for k, v in self._stats.items()}

    def get_bucket_info(self, token: str) -> dict:
        """获取 bucket 详细信息"""
        bucket = self._get_or_create_bucket(token)
        
        locked_remaining = 0.0
        if bucket.locked_until:
            locked_remaining = max(0, bucket.locked_until - time.monotonic())
        
        return {
            "tokens": round(bucket.tokens, 2),
            "max_tokens": bucket.config.max_tokens,
            "tokens_per_second": round(bucket.config.tokens_per_second, 2),
            "locked": locked_remaining > 0,
            "locked_remaining": round(locked_remaining, 2),
            "success_count": bucket.success_count,
            "rate_limit_count": bucket.rate_limit_count
        }

    def remove_token(self, token: str):
        """移除 token（清理资源）"""
        with self._lock:
            if token in self._buckets:
                del self._buckets[token]
            if token in self._stats:
                del self._stats[token]


class RateLimitedCaller:
    """
    带限流的 API 调用器
    
    封装限流逻辑，自动处理等待和降级
    """

    def __init__(
        self,
        rate_limiter: MultiTokenBucketRateLimiter,
        token_provider: Callable[[], str],
        on_rate_limit: Callable[[str], None] = None
    ):
        """
        Args:
            rate_limiter: 限流器
            token_provider: token 提供函数（返回当前使用的 token）
            on_rate_limit: 触发限流时的回调
        """
        self.rate_limiter = rate_limiter
        self.token_provider = token_provider
        self.on_rate_limit = on_rate_limit

    def call(
        self,
        api_func: Callable,
        *args,
        max_retries: int = 3,
        **kwargs
    ):
        """
        调用 API（自动限流）
        
        Args:
            api_func: API 函数
            *args: API 函数参数
            max_retries: 最大重试次数（限流触发时）
            **kwargs: API 函数关键字参数
        
        Returns:
            API 返回值
        
        Raises:
            API 函数自身的异常
        """
        retries = 0
        
        while True:
            token = self.token_provider()
            
            if not self.rate_limiter.wait_and_acquire(token, timeout=30.0):
                # 等待超时，可能限流中
                if retries < max_retries:
                    retries += 1
                    time.sleep(min(5 * retries, 30))
                    continue
                raise Exception("Rate limit timeout, cannot acquire token")

            try:
                result = api_func(*args, **kwargs)
                
                # 检查返回是否是限流错误（由调用方判断）
                return result
                
            except Exception as e:
                error_str = str(e).lower()
                
                # 检测限流错误
                if "429" in error_str or "rate limit" in error_str or "too many requests" in error_str:
                    self.rate_limiter.trigger_rate_limit(token)
                    
                    if self.on_rate_limit:
                        self.on_rate_limit(token)
                    
                    if retries < max_retries:
                        retries += 1
                        # 根据限流次数调整等待时间
                        wait_time = min(60, 5 * retries)
                        logger.warning(f"Rate limit hit, waiting {wait_time}s before retry {retries}/{max_retries}")
                        time.sleep(wait_time)
                        continue
                
                raise

    def notify_rate_limit_response(self, token: str, status_code: int):
        """
        通知 API 响应（用于自适应调整）
        
        Args:
            token: API token
            status_code: HTTP 状态码
        """
        if status_code == 429:
            self.rate_limiter.trigger_rate_limit(token)
            self.rate_limiter.adapt_rate(token, multiplier=0.8)
        elif status_code == 200:
            # 成功，可以稍微放宽限制
            pass  # 保持当前速率


# 全局限流器实例
_global_limiter: Optional[MultiTokenBucketRateLimiter] = None
_limiter_lock = threading.Lock()


def get_rate_limiter() -> MultiTokenBucketRateLimiter:
    """获取全局限流器"""
    global _global_limiter
    
    with _limiter_lock:
        if _global_limiter is None:
            _global_limiter = MultiTokenBucketRateLimiter()
        return _global_limiter


def reset_rate_limiter():
    """重置全局限流器（用于测试）"""
    global _global_limiter
    
    with _limiter_lock:
        _global_limiter = None