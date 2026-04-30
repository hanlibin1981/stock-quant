"""
缓存模块

包含：
- redis_cache: Redis 分布式缓存
"""

from src.core.cache.redis_cache import (
    RedisDistributedCache,
    CacheConfig,
    get_cache,
    close_cache
)

__all__ = [
    'RedisDistributedCache',
    'CacheConfig',
    'get_cache',
    'close_cache'
]