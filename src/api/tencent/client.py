"""
腾讯财经 API 客户端
用于获取实时股票行情
"""

import re
import requests
import pandas as pd
from typing import Optional, Dict
from datetime import datetime, timedelta
import logging

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class TencentFinanceClient:
    """腾讯财经数据客户端"""

    BASE_URL = "https://qt.gtimg.cn/q="

    def __init__(self):
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        }
        # 使用session复用连接
        self.session = requests.Session()
        self.session.headers.update(self.headers)
    
    def get_realtime(self, code: str) -> Optional[Dict]:
        """
        获取实时行情
        
        Args:
            code: 股票代码 (如 000001, 600519)
        
        Returns:
            行情字典
        """
        # 转换代码格式
        if code.startswith('6'):
            market = 'sh'
        else:
            market = 'sz'
        
        url = f"{self.BASE_URL}{market}{code}"
        
        try:
            resp = self.session.get(url, timeout=10)
            resp.raise_for_status()
            text = resp.text

            # 解析返回数据
            # 格式: v_sh000001="0~平安银行~000001~10.91~10.90~..."
            match = re.search(r'="([^"]+)"', text)
            if not match:
                return None

            parts = match.group(1).split('~')
            if len(parts) < 50:
                return None

            return {
                'code': code,
                'name': parts[1] if parts[1] else '',
                'price': float(parts[3]) if parts[3] else 0,   # 当前价
                'open': float(parts[5]) if parts[5] else 0,    # 开盘
                'high': float(parts[33]) if parts[33] else 0,  # 最高
                'low': float(parts[34]) if parts[34] else 0,    # 最低
                'close': float(parts[4]) if parts[4] else 0,    # 昨收
                'volume': float(parts[6]) if parts[6] else 0,  # 成交量(手)
                'amount': float(parts[7]) if parts[7] else 0,  # 成交额(元)
                'change': float(parts[31]) if parts[31] else 0,   # 涨跌幅
                'change_amount': float(parts[32]) if parts[32] else 0,  # 涨跌额
                'turnover': float(parts[38]) if parts[38] else 0,  # 换手率
                'source': 'tencent'
            }

        except requests.RequestException as e:
            logger.error(f"Error fetching realtime for {code}: {e}")
        except (ValueError, IndexError) as e:
            logger.error(f"Error parsing realtime data for {code}: {e}")

        return None
    
    def get_realtime_batch(self, codes: list) -> Dict[str, Dict]:
        """
        批量获取实时行情
        
        Args:
            codes: 股票代码列表
        
        Returns:
            字典，key为股票代码
        """
        # 构建批量请求URL
        market_codes = []
        for code in codes:
            if code.startswith('6'):
                market_codes.append(f'sh{code}')
            else:
                market_codes.append(f'sz{code}')
        
        url = self.BASE_URL + '_'.join(market_codes)
        
        try:
            resp = self.session.get(url, timeout=15)
            resp.raise_for_status()
            text = resp.text

            results = {}

            # 解析每个股票的数据
            for code in codes:
                pattern = f's{"sh" if code.startswith("6") else "sz"}{code}="([^"]+)"'
                match = re.search(pattern, text)

                if match:
                    parts = match.group(1).split('~')
                    if len(parts) >= 50:
                        results[code] = {
                            'code': code,
                            'name': parts[1] if parts[1] else '',
                            'price': float(parts[3]) if parts[3] else 0,
                            'open': float(parts[5]) if parts[5] else 0,
                            'high': float(parts[33]) if parts[33] else 0,
                            'low': float(parts[34]) if parts[34] else 0,
                            'close': float(parts[4]) if parts[4] else 0,
                            'volume': float(parts[6]) if parts[6] else 0,
                            'amount': float(parts[7]) if parts[7] else 0,
                            'change': float(parts[31]) if parts[31] else 0,
                            'change_amount': float(parts[32]) if parts[32] else 0,
                            'turnover': float(parts[38]) if parts[38] else 0,
                        }

            return results

        except requests.RequestException as e:
            logger.error(f"Error fetching batch realtime: {e}")
        except (ValueError, IndexError) as e:
            logger.error(f"Error parsing batch realtime data: {e}")

        return {}
    
    def get_kline(self, code: str, days: int = 60) -> Optional[pd.DataFrame]:
        """
        获取K线数据 (日K)
        
        Args:
            code: 股票代码
            days: 获取天数
        
        Returns:
            DataFrame
        """
        import json
        
        # 转换代码格式
        if code.startswith('6'):
            market = 'sh'
        else:
            market = 'sz'
        
        # 腾讯财经K线API
        url = f"https://web.ifzq.gtimg.cn/appstock/app/fqkline/get"
        params = {
            '_var': 'kline_dayqfq',
            'param': f'{market}{code},day,,,{days},qfq'
        }
        
        try:
            resp = self.session.get(url, params=params, timeout=15)
            resp.raise_for_status()
            text = resp.text

            # 解析返回数据
            # 格式: kline_dayqfq={"data":{"sh600519":{"day":[["2024-01-01",...],...]}}}
            match = re.search(r'kline_dayqfq=(.+)', text)
            if not match:
                return None

            data = json.loads(match.group(1))

            if 'data' not in data:
                return None

            stock_data = data['data'].get(f'{market}{code}') or data['data'].get(code)
            if not stock_data:
                return None

            # 优先使用qfqday（前复权数据），如果没有则使用day
            klines = stock_data.get('qfqday') or stock_data.get('day')
            if not klines:
                return None

            records = []
            for kline in klines:
                if len(kline) >= 6:
                    records.append({
                        'date': kline[0],
                        'open': float(kline[1]),
                        'close': float(kline[2]),
                        'high': float(kline[3]),
                        'low': float(kline[4]),
                        'volume': float(kline[5]),
                        'amount': float(kline[6]) if len(kline) > 6 else 0
                    })

            df = pd.DataFrame(records)
            df['date'] = pd.to_datetime(df['date']).dt.strftime('%Y-%m-%d')
            return df

        except requests.RequestException as e:
            logger.error(f"Error fetching kline for {code}: {e}")
        except (ValueError, KeyError, IndexError, json.JSONDecodeError) as e:
            logger.error(f"Error parsing kline data for {code}: {e}")

        return None


# 全局实例
_tencent_client = None

def get_tencent_client() -> TencentFinanceClient:
    """获取腾讯财经客户端实例"""
    global _tencent_client
    if _tencent_client is None:
        _tencent_client = TencentFinanceClient()
    return _tencent_client
