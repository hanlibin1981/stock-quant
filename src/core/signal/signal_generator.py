"""
交易信号模块 - 优化版
增强信号生成，包含更多指标和验证
"""

import pandas as pd
import numpy as np
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from datetime import datetime


@dataclass
class TradeSignal:
    """交易信号"""
    date: str
    signal: str  # 'buy', 'sell', 'hold'
    price: float
    reason: str
    strength: float = 0.0  # 信号强度 0-1
    details: Dict = None  # 详细指标数据


class SignalGenerator:
    """增强版信号生成器"""
    
    def __init__(self):
        self.signal_history = []
    
    def analyze(self, df: pd.DataFrame) -> Dict:
        """
        综合分析生成交易信号
        
        Args:
            df: 包含OHLCV和技术指标的DataFrame
        
        Returns:
            包含信号和详情的字典
        """
        if df is None or len(df) < 30:
            return {'signal': 'hold', 'reason': '数据不足', 'strength': 0}
        
        latest = df.iloc[-1]
        prev = df.iloc[-2] if len(df) > 1 else latest
        prev2 = df.iloc[-3] if len(df) > 2 else latest
        
        # 获取趋势
        trend = self._get_trend(df)  # 'up', 'down', 'sideways'
        
        signals = []
        
        # 1. MACD 信号 (权重 0.2)
        if 'macd_dif' in df.columns and 'macd_dea' in df.columns:
            macd_signal = self._analyze_macd(df)
            signals.append({**macd_signal, 'weight': 0.2})
        
        # 2. RSI 信号 (权重 0.15)
        if 'rsi12' in df.columns:
            rsi_signal = self._analyze_rsi(df)
            signals.append({**rsi_signal, 'weight': 0.15})
        
        # 3. KDJ 信号 (权重 0.15)
        if 'kdj_k' in df.columns and 'kdj_d' in df.columns:
            kdj_signal = self._analyze_kdj(df)
            signals.append({**kdj_signal, 'weight': 0.15})
        
        # 4. 布林带信号 (权重 0.1)
        if 'boll_upper' in df.columns and 'boll_lower' in df.columns:
            boll_signal = self._analyze_boll(df)
            signals.append({**boll_signal, 'weight': 0.1})
        
        # 5. 均线信号 (权重 0.15)
        if 'ma5' in df.columns and 'ma20' in df.columns:
            ma_signal = self._analyze_ma(df)
            signals.append({**ma_signal, 'weight': 0.15})
        
        # 6. CCI 信号 (权重 0.08)
        if 'cci' in df.columns:
            cci_signal = self._analyze_cci(df)
            signals.append({**cci_signal, 'weight': 0.08})
        
        # 7. WR 信号 (权重 0.07)
        if 'wr6' in df.columns:
            wr_signal = self._analyze_wr(df)
            signals.append({**wr_signal, 'weight': 0.07})
        
        # 8. 成交量验证 (权重 0.1)
        volume_signal = self._analyze_volume(df)
        signals.append({**volume_signal, 'weight': 0.1})
        
        # 综合判断
        if not signals:
            return {'signal': 'hold', 'reason': '无明确信号', 'strength': 0}
        
        # 过滤非 hold 信号
        active_signals = [s for s in signals if s['signal'] != 'hold']
        
        if not active_signals:
            return {'signal': 'hold', 'reason': f'趋势{trend}中，无明确信号', 'strength': 0.3, 'trend': trend}
        
        # 趋势过滤
        buy_signals = [s for s in active_signals if s['signal'] == 'buy']
        sell_signals = [s for s in active_signals if s['signal'] == 'sell']
        
        # 趋势过滤：上涨趋势中忽略卖出信号，下跌趋势中忽略买入信号
        if trend == 'down':
            buy_signals = []  # 下跌趋势不做多
        elif trend == 'up':
            sell_signals = []  # 上涨趋势不做空
        
        # 计算加权信号
        buy_score = sum(s['strength'] * s['weight'] for s in buy_signals)
        sell_score = sum(s['strength'] * s['weight'] for s in sell_signals)
        
        # 获取关键价位
        levels = self._get_support_resistance(df)
        
        # 构建详细结果
        details = {
            'trend': trend,
            'price': float(latest.get('close', 0)),
            'volume': float(latest.get('volume', 0)),
            'ma5': float(latest.get('ma5', 0)) if pd.notna(latest.get('ma5')) else None,
            'ma20': float(latest.get('ma20', 0)) if pd.notna(latest.get('ma20')) else None,
            'macd_dif': float(latest.get('macd_dif', 0)) if pd.notna(latest.get('macd_dif')) else None,
            'macd_dea': float(latest.get('macd_dea', 0)) if pd.notna(latest.get('macd_dea')) else None,
            'rsi12': float(latest.get('rsi12', 50)) if pd.notna(latest.get('rsi12')) else 50,
            'kdj_k': float(latest.get('kdj_k', 50)) if pd.notna(latest.get('kdj_k')) else 50,
            'kdj_d': float(latest.get('kdj_d', 50)) if pd.notna(latest.get('kdj_d')) else 50,
            'boll_upper': float(latest.get('boll_upper', 0)) if pd.notna(latest.get('boll_upper')) else None,
            'boll_lower': float(latest.get('boll_lower', 0)) if pd.notna(latest.get('boll_lower')) else None,
            'cci': float(latest.get('cci', 0)) if pd.notna(latest.get('cci')) else 0,
            'wr6': float(latest.get('wr6', 0)) if pd.notna(latest.get('wr6')) else 0,
            'support': levels['support'],
            'resistance': levels['resistance'],
            'signals': signals
        }
        
        # 判断
        if buy_score > 0.3:
            return {
                'signal': 'buy',
                'reason': f"买入信号 ({len(buy_signals)}/{len(active_signals)}指标, 得分{buy_score:.2f})",
                'strength': min(buy_score, 1.0),
                'trend': trend,
                'details': details
            }
        elif sell_score > 0.3:
            return {
                'signal': 'sell',
                'reason': f"卖出信号 ({len(sell_signals)}/{len(active_signals)}指标, 得分{sell_score:.2f})",
                'strength': min(sell_score, 1.0),
                'trend': trend,
                'details': details
            }
        else:
            return {
                'signal': 'hold',
                'reason': f'信号不明显 (买{buy_score:.2f}/卖{sell_score:.2f})',
                'strength': 0.3,
                'trend': trend,
                'details': details
            }

    def validate_signal_history(self, df: pd.DataFrame, horizons: List[int] = None) -> Dict:
        """基于历史滚动窗口验证当前信号逻辑的后续表现"""
        horizons = horizons or [3, 5, 10]
        if df is None or len(df) < 40:
            return {
                'signal_count': 0,
                'buy_count': 0,
                'sell_count': 0,
                'summary': {},
                'recent_signals': [],
            }

        validated_signals = []
        max_horizon = max(horizons)
        start_index = 30
        end_index = len(df) - max_horizon

        for idx in range(start_index, end_index):
            window = df.iloc[: idx + 1].copy()
            result = self.analyze(window)
            signal = result.get('signal', 'hold')
            if signal == 'hold':
                continue

            entry_price = float(df.iloc[idx]['close'])
            forward_returns = {}
            hit_map = {}

            for horizon in horizons:
                future_price = float(df.iloc[idx + horizon]['close'])
                pct_return = (future_price / entry_price - 1) * 100 if entry_price else 0.0
                forward_returns[str(horizon)] = pct_return
                if signal == 'buy':
                    hit_map[str(horizon)] = pct_return > 0
                else:
                    hit_map[str(horizon)] = pct_return < 0

            validated_signals.append(
                {
                    'date': str(df.iloc[idx]['date'])[:10],
                    'signal': signal,
                    'reason': result.get('reason', ''),
                    'strength': float(result.get('strength', 0)),
                    'forward_returns': forward_returns,
                    'hit_map': hit_map,
                }
            )

        summary = self._build_validation_summary(validated_signals, horizons)
        buy_signals = [item for item in validated_signals if item['signal'] == 'buy']
        sell_signals = [item for item in validated_signals if item['signal'] == 'sell']

        return {
            'signal_count': len(validated_signals),
            'buy_count': len(buy_signals),
            'sell_count': len(sell_signals),
            'summary': summary,
            'buy_summary': self._build_validation_summary(buy_signals, horizons),
            'sell_summary': self._build_validation_summary(sell_signals, horizons),
            'recent_signals': validated_signals[-5:],
        }

    def _build_validation_summary(self, signals: List[Dict], horizons: List[int]) -> Dict:
        """按周期汇总历史信号表现"""
        summary = {}
        for horizon in horizons:
            horizon_key = str(horizon)
            horizon_returns = [item['forward_returns'][horizon_key] for item in signals]
            if not horizon_returns:
                summary[horizon_key] = {'avg_return': 0.0, 'hit_rate': 0.0}
                continue
            hit_count = sum(1 for item in signals if item['hit_map'][horizon_key])
            summary[horizon_key] = {
                'avg_return': float(np.mean(horizon_returns)),
                'hit_rate': float(hit_count / len(horizon_returns) * 100),
            }
        return summary
    
    def _get_trend(self, df: pd.DataFrame) -> str:
        """判断趋势：上涨/下跌/震荡"""
        if len(df) < 20:
            return 'sideways'
        
        latest = df.iloc[-1]
        ma5 = latest.get('ma5')
        ma20 = latest.get('ma20')
        
        if pd.isna(ma5) or pd.isna(ma20):
            return 'sideways'
        
        # 均线多头排列
        ma10 = latest.get('ma10')
        if pd.notna(ma10) and ma5 > ma10 > ma20:
            return 'up'
        # 均线空头排列
        elif pd.notna(ma10) and ma5 < ma10 < ma20:
            return 'down'
        
        # 简单判断：价格与均线关系
        close = latest.get('close', 0)
        if close > ma20 and ma5 > ma20:
            return 'up'
        elif close < ma20 and ma5 < ma20:
            return 'down'
        
        return 'sideways'
    
    def _get_support_resistance(self, df: pd.DataFrame) -> Dict:
        """获取支撑位和压力位"""
        if len(df) < 20:
            return {'support': None, 'resistance': None}
        
        latest = df.iloc[-1]
        close = latest.get('close', 0)
        
        # 布林带
        boll_lower = latest.get('boll_lower')
        boll_upper = latest.get('boll_upper')
        
        # 近期高低点
        low20 = df['low'].tail(20).min()
        high20 = df['high'].tail(20).max()
        
        support = []
        resistance = []
        
        if pd.notna(boll_lower):
            support.append(boll_lower)
        support.append(low20)
        
        if pd.notna(boll_upper):
            resistance.append(boll_upper)
        resistance.append(high20)
        
        # 均线支撑/压力
        for ma in ['ma5', 'ma10', 'ma20']:
            if ma in df.columns:
                val = latest.get(ma)
                if pd.notna(val):
                    if val < close:
                        support.append(val)
                    else:
                        resistance.append(val)
        
        return {
            'support': round(min(support), 2) if support else None,
            'resistance': round(max(resistance), 2) if resistance else None
        }
    
    def _analyze_macd(self, df: pd.DataFrame) -> Dict:
        """MACD分析"""
        latest = df.iloc[-1]
        prev = df.iloc[-2] if len(df) > 1 else latest
        
        dif = latest.get('macd_dif', 0) or 0
        dea = latest.get('macd_dea', 0) or 0
        prev_dif = prev.get('macd_dif', 0) or 0
        prev_dea = prev.get('macd_dea', 0) or 0
        hist = latest.get('macd_hist', 0) or 0
        
        # 金叉
        if prev_dif <= prev_dea and dif > dea:
            strength = min(abs(hist) * 5, 1.0)
            return {'indicator': 'MACD', 'signal': 'buy', 'reason': '金叉', 'strength': strength}
        
        # 死叉
        elif prev_dif >= prev_dea and dif < dea:
            strength = min(abs(hist) * 5, 1.0)
            return {'indicator': 'MACD', 'signal': 'sell', 'reason': '死叉', 'strength': strength}
        
        # 零轴位置
        if dif > 0 and dea > 0:
            return {'indicator': 'MACD', 'signal': 'hold', 'reason': '多头', 'strength': 0.2}
        elif dif < 0 and dea < 0:
            return {'indicator': 'MACD', 'signal': 'hold', 'reason': '空头', 'strength': 0.2}
        
        return {'indicator': 'MACD', 'signal': 'hold', 'reason': '中性', 'strength': 0}
    
    def _analyze_rsi(self, df: pd.DataFrame) -> Dict:
        """RSI分析"""
        latest = df.iloc[-1]
        rsi = latest.get('rsi12', 50) or 50
        
        if rsi < 20:
            return {'indicator': 'RSI', 'signal': 'buy', 'reason': f'超卖({rsi:.0f})', 'strength': 0.9}
        elif rsi < 30:
            return {'indicator': 'RSI', 'signal': 'buy', 'reason': f'接近超卖({rsi:.0f})', 'strength': 0.6}
        elif rsi > 80:
            return {'indicator': 'RSI', 'signal': 'sell', 'reason': f'超买({rsi:.0f})', 'strength': 0.9}
        elif rsi > 70:
            return {'indicator': 'RSI', 'signal': 'sell', 'reason': f'接近超买({rsi:.0f})', 'strength': 0.6}
        
        return {'indicator': 'RSI', 'signal': 'hold', 'reason': f'中性({rsi:.0f})', 'strength': 0}
    
    def _analyze_kdj(self, df: pd.DataFrame) -> Dict:
        """KDJ分析"""
        latest = df.iloc[-1]
        prev = df.iloc[-2] if len(df) > 1 else latest
        
        k = latest.get('kdj_k', 50) or 50
        d = latest.get('kdj_d', 50) or 50
        j = latest.get('kdj_j', 50) or 50
        
        prev_k = prev.get('kdj_k', 50) or 50
        prev_d = prev.get('kdj_d', 50) or 50
        
        # 金叉
        if prev_k <= prev_d and k > d:
            if j < 20:
                return {'indicator': 'KDJ', 'signal': 'buy', 'reason': '超卖金叉', 'strength': 0.9}
            return {'indicator': 'KDJ', 'signal': 'buy', 'reason': '金叉', 'strength': 0.5}
        
        # 死叉
        elif prev_k >= prev_d and k < d:
            if j > 80:
                return {'indicator': 'KDJ', 'signal': 'sell', 'reason': '超买死叉', 'strength': 0.9}
            return {'indicator': 'KDJ', 'signal': 'sell', 'reason': '死叉', 'strength': 0.5}
        
        # 超卖超买
        if k < 20:
            return {'indicator': 'KDJ', 'signal': 'buy', 'reason': f'超卖(K={k:.0f})', 'strength': 0.7}
        elif k > 80:
            return {'indicator': 'KDJ', 'signal': 'sell', 'reason': f'超买(K={k:.0f})', 'strength': 0.7}
        
        return {'indicator': 'KDJ', 'signal': 'hold', 'reason': '中性', 'strength': 0}
    
    def _analyze_boll(self, df: pd.DataFrame) -> Dict:
        """布林带分析"""
        latest = df.iloc[-1]
        close = latest.get('close', 0)
        
        upper = latest.get('boll_upper')
        lower = latest.get('boll_lower')
        
        if pd.isna(upper) or pd.isna(lower):
            return {'indicator': 'BOLL', 'signal': 'hold', 'reason': '数据不足', 'strength': 0}
        
        # 突破上下轨
        if close < lower:
            return {'indicator': 'BOLL', 'signal': 'buy', 'reason': '跌破下轨超卖', 'strength': 0.8}
        elif close > upper:
            return {'indicator': 'BOLL', 'signal': 'sell', 'reason': '突破上轨超买', 'strength': 0.8}
        
        # 触及下轨
        if close < lower * 1.02:
            return {'indicator': 'BOLL', 'signal': 'buy', 'reason': '接近下轨', 'strength': 0.5}
        # 触及上轨
        elif close > upper * 0.98:
            return {'indicator': 'BOLL', 'signal': 'sell', 'reason': '接近上轨', 'strength': 0.5}
        
        return {'indicator': 'BOLL', 'signal': 'hold', 'reason': '轨道内', 'strength': 0}
    
    def _analyze_ma(self, df: pd.DataFrame) -> Dict:
        """均线分析"""
        latest = df.iloc[-1]
        ma5 = latest.get('ma5')
        ma10 = latest.get('ma10')
        ma20 = latest.get('ma20')
        close = latest.get('close', 0)
        
        if pd.isna(ma5) or pd.isna(ma20):
            return {'indicator': 'MA', 'signal': 'hold', 'reason': '数据不足', 'strength': 0}
        
        # 多头排列
        if pd.notna(ma10) and ma5 > ma10 > ma20 and close > ma5:
            return {'indicator': 'MA', 'signal': 'buy', 'reason': '多头排列', 'strength': 0.8}
        
        # 空头排列
        elif pd.notna(ma10) and ma5 < ma10 < ma20 and close < ma5:
            return {'indicator': 'MA', 'signal': 'sell', 'reason': '空头排列', 'strength': 0.8}
        
        # 均线金叉
        prev = df.iloc[-2]
        prev_ma5 = prev.get('ma5', 0) or 0
        prev_ma20 = prev.get('ma20', 0) or 0
        
        if prev_ma5 <= prev_ma20 and ma5 > ma20:
            return {'indicator': 'MA', 'signal': 'buy', 'reason': 'MA5上穿MA20', 'strength': 0.6}
        elif prev_ma5 >= prev_ma20 and ma5 < ma20:
            return {'indicator': 'MA', 'signal': 'sell', 'reason': 'MA5下穿MA20', 'strength': 0.6}
        
        return {'indicator': 'MA', 'signal': 'hold', 'reason': '中性', 'strength': 0}
    
    def _analyze_cci(self, df: pd.DataFrame) -> Dict:
        """CCI分析"""
        latest = df.iloc[-1]
        cci = latest.get('cci', 0) or 0
        
        if cci < -100:
            return {'indicator': 'CCI', 'signal': 'buy', 'reason': f'超卖({cci:.0f})', 'strength': 0.8}
        elif cci > 100:
            return {'indicator': 'CCI', 'signal': 'sell', 'reason': f'超买({cci:.0f})', 'strength': 0.8}
        
        return {'indicator': 'CCI', 'signal': 'hold', 'reason': f'中性({cci:.0f})', 'strength': 0}
    
    def _analyze_wr(self, df: pd.DataFrame) -> Dict:
        """威廉指标分析"""
        latest = df.iloc[-1]
        wr6 = latest.get('wr6', -50) or -50
        
        # WR 超卖是负值，转换一下
        wr = abs(wr6)
        
        if wr < 20:
            return {'indicator': 'WR', 'signal': 'sell', 'reason': f'超买({wr:.0f})', 'strength': 0.7}
        elif wr > 80:
            return {'indicator': 'WR', 'signal': 'buy', 'reason': f'超卖({wr:.0f})', 'strength': 0.7}
        
        return {'indicator': 'WR', 'signal': 'hold', 'reason': f'中性({wr:.0f})', 'strength': 0}
    
    def _analyze_volume(self, df: pd.DataFrame) -> Dict:
        """成交量分析"""
        if len(df) < 5 or 'volume' not in df.columns:
            return {'indicator': 'VOL', 'signal': 'hold', 'reason': '数据不足', 'strength': 0}
        
        latest = df.iloc[-1]
        prev = df.iloc[-2]
        
        vol = latest.get('volume', 0)
        prev_vol = prev.get('volume', 0)
        
        # 放量判断
        avg_vol = df['volume'].tail(20).mean()
        
        if vol > avg_vol * 1.5:
            # 放量
            price = latest.get('close', 0)
            prev_price = prev.get('close', 0)
            
            if price > prev_price:
                return {'indicator': 'VOL', 'signal': 'buy', 'reason': '放量上涨', 'strength': 0.8}
            elif price < prev_price:
                return {'indicator': 'VOL', 'signal': 'sell', 'reason': '放量下跌', 'strength': 0.8}
        
        elif vol < avg_vol * 0.5:
            # 缩量
            price = latest.get('close', 0)
            prev_price = prev.get('close', 0)
            
            if price > prev_price:
                return {'indicator': 'VOL', 'signal': 'buy', 'reason': '缩量上涨', 'strength': 0.4}
            elif price < prev_price:
                return {'indicator': 'VOL', 'signal': 'sell', 'reason': '缩量下跌', 'strength': 0.4}
        
        return {'indicator': 'VOL', 'signal': 'hold', 'reason': '量能正常', 'strength': 0}


# 单例
_signal_generator = None

def get_signal_generator() -> SignalGenerator:
    """获取信号生成器单例"""
    global _signal_generator
    if _signal_generator is None:
        _signal_generator = SignalGenerator()
    return _signal_generator
