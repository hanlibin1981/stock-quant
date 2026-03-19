"""
Tushare 数据源
集成 TuShare 获取更稳定的股票数据
"""

import os
import sys
from pathlib import Path
import pandas as pd
from typing import Optional, Dict, List
import logging

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class TushareClient:
    """TuShare 数据客户端"""

    def __init__(self, token: str = None):
        self.token = token or os.environ.get('TUSHARE_TOKEN')
        self.base_url = 'https://api.tushare.pro'
        self.pro = None
        self._ts_module = None  # 缓存tushare模块引用

        if self.token:
            self._init_pro()

    def _init_pro(self):
        """初始化 TuShare Pro"""
        try:
            import tushare as ts
            self._ts_module = ts  # 缓存模块引用
            ts.set_token(self.token)
            self.pro = ts.pro_api()
            logger.info("TuShare Pro initialized successfully")
        except ImportError:
            logger.warning("tushare not installed")
        except Exception as e:
            logger.error(f"Error initializing TuShare: {e}")
    
    def is_available(self) -> bool:
        """检查是否可用"""
        return self.pro is not None
    
    def get_realtime(self, code: str) -> Optional[Dict]:
        """获取实时行情"""
        if not self.pro:
            return None

        try:
            # 转换代码格式
            ts_code = self._convert_code(code)

            df = self.pro.realtime_daily(ts_code=ts_code)
            if df is not None and not df.empty:
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

        return None
    
    def get_kline(self, code: str, days: int = 250, ktype: str = 'D') -> Optional[pd.DataFrame]:
        """
        获取K线数据

        Args:
            code: 股票代码
            days: 天数
            ktype: K线类型 D/W/M (日/周/月)
        """
        if not self.pro:
            return None

        try:
            ts_code = self._convert_code(code)

            # 计算日期范围
            from datetime import datetime, timedelta
            end_date = datetime.now().strftime('%Y%m%d')
            start_date = (datetime.now() - timedelta(days=days+30)).strftime('%Y%m%d')

            df = self.pro.daily(
                ts_code=ts_code,
                start_date=start_date,
                end_date=end_date
            )

            if df is not None and not df.empty:
                # 转换列名
                df = df.rename(columns={
                    'ts_code': 'code',
                    'trade_date': 'date',
                    'vol': 'volume'
                })

                # 转换日期格式
                df['date'] = pd.to_datetime(df['date'])

                # 按日期排序
                df = df.sort_values('date')

                # 只返回最近的天数
                df = df.tail(days)

                return df[['date', 'open', 'close', 'high', 'low', 'volume', 'amount']]

        except Exception as e:
            logger.error(f"Error getting kline from TuShare: {e}")

        return None
    
    def get_stock_info(self, code: str) -> Optional[Dict]:
        """获取股票基本信息"""
        if not self.pro:
            return None
        
        try:
            ts_code = self._convert_code(code)
            df = self.pro.stock_basic(ts_code=ts_code, fields='ts_code,name,industry,market,list_date')
            
            if df is not None and not df.empty:
                row = df.iloc[0]
                return {
                    'code': code,
                    'name': row.get('name', ''),
                    'industry': row.get('industry', ''),
                    'market': row.get('market', ''),
                    'list_date': row.get('list_date', ''),
                }
        except Exception as e:
            print(f"Error getting stock info: {e}")
        
        return None
    
    def get_daily_basic(self, code: str, days: int = 30) -> Optional[pd.DataFrame]:
        """获取每日基本面数据"""
        if not self.pro:
            return None

        try:
            ts_code = self._convert_code(code)

            from datetime import datetime, timedelta
            end_date = datetime.now().strftime('%Y%m%d')
            start_date = (datetime.now() - timedelta(days=days+30)).strftime('%Y%m%d')

            df = self.pro.daily_basic(
                ts_code=ts_code,
                start_date=start_date,
                end_date=end_date,
                fields='ts_code,trade_date,close,volume,turnover_rate_f,pe,pb,ps'
            )

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


# 单例实例
_tushare_client = None

def get_tushare_client() -> TushareClient:
    """获取 TuShare 客户端单例"""
    global _tushare_client
    if _tushare_client is None:
        _tushare_client = TushareClient()
    return _tushare_client
