"""
策略引擎模块
"""

import pandas as pd
import numpy as np
from typing import Dict, List, Callable, Optional
from dataclasses import dataclass
from enum import Enum


class SignalType(Enum):
    """信号类型"""
    BUY = 1
    SELL = -1
    HOLD = 0


@dataclass
class TradeSignal:
    """交易信号"""
    date: str
    signal: SignalType
    price: float
    reason: str


class BaseStrategy:
    """策略基类"""
    
    name: str = "base"
    description: str = ""
    
    def __init__(self, params: Dict = None):
        self.params = params or {}
    
    def generate_signals(self, df: pd.DataFrame) -> List[TradeSignal]:
        """生成交易信号"""
        raise NotImplementedError

    def get_diagnostics(self, df: pd.DataFrame) -> Optional[Dict]:
        """返回策略诊断信息，默认无额外输出"""
        return None


class DualMAStrategy(BaseStrategy):
    """双均线策略"""
    
    name = "双均线策略"
    description = "快线均线上穿慢线买入，下穿卖出"
    
    def __init__(self, params: Dict = None):
        super().__init__(params)
        self.fast_ma = self.params.get('fast_ma', 5)
        self.slow_ma = self.params.get('slow_ma', 20)
    
    def generate_signals(self, df: pd.DataFrame) -> List[TradeSignal]:
        signals = []
        
        # 计算均线
        df['fast_ma'] = df['close'].rolling(window=self.fast_ma).mean()
        df['slow_ma'] = df['close'].rolling(window=self.slow_ma).mean()
        
        for i in range(1, len(df)):
            curr = df.iloc[i]
            prev = df.iloc[i-1]
            
            # 跳过没有完整均线数据的情况
            if pd.isna(curr['fast_ma']) or pd.isna(curr['slow_ma']):
                continue
            
            # 金叉：快线从下穿上慢线
            if prev['fast_ma'] <= prev['slow_ma'] and curr['fast_ma'] > curr['slow_ma']:
                signals.append(TradeSignal(
                    date=str(curr['date']),
                    signal=SignalType.BUY,
                    price=curr['close'],
                    reason=f"金叉: MA{self.fast_ma} > MA{self.slow_ma}"
                ))
            # 死叉：快线从上穿下慢线
            elif prev['fast_ma'] >= prev['slow_ma'] and curr['fast_ma'] < curr['slow_ma']:
                signals.append(TradeSignal(
                    date=str(curr['date']),
                    signal=SignalType.SELL,
                    price=curr['close'],
                    reason=f"死叉: MA{self.fast_ma} < MA{self.slow_ma}"
                ))
        
        return signals


class MACDStrategy(BaseStrategy):
    """MACD 策略"""
    
    name = "MACD策略"
    description = "MACD金叉买入，死叉卖出"
    
    def __init__(self, params: Dict = None):
        super().__init__(params)
    
    def generate_signals(self, df: pd.DataFrame) -> List[TradeSignal]:
        signals = []
        
        # 计算 MACD
        ema12 = df['close'].ewm(span=12, adjust=False).mean()
        ema26 = df['close'].ewm(span=26, adjust=False).mean()
        df['macd_dif'] = ema12 - ema26
        df['macd_dea'] = df['macd_dif'].ewm(span=9, adjust=False).mean()
        
        for i in range(1, len(df)):
            curr = df.iloc[i]
            prev = df.iloc[i-1]
            
            if pd.isna(curr['macd_dif']) or pd.isna(curr['macd_dea']):
                continue
            
            # 金叉
            if prev['macd_dif'] <= prev['macd_dea'] and curr['macd_dif'] > curr['macd_dea']:
                signals.append(TradeSignal(
                    date=str(curr['date']),
                    signal=SignalType.BUY,
                    price=curr['close'],
                    reason="MACD金叉"
                ))
            # 死叉
            elif prev['macd_dif'] >= prev['macd_dea'] and curr['macd_dif'] < curr['macd_dea']:
                signals.append(TradeSignal(
                    date=str(curr['date']),
                    signal=SignalType.SELL,
                    price=curr['close'],
                    reason="MACD死叉"
                ))
        
        return signals


