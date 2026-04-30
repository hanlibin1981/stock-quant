"""
Redis 分布式缓存模块
支持多实例共享缓存、缓存预热、失效广播
"""

import json
import hashlib
import pickle
from typing import Any, Optional, Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
import threading
import logging

logger = logging.getLogger(__name__)


@dataclass
class CacheConfig:
    """缓存配置"""
    host: str = "localhost"
    port: int = 6379
    db: int = 0
    password: str = None
    key_prefix: str = "stock_quant:"
    default_ttl: int = 3600  # 默认TTL（秒）
    max_retries: int = 3
    socket_timeout: int = 5


class RedisDistributedCache:
    """
    Redis 分布式缓存
    
    特性：
    1. 多实例共享缓存
    2. TTL 自动过期
    3. 缓存预热和批量加载
    4. 失效广播（通过 Redis pub/sub）
    5. 降级策略：Redis 不可用时自动降级到内存缓存
    """

    def __init__(self, config: CacheConfig = None):
        """
        Args:
            config: 缓存配置
        """
        self.config = config or CacheConfig()
        self._client = None
        self._pubsub = None
        self._fallback_cache = {}  # 降级到内存缓存
        self._fallback_lock = threading.Lock()
        self._subscribers = {}  # 失效订阅回调
        self._connected = False
        self._connect_lock = threading.Lock()

    def connect(self) -> bool:
        """建立 Redis 连接"""
        with self._connect_lock:
            if self._connected:
                return True
            
            try:
                import redis
                self._client = redis.Redis(
                    host=self.config.host,
                    port=self.config.port,
                    db=self.config.db,
                    password=self.config.password,
                    socket_timeout=self.config.socket_timeout,
                    socket_connect_timeout=self.config.socket_timeout,
                    retry_on_timeout=True,
                    decode_responses=False  # 使用二进制存储
                )
                # 测试连接
                self._client.ping()
                self._connected = True
                logger.info(f"Redis connected: {self.config.host}:{self.config.port}")
                return True
            except ImportError:
                logger.warning("redis-py not installed, using memory fallback cache")
                self._connected = False
                return False
            except Exception as e:
                logger.warning(f"Redis connection failed, using memory fallback: {e}")
                self._connected = False
                return False

    def _get_key(self, key: str) -> str:
        """获取带前缀的完整 key"""
        return f"{self.config.key_prefix}{key}"

    def get(self, key: str, default: Any = None) -> Any:
        """
        获取缓存值
        
        Args:
            key: 缓存 key
            default: 默认值
        
        Returns:
            缓存值或默认值
        """
        # 先尝试 Redis
        if self._connected and self._client:
            try:
                full_key = self._get_key(key)
                value = self._client.get(full_key)
                if value is not None:
                    return pickle.loads(value)
            except Exception as e:
                logger.debug(f"Redis get failed: {e}")

        # 降级到内存缓存
        with self._fallback_lock:
            if key in self._fallback_cache:
                entry = self._fallback_cache[key]
                if entry["expires_at"] > datetime.now():
                    return entry["value"]
                else:
                    del self._fallback_cache[key]

        return default

    def set(
        self,
        key: str,
        value: Any,
        ttl: int = None,
        broadcast: bool = False
    ) -> bool:
        """
        设置缓存值
        
        Args:
            key: 缓存 key
            value: 缓存值
            ttl: TTL 秒数（None 使用默认）
            broadcast: 是否广播失效通知
        
        Returns:
            是否成功
        """
        if ttl is None:
            ttl = self.config.default_ttl

        # 先尝试 Redis
        if self._connected and self._client:
            try:
                full_key = self._get_key(key)
                serialized = pickle.dumps(value)
                self._client.setex(full_key, ttl, serialized)
                
                # 广播失效（通过 pub/sub）
                if broadcast:
                    self._publish_invalidation(key)
                
                return True
            except Exception as e:
                logger.debug(f"Redis set failed: {e}")

        # 降级到内存缓存
        with self._fallback_lock:
            self._fallback_cache[key] = {
                "value": value,
                "expires_at": datetime.now() + timedelta(seconds=ttl)
            }

        return True

    def delete(self, key: str, broadcast: bool = False) -> bool:
        """
        删除缓存
        
        Args:
            key: 缓存 key
            broadcast: 是否广播失效通知
        
        Returns:
            是否成功
        """
        if self._connected and self._client:
            try:
                full_key = self._get_key(key)
                self._client.delete(full_key)
                if broadcast:
                    self._publish_invalidation(key)
                return True
            except Exception as e:
                logger.debug(f"Redis delete failed: {e}")

        with self._fallback_lock:
            self._fallback_cache.pop(key, None)

        return True

    def exists(self, key: str) -> bool:
        """检查 key 是否存在"""
        if self._connected and self._client:
            try:
                return bool(self._client.exists(self._get_key(key)))
            except Exception:
                pass

        with self._fallback_lock:
            if key in self._fallback_cache:
                entry = self._fallback_cache[key]
                if entry["expires_at"] > datetime.now():
                    return True
                else:
                    del self._fallback_cache[key]
        return False

    def get_many(self, keys: list) -> dict:
        """
        批量获取缓存
        
        Args:
            keys: key 列表
        
        Returns:
            {key: value} 字典，只包含存在的 key
        """
        result = {}
        
        if self._connected and self._client:
            try:
                full_keys = [self._get_key(k) for k in keys]
                values = self._client.mget(full_keys)
                for key, value in zip(keys, values):
                    if value is not None:
                        result[key] = pickle.loads(value)
            except Exception as e:
                logger.debug(f"Redis mget failed: {e}")

        # 补充内存缓存
        with self._fallback_lock:
            now = datetime.now()
            for key in keys:
                if key not in result and key in self._fallback_cache:
                    entry = self._fallback_cache[key]
                    if entry["expires_at"] > now:
                        result[key] = entry["value"]

        return result

    def set_many(self, mapping: dict, ttl: int = None) -> bool:
        """
        批量设置缓存
        
        Args:
            mapping: {key: value} 字典
            ttl: TTL 秒数
        
        Returns:
            是否成功
        """
        if ttl is None:
            ttl = self.config.default_ttl

        success = True
        
        if self._connected and self._client:
            try:
                pipe = self._client.pipeline()
                for key, value in mapping.items():
                    full_key = self._get_key(key)
                    serialized = pickle.dumps(value)
                    pipe.setex(full_key, ttl, serialized)
                pipe.execute()
                return True
            except Exception as e:
                logger.debug(f"Redis mset failed: {e}")
                success = False

        # 降级到内存缓存
        with self._fallback_lock:
            expires_at = datetime.now() + timedelta(seconds=ttl)
            for key, value in mapping.items():
                self._fallback_cache[key] = {
                    "value": value,
                    "expires_at": expires_at
                }

        return success

    def clear_pattern(self, pattern: str) -> int:
        """
        清除匹配 pattern 的所有 key
        
        Args:
            pattern: key 模式（如 "stock:*"）
        
        Returns:
            清除的 key 数量
        """
        count = 0
        
        if self._connected and self._client:
            try:
                full_pattern = self._get_key(pattern)
                cursor = 0
                while True:
                    cursor, keys = self._client.scan(cursor, match=full_pattern, count=100)
                    if keys:
                        self._client.delete(*keys)
                        count += len(keys)
                    if cursor == 0:
                        break
            except Exception as e:
                logger.debug(f"Redis clear_pattern failed: {e}")

        return count

    def get_ttl(self, key: str) -> int:
        """
        获取 key 的剩余 TTL
        
        Args:
            key: 缓存 key
        
        Returns:
            剩余秒数，-1 表示不存在，-2 表示无过期时间
        """
        if self._connected and self._client:
            try:
                return self._client.ttl(self._get_key(key))
            except Exception:
                pass

        with self._fallback_lock:
            if key in self._fallback_cache:
                entry = self._fallback_cache[key]
                remaining = (entry["expires_at"] - datetime.now()).total_seconds()
                return max(0, int(remaining))
        return -1

    def _publish_invalidation(self, key: str):
        """发布失效通知"""
        try:
            channel = f"{self.config.key_prefix}invalidation"
            message = json.dumps({"key": key, "timestamp": datetime.now().isoformat()})
            self._client.publish(channel, message)
        except Exception as e:
            logger.debug(f"Publish invalidation failed: {e}")

    def subscribe_invalidation(self, key_pattern: str, callback: Callable):
        """
        订阅失效通知
        
        Args:
            key_pattern: key 模式（如 "stock:*"）
            callback: 失效回调函数 (key)
        """
        if not self._connected:
            return

        try:
            channel = f"{self.config.key_prefix}invalidation"
            
            def listener(msg):
                if msg["type"] == "message":
                    try:
                        data = json.loads(msg["data"])
                        pattern_key = data["key"]
                        # 检查是否匹配模式
                        if self._match_pattern(key_pattern, pattern_key):
                            callback(pattern_key)
                    except Exception:
                        pass
            
            pubsub = self._client.pubsub()
            pubsub.subscribe(**{channel: listener})
            self._subscribers[key_pattern] = pubsub
        except Exception as e:
            logger.debug(f"Subscribe invalidation failed: {e}")

    def _match_pattern(self, pattern: str, key: str) -> bool:
        """简单的模式匹配（支持 * 和 ?）"""
        import fnmatch
        return fnmatch.fnmatch(key, pattern)

    def warm_up(self, data_loader: Callable, keys: list, ttl: int = None):
        """
        缓存预热：批量加载数据并缓存
        
        Args:
            data_loader: 数据加载函数 (keys) -> {key: value}
            keys: key 列表
            ttl: TTL 秒数
        """
        try:
            # 批量加载数据
            data = data_loader(keys)
            if data:
                self.set_many(data, ttl)
                logger.info(f"Cache warm-up completed: {len(data)} items")
        except Exception as e:
            logger.error(f"Cache warm-up failed: {e}")

    def get_stats(self) -> dict:
        """获取缓存统计"""
        stats = {
            "connected": self._connected,
            "fallback_size": 0,
            "subscribers": len(self._subscribers)
        }

        if self._connected and self._client:
            try:
                info = self._client.info("stats")
                stats["hits"] = info.get("keyspace_hits", 0)
                stats["misses"] = info.get("keyspace_misses", 0)
                stats["memory"] = info.get("used_memory_human", "N/A")
            except Exception:
                pass

        with self._fallback_lock:
            stats["fallback_size"] = len(self._fallback_cache)

        return stats

    def close(self):
        """关闭连接"""
        if self._client:
            try:
                for pubsub in self._subscribers.values():
                    pubsub.close()
            except Exception:
                pass
            try:
                self._client.close()
            except Exception:
                pass
        self._connected = False
        self._subscribers.clear()


# 全局缓存实例
_global_cache = None
_global_cache_lock = threading.Lock()


def get_cache(config: CacheConfig = None) -> RedisDistributedCache:
    """
    获取全局缓存实例（单例）
    
    Args:
        config: 缓存配置
    
    Returns:
        RedisDistributedCache 实例
    """
    global _global_cache
    
    with _global_cache_lock:
        if _global_cache is None:
            _global_cache = RedisDistributedCache(config)
            _global_cache.connect()
        return _global_cache


def close_cache():
    """关闭全局缓存"""
    global _global_cache
    
    with _global_cache_lock:
        if _global_cache is not None:
            _global_cache.close()
            _global_cache = None