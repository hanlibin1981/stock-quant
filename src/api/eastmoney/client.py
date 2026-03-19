"""
东方财富 API 客户端
"""

import requests
import pandas as pd
from typing import Optional, Dict, List
from datetime import datetime, timedelta
import logging

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class EastMoneyClient:
    """东方财富数据客户端"""

    BASE_URL = "https://push2.eastmoney.com"

    def __init__(self):
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': '*/*',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
            'Referer': 'https://www.eastmoney.com/'
        }
        # 使用session复用连接
        self.session = requests.Session()
        self.session.headers.update(self.headers)
    
    def get_realtime(self, code: str) -> Optional[Dict]:
        """
        获取实时行情
        
        Args:
            code: 股票代码 (如 000002)
        
        Returns:
            行情字典
        """
        # 确定市场代码
        if code.startswith('6'):
            secid = f"1.{code}"  # 上海
        elif code.startswith('0') or code.startswith('3'):
            secid = f"0.{code}"  # 深圳
        else:
            secid = f"0.{code}"
        
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
    
    def get_kline(self, code: str, days: int = 250) -> Optional[pd.DataFrame]:
        """
        获取K线数据
        
        Args:
            code: 股票代码
            days: 获取天数
        
        Returns:
            DataFrame
        """
        # 确定市场
        if code.startswith('6'):
            secid = f"1.{code}"
        else:
            secid = f"0.{code}"
        
        url = f"{self.BASE_URL}/api/qt/stock/kline/get"
        params = {
            'secid': secid,
            'fields1': 'f1,f2,f3,f4,f5,f6',
            'fields2': 'f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61',
            'klt': 101,  # 日K
            'fqt': 0,    # 不复权
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
                for kline in klines:
                    parts = kline.split(',')
                    if len(parts) >= 6:
                        records.append({
                            'date': parts[0],
                            'open': float(parts[1]),
                            'close': float(parts[2]),
                            'high': float(parts[3]),
                            'low': float(parts[4]),
                            'volume': float(parts[5]),
                            'amount': float(parts[6]) if len(parts) > 6 else 0
                        })

                df = pd.DataFrame(records)
                df['date'] = pd.to_datetime(df['date']).dt.strftime('%Y-%m-%d')
                return df

        except requests.RequestException as e:
            logger.error(f"Error fetching kline for {code}: {e}")
        except (ValueError, KeyError, IndexError) as e:
            logger.error(f"Error parsing kline data for {code}: {e}")

        return None
    
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