class BreakoutStrategy(BaseStrategy):
    """突破策略"""
    
    name = "突破策略"
    description = "突破20日高点买入，跌破20日低点卖出"
    
    def __init__(self, params: Dict = None):
        super().__init__(params)
        self.period = self.params.get('period', 20)
    
    def generate_signals(self, df: pd.DataFrame) -> List[TradeSignal]:
        signals = []
        
        # 计算高低点
        df['highest'] = df['high'].rolling(window=self.period).max().shift(1)
        df['lowest'] = df['low'].rolling(window=self.period).min().shift(1)
        
        for i in range(self.period, len(df)):
            curr = df.iloc[i]
            prev = df.iloc[i-1]
            
            # 突破高点
            if curr['close'] > curr['highest'] and prev['close'] <= prev['highest']:
                signals.append(TradeSignal(
                    date=str(curr['date']),
                    signal=SignalType.BUY,
                    price=curr['close'],
                    reason=f"突破{self.period}日高点"
                ))
            # 跌破低点
            elif curr['close'] < curr['lowest'] and prev['close'] >= prev['lowest']:
                signals.append(TradeSignal(
                    date=str(curr['date']),
                    signal=SignalType.SELL,
                    price=curr['close'],
                    reason=f"跌破{self.period}日低点"
                ))
        
        return signals


class RSIStrategy(BaseStrategy):
    """RSI 策略"""

    name = "RSI策略"
    description = "RSI低于20超卖买入，高于80超买卖出"

    def __init__(self, params: Dict = None):
        super().__init__(params)
        self.period = self.params.get('period', 14)
        self.oversold = self.params.get('oversold', 20)
        self.overbought = self.params.get('overbought', 80)

    def generate_signals(self, df: pd.DataFrame) -> List[TradeSignal]:
        signals = []

        # 优先复用已有的 RSI 列（由 IndicatorCalculator 计算），
        # 否则自己计算。rs6 列对应 period=6，与 self.period 可能不同，
        # 这里取 self.period 匹配的列，或 fallback 到手动计算。
        rsi_col = f'rsi{self.period}'
        if rsi_col not in df.columns:
            # 手动计算 RSI
            delta = df['close'].diff()
            gain = (delta.where(delta > 0, 0)).rolling(window=self.period).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(window=self.period).mean()
            rs = gain / loss.replace(0, np.nan)
            df['rsi'] = (100 - (100 / (1 + rs))).fillna(50)
            rsi_col = 'rsi'

        position = None  # 当前持仓状态

        for i in range(self.period, len(df)):
            curr = df.iloc[i]

            if pd.isna(curr.get(rsi_col)):
                continue

            rsi = curr[rsi_col]

            # 超卖买入
            if rsi < self.oversold and position != 'long':
                signals.append(TradeSignal(
                    date=str(curr['date']),
                    signal=SignalType.BUY,
                    price=curr['close'],
                    reason=f"RSI超卖({rsi:.1f})"
                ))
                position = 'long'
            # 超买卖出
            elif rsi > self.overbought and position == 'long':
                signals.append(TradeSignal(
                    date=str(curr['date']),
                    signal=SignalType.SELL,
                    price=curr['close'],
                    reason=f"RSI超买({rsi:.1f})"
                ))
                position = None

        return signals


