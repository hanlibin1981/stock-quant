"""
Tushare 数据源 - 优化版
添加重试机制、429限流处理、数据缓存
"""

import os
import sys
import socket
import threading
import time
import logging
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional, Dict, List
from functools import wraps

import pandas as pd

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def tushare_retry_on_error(max_retries: int = 3, base_delay: float = 1.0):
    """
    Tushare API 重试装饰器（指数退避 + 429限流处理）
    
    Args:
        max_retries: 最大重试次数
        base_delay: 基础延迟（秒），指数退避
    """
    def decorator(func):
        @wraps(func)
        def wrapper(self, *args, **kwargs):
            last_error = None
            consecutive_429 = 0
            
            for attempt in range(max_retries):
                try:
                    result = func(self, *args, **kwargs)
                    # 成功时重置429计数
                    consecutive_429 = 0
                    return result
                    
                except Exception as e:
                    last_error = e
                    error_str = str(e).lower()
                    
                    # 检测429限流
                    if '429' in error_str or 'rate limit' in error_str or 'too many' in error_str:
                        consecutive_429 += 1
                        # 429后等待更长时间（60秒或指数退避）
                        wait_time = max(60, base_delay * (2 ** consecutive_429))
                        logger.warning(f"Tushare API 限流，等待 {wait_time:.1f}秒后重试...")
                        time.sleep(wait_time)
                        continue
                    
                    # 网络错误，指数退避重试
                    if attempt < max_retries - 1:
                        delay = base_delay * (2 ** attempt)
                        logger.warning(f"Tushare API 请求失败 ({attempt+1}/{max_retries}): {e}，{delay:.1f}秒后重试...")
                        time.sleep(delay)
                        continue
                    else:
                        # 最后一次尝试也失败
                        logger.error(f"Tushare API 请求失败 {max_retries}次: {e}")
                        raise
                
            # 所有重试都失败
            if last_error:
                raise last_error
            return None
                
        return wrapper
    return decorator


class TushareCache:
    """Tushare 数据缓存（内存LRU）"""
    
    def __init__(self, max_size: int = 100, ttl_seconds: int = 3600):
        self._cache: Dict[str, tuple] = {}  # key -> (data, timestamp)
        self._max_size = max_size
        self._ttl_seconds = ttl_seconds
        self._lock = threading.Lock()
    
    def _make_key(self, prefix: str, **kwargs) -> str:
        """生成缓存键"""
        parts = [prefix]
        for k, v in sorted(kwargs.items()):
            parts.append(f"{k}={v}")
        return "|".join(parts)
    
    def get(self, prefix: str, **kwargs) -> Optional[pd.DataFrame]:
        """获取缓存数据"""
        key = self._make_key(prefix, **kwargs)
        with self._lock:
            if key in self._cache:
                data, timestamp = self._cache[key]
                if time.time() - timestamp < self._ttl_seconds:
                    logger.debug(f"缓存命中: {key}")
                    return data
                else:
                    # 过期删除
                    del self._cache[key]
        return None
    
    def set(self, prefix: str, data: pd.DataFrame, **kwargs):
        """设置缓存数据"""
        if data is None or data.empty:
            return
        
        key = self._make_key(prefix, **kwargs)
        with self._lock:
            # LRU清理
            if len(self._cache) >= self._max_size:
                oldest_key = min(self._cache.keys(), key=lambda k: self._cache[k][1])
                del self._cache[oldest_key]
            self._cache[key] = (data.copy(), time.time())
            logger.debug(f"缓存写入: {key}")
    
    def clear(self):
        """清空缓存"""
        with self._lock:
            self._cache.clear()


