"""
回测滑点模型模块
支持固定滑点、成交量滑点、分位数滑点
"""

import pandas as pd
import numpy as np
from typing import Dict, Optional
from abc import ABC, abstractmethod
from dataclasses import dataclass
import logging

logger = logging.getLogger(__name__)


class SlippageModel(ABC):
    """
    滑点模型抽象基类
    
    滑点是指实际成交价格与委托价格的差异，
    通常由市场流动性、订单大小等因素导致。
    """

    @abstractmethod
    def calculate(
        self,
        order_price: float,
        order_volume: float,
        market_data: Dict = None
    ) -> float:
        """
        计算滑点后的成交价格
        
        Args:
            order_price: 委托价格
            order_volume: 委托数量
            market_data: 市场数据（包含当前成交量等）
        
        Returns:
            滑点后的实际成交价格
        """
        pass

    def apply_to_dataframe(self, df: pd.DataFrame, side_col: str = 'side') -> pd.DataFrame:
        """
        应用滑点模型到 DataFrame
        
        Args:
            df: 包含交易记录的 DataFrame
            side_col: 交易方向列名 ('buy'/'sell')
        
        Returns:
            添加了 slippage 和 execution_price 列的 DataFrame
        """
        df = df.copy()
        df['slippage'] = 0.0
        df['execution_price'] = df['price']
        
        for idx, row in df.iterrows():
            side = row.get(side_col, 'buy')
            price = row['price']
            volume = row.get('volume', 0)
            
            market_data = {
                'volume': volume,
                'avg_price': price,
                'high': row.get('high', price),
                'low': row.get('low', price),
                'close': row.get('close', price)
            }
            
            # 计算滑点
            slippage_price = self.calculate(price, volume, market_data)
            actual_price = slippage_price
            
            # 根据买卖方向调整
            if side == 'buy':
                # 买入：实际成交价向上滑
                actual_price = max(price, slippage_price)
            else:
                # 卖出：实际成交价向下滑
                actual_price = min(price, slippage_price)
            
            df.at[idx, 'slippage'] = abs(actual_price - price)
            df.at[idx, 'execution_price'] = actual_price
        
        return df


@dataclass
class FixedSlippageConfig:
    """固定滑点配置"""
    slippage_ratio: float = 0.001  # 滑点比例 (0.001 = 0.1%)
    buy_slippage_ratio: float = None  # 买入滑点比例
    sell_slippage_ratio: float = None  # 卖出滑点比例


class FixedSlippage(SlippageModel):
    """
    固定滑点模型
    
    每次交易使用固定的滑点比例计算成交价格。
    适用于流动性较好的大盘股。
    """

    def __init__(self, config: FixedSlippageConfig = None):
        """
        Args:
            config: 固定滑点配置
        """
        self.config = config or FixedSlippageConfig()

    def calculate(
        self,
        order_price: float,
        order_volume: float,
        market_data: Dict = None
    ) -> float:
        """固定滑点计算"""
        slippage_ratio = self.config.slippage_ratio
        return order_price * (1 + slippage_ratio)


@dataclass
class VolumeSlippageConfig:
    """成交量滑点配置"""
    base_slippage: float = 0.0005      # 基础滑点比例
    volume_sensitivity: float = 0.1    # 成交量敏感度
    max_slippage: float = 0.01         # 最大滑点比例
    market_impact_coeff: float = 0.5   # 市场影响系数


class VolumeSlippage(SlippageModel):
    """
    成交量比例滑点模型
    
    滑点与委托量占市场成交量的比例成正相关。
    适用于考虑订单对市场冲击的场景。
    """

    def __init__(self, config: VolumeSlippageConfig = None):
        """
        Args:
            config: 成交量滑点配置
        """
        self.config = config or VolumeSlippageConfig()

    def calculate(
        self,
        order_price: float,
        order_volume: float,
        market_data: Dict = None
    ) -> float:
        """
        成交量滑点计算
        
        滑点比例 = 基础滑点 + 敏感度 * (订单量 / 市场成交量)
        """
        market_volume = 1_000_000  # 默认假设日成交量100万股
        
        if market_data:
            vol = market_data.get('volume', market_volume)
            if vol and vol > 0:
                market_volume = vol
        
        # 计算订单量占市场成交量的比例
        volume_ratio = min(order_volume / market_volume, 1.0)
        
        # 滑点比例
        slippage_ratio = min(
            self.config.base_slippage + 
            self.config.volume_sensitivity * volume_ratio,
            self.config.max_slippage
        )
        
        # 市场影响调整
        if market_data:
            spread = (market_data.get('high', order_price) - 
                    market_data.get('low', order_price)) / order_price
            slippage_ratio += spread * self.config.market_impact_coeff * volume_ratio
        
        return order_price * (1 + slippage_ratio)