class BollReversionStrategy(BaseStrategy):
    """布林带均值回归策略"""

    name = "布林带均值回归"
    description = "价格跌破布林下轨且RSI超卖买入，反弹到中轨/超买卖出"

    def __init__(self, params: Dict = None):
        super().__init__(params)
        self.period = self.params.get("period", 20)
        self.std_dev = self.params.get("std_dev", 2)
        self.rsi_period = self.params.get("rsi_period", 14)
        self.oversold = self.params.get("oversold", 30)
        self.overbought = self.params.get("overbought", 70)

    def generate_signals(self, df: pd.DataFrame) -> List[TradeSignal]:
        signals = []

        df["boll_mid"] = df["close"].rolling(window=self.period).mean()
        df["boll_std"] = df["close"].rolling(window=self.period).std()
        df["boll_upper"] = df["boll_mid"] + self.std_dev * df["boll_std"]
        df["boll_lower"] = df["boll_mid"] - self.std_dev * df["boll_std"]

        delta = df["close"].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=self.rsi_period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=self.rsi_period).mean()
        rs = gain / loss.replace(0, np.nan)
        df["rsi"] = (100 - (100 / (1 + rs))).fillna(100)

        in_position = False
        start = max(self.period, self.rsi_period)
        for i in range(start, len(df)):
            curr = df.iloc[i]
            if pd.isna(curr["boll_lower"]) or pd.isna(curr["rsi"]):
                continue

            if not in_position and curr["close"] <= curr["boll_lower"] and curr["rsi"] <= self.oversold:
                signals.append(
                    TradeSignal(
                        date=str(curr["date"]),
                        signal=SignalType.BUY,
                        price=curr["close"],
                        reason=f"跌破布林下轨且RSI超卖({curr['rsi']:.1f})",
                    )
                )
                in_position = True
            elif in_position and (curr["close"] >= curr["boll_mid"] or curr["rsi"] >= self.overbought):
                signals.append(
                    TradeSignal(
                        date=str(curr["date"]),
                        signal=SignalType.SELL,
                        price=curr["close"],
                        reason="反弹到布林中轨/RSI修复",
                    )
                )
                in_position = False

        return signals


class TurtleBreakoutStrategy(BaseStrategy):
    """海龟通道突破策略"""

    name = "海龟突破策略"
    description = "突破N日新高买入，跌破M日低点卖出"

    def __init__(self, params: Dict = None):
        super().__init__(params)
        self.entry_period = self.params.get("period", self.params.get("entry_period", 20))
        self.exit_period = self.params.get("exit_period", 10)

    def generate_signals(self, df: pd.DataFrame) -> List[TradeSignal]:
        signals = []

        df["entry_high"] = df["high"].rolling(window=self.entry_period).max().shift(1)
        df["exit_low"] = df["low"].rolling(window=self.exit_period).min().shift(1)

        in_position = False
        start = max(self.entry_period, self.exit_period)
        for i in range(start, len(df)):
            curr = df.iloc[i]
            if pd.isna(curr["entry_high"]) or pd.isna(curr["exit_low"]):
                continue

            if not in_position and curr["close"] > curr["entry_high"]:
                signals.append(
                    TradeSignal(
                        date=str(curr["date"]),
                        signal=SignalType.BUY,
                        price=curr["close"],
                        reason=f"突破{self.entry_period}日新高",
                    )
                )
                in_position = True
            elif in_position and curr["close"] < curr["exit_low"]:
                signals.append(
                    TradeSignal(
                        date=str(curr["date"]),
                        signal=SignalType.SELL,
                        price=curr["close"],
                        reason=f"跌破{self.exit_period}日低点",
                    )
                )
                in_position = False

        return signals


class VolumeBreakoutStrategy(BaseStrategy):
    """成交量确认突破策略"""

    name = "放量突破策略"
    description = "放量突破区间高点买入，跌回突破位或均线下方卖出"

    def __init__(self, params: Dict = None):
        super().__init__(params)
        self.period = self.params.get("period", 20)
        self.volume_period = self.params.get("volume_period", 10)
        self.volume_multiplier = self.params.get("volume_multiplier", 1.5)
        self.exit_ma = self.params.get("exit_ma", 10)

    def generate_signals(self, df: pd.DataFrame) -> List[TradeSignal]:
        signals = []

        df["range_high"] = df["high"].rolling(window=self.period).max().shift(1)
        df["vol_ma"] = df["volume"].rolling(window=self.volume_period).mean()
        df["exit_ma"] = df["close"].rolling(window=self.exit_ma).mean()

        in_position = False
        breakout_level = None
        start = max(self.period, self.volume_period, self.exit_ma)
        for i in range(start, len(df)):
            curr = df.iloc[i]
            if pd.isna(curr["range_high"]) or pd.isna(curr["vol_ma"]) or pd.isna(curr["exit_ma"]):
                continue

            breakout_confirmed = (
                curr["close"] > curr["range_high"]
                and curr["volume"] >= curr["vol_ma"] * self.volume_multiplier
            )
            if not in_position and breakout_confirmed:
                breakout_level = curr["range_high"]
                signals.append(
                    TradeSignal(
                        date=str(curr["date"]),
                        signal=SignalType.BUY,
                        price=curr["close"],
                        reason=f"放量突破{self.period}日高点",
                    )
                )
                in_position = True
            elif in_position and (
                curr["close"] < (breakout_level or curr["range_high"]) or curr["close"] < curr["exit_ma"]
            ):
                signals.append(
                    TradeSignal(
                        date=str(curr["date"]),
                        signal=SignalType.SELL,
                        price=curr["close"],
                        reason="跌回突破位或失守退出均线",
                    )
                )
                in_position = False
                breakout_level = None

        return signals


