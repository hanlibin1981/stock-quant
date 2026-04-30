"""
数据增量更新模块
减少API调用，只获取新数据
"""

import pandas as pd
import threading
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional, Dict, Tuple
from dataclasses import dataclass

from src.utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class DataFreshness:
    """数据新鲜度"""
    code: str
    last_date: str  # 最新数据的日期
    days_ago: int  # 距离今天的天数
    is_stale: bool  # 是否过期需要更新
    needs_full_reload: bool  # 是否需要完全重新加载


class IncrementalDataManager:
    """
    增量数据管理器
    
    策略：
    1. 检查本地数据新鲜度
    2. 只获取本地数据截止日期之后的新数据
    3. 合并增量数据更新本地缓存
    4. 定期清理过期数据
    """

    # 数据新鲜度阈值（天）
    FRESH_THRESHOLD_MINUTES = 30  # 交易时间内30分钟
    FRESH_THRESHOLD_HOURS = 2  # 非交易时间2小时
    STALE_THRESHOLD_DAYS = 5  # 超过5天认为是旧数据

    def __init__(self, data_manager):
        """
        Args:
            data_manager: StockDataManager 实例
        """
        self.data_manager = data_manager
        self._cache: Dict[str, tuple] = {}  # code -> (df, timestamp)
        self._lock = threading.Lock()

    def check_freshness(self, code: str) -> DataFreshness:
        """
        检查数据的最新程度
        
        Args:
            code: 股票代码
        
        Returns:
            DataFreshness 数据新鲜度信息
        """
        df = self.get_cached_data(code)
        
        if df is None or df.empty:
            return DataFreshness(
                code=code,
                last_date="",
                days_ago=999,
                is_stale=True,
                needs_full_reload=True
            )
        
        latest_date = df['date'].max()
        latest_str = str(latest_date)[:10] if hasattr(latest_date, 'date') else str(latest_date)[:10]
        
        try:
            from datetime import datetime
            latest_dt = datetime.strptime(latest_str, '%Y-%m-%d')
            days_ago = (datetime.now() - latest_dt).days
        except:
            days_ago = 999
        
        now = datetime.now()
        is_trading_time = self._is_trading_hours(now)
        
        # 判断是否过期
        if is_trading_time:
            is_stale = days_ago > 0  # 交易时间只要不是今天就过期
        else:
            # 非交易时间
            if days_ago == 0:
                is_stale = False  # 今天的数据不标记过期
            elif days_ago == 1 and now.hour < 9:
                is_stale = False  # 昨天收盘后但今天开盘前的数据可接受
            else:
                is_stale = days_ago >= self.STALE_THRESHOLD_DAYS
        
        needs_full_reload = days_ago > 30  # 超过30天需要全量加载
        
        return DataFreshness(
            code=code,
            last_date=latest_str,
            days_ago=days_ago,
            is_stale=is_stale,
            needs_full_reload=needs_full_reload
        )

    def _is_trading_hours(self, dt: datetime) -> bool:
        """判断是否在交易时间内"""
        weekday = dt.weekday()
        if weekday >= 5:  # 周六、周日
            return False
        
        hour = dt.hour
        minute = dt.minute
        current_minutes = hour * 60 + minute
        
        # 上午: 9:30 - 11:30
        morning_start = 9 * 60 + 30
        morning_end = 11 * 60 + 30
        
        # 下午: 13:00 - 15:00
        afternoon_start = 13 * 60
        afternoon_end = 15 * 60
        
        return (morning_start <= current_minutes <= morning_end or 
                afternoon_start <= current_minutes <= afternoon_end)

    def get_cached_data(self, code: str) -> Optional[pd.DataFrame]:
        """获取缓存数据"""
        with self._lock:
            if code in self._cache:
                df, timestamp = self._cache[code]
                # 缓存有效期2小时
                import time
                if time.time() - timestamp < 7200:
                    return df.copy()
            return None

    def set_cached_data(self, code: str, df: pd.DataFrame):
        """设置缓存数据"""
        if df is None or df.empty:
            return
        with self._lock:
            import time
            self._cache[code] = (df.copy(), time.time())

    def get_incremental_update(
        self, 
        code: str, 
        api_client,
        days: int = 250
    ) -> Tuple[Optional[pd.DataFrame], bool]:
        """
        获取增量更新数据
        
        Args:
            code: 股票代码
            api_client: API客户端
            days: 最大天数
        
        Returns:
            (增量数据, 是否全量加载)
        """
        # 获取本地数据
        local_df = self.data_manager.get_stock_data(code)
        
        if local_df is not None and not local_df.empty:
            # 有本地数据，检查新鲜度
            freshness = self.check_freshness(code)
            
            if not freshness.is_stale:
                # 数据足够新鲜，直接返回本地数据
                self.set_cached_data(code, local_df)
                return local_df, False
            
            # 需要增量更新
            if not freshness.is_stale and not freshness.needs_full_reload:
                # 获取本地最新日期
                last_date = local_df['date'].max()
                last_date_str = str(last_date)[:10]
                
                # 只获取比last_date更新的数据（加1天避免重复）
                try:
                    from datetime import datetime, timedelta
                    start_date_dt = datetime.strptime(last_date_str, '%Y-%m-%d') + timedelta(days=1)
                    start_date = start_date_dt.strftime('%Y%m%d')
                except:
                    start_date = None
                
                # 增量获取
                incremental_df = self._fetch_incremental(api_client, code, start_date)
                
                if incremental_df is not None and not incremental_df.empty:
                    # 合并数据
                    combined_df = pd.concat([local_df, incremental_df], ignore_index=True)
                    # 去重（按日期）
                    combined_df = combined_df.drop_duplicates(subset=['date'], keep='last')
                    combined_df = combined_df.sort_values('date')
                    
                    # 更新本地存储
                    self.data_manager.save_stock_data(code, combined_df)
                    self.set_cached_data(code, combined_df)
                    
                    logger.info(f"增量更新 {code}: +{len(incremental_df)} 条新数据")
                    return combined_df, False
                else:
                    # 增量获取失败，返回本地数据
                    self.set_cached_data(code, local_df)
                    return local_df, False
            else:
                # 数据太旧，需要全量重新加载
                pass
        
        # 全量加载
        full_df = self._fetch_full(api_client, code, days)
        if full_df is not None and not full_df.empty:
            self.data_manager.save_stock_data(code, full_df)
            self.set_cached_data(code, full_df)
            logger.info(f"全量加载 {code}: {len(full_df)} 条数据")
        
        return full_df, True

    def _fetch_incremental(
        self, 
        api_client, 
        code: str, 
        start_date: str
    ) -> Optional[pd.DataFrame]:
        """获取增量数据"""
        try:
            if hasattr(api_client, 'get_kline'):
                return api_client.get_kline(code, days=5)  # 只获取最近5天
            elif hasattr(api_client, 'daily'):
                df = api_client.daily(
                    ts_code=self._convert_code(code),
                    start_date=start_date
                )
                if df is not None:
                    df = df.rename(columns={
                        'ts_code': 'code',
                        'trade_date': 'date'
                    })
                    df['date'] = pd.to_datetime(df['date'])
                return df
        except Exception as e:
            logger.error(f"增量获取失败 {code}: {e}")
        return None

    def _fetch_full(
        self, 
        api_client, 
        code: str, 
        days: int
    ) -> Optional[pd.DataFrame]:
        """获取全量数据"""
        try:
            if hasattr(api_client, 'get_kline'):
                return api_client.get_kline(code, days=days)
        except Exception as e:
            logger.error(f"全量获取失败 {code}: {e}")
        return None

    def _convert_code(self, code: str) -> str:
        """转换股票代码"""
        if code.startswith('6'):
            return f"{code}.SH"
        elif code.startswith('0') or code.startswith('3'):
            return f"{code}.SZ"
        return f"{code}.SZ"

    def clear_cache(self):
        """清空缓存"""
        with self._lock:
            self._cache.clear()
        logger.info("增量更新缓存已清空")

    def get_stats(self) -> Dict:
        """获取统计信息"""
        stats = {
            'cached_codes': len(self._cache),
            'cache_total_size': sum(
                len(df) for df, _ in self._cache.values()
            )
        }
        return stats


def create_incremental_manager(data_manager) -> IncrementalDataManager:
    """创建增量数据管理器"""
    return IncrementalDataManager(data_manager)
