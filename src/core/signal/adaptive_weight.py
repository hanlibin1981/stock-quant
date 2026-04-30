"""
自适应信号权重模块
根据市场状态动态调整各指标权重
"""

import pandas as pd
import numpy as np
from typing import Dict, List, Tuple
from dataclasses import dataclass
from enum import Enum


class MarketRegime(Enum):
    """市场状态"""
    TREND_UP = "trend_up"      # 上涨趋势
    TREND_DOWN = "trend_down"  # 下跌趋势
    VOLATILE = "volatile"      # 高波动震荡
    CONSOLIDATION = "consolidation"  # 低波动整理


@dataclass
class MarketState:
    """市场状态分析结果"""
    regime: MarketRegime
    volatility: float  # 波动率（ATR/价格比率）
    trend_strength: float  # 趋势强度 (0-1)
    volume_ratio: float  # 量比（当日成交量/平均成交量）
    description: str


class AdaptiveWeightEngine:
    """
    自适应权重引擎
    
    根据市场状态动态调整各指标权重：
    - 趋势市场：均线、MACD、DMI权重增加
    - 震荡市场：RSI、KDJ、WR权重增加
    - 高波动：布林带、ATR权重增加
    - 低波动：动量指标权重降低
    """

    # 基础权重配置
    BASE_WEIGHTS = {
        'macd': 0.20,
        'rsi': 0.15,
        'kdj': 0.15,
        'boll': 0.10,
        'ma': 0.15,
        'cci': 0.08,
        'wr': 0.07,
        'volume': 0.10,
    }

    # 各市场状态下的权重调整
    REGIME_ADJUSTMENTS = {
        MarketRegime.TREND_UP: {
            'macd': 0.05,   # 趋势上涨时MACD更可靠
            'ma': 0.10,     # 均线信号更强
            'kdj': -0.05,  # 随机指标在趋势市场中可靠性下降
            'rsi': -0.05,  # RSI在趋势市场中可靠性下降
            'wr': -0.05,   # WR在趋势市场中可靠性下降
        },
        MarketRegime.TREND_DOWN: {
            'macd': 0.05,   # 趋势下跌时MACD更可靠
            'ma': 0.05,     # 均线信号更强
            'kdj': -0.05,
            'rsi': -0.05,
            'wr': 0.05,     # WR超卖信号更可靠
            'boll': 0.05,   # 布林带反弹信号更可靠
        },
        MarketRegime.VOLATILE: {
            'boll': 0.10,   # 高波动时布林带更可靠
            'atr': 0.10,    # ATR波动指标
            'kdj': 0.05,    # KDJ在震荡市中较好
            'macd': -0.05,
            'ma': -0.05,
            'rsi': -0.05,
        },
        MarketRegime.CONSOLIDATION: {
            'rsi': 0.10,    # 震荡整理时RSI超买超卖更可靠
            'kdj': 0.05,
            'wr': 0.05,
            'macd': -0.05,
            'ma': -0.05,
        },
    }

    def __init__(self):
        self.last_regime = MarketRegime.CONSOLIDATION

    def analyze_market_state(self, df: pd.DataFrame) -> MarketState:
        """
        分析当前市场状态
        
        Args:
            df: OHLCV数据
        
        Returns:
            MarketState 市场状态分析结果
        """
        if len(df) < 30:
            return MarketState(
                regime=MarketRegime.CONSOLIDATION,
                volatility=0.0,
                trend_strength=0.0,
                volume_ratio=1.0,
                description="数据不足"
            )

        latest = df.iloc[-1]
        
        # 1. 计算波动率（ATR/收盘价）
        atr = self._calc_atr(df)
        volatility = atr / latest['close'] if latest['close'] > 0 else 0.0
        
        # 2. 计算趋势强度（均线多头/空头排列）
        trend_strength = self._calc_trend_strength(df)
        
        # 3. 计算量比
        volume_ratio = self._calc_volume_ratio(df)
        
        # 4. 判断市场状态
        regime = self._determine_regime(volatility, trend_strength)
        self.last_regime = regime
        
        descriptions = {
            MarketRegime.TREND_UP: f"上涨趋势 (强度{trend_strength:.2f})",
            MarketRegime.TREND_DOWN: f"下跌趋势 (强度{trend_strength:.2f})",
            MarketRegime.VOLATILE: f"高波动震荡 (波动率{volatility:.4f})",
            MarketRegime.CONSOLIDATION: f"低波动整理 (波动率{volatility:.4f})",
        }
        
        return MarketState(
            regime=regime,
            volatility=volatility,
            trend_strength=trend_strength,
            volume_ratio=volume_ratio,
            description=descriptions.get(regime, "未知")
        )

    def _calc_atr(self, df: pd.DataFrame, period: int = 14) -> float:
        """计算ATR"""
        high_low = df['high'] - df['low']
        high_close = np.abs(df['high'] - df['close'].shift())
        low_close = np.abs(df['low'] - df['close'].shift())
        tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
        return tr.iloc[-period:].mean() if len(tr) >= period else tr.mean()

    def _calc_trend_strength(self, df: pd.DataFrame) -> float:
        """计算趋势强度"""
        if len(df) < 60:
            return 0.0
        
        # 计算各均线
        ma5 = df['close'].rolling(5).mean()
        ma20 = df['close'].rolling(20).mean()
        ma60 = df['close'].rolling(60).mean()
        
        latest = df.iloc[-1]
        
        # 多头排列得分
        score = 0.0
        if latest['close'] > ma5.iloc[-1]:
            score += 0.3
        if ma5.iloc[-1] > ma20.iloc[-1]:
            score += 0.3
        if ma20.iloc[-1] > ma60.iloc[-1]:
            score += 0.4
        
        return score

    def _calc_volume_ratio(self, df: pd.DataFrame) -> float:
        """计算量比"""
        if len(df) < 20:
            return 1.0
        
        avg_volume = df['volume'].iloc[-20:-1].mean()
        today_volume = df['volume'].iloc[-1]
        
        return today_volume / avg_volume if avg_volume > 0 else 1.0

    def _determine_regime(self, volatility: float, trend_strength: float) -> MarketRegime:
        """判断市场状态"""
        # 高波动
        if volatility > 0.03:
            return MarketRegime.VOLATILE
        
        # 低波动
        if volatility < 0.01:
            return MarketRegime.CONSOLIDATION
        
        # 趋势判断
        if trend_strength > 0.6:
            return MarketRegime.TREND_UP
        elif trend_strength < 0.3:
            return MarketRegime.TREND_DOWN
        
        return MarketRegime.CONSOLIDATION

    def get_adaptive_weights(self, market_state: MarketState = None) -> Dict[str, float]:
        """
        获取自适应权重
        
        Args:
            market_state: 市场状态，None则使用最近一次状态
        
        Returns:
            各指标的自适应权重字典
        """
        if market_state is None:
            regime = self.last_regime
        else:
            regime = market_state.regime
        
        # 从基础权重开始
        weights = self.BASE_WEIGHTS.copy()
        
        # 应用状态调整
        adjustments = self.REGIME_ADJUSTMENTS.get(regime, {})
        for indicator, adjustment in adjustments.items():
            if indicator in weights:
                weights[indicator] = max(0.01, weights[indicator] + adjustment)
        
        # 归一化权重（确保总和为1）
        total = sum(weights.values())
        if total > 0:
            weights = {k: v / total for k, v in weights.items()}
        
        return weights

    def get_weights_with_volume(self, df: pd.DataFrame) -> Dict[str, float]:
        """
        获取考虑成交量的自适应权重
        
        Args:
            df: OHLCV数据
        
        Returns:
            各指标的自适应权重（考虑量能验证）
        """
        market_state = self.analyze_market_state(df)
        weights = self.get_adaptive_weights(market_state)
        
        # 量能验证权重调整
        vr = market_state.volume_ratio
        if vr > 1.5:
            # 高成交量，趋势信号更可靠
            weights['volume'] = 0.05  # 降低成交量指标权重，因为高成交量本身确认了趋势
        elif vr < 0.7:
            # 低成交量，可能假突破
            weights['volume'] = 0.15  # 增加成交量指标权重，需要多重确认
            weights['macd'] *= 0.8  # 降低MACD权重，低成交量时MACD可能失真
            weights['kdj'] *= 0.8
        
        # 重新归一化
        total = sum(weights.values())
        if total > 0:
            weights = {k: v / total for k, v in weights.items()}
        
        return weights


# 全局实例
_adaptive_engine = None

def get_adaptive_weight_engine() -> AdaptiveWeightEngine:
    """获取自适应权重引擎单例"""
    global _adaptive_engine
    if _adaptive_engine is None:
        _adaptive_engine = AdaptiveWeightEngine()
    return _adaptive_engine