class MultiFactorStrategy(BaseStrategy):
    """多因子技术面评分策略"""

    name = "多因子模型"
    description = "综合趋势、动量、均值回归和量能评分，分数突破阈值买入/卖出"

    def __init__(self, params: Dict = None):
        super().__init__(params)
        self.fast_ma = self.params.get("fast_ma", 5)
        self.slow_ma = self.params.get("slow_ma", 20)
        self.period = self.params.get("period", 14)
        self.buy_threshold = self.params.get("buy_threshold", 0.55)
        self.sell_threshold = self.params.get("sell_threshold", 0.45)
        self.volume_period = self.params.get("volume_period", 10)
        self.use_trend_factor = bool(self.params.get("use_trend_factor", 1))
        self.use_momentum_factor = bool(self.params.get("use_momentum_factor", 1))
        self.use_reversion_factor = bool(self.params.get("use_reversion_factor", 1))
        self.use_volume_factor = bool(self.params.get("use_volume_factor", 1))
        self.min_factor_pass_count = max(int(self.params.get("min_factor_pass_count", 2)), 1)
        self.trend_weight = float(self.params.get("trend_weight", 0.35))
        self.momentum_weight = float(self.params.get("momentum_weight", 0.30))
        self.reversion_weight = float(self.params.get("reversion_weight", 0.20))
        self.volume_weight = float(self.params.get("volume_weight", 0.15))

    def _normalized_weights(self) -> Dict[str, float]:
        weights = {
            "trend": max(self.trend_weight, 0.0) if self.use_trend_factor else 0.0,
            "momentum": max(self.momentum_weight, 0.0) if self.use_momentum_factor else 0.0,
            "reversion": max(self.reversion_weight, 0.0) if self.use_reversion_factor else 0.0,
            "volume": max(self.volume_weight, 0.0) if self.use_volume_factor else 0.0,
        }
        total_weight = sum(weights.values())
        if total_weight <= 0:
            return {
                "trend": 0.35,
                "momentum": 0.30,
                "reversion": 0.20,
                "volume": 0.15,
            }
        return {key: value / total_weight for key, value in weights.items()}

    def _build_analysis_frame(self, df: pd.DataFrame) -> tuple[pd.DataFrame, Dict[str, float], int, int]:
        working = df.copy()
        weights = self._normalized_weights()
        enabled_factor_count = sum(1 for value in weights.values() if value > 0)
        required_pass_count = min(self.min_factor_pass_count, max(enabled_factor_count, 1))

        working["fast_ma"] = working["close"].rolling(window=self.fast_ma).mean()
        working["slow_ma"] = working["close"].rolling(window=self.slow_ma).mean()

        ema12 = working["close"].ewm(span=12, adjust=False).mean()
        ema26 = working["close"].ewm(span=26, adjust=False).mean()
        working["macd_dif"] = ema12 - ema26
        working["macd_dea"] = working["macd_dif"].ewm(span=9, adjust=False).mean()

        delta = working["close"].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=self.period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=self.period).mean()
        rs = gain / loss.replace(0, np.nan)
        working["rsi"] = (100 - (100 / (1 + rs))).fillna(100)

        working["boll_mid"] = working["close"].rolling(window=self.period).mean()
        working["boll_std"] = working["close"].rolling(window=self.period).std()
        working["boll_upper"] = working["boll_mid"] + 2 * working["boll_std"]
        working["boll_lower"] = working["boll_mid"] - 2 * working["boll_std"]

        working["vol_ma"] = working["volume"].rolling(window=self.volume_period).mean()
        working["price_momentum"] = working["close"].pct_change(self.period).replace([np.inf, -np.inf], np.nan)

        working["trend_score"] = np.where(working["fast_ma"] > working["slow_ma"], 1.0, 0.0)
        working["momentum_score"] = np.where(
            (working["macd_dif"] > working["macd_dea"]) & (working["price_momentum"] > 0),
            1.0,
            0.0,
        )
        working["reversion_score"] = 0.5
        working.loc[(working["close"] <= working["boll_lower"]) & (working["rsi"] <= 35), "reversion_score"] = 1.0
        working.loc[(working["close"] >= working["boll_upper"]) & (working["rsi"] >= 65), "reversion_score"] = 0.0

        volume_ratio = (working["volume"] / working["vol_ma"]).replace([np.inf, -np.inf], np.nan)
        scaled_volume = ((volume_ratio - 0.8) / 0.8).clip(lower=0.0, upper=1.0)
        working["volume_score"] = np.where(working["close"] > working["close"].shift(1), scaled_volume.fillna(0.0), 0.0)

        working["passed_factor_count"] = (
            (working["trend_score"] >= 0.5).astype(int) * int(weights["trend"] > 0)
            + (working["momentum_score"] >= 0.5).astype(int) * int(weights["momentum"] > 0)
            + (working["reversion_score"] >= 0.5).astype(int) * int(weights["reversion"] > 0)
            + (working["volume_score"] >= 0.5).astype(int) * int(weights["volume"] > 0)
        )
        working["composite_score"] = (
            working["trend_score"] * weights["trend"]
            + working["momentum_score"] * weights["momentum"]
            + working["reversion_score"] * weights["reversion"]
            + working["volume_score"] * weights["volume"]
        )

        return working, weights, enabled_factor_count, required_pass_count

    def generate_signals(self, df: pd.DataFrame) -> List[TradeSignal]:
        signals = []
        working, weights, enabled_factor_count, required_pass_count = self._build_analysis_frame(df)

        in_position = False
        start = max(self.slow_ma, self.period, self.volume_period)
        for i in range(start, len(working)):
            curr = working.iloc[i]

            required = [
                curr["fast_ma"],
                curr["slow_ma"],
                curr["macd_dif"],
                curr["macd_dea"],
                curr["rsi"],
                curr["boll_mid"],
                curr["boll_upper"],
                curr["boll_lower"],
                curr["vol_ma"],
                curr["price_momentum"],
            ]
            if any(pd.isna(value) for value in required):
                continue

            trend_score = float(curr["trend_score"])
            momentum_score = float(curr["momentum_score"])
            reversion_score = float(curr["reversion_score"])
            volume_score = float(curr["volume_score"])
            passed_factor_count = int(curr["passed_factor_count"])
            composite_score = float(curr["composite_score"])

            if (
                not in_position
                and composite_score >= self.buy_threshold
                and passed_factor_count >= required_pass_count
            ):
                signals.append(
                    TradeSignal(
                        date=str(curr["date"]),
                        signal=SignalType.BUY,
                        price=curr["close"],
                        reason=(
                            f"多因子买入({composite_score:.2f}, "
                            f"{passed_factor_count}/{enabled_factor_count}, "
                            f"T{trend_score:.1f}/M{momentum_score:.1f}/R{reversion_score:.1f}/V{volume_score:.1f})"
                        ),
                    )
                )
                in_position = True
            elif (
                in_position
                and (composite_score <= self.sell_threshold or passed_factor_count < required_pass_count)
            ):
                signals.append(
                    TradeSignal(
                        date=str(curr["date"]),
                        signal=SignalType.SELL,
                        price=curr["close"],
                        reason=(
                            f"多因子卖出({composite_score:.2f}, "
                            f"{passed_factor_count}/{enabled_factor_count}, "
                            f"T{trend_score:.1f}/M{momentum_score:.1f}/R{reversion_score:.1f}/V{volume_score:.1f})"
                        ),
                    )
                )
                in_position = False

        return signals

    def get_diagnostics(self, df: pd.DataFrame) -> Optional[Dict]:
        working, weights, enabled_factor_count, required_pass_count = self._build_analysis_frame(df)
        factor_curve = []
        start = max(self.slow_ma, self.period, self.volume_period)
        for i in range(start, len(working)):
            curr = working.iloc[i]
            required = [
                curr["fast_ma"],
                curr["slow_ma"],
                curr["macd_dif"],
                curr["macd_dea"],
                curr["rsi"],
                curr["boll_mid"],
                curr["boll_upper"],
                curr["boll_lower"],
                curr["vol_ma"],
                curr["price_momentum"],
            ]
            if any(pd.isna(value) for value in required):
                continue
            factor_curve.append(
                {
                    "date": str(curr["date"])[:10],
                    "close": float(curr["close"]),
                    "trend_score": float(curr["trend_score"]),
                    "momentum_score": float(curr["momentum_score"]),
                    "reversion_score": float(curr["reversion_score"]),
                    "volume_score": float(curr["volume_score"]),
                    "composite_score": float(curr["composite_score"]),
                    "passed_factor_count": int(curr["passed_factor_count"]),
                    "enabled_factor_count": enabled_factor_count,
                }
            )

        return {
            "weights": weights,
            "enabled_factors": {
                "trend": self.use_trend_factor,
                "momentum": self.use_momentum_factor,
                "reversion": self.use_reversion_factor,
                "volume": self.use_volume_factor,
            },
            "required_pass_count": required_pass_count,
            "factor_curve": factor_curve,
        }


