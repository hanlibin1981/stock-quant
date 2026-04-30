"""
技术指标计算模块 - 优化版
添加指标缓存，避免重复计算
"""

import pandas as pd
import numpy as np
from typing import Dict, List, Union, Optional, Set
from functools import lru_cache
import hashlib
import pickle


class IndicatorCalculator:
    """技术指标计算器（带缓存）"""

    def __init__(self, cache_size: int = 100):
        self.supported_indicators = [
            'ma', 'ema', 'macd', 'rsi', 'kdj', 'boll', 'cci', 'atr', 'obv', 'wr',
            # 新增指标
            'skdj', 'dmi', 'vr', 'mi', 'pvi', 'nvi', 'trix', 'dma', 'expma', 'bias',
            'psy', 'vr', 'mfi', 'tema'
        ]
        self.default_indicators = ['ma', 'ema', 'macd', 'rsi', 'kdj', 'boll', 'cci', 'wr']
        self._cache: Dict[str, pd.DataFrame] = {}
        self._cache_size = cache_size

    def _make_cache_key(self, df: pd.DataFrame, indicators: Tuple[str, ...]) -> str:
        """生成缓存键"""
        # 使用数据的指纹（只取最后100行和列名）
        n_rows = min(len(df), 100)
        content = f"{df.iloc[-n_rows:].to_csv()},{sorted(indicators)}"
        return hashlib.md5(content.encode()).hexdigest()

    def _get_from_cache(self, df: pd.DataFrame, indicators: Tuple[str, ...]) -> Optional[pd.DataFrame]:
        """尝试从缓存获取"""
        if len(df) < 30:
            return None
        key = self._make_cache_key(df, indicators)
        return self._cache.get(key)

    def _save_to_cache(self, df: pd.DataFrame, indicators: Tuple[str, ...], result: pd.DataFrame):
        """保存到缓存"""
        if len(df) < 30:
            return
        key = self._make_cache_key(df, indicators)
        # LRU 清理
        if len(self._cache) >= self._cache_size:
            # 删除最早的条目
            first_key = next(iter(self._cache))
            del self._cache[first_key]
        self._cache[key] = result.copy()

    def clear_cache(self):
        """清空缓存"""
        self._cache.clear()

    def calculate(self, df: pd.DataFrame, indicators: List[str] = None, copy: bool = False) -> pd.DataFrame:
        """
        计算技术指标（带缓存优化）

        Args:
            df: 包含 OHLCV 数据的 DataFrame
            indicators: 指标列表，None 则计算默认全部指标
            copy: 是否复制DataFrame，默认为False以提高性能

        Returns:
            添加了指标列的 DataFrame
        """
        if df is None or df.empty:
            return df

        if indicators is None:
            indicators = self.default_indicators

        # 转换为不可变类型用于缓存键
        indicators_tuple = tuple(sorted(set(ind.lower() for ind in indicators)))

        # 尝试从缓存获取
        cached = self._get_from_cache(df, indicators_tuple)
        if cached is not None:
            if copy:
                return cached.copy()
            # 直接修改缓存会导致数据污染，所以这里总是返回副本或原始df
            result = df.copy() if not copy else df
            for col in cached.columns:
                if col not in result.columns:
                    result[col] = cached[col]
            return result

        # 避免不必要的复制，默认直接修改原DataFrame
        result = df.copy() if copy else df

        for indicator in indicators_tuple:
            if indicator == 'ma':
                result = self._calc_ma(result)
            elif indicator == 'ema':
                result = self._calc_ema(result)
            elif indicator == 'macd':
                result = self._calc_macd(result)
            elif indicator == 'rsi':
                result = self._calc_rsi(result)
            elif indicator == 'kdj':
                result = self._calc_kdj(result)
            elif indicator == 'boll':
                result = self._calc_boll(result)
            elif indicator == 'cci':
                result = self._calc_cci(result)
            elif indicator == 'atr':
                result = self._calc_atr(result)
            elif indicator == 'obv':
                result = self._calc_obv(result)
            elif indicator == 'wr':
                result = self._calc_wr(result)
            elif indicator == 'skdj':
                result = self._calc_skdj(result)
            elif indicator == 'dmi':
                result = self._calc_dmi(result)
            elif indicator == 'vr':
                result = self._calc_vr(result)
            elif indicator == 'mi':
                result = self._calc_mi(result)
            elif indicator == 'pvi':
                result = self._calc_pvi(result)
            elif indicator == 'nvi':
                result = self._calc_nvi(result)
            elif indicator == 'trix':
                result = self._calc_trix(result)
            elif indicator == 'dma':
                result = self._calc_dma(result)
            elif indicator == 'expma':
                result = self._calc_expma(result)
            elif indicator == 'bias':
                result = self._calc_bias(result)
            elif indicator == 'psy':
                result = self._calc_psy(result)
            elif indicator == 'mfi':
                result = self._calc_mfi(result)
            elif indicator == 'tema':
                result = self._calc_tema(result)

        # 保存到缓存
        self._save_to_cache(df, indicators_tuple, result)

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
        ema12 = df['close'].ewm(span=12, adjust=False).mean()
        ema26 = df['close'].ewm(span=26, adjust=False).mean()
        df['macd_dif'] = ema12 - ema26
        df['macd_dea'] = df['macd_dif'].ewm(span=9, adjust=False).mean()
        df['macd_hist'] = 2 * (df['macd_dif'] - df['macd_dea'])
        return df

    def _calc_rsi(self, df: pd.DataFrame, periods: List[int] = [6, 12, 24]) -> pd.DataFrame:
        """RSI 相对强弱指标"""
        for period in periods:
            delta = df['close'].diff()
            gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
            rs = np.where((gain == 0) & (loss == 0), np.nan,
                     np.where(loss == 0, np.inf, gain / loss))
            df[f'rsi{period}'] = np.where(
                np.isnan(rs), 50,
                np.where(np.isinf(rs), 100, 100 - (100 / (1 + rs)))
            )
        return df

    def _calc_kdj(self, df: pd.DataFrame) -> pd.DataFrame:
        """KDJ 随机指标"""
        low_min = df['low'].rolling(window=9).min()
        high_max = df['high'].rolling(window=9).max()
        diff = high_max - low_min
        diff = diff.replace(0, np.nan)
        df['kdj_k'] = 100 * (df['close'] - low_min) / diff
        df['kdj_d'] = df['kdj_k'].rolling(window=3).mean()
        df['kdj_j'] = 3 * df['kdj_k'] - 2 * df['kdj_d']
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
            diff = highest - lowest
            diff = diff.replace(0, np.nan)
            df[f'wr{period}'] = -100 * (highest - df['close']) / diff
        return df

    def _calc_skdj(self, df: pd.DataFrame, period: int = 9) -> pd.DataFrame:
        """SKDJ 慢速随机指标"""
        low_min = df['low'].rolling(window=period).min()
        high_max = df['high'].rolling(window=period).max()
        diff = high_max - low_min
        diff = diff.replace(0, np.nan)
        # RSV
        rsv = 100 * (df['close'] - low_min) / diff
        # K值平滑
        df['skdj_k'] = rsv.ewm(span=3, adjust=False).mean()
        # D值平滑
        df['skdj_d'] = df['skdj_k'].ewm(span=3, adjust=False).mean()
        df['skdj_k'] = df['skdj_k'].fillna(50)
        df['skdj_d'] = df['skdj_d'].fillna(50)
        return df

    def _calc_dmi(self, df: pd.DataFrame, period: int = 14) -> pd.DataFrame:
        """DMI 趋向指标"""
        # +DI 和 -DI
        high_diff = df['high'].diff()
        low_diff = -df['low'].diff()
        plus_dm = high_diff.where((high_diff > low_diff) & (high_diff > 0), 0)
        minus_dm = low_diff.where((low_diff > high_diff) & (low_diff > 0), 0)
        tr = self._calc_tr(df)
        plus_di = 100 * (plus_dm.rolling(window=period).mean() / tr)
        minus_di = 100 * (minus_dm.rolling(window=period).mean() / tr)
        dx = 100 * np.abs(plus_di - minus_di) / (plus_di + minus_di)
        df['dmi_plus'] = plus_di
        df['dmi_minus'] = minus_di
        df['dmi_adx'] = dx.rolling(window=period).mean()
        return df

    def _calc_tr(self, df: pd.DataFrame) -> pd.Series:
        """True Range"""
        high_low = df['high'] - df['low']
        high_close = np.abs(df['high'] - df['close'].shift())
        low_close = np.abs(df['low'] - df['close'].shift())
        return pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)

    def _calc_vr(self, df: pd.DataFrame, period: int = 26) -> pd.DataFrame:
        """VR 成交量变异率"""
        df_temp = df.copy()
        df_temp['gain'] = np.where(df_temp['close'].diff() > 0, df_temp['volume'], 0)
        df_temp['loss'] = np.where(df_temp['close'].diff() < 0, df_temp['volume'], 0)
        gain_sum = df_temp['gain'].rolling(window=period).sum()
        loss_sum = df_temp['loss'].rolling(window=period).sum()
        vr = 100 * (gain_sum + 0.5 * df_temp['volume'].rolling(window=period).sum()) / \
             (loss_sum + 0.5 * df_temp['volume'].rolling(window=period).sum())
        df['vr'] = vr
        return df

    def _calc_mi(self, df: pd.DataFrame, period: int = 26) -> pd.DataFrame:
        """MI 质量指标"""
        typical_price = (df['high'] + df['low'] + df['close']) / 3
        # 分子：典型价的变化量累加
        tp_diff = typical_price.diff().abs()
        # 分母：典型价的累加
        tp_sum = typical_price.rolling(window=period).sum()
        df['mi'] = 100 * tp_diff.rolling(window=period).sum() / tp_sum
        return df

    def _calc_pvi(self, df: pd.DataFrame, period: int = 255) -> pd.DataFrame:
        """PVI 正量指标"""
        df['pvi'] = 1000
        for i in range(1, len(df)):
            if df['volume'].iloc[i] > df['volume'].iloc[i-1]:
                df['pvi'].iloc[i] = df['pvi'].iloc[i-1] + (df['close'].iloc[i] - df['close'].iloc[i-1]) / df['close'].iloc[i-1] * df['pvi'].iloc[i-1]
            else:
                df['pvi'].iloc[i] = df['pvi'].iloc[i-1]
        return df

    def _calc_nvi(self, df: pd.DataFrame, period: int = 255) -> pd.DataFrame:
        """NVI 负量指标"""
        df['nvi'] = 1000
        for i in range(1, len(df)):
            if df['volume'].iloc[i] < df['volume'].iloc[i-1]:
                df['nvi'].iloc[i] = df['nvi'].iloc[i-1] + (df['close'].iloc[i] - df['close'].iloc[i-1]) / df['close'].iloc[i-1] * df['nvi'].iloc[i-1]
            else:
                df['nvi'].iloc[i] = df['nvi'].iloc[i-1]
        return df

    def _calc_trix(self, df: pd.DataFrame, period: int = 12) -> pd.DataFrame:
        """TRIX 三重指数平滑平均线"""
        ema1 = df['close'].ewm(span=period, adjust=False).mean()
        ema2 = ema1.ewm(span=period, adjust=False).mean()
        ema3 = ema2.ewm(span=period, adjust=False).mean()
        df['trix'] = ema3.pct_change() * 100
        df['trix_signal'] = df['trix'].ewm(span=9, adjust=False).mean()
        return df

    def _calc_dma(self, df: pd.DataFrame) -> pd.DataFrame:
        """DMA 差分平均线"""
        df['dma10'] = df['close'].rolling(window=10).mean()
        df['dma50'] = df['close'].rolling(window=50).mean()
        df['dma_diff'] = df['dma10'] - df['dma50']
        return df

    def _calc_expma(self, df: pd.DataFrame) -> pd.DataFrame:
        """EXPMA 指数加权移动平均"""
        df['expma12'] = df['close'].ewm(span=12, adjust=False).mean()
        df['expma50'] = df['close'].ewm(span=50, adjust=False).mean()
        return df

    def _calc_bias(self, df: pd.DataFrame, periods: List[int] = [6, 12, 24]) -> pd.DataFrame:
        """BIAS 乖离率"""
        for period in periods:
            ma = df['close'].rolling(window=period).mean()
            df[f'bias{period}'] = 100 * (df['close'] - ma) / ma
        return df

    def _calc_psy(self, df: pd.DataFrame, period: int = 12) -> pd.DataFrame:
        """PSY 心理线"""
        df['psy'] = 100 * (df['close'].diff() > 0).rolling(window=period).sum() / period
        return df

    def _calc_mfi(self, df: pd.DataFrame, period: int = 14) -> pd.DataFrame:
        """MFI 资金流量指标"""
        tp = (df['high'] + df['low'] + df['close']) / 3
        mf = tp * df['volume']
        mf_diff = mf.diff()
        pos_mf = mf_diff.where(mf_diff > 0, 0).rolling(window=period).sum()
        neg_mf = mf_diff.where(mf_diff < 0, 0).rolling(window=period).sum()
        mr = pos_mf / neg_mf
        df['mfi'] = 100 - (100 / (1 + mr))
        return df

    def _calc_tema(self, df: pd.DataFrame, period: int = 20) -> pd.DataFrame:
        """TEMA 三重指数移动平均"""
        ema1 = df['close'].ewm(span=period, adjust=False).mean()
        ema2 = ema1.ewm(span=period, adjust=False).mean()
        ema3 = ema2.ewm(span=period, adjust=False).mean()
        df['tema'] = 3 * ema1 - 3 * ema2 + ema3
        return df

    def get_signals(self, df: pd.DataFrame) -> Dict:
        """
        根据指标生成交易信号
        """
        signals = {}
        latest = df.iloc[-1] if len(df) > 0 else None
        prev = df.iloc[-2] if len(df) > 1 else latest

        if latest is None:
            return signals

        # MACD
        if 'macd_dif' in df.columns and 'macd_dea' in df.columns:
            if latest['macd_dif'] > latest['macd_dea'] and prev['macd_dif'] <= prev['macd_dea']:
                signals['macd'] = 'golden_cross'
            elif latest['macd_dif'] < latest['macd_dea'] and prev['macd_dif'] >= prev['macd_dea']:
                signals['macd'] = 'death_cross'
            else:
                signals['macd'] = 'hold'

        # RSI
        if 'rsi12' in df.columns:
            rsi = latest['rsi12']
            if rsi > 80:
                signals['rsi'] = 'overbought'
            elif rsi < 20:
                signals['rsi'] = 'oversold'
            else:
                signals['rsi'] = 'neutral'

        # KDJ
        if 'kdj_k' in df.columns and 'kdj_d' in df.columns:
            if latest['kdj_k'] > latest['kdj_d'] and prev['kdj_k'] <= prev['kdj_d']:
                signals['kdj'] = 'golden_cross'
            elif latest['kdj_k'] < latest['kdj_d'] and prev['kdj_k'] >= prev['kdj_d']:
                signals['kdj'] = 'death_cross'
            else:
                signals['kdj'] = 'hold'

        return signals