class TushareClient:
    """TuShare 数据客户端（线程安全单例）- 优化版"""

    _lock = threading.Lock()
    _client_cache = TushareCache(max_size=100, ttl_seconds=3600)

    def __init__(self, token: str = None):
        self.token = token or os.environ.get('TUSHARE_TOKEN')
        self.base_url = 'https://api.tushare.pro'
        self.pro = None
        self._ts_module = None

        if self.token:
            self._init_pro()

    def _init_pro(self):
        """初始化 TuShare Pro（线程安全）"""
        with self._lock:
            if self.pro is not None:
                return
            try:
                import tushare as ts
                socket.setdefaulttimeout(15)
                self._ts_module = ts
                ts.set_token(self.token)
                self.pro = ts.pro_api()
                self.pro._DataApi__timeout = 10
                logger.info("TuShare Pro initialized (timeout=10s)")
            except ImportError:
                logger.warning("tushare not installed")
            except Exception as e:
                logger.error(f"Error initializing TuShare: {e}")

    def is_available(self) -> bool:
        """检查是否可用"""
        return self.pro is not None

    @tushare_retry_on_error(max_retries=3, base_delay=1.0)
    def get_realtime(self, code: str) -> Optional[Dict]:
        """获取实时行情（带重试）"""
        if not self.pro:
            return None

        # 检查缓存（实时数据1分钟有效期）
        cached = TushareClient._client_cache.get("realtime", code=code)
        if cached is not None and not cached.empty:
            row = cached.iloc[-1]
            return {
                'code': code,
                'name': row.get('name', ''),
                'price': row.get('close', 0),
                'open': row.get('open', 0),
                'high': row.get('high', 0),
                'low': row.get('low', 0),
                'volume': row.get('vol', 0),
                'amount': row.get('amount', 0),
                'change': row.get('pct_chg', 0),
            }

        try:
            ts_code = self._convert_code(code)
            df = self.pro.realtime_daily(ts_code=ts_code)
            if df is not None and not df.empty:
                # 写入缓存
                TushareClient._client_cache.set("realtime", df, code=code)
                row = df.iloc[-1]
                return {
                    'code': code,
                    'name': row.get('name', ''),
                    'price': row.get('close', 0),
                    'open': row.get('open', 0),
                    'high': row.get('high', 0),
                    'low': row.get('low', 0),
                    'volume': row.get('vol', 0),
                    'amount': row.get('amount', 0),
                    'change': row.get('pct_chg', 0),
                }
        except Exception as e:
            logger.error(f"Error getting realtime from TuShare: {e}")
            raise  # 让装饰器处理重试

        return None

    @tushare_retry_on_error(max_retries=3, base_delay=1.0)
    def get_kline(self, code: str, days: int = 250, ktype: str = 'D') -> Optional[pd.DataFrame]:
        """
        获取K线数据（带重试和缓存）

        Args:
            code: 股票代码
            days: 天数 (日线=天数，周线=周数，月线=月数)
            ktype: K线类型 D/W/M (日/周/月)
        """
        if not self.pro:
            return None

        # 检查缓存（日线数据1小时有效期）
        cache_ttl = 3600 if ktype == 'D' else 86400  # 周线/月线缓存更久
        TushareClient._client_cache._ttl_seconds = cache_ttl
        cached = TushareClient._client_cache.get("kline", code=code, days=days, ktype=ktype)
        if cached is not None and not cached.empty:
            return cached

        try:
            ts_code = self._convert_code(code)

            # 根据周期类型调整日期范围
            if ktype == 'W':
                days = days * 7
            elif ktype == 'M':
                days = days * 30
            
            end_date = datetime.now().strftime('%Y%m%d')
            start_date = (datetime.now() - timedelta(days=days+30)).strftime('%Y%m%d')

            if ktype == 'W':
                df = self.pro.weekly(ts_code=ts_code, start_date=start_date, end_date=end_date)
            elif ktype == 'M':
                df = self.pro.monthly(ts_code=ts_code, start_date=start_date, end_date=end_date)
            else:
                df = self.pro.daily(ts_code=ts_code, start_date=start_date, end_date=end_date)

            if df is not None and not df.empty:
                df = df.rename(columns={
                    'ts_code': 'code',
                    'trade_date': 'date',
                    'vol': 'volume'
                })
                df['date'] = pd.to_datetime(df['date'])
                df = df.sort_values('date')
                df = df.tail(days)

                # 写入缓存
                TushareClient._client_cache.set("kline", df, code=code, days=days, ktype=ktype)
                
                return df[['date', 'open', 'close', 'high', 'low', 'volume', 'amount']]

        except Exception as e:
            logger.error(f"Error getting kline from TuShare: {e}")
            raise  # 让装饰器处理重试

        return None

    def get_stock_info(self, code: str) -> Optional[Dict]:
        """获取股票基本信息"""
        if not self.pro:
            return None

        cached = TushareClient._client_cache.get("info", code=code)
        if cached is not None and not cached.empty:
            row = cached.iloc[0]
            return {
                'code': code,
                'name': row.get('name', ''),
                'industry': row.get('industry', ''),
                'market': row.get('market', ''),
                'list_date': row.get('list_date', ''),
            }

        try:
            ts_code = self._convert_code(code)
            df = self.pro.stock_basic(ts_code=ts_code, fields='ts_code,name,industry,market,list_date')
            
            if df is not None and not df.empty:
                TushareClient._client_cache.set("info", df, code=code)
                row = df.iloc[0]
                return {
                    'code': code,
                    'name': row.get('name', ''),
                    'industry': row.get('industry', ''),
                    'market': row.get('market', ''),
                    'list_date': row.get('list_date', ''),
                }
        except Exception as e:
            logger.error(f"Error getting stock info: {e}")
        
        return None

    def get_daily_basic(self, code: str, days: int = 30) -> Optional[pd.DataFrame]:
        """获取每日基本面数据"""
        if not self.pro:
            return None

        cached = TushareClient._client_cache.get("basic", code=code, days=days)
        if cached is not None and not cached.empty:
            return cached

        try:
            ts_code = self._convert_code(code)
            end_date = datetime.now().strftime('%Y%m%d')
            start_date = (datetime.now() - timedelta(days=days+30)).strftime('%Y%m%d')

            df = self.pro.daily_basic(
                ts_code=ts_code,
                start_date=start_date,
                end_date=end_date,
                fields='ts_code,trade_date,close,volume,turnover_rate_f,pe,pb,ps'
            )

            if df is not None and not df.empty:
                TushareClient._client_cache.set("basic", df, code=code, days=days)

            return df

        except Exception as e:
            logger.error(f"Error getting daily basic: {e}")
            return None

    def _convert_code(self, code: str) -> str:
        """转换股票代码格式"""
        if code.startswith('6'):
            return f"{code}.SH"
        elif code.startswith('0') or code.startswith('3'):
            return f"{code}.SZ"
        else:
            return f"{code}.SZ"

    @classmethod
    def clear_cache(cls):
        """清空所有缓存"""
        cls._client_cache.clear()
        logger.info("TushareClient 缓存已清空")


# 单例实例
_tushare_client = None
_tushare_lock = threading.Lock()

def get_tushare_client() -> TushareClient:
    """获取 TuShare 客户端单例（线程安全）"""
    global _tushare_client
    if _tushare_client is None:
        with _tushare_lock:
            if _tushare_client is None:
                _tushare_client = TushareClient()
    return _tushare_client