class StrategyEngine:
    """策略引擎"""
    
    def __init__(self):
        self.strategies: Dict[str, type] = {
            'dual_ma': DualMAStrategy,
            'macd': MACDStrategy,
            'breakout': BreakoutStrategy,
            'rsi': RSIStrategy,
            'boll_reversion': BollReversionStrategy,
            'turtle_breakout': TurtleBreakoutStrategy,
            'volume_breakout': VolumeBreakoutStrategy,
            'multi_factor': MultiFactorStrategy,
        }
    
    def get_available_strategies(self) -> List[str]:
        """获取可用策略列表"""
        return list(self.strategies.keys())

    def get_strategy_param_ranges(self, name: str) -> Dict[str, List]:
        """获取策略默认参数搜索范围"""
        ranges = {
            'dual_ma': {
                'fast_ma': [3, 5, 8, 10],
                'slow_ma': [15, 20, 30, 60],
            },
            'macd': {},
            'breakout': {
                'period': [10, 20, 30, 60],
            },
            'rsi': {
                'period': [6, 14, 21],
                'oversold': [20, 25, 30],
                'overbought': [70, 75, 80],
            },
            'boll_reversion': {
                'period': [14, 20, 26],
                'oversold': [20, 25, 30],
                'overbought': [65, 70, 75],
            },
            'turtle_breakout': {
                'period': [20, 30, 55],
                'exit_period': [10, 15, 20],
            },
            'volume_breakout': {
                'period': [10, 20, 30],
            },
            'multi_factor': {
                'fast_ma': [5, 8, 10],
                'slow_ma': [20, 30, 60],
                'period': [10, 14, 20],
                'buy_threshold': [0.5, 0.55, 0.6],
                'sell_threshold': [0.35, 0.4, 0.45],
                'min_factor_pass_count': [2, 3],
                'trend_weight': [0.2, 0.35, 0.5],
                'momentum_weight': [0.2, 0.3, 0.4],
                'reversion_weight': [0.1, 0.2, 0.3],
                'volume_weight': [0.1, 0.15, 0.25],
            },
        }
        if name not in ranges:
            raise ValueError(f"Unknown strategy: {name}")
        return ranges[name]
    
    def create_strategy(self, name: str, params: Dict = None) -> BaseStrategy:
        """创建策略实例"""
        if name not in self.strategies:
            raise ValueError(f"Unknown strategy: {name}")
        
        return self.strategies[name](params)
    
    def run_strategy(self, df: pd.DataFrame, strategy_name: str, params: Dict = None) -> List[TradeSignal]:
        """运行策略"""
        strategy = self.create_strategy(strategy_name, params)
        return strategy.generate_signals(df)
