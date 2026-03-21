"""
东方财富 API 客户端
"""

import re
import time
import requests
import pandas as pd
from typing import Optional, Dict, List
from datetime import datetime, timedelta
from functools import wraps

from src.utils.logger import get_logger
from src.utils.validation import validate_stock_code, validate_stock_code_with_exchange

logger = get_logger(__name__)


def _retry_on_error(max_retries: int = 3, delay: float = 0.5):
    """网络请求重试装饰器"""
    def decorator(func):
        @wraps(func)
        def wrapper(self, *args, **kwargs):
            last_error = None
            for attempt in range(max_retries):
                try:
                    return func(self, *args, **kwargs)
                except (requests.RequestException, ValueError, KeyError) as e:
                    last_error = e
                    if attempt < max_retries - 1:
                        time.sleep(delay * (attempt + 1))  # 指数退避
            logger.error(f"重试{max_retries}次后仍失败: {last_error}")
            return None
        return wrapper
    return decorator


class EastMoneyClient:
    """东方财富数据客户端"""

    BASE_URL = "https://push2.eastmoney.com"

    def __init__(self, max_retries: int = 3):
        self.max_retries = max_retries
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': '*/*',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
            'Referer': 'https://www.eastmoney.com/'
        }
        # 使用session复用连接
        self.session = requests.Session()
        self.session.headers.update(self.headers)

    def _validate_code(self, code: str) -> bool:
        """验证股票代码格式"""
        return validate_stock_code(code)

    def _convert_secid(self, code: str) -> str:
        """将股票代码转换为市场secid"""
        result = validate_stock_code_with_exchange(code)
        if not result:
            raise ValueError(f"无效的股票代码: {code}")
        code, exchange = result
        # eastmoney 使用 1.前缀表示上海，0.前缀表示深圳
        prefix = "1" if exchange == "SH" else "0"
        return f"{prefix}.{code}"
    
    @_retry_on_error(max_retries=3, delay=0.5)
    def get_realtime(self, code: str) -> Optional[Dict]:
        """
        获取实时行情

        Args:
            code: 股票代码 (如 000002)

        Returns:
            行情字典
        """
        # 验证并转换市场代码
        try:
            secid = self._convert_secid(code)
        except ValueError as e:
            logger.warning(f"{e}")
            return None

        url = f"{self.BASE_URL}/api/qt/stock/get"
        params = {
            'secid': secid,
            'fields': 'f43,f44,f45,f46,f47,f48,f49,f50,f51,f52,f57,f58,f59,f60,f169,f170,f171'
        }
        
        try:
            resp = self.session.get(url, params=params, timeout=10)
            resp.raise_for_status()
            data = resp.json()

            if data.get('data'):
                d = data['data']
                return {
                    'code': code,
                    'name': d.get('f58', '').strip(),
                    'price': d.get('f43', 0) / 100,  # 价格除以100
                    'open': d.get('f46', 0) / 100,
                    'high': d.get('f44', 0) / 100,
                    'low': d.get('f45', 0) / 100,
                    'close': d.get('f60', 0) / 100,
                    'volume': d.get('f47', 0),  # 手
                    'amount': d.get('f48', 0),  # 元
                    'change': d.get('f170', 0) / 100,  # 涨跌幅
                    'change_amount': d.get('f169', 0) / 1000,  # 涨跌额 (单位是分，需要除以1000)
                    'turnover': d.get('f50', 0) / 100,  # 换手率
                    'industry': d.get('f171', '')  # 行业
                }
        except requests.RequestException as e:
            logger.error(f"Error fetching realtime for {code}: {e}")
        except (ValueError, KeyError) as e:
            logger.error(f"Error parsing realtime data for {code}: {e}")

        return None
    
    @_retry_on_error(max_retries=3, delay=0.5)
    def get_kline(self, code: str, days: int = 250) -> Optional[pd.DataFrame]:
        """
        获取K线数据

        Args:
            code: 股票代码
            days: 获取天数

        Returns:
            DataFrame
        """
        # 验证并转换市场
        try:
            secid = self._convert_secid(code)
        except ValueError as e:
            logger.warning(f"{e}")
            return None

        url = f"{self.BASE_URL}/api/qt/stock/kline/get"
        params = {
            'secid': secid,
            'fields1': 'f1,f2,f3,f4,f5,f6',
            'fields2': 'f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61',
            'klt': 101,  # 日K
            'fqt': 1,    # 前复权（避免除权除息失真）
            'beg': (datetime.now() - timedelta(days=days)).strftime('%Y%m%d'),
            'end': datetime.now().strftime('%Y%m%d')
        }
        
        try:
            resp = self.session.get(url, params=params, timeout=15)
            resp.raise_for_status()
            data = resp.json()

            if data.get('data') and data['data'].get('klines'):
                klines = data['data']['klines']

                records = []
                invalid_count = 0
                for kline in klines:
                    parts = kline.split(',')
                    if len(parts) >= 6:
                        open_price = float(parts[1])
                        close_price = float(parts[2])
                        high_price = float(parts[3])
                        low_price = float(parts[4])

                        # 数据校验：high >= low 且价格在合理范围内
                        if high_price < low_price:
                            invalid_count += 1
                            continue
                        if high_price < max(open_price, close_price) or low_price > min(open_price, close_price):
                            # 开盘价和收盘价应该在高低价之间
                            invalid_count += 1
                            continue
                        if high_price <= 0 or low_price <= 0:
                            invalid_count += 1
                            continue

                        records.append({
                            'date': parts[0],
                            'open': open_price,
                            'close': close_price,
                            'high': high_price,
                            'low': low_price,
                            'volume': float(parts[5]),
                            'amount': float(parts[6]) if len(parts) > 6 else 0
                        })

                if invalid_count > 0:
                    logger.warning(f"股票 {code} 过滤了 {invalid_count} 条异常K线数据")

                df = pd.DataFrame(records)
                df['date'] = pd.to_datetime(df['date']).dt.strftime('%Y-%m-%d')
                return df

        except requests.RequestException as e:
            logger.error(f"Error fetching kline for {code}: {e}")
        except (ValueError, KeyError, IndexError) as e:
            logger.error(f"Error parsing kline data for {code}: {e}")

        return None
    
    @_retry_on_error(max_retries=3, delay=0.5)
    def search_stock(self, keyword: str) -> List[Dict]:
        """
        搜索股票
        
        Args:
            keyword: 关键词
        
        Returns:
            股票列表
        """
        url = "https://searchapi.eastmoney.com/api/suggest/get"
        params = {
            'input': keyword,
            'type': 14,
            'count': 10
        }
        
        try:
            resp = self.session.get(url, params=params, timeout=10)
            resp.raise_for_status()
            data = resp.json()

            if data.get('QuotationCodeTable'):
                stocks = data['QuotationCodeTable'].get('Data', [])
                return [{
                    'code': s['Code'],
                    'name': s['Name'],
                    'market': s.get('SecurityTypeName', '')
                } for s in stocks]
        except requests.RequestException as e:
            logger.error(f"Error searching stock: {e}")
        except (ValueError, KeyError) as e:
            logger.error(f"Error parsing search data: {e}")

        return []
    
    def get_stock_info(self, code: str) -> Optional[Dict]:
        """获取股票基本信息"""
        # 这里可以扩展获取更多信息
        return self.get_realtime(code)
    
    def get_daily_stats(self, code: str) -> Optional[Dict]:
        """获取每日统计（涨跌停等）"""
        realtime = self.get_realtime(code)
        if not realtime:
            return None
        
        # 判断涨跌停
        prev_close = realtime.get('close', 0) - realtime.get('change_amount', 0)
        
        if prev_close > 0:
            change_pct = (realtime['close'] - prev_close) / prev_close * 100
            
            if change_pct >= 9.9:
                status = '涨停'
            elif change_pct <= -9.9:
                status = '跌停'
            else:
                status = '正常'
        else:
            status = '未知'
        
        return {
            **realtime,
            'status': status,
            'prev_close': prev_close
        }
