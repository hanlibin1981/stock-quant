"""
模拟/演示数据生成器
当真实API不可用时，提供模拟数据用于演示
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta


class MockDataGenerator:
    """生成模拟股票数据"""

    # 全局随机种子状态，允许外部重置以实现不同场景模拟
    _global_seed = None

    @classmethod
    def reset_seed(cls, seed: int = None):
        """重置随机种子，None 则使用代码+时间哈希（每次不同）"""
        cls._global_seed = seed if seed is not None else hash(str(datetime.now())) % 100000

    @staticmethod
    def generate_kline(code: str = '000002', days: int = 60, base_price: float = 10.0) -> pd.DataFrame:
        """生成模拟K线数据"""
        # 使用 code 的哈希作为基础种子，允许不同股票有不同走势
        seed = hash(code) % 10000
        np.random.seed(seed)

        dates = pd.date_range(end=datetime.now(), periods=days, freq='D')

        # 模拟价格走势
        returns = np.random.normal(0.001, 0.02, days)
        prices = base_price * np.exp(np.cumsum(returns))

        # 生成OHLC数据
        data = []
        for i, (date, close) in enumerate(zip(dates, prices)):
            open_price = close * (1 + np.random.uniform(-0.01, 0.01))
            high_price = max(open_price, close) * (1 + np.random.uniform(0, 0.02))
            low_price = min(open_price, close) * (1 - np.random.uniform(0, 0.02))
            volume = int(np.random.uniform(1000000, 10000000))

            data.append({
                'date': date,
                'open': round(open_price, 2),
                'close': round(close, 2),
                'high': round(high_price, 2),
                'low': round(low_price, 2),
                'volume': volume,
                'amount': volume * close
            })

        df = pd.DataFrame(data)
        # 确保日期格式正确
        df['date'] = pd.to_datetime(df['date']).dt.strftime('%Y-%m-%d')
        return df
    
    @staticmethod
    def generate_realtime(code: str = '000002', name: str = '万科A') -> dict:
        """生成模拟实时行情"""
        np.random.seed(hash(code) % 10000)
        
        base_price = 4.70
        change = np.random.uniform(-2, 2)
        
        return {
            'code': code,
            'name': name,
            'price': round(base_price * (1 + change/100), 2),
            'open': round(base_price * (1 + np.random.uniform(-1, 1)/100), 2),
            'high': round(base_price * (1 + np.random.uniform(0, 3)/100), 2),
            'low': round(base_price * (1 - np.random.uniform(0, 3)/100), 2),
            'volume': int(np.random.uniform(1000000, 5000000)),
            'amount': np.random.uniform(500000000, 2000000000),
            'change': round(change, 2),
            'change_amount': round(base_price * change / 100, 2),
            'turnover': round(np.random.uniform(0.5, 5), 2),
        }
    
    @staticmethod
    def generate_stock_info(code: str = '000002') -> dict:
        """生成模拟股票信息"""
        stocks = {
            '000002': {'name': '万科A', 'industry': '房地产', 'market': '深市主板'},
            '000001': {'name': '平安银行', 'industry': '银行', 'market': '深市主板'},
            '600519': {'name': '贵州茅台', 'industry': '酿酒', 'market': '沪市主板'},
            '600036': {'name': '招商银行', 'industry': '银行', 'market': '沪市主板'},
            '000858': {'name': '五粮液', 'industry': '酿酒', 'market': '深市主板'},
        }
        
        info = stocks.get(code, {'name': f'股票{code}', 'industry': '未知', 'market': 'A股'})
        
        return {
            'code': code,
            'name': info['name'],
            'industry': info['industry'],
            'market': info['market'],
            'list_date': '20100101'
        }
