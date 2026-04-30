"""
背离检测模块
检测价格与技术指标之间的背离信号
"""

import pandas as pd
import numpy as np
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from enum import Enum


class DivergenceType(Enum):
    """背离类型"""
    BULLISH_DIVERGENCE = " bullish_divergence"  # 底背离 - 价格上涨信号
    BEARISH_DIVERGENCE = "bearish_divergence"  # 顶背离 - 价格下跌信号
    HIDDEN_BULLISH = "hidden_bullish"  # 隐藏底背离
    HIDDEN_BEARISH = "hidden_bearish"  # 隐藏顶背离
    NONE = "none"


@dataclass
class DivergenceSignal:
    """背离信号"""
    indicator: str
    divergence_type: DivergenceType
    strength: float  # 0-1
    price_change: float  # 价格变化百分比
    indicator_change: float  # 指标变化
    price_peaks: Tuple[float, float]  # (前一个峰值, 当前峰值)
    indicator_peaks: Tuple[float, float]  # (前一个指标值, 当前指标值)
    description: str


class DivergenceDetector:
    """
    背离检测器
    
    检测规则：
    - 顶背离：价格创新高，但指标没有创新高 → 看跌信号
    - 底背离：价格创新低，但指标没有创新低 → 看涨信号
    - 隐藏顶背离：价格较低点高于前一个低点，但指标较低点低于前一个低点 → 看跌
    - 隐藏底背离：价格较高点低于前一个高点，但指标较高点高于前一个高点 → 看涨
    """

    def __init__(self, lookback: int = 20, min_swing: float = 0.02):
        """
        Args:
            lookback: 回溯周期数，用于找峰值
            min_swing: 最小波动阈值（过滤噪音）
        """
        self.lookback = lookback
        self.min_swing = min_swing

    def detect(self, df: pd.DataFrame, indicator: str) -> List[DivergenceSignal]:
        """
        检测背离
        
        Args:
            df: OHLCV + 指标数据
            indicator: 指标名（如 'macd_dif', 'rsi12', 'kdj_k'）
        
        Returns:
            背离信号列表
        """
        signals = []
        
        if indicator not in df.columns or len(df) < self.lookback * 2:
            return signals
        
        # 检测顶底背离
        divergences = self._find_divergences(df, indicator)
        signals.extend(divergences)
        
        return signals

    def _find_divergences(self, df: pd.DataFrame, indicator: str) -> List[DivergenceSignal]:
        """查找背离"""
        signals = []
        
        # 找价格峰值和谷值
        price_peaks = self._find_peaks(df['close'].values)
        price_valleys = self._find_valleys(df['close'].values)
        
        # 找指标峰值和谷值
        indicator_peaks = self._find_peaks(df[indicator].values)
        indicator_valleys = self._find_valleys(df[indicator].values)
        
        # 检测顶背离（看跌）
        for i, (p_idx, p_val) in enumerate(price_peaks):
            if i == 0:
                continue
            prev_p_idx, prev_p_val = price_peaks[i - 1]
            
            # 找对应指标的峰值
            ind_peak = self._find_nearest_peak(indicator_peaks, p_idx)
            prev_ind_peak = self._find_nearest_peak(indicator_peaks, prev_p_idx) if i > 0 else None
            
            if ind_peak and prev_ind_peak:
                # 价格创新高，指标没创新高 → 顶背离
                if p_val > prev_p_val and ind_peak[1] <= prev_ind_peak[1]:
                    strength = self._calc_strength(
                        p_val, prev_p_val, 
                        prev_ind_peak[1], ind_peak[1]
                    )
                    signals.append(DivergenceSignal(
                        indicator=indicator,
                        divergence_type=DivergenceType.BEARISH_DIVERGENCE,
                        strength=strength,
                        price_change=self._pct_change(prev_p_val, p_val),
                        indicator_change=self._pct_change(prev_ind_peak[1], ind_peak[1]),
                        price_peaks=(prev_p_val, p_val),
                        indicator_peaks=(prev_ind_peak[1], ind_peak[1]),
                        description=f"顶背离: 价格{p_val:.2f}>前高{prev_p_val:.2f}，指标{ind_peak[1]:.4f}<前高{prev_ind_peak[1]:.4f}"
                    ))
        
        # 检测底背离（看涨）
        for i, (v_idx, v_val) in enumerate(price_valleys):
            if i == 0:
                continue
            prev_v_idx, prev_v_val = price_valleys[i - 1]
            
            ind_valley = self._find_nearest_valley(indicator_valleys, v_idx)
            prev_ind_valley = self._find_nearest_valley(indicator_valleys, prev_v_idx) if i > 0 else None
            
            if ind_valley and prev_ind_valley:
                # 价格创新低，指标没创新低 → 底背离
                if v_val < prev_v_val and ind_valley[1] >= prev_ind_valley[1]:
                    strength = self._calc_strength(
                        prev_v_val, v_val,
                        ind_valley[1], prev_ind_valley[1]
                    )
                    signals.append(DivergenceSignal(
                        indicator=indicator,
                        divergence_type=DivergenceType.BULLISH_DIVERGENCE,
                        strength=strength,
                        price_change=self._pct_change(prev_v_val, v_val),
                        indicator_change=self._pct_change(ind_valley[1], prev_ind_valley[1]),
                        price_peaks=(prev_v_val, v_val),
                        indicator_peaks=(ind_valley[1], prev_ind_valley[1]),
                        description=f"底背离: 价格{v_val:.2f}<前低{prev_v_val:.2f}，指标{ind_valley[1]:.4f}>前低{prev_ind_valley[1]:.4f}"
                    ))
        
        return signals

    def _find_peaks(self, values: np.ndarray) -> List[Tuple[int, float]]:
        """找峰值（局部高点）"""
        peaks = []
        for i in range(1, len(values) - 1):
            # 简单峰值检测
            if values[i] > values[i-1] and values[i] > values[i+1]:
                # 过滤噪音
                if i > 0 and i < len(values) - 1:
                    swing = abs(values[i] - max(values[i-1], values[i+1]))
                    if swing / (abs(values[i]) + 1e-9) > self.min_swing:
                        peaks.append((i, values[i]))
        return peaks

    def _find_valleys(self, values: np.ndarray) -> List[Tuple[int, float]]:
        """找谷值（局部低点）"""
        valleys = []
        for i in range(1, len(values) - 1):
            if values[i] < values[i-1] and values[i] < values[i+1]:
                swing = abs(values[i] - min(values[i-1], values[i+1]))
                if swing / (abs(values[i]) + 1e-9) > self.min_swing:
                    valleys.append((i, values[i]))
        return valleys

    def _find_nearest_peak(self, peaks: List[Tuple[int, float]], target_idx: int) -> Optional[Tuple[int, float]]:
        """找最近的峰值"""
        if not peaks:
            return None
        nearest = min(peaks, key=lambda p: abs(p[0] - target_idx))
        if abs(nearest[0] - target_idx) <= self.lookback:
            return nearest
        return None

    def _find_nearest_valley(self, valleys: List[Tuple[int, float]], target_idx: int) -> Optional[Tuple[int, float]]:
        """找最近的谷值"""
        if not valleys:
            return None
        nearest = min(valleys, key=lambda v: abs(v[0] - target_idx))
        if abs(nearest[0] - target_idx) <= self.lookback:
            return nearest
        return None

    def _calc_strength(self, price1: float, price2: float, ind1: float, ind2: float) -> float:
        """计算背离强度"""
        price_change = abs(price2 - price1) / (price1 + 1e-9)
        ind_change = abs(ind2 - ind1) / (abs(ind1) + 1e-9)
        
        # 强度 = 价格变化与指标变化的比值（比值越大，背离越明显）
        if ind_change > 0:
            ratio = price_change / ind_change
            strength = min(ratio / 2, 1.0)  # 归一化到 0-1
        else:
            strength = 0.5
        
        return strength

    def _pct_change(self, old: float, new: float) -> float:
        """百分比变化"""
        if old == 0:
            return 0
        return (new - old) / old * 100