@dataclass
class PercentileSlippageConfig:
    """分位数滑点配置"""
    price_history: list = None         # 历史价格列表
    slippage_percentile: float = 95    # 滑点分位数 (1-100)
    lookback_days: int = 20            # 回看天数


class PercentileSlippage(SlippageModel):
    """
    分位数滑点模型
    
    基于历史价格波动率的分位数计算滑点。
    适用于有足够历史数据的股票。
    """

    def __init__(self, config: PercentileSlippageConfig = None):
        """
        Args:
            config: 分位数滑点配置
        """
        self.config = config or PercentileSlippageConfig()
        self._cache = {}

    def calculate(
        self,
        order_price: float,
        order_volume: float,
        market_data: Dict = None
    ) -> float:
        """
        分位数滑点计算
        
        基于历史价格波动率的分位数计算滑点
        """
        history = self.config.price_history or []
        
        if market_data and 'price_history' in market_data:
            history = market_data['price_history']
        
        if len(history) < self.config.lookback_days:
            # 数据不足，返回0滑点
            return order_price
        
        # 计算收益率序列
        returns = []
        price_array = history[-self.config.lookback_days:]
        for i in range(1, len(price_array)):
            ret = (price_array[i] - price_array[i-1]) / price_array[i-1]
            returns.append(abs(ret))
        
        if not returns:
            return order_price
        
        # 按绝对值排序
        sorted_returns = sorted(returns)
        
        # 计算分位数索引
        percentile_idx = int(len(sorted_returns) * (self.config.slippage_percentile / 100))
        percentile_idx = min(percentile_idx, len(sorted_returns) - 1)
        
        # 获取分位数作为滑点
        slippage_ratio = sorted_returns[percentile_idx]
        
        return order_price * (1 + slippage_ratio)


@dataclass
class SpreadSlippageConfig:
    """价差滑点配置"""
    use_half_spread: bool = True  # 使用半价差作为滑点


class SpreadSlippage(SlippageModel):
    """
    价差滑点模型
    
    基于买卖价差计算滑点。
    适用于盘口数据不透明但有价差信息的场景。
    """

    def __init__(self, config: SpreadSlippageConfig = None):
        """
        Args:
            config: 价差滑点配置
        """
        self.config = config or SpreadSlippageConfig()

    def calculate(
        self,
        order_price: float,
        order_volume: float,
        market_data: Dict = None
    ) -> float:
        """
        价差滑点计算
        
        滑点 = 价差的一半（或全部）
        """
        if not market_data:
            # 无市场数据，假设0.05%价差
            return order_price * 1.00025
        
        high = market_data.get('high', order_price)
        low = market_data.get('low', order_price)
        
        # 计算价差
        spread = high - low
        spread_ratio = spread / order_price if order_price > 0 else 0.001
        
        if self.config.use_half_spread:
            slippage_ratio = spread_ratio / 2
        else:
            slippage_ratio = spread_ratio
        
        return order_price * (1 + slippage_ratio)


class SlippageModelFactory:
    """滑点模型工厂"""

    _models = {
        'fixed': FixedSlippage,
        'volume': VolumeSlippage,
        'percentile': PercentileSlippage,
        'spread': SpreadSlippage
    }

    @classmethod
    def create(cls, model_type: str, **kwargs) -> SlippageModel:
        """
        创建滑点模型
        
        Args:
            model_type: 模型类型 ('fixed', 'volume', 'percentile', 'spread')
            **kwargs: 模型配置参数
        
        Returns:
            滑点模型实例
        """
        model_class = cls._models.get(model_type.lower())
        if model_class is None:
            logger.warning(f"Unknown slippage model: {model_type}, using fixed")
            model_class = FixedSlippage
        
        config = kwargs.get('config')
        if config:
            return model_class(config)
        else:
            return model_class()

    @classmethod
    def register(cls, name: str, model_class: type):
        """注册新的滑点模型"""
        cls._models[name.lower()] = model_class


def calculate_slippage(
    order_price: float,
    order_volume: float,
    model_type: str = 'fixed',
    market_data: Dict = None,
    **config_kwargs
) -> Dict:
    """
    便捷函数：计算滑点
    
    Args:
        order_price: 委托价格
        order_volume: 委托数量
        model_type: 滑点模型类型
        market_data: 市场数据
        **config_kwargs: 模型配置参数
    
    Returns:
        {
            'order_price': 委托价格,
            'execution_price': 实际成交价格,
            'slippage': 滑点金额,
            'slippage_ratio': 滑点比例,
            'model': 模型类型
        }
    """
    model = SlippageModelFactory.create(model_type, **config_kwargs)
    execution_price = model.calculate(order_price, order_volume, market_data)
    
    slippage = abs(execution_price - order_price)
    slippage_ratio = slippage / order_price if order_price > 0 else 0
    
    return {
        'order_price': order_price,
        'execution_price': execution_price,
        'slippage': slippage,
        'slippage_ratio': slippage_ratio,
        'model': model_type
    }
