"""
技术指标计算模块
"""

import pandas as pd
import numpy as np
from typing import Dict, List, Union


class IndicatorCalculator:
    """技术指标计算器"""
    
    def __init__(self):
        self.supported_indicators = [
            'ma', 'ema', 'macd', 'rsi', 'kdj', 'boll', 'cci', 'atr', 'obv', 'wr'
        ]
        # 默认计算的指标
        self.default_indicators = ['ma', 'ema', 'macd', 'rsi', 'kdj', 'boll', 'cci', 'wr']
    
    def calculate(self, df: pd.DataFrame, indicators: List[str] = None) -> pd.DataFrame:
        """
        计算技术指标
        
        Args:
            df: 包含 OHLCV 数据的 DataFrame
            indicators: 指标列表，None 则计算默认全部指标
        
        Returns:
            添加了指标列的 DataFrame
        """
        if df is None or df.empty:
            return df
        
        result = df.copy()
        
        if indicators is None:
            indicators = self.default_indicators
        
        for indicator in indicators:
            if indicator.lower() == 'ma':
                result = self._calc_ma(result)
            elif indicator.lower() == 'ema':
                result = self._calc_ema(result)
            elif indicator.lower() == 'macd':
                result = self._calc_macd(result)
            elif indicator.lower() == 'rsi':
                result = self._calc_rsi(result)
            elif indicator.lower() == 'kdj':
                result = self._calc_kdj(result)
            elif indicator.lower() == 'boll':
                result = self._calc_boll(result)
            elif indicator.lower() == 'cci':
                result = self._calc_cci(result)
            elif indicator.lower() == 'atr':
                result = self._calc_atr(result)
            elif indicator.lower() == 'obv':
                result = self._calc_obv(result)
            elif indicator.lower() == 'wr':
                result = self._calc_wr(result)
        
        return result
    
    def _calc_ma(self, df: pd.DataFrame, periods: List[int] = [5, 10, 20, 60]) -> pd.DataFrame:
        """移动平均线"""
        for period in periods:
            df[f'ma{period}'] = df['close'].rolling(window=period).mean()
        return df
    
    def _calc_ema(self, df: pd.DataFrame, periods: List[int] = [12, 26]) -> pd.DataFrame:
        """指数移动平均线"""
        for period in periods:
            df[f'ema{period}'] = df['close'].ewm(span=period, adjust=False).mean()
        return df
    
    def _calc_macd(self, df: pd.DataFrame) -> pd.DataFrame:
        """MACD 指标"""
        # 12日EMA
        ema12 = df['close'].ewm(span=12, adjust=False).mean()
        # 26日EMA
        ema26 = df['close'].ewm(span=26, adjust=False).mean()
        
        # DIF (MACD Line)
        df['macd_dif'] = ema12 - ema26
        # DEA (Signal Line)
        df['macd_dea'] = df['macd_dif'].ewm(span=9, adjust=False).mean()
        # MACD Histogram
        df['macd_hist'] = 2 * (df['macd_dif'] - df['macd_dea'])
        
        return df
    
    def _calc_rsi(self, df: pd.DataFrame, periods: List[int] = [6, 12, 24]) -> pd.DataFrame:
        """RSI 相对强弱指标"""
        for period in periods:
            delta = df['close'].diff()
            gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()

            # 避免除零：当loss为0时（无亏损），RSI=100
            rs = gain / loss.replace(0, np.nan)
            df[f'rsi{period}'] = 100 - (100 / (1 + rs))
            # 处理 inf 和 nan：无亏损时RSI应为100
            df[f'rsi{period}'] = df[f'rsi{period}'].fillna(100)
        
        return df
    
    def _calc_kdj(self, df: pd.DataFrame) -> pd.DataFrame:
        """KDJ 随机指标"""
        low_min = df['low'].rolling(window=9).min()
        high_max = df['high'].rolling(window=9).max()

        # 避免除零
        diff = high_max - low_min
        diff = diff.replace(0, np.nan)

        # K值
        df['kdj_k'] = 100 * (df['close'] - low_min) / diff
        # D值
        df['kdj_d'] = df['kdj_k'].rolling(window=3).mean()
        # J值
        df['kdj_j'] = 3 * df['kdj_k'] - 2 * df['kdj_d']

        # 填充 NaN
        df['kdj_k'] = df['kdj_k'].fillna(50)
        df['kdj_d'] = df['kdj_d'].fillna(50)
        df['kdj_j'] = df['kdj_j'].fillna(50)

        return df
    
    def _calc_boll(self, df: pd.DataFrame, period: int = 20, std_dev: int = 2) -> pd.DataFrame:
        """布林带指标"""
        df['boll_mid'] = df['close'].rolling(window=period).mean()
        df['boll_std'] = df['close'].rolling(window=period).std()
        df['boll_upper'] = df['boll_mid'] + std_dev * df['boll_std']
        df['boll_lower'] = df['boll_mid'] - std_dev * df['boll_std']
        
        return df
    
    def _calc_cci(self, df: pd.DataFrame, period: int = 14) -> pd.DataFrame:
        """CCI 商品通道指标"""
        tp = (df['high'] + df['low'] + df['close']) / 3
        sma = tp.rolling(window=period).mean()
        mad = tp.rolling(window=period).apply(lambda x: np.abs(x - x.mean()).mean())
        
        df['cci'] = (tp - sma) / (0.015 * mad)
        
        return df
    
    def _calc_atr(self, df: pd.DataFrame, period: int = 14) -> pd.DataFrame:
        """ATR 平均真实波幅"""
        high_low = df['high'] - df['low']
        high_close = np.abs(df['high'] - df['close'].shift())
        low_close = np.abs(df['low'] - df['close'].shift())
        
        true_range = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
        df['atr'] = true_range.rolling(window=period).mean()
        
        return df
    
    def _calc_obv(self, df: pd.DataFrame) -> pd.DataFrame:
        """OBV 能量潮"""
        df['obv'] = (np.sign(df['close'].diff()) * df['volume']).fillna(0).cumsum()
        return df
    
    def _calc_wr(self, df: pd.DataFrame, periods: List[int] = [6, 10]) -> pd.DataFrame:
        """威廉指标"""
        for period in periods:
            highest = df['high'].rolling(window=period).max()
            lowest = df['low'].rolling(window=period).min()
            # 避免除零
            diff = highest - lowest
            diff = diff.replace(0, np.nan)
            df[f'wr{period}'] = -100 * (highest - df['close']) / diff
            # 填充 NaN
            df[f'wr{period}'] = df[f'wr{period}'].fillna(-50)

        return df
    
    def get_signals(self, df: pd.DataFrame) -> Dict:
        """
        根据指标生成交易信号
        
        Returns:
            dict: 包含各指标信号
        """
        signals = {}
        
        # MACD 金叉/死叉
        if 'macd_dif' in df.columns and 'macd_dea' in df.columns:
            latest = df.iloc[-1]
            prev = df.iloc[-2] if len(df) > 1 else latest
            
            if latest['macd_dif'] > latest['macd_dea'] and prev['macd_dif'] <= prev['macd_dea']:
                signals['macd'] = 'golden_cross'  # 金叉买入
            elif latest['macd_dif'] < latest['macd_dea'] and prev['macd_dif'] >= prev['macd_dea']:
                signals['macd'] = 'death_cross'  # 死叉卖出
            else:
                signals['macd'] = 'hold'
        
        # RSI 超买超卖
        if 'rsi12' in df.columns:
            rsi = df.iloc[-1]['rsi12']
            if rsi > 80:
                signals['rsi'] = 'overbought'  # 超买
            elif rsi < 20:
                signals['rsi'] = 'oversold'  # 超卖
            else:
                signals['rsi'] = 'neutral'
        
        # 布林带
        if 'boll_upper' in df.columns:
            latest = df.iloc[-1]
            if latest['close'] > latest['boll_upper']:
                signals['boll'] = 'overbought'
            elif latest['close'] < latest['boll_lower']:
                signals['boll'] = 'oversold'
            else:
                signals['boll'] = 'normal'
        
        # KDJ
        if 'kdj_k' in df.columns and 'kdj_d' in df.columns:
            latest = df.iloc[-1]
            prev = df.iloc[-2] if len(df) > 1 else latest
            
            if latest['kdj_k'] > latest['kdj_d'] and prev['kdj_k'] <= prev['kdj_d']:
                signals['kdj'] = 'golden_cross'
            elif latest['kdj_k'] < latest['kdj_d'] and prev['kdj_k'] >= prev['kdj_d']:
                signals['kdj'] = 'death_cross'
            else:
                signals['kdj'] = 'hold'
        
        return signals