def detect_all_divergences(df: pd.DataFrame, indicators: List[str] = None) -> Dict[str, List[DivergenceSignal]]:
    """
    检测所有指标的背离
    
    Args:
        df: OHLCV + 指标数据
        indicators: 指标列表，None 则检测默认指标
    
    Returns:
        各指标的背离信号字典
    """
    if indicators is None:
        indicators = ['macd_dif', 'rsi12', 'kdj_k', 'cci']
    
    detector = DivergenceDetector(lookback=20)
    results = {}
    
    for indicator in indicators:
        if indicator not in df.columns:
            continue
        signals = detector.detect(df, indicator)
        if signals:
            results[indicator] = signals
    
    return results


def get_divergence_signal(df: pd.DataFrame) -> Dict:
    """
    获取综合背离信号
    
    Returns:
        包含背离信号的字典
    """
    results = detect_all_divergences(df)
    
    if not results:
        return {
            'has_divergence': False,
            'signal': 'hold',
            'reason': '无背离信号',
            'strength': 0
        }
    
    # 统计各类背离
    bullish_count = 0
    bearish_count = 0
    max_strength = 0.0
    descriptions = []
    
    for indicator, signals in results.items():
        for sig in signals:
            if sig.divergence_type == DivergenceType.BULLISH_DIVERGENCE:
                bullish_count += 1
                max_strength = max(max_strength, sig.strength)
            elif sig.divergence_type == DivergenceType.BEARISH_DIVERGENCE:
                bearish_count += 1
                max_strength = max(max_strength, sig.strength)
            descriptions.append(sig.description)
    
    # 判断信号
    if bullish_count > 0 and bullish_count >= bearish_count:
        signal = 'buy'
        reason = f"底背离信号 ({bullish_count}个指标)"
    elif bearish_count > 0:
        signal = 'sell'
        reason = f"顶背离信号 ({bearish_count}个指标)"
    else:
        signal = 'hold'
        reason = '无明确背离信号'
    
    return {
        'has_divergence': bullish_count > 0 or bearish_count > 0,
        'signal': signal,
        'reason': reason,
        'strength': max_strength,
        'bullish_count': bullish_count,
        'bearish_count': bearish_count,
        'details': results,
        'descriptions': descriptions[:5]  # 最多5条描述
    }
