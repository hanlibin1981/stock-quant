"""
蒙特卡洛模拟模块
模拟策略收益分布，评估风险和不确定性
"""

import pandas as pd
import numpy as np
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass
from enum import Enum
import random


class SimulationType(Enum):
    """模拟类型"""
    BOOTSTRAP = "bootstrap"  # Bootstrap重采样
    SHUFFLE = "shuffle"  # 时间洗牌
    GEOMETRIC = "geometric"  # 几何布朗运动


@dataclass
class SimulationResult:
    """模拟结果"""
    simulation_type: str
    n_simulations: int
    n_periods: int
    
    # 收益分布
    returns_distribution: List[float]  # 最终收益分布
    mean_return: float
    median_return: float
    std_return: float
    
    # 风险指标
    var_95: float  # 95% VaR
    cvar_95: float  # 95% CVaR
    max_loss: float
    max_gain: float
    
    # 百分位
    percentile_5: float
    percentile_25: float
    percentile_50: float
    percentile_75: float
    percentile_95: float
    
    # 胜率
    win_rate: float  # 正收益占比
    loss_rate: float  # 负收益占比
    
    # 路径统计
    all_paths: Optional[List[List[float]]] = None  # 所有模拟路径（可选）
    worst_paths: List[List[float]] = None  # 最差10%路径
    best_paths: List[List[float]] = None  # 最好10%路径


class MonteCarloSimulator:
    """
    蒙特卡洛模拟器
    
    支持多种模拟方法：
    1. Bootstrap - 从历史收益率中重采样
    2. Shuffle - 随机打乱历史收益率顺序
    3. Geometric Brownian Motion - 假设收益率服从对数正态分布
    """

    def __init__(self, seed: int = None):
        """
        Args:
            seed: 随机种子，用于复现
        """
        self.seed = seed
        if seed is not None:
            random.seed(seed)
            np.random.seed(seed)

    def simulate(
        self,
        equity_curve: List[Dict],
        trades: List[Dict] = None,
        n_simulations: int = 1000,
        simulation_type: SimulationType = SimulationType.BOOTSTRAP,
        initial_capital: float = 100000,
        n_periods: int = None
    ) -> SimulationResult:
        """
        运行蒙特卡洛模拟
        
        Args:
            equity_curve: 历史权益曲线
            trades: 交易记录（可选，用于分析交易统计）
            n_simulations: 模拟次数
            simulation_type: 模拟方法
            initial_capital: 初始资金
            n_periods: 模拟周期数（None则使用历史长度）
        
        Returns:
            SimulationResult 模拟结果
        """
        if not equity_curve or len(equity_curve) < 2:
            return self._empty_result(n_simulations, 0, simulation_type.value)
        
        # 提取历史权益
        equity_series = pd.Series([point["equity"] for point in equity_curve], dtype=float)
        daily_returns = equity_series.pct_change().replace([np.inf, -np.inf], np.nan).dropna()
        
        if len(daily_returns) < 2:
            return self._empty_result(n_simulations, len(equity_curve), simulation_type.value)
        
        # 基础统计
        mean_daily_return = daily_returns.mean()
        std_daily_return = daily_returns.std()
        
        # 确定模拟周期
        if n_periods is None:
            n_periods = len(daily_returns)
        
        # 根据模拟类型生成路径
        if simulation_type == SimulationType.BOOTSTRAP:
            paths = self._bootstrap_simulation(
                daily_returns, mean_daily_return, std_daily_return,
                n_simulations, n_periods, initial_capital
            )
        elif simulation_type == SimulationType.SHUFFLE:
            paths = self._shuffle_simulation(
                daily_returns, mean_daily_return, std_daily_return,
                n_simulations, n_periods, initial_capital
            )
        elif simulation_type == SimulationType.GEOMETRIC:
            paths = self._gbm_simulation(
                daily_returns, mean_daily_return, std_daily_return,
                n_simulations, n_periods, initial_capital
            )
        else:
            paths = self._bootstrap_simulation(
                daily_returns, mean_daily_return, std_daily_return,
                n_simulations, n_periods, initial_capital
            )
        
        # 计算最终收益分布
        final_returns = [(path[-1] / initial_capital - 1) * 100 for path in paths]
        
        # 统计计算
        returns_distribution = sorted(final_returns)
        mean_return = np.mean(final_returns)
        median_return = np.median(final_returns)
        std_return = np.std(final_returns)
        
        # VaR / CVaR
        var_95 = np.percentile(returns_distribution, 5)
        cvar_95 = np.mean(returns_distribution[:int(len(returns_distribution) * 0.05)])
        
        # 最大收益/亏损
        max_loss = min(final_returns)
        max_gain = max(final_returns)
        
        # 百分位
        percentile_5 = np.percentile(returns_distribution, 5)
        percentile_25 = np.percentile(returns_distribution, 25)
        percentile_50 = np.percentile(returns_distribution, 50)
        percentile_75 = np.percentile(returns_distribution, 75)
        percentile_95 = np.percentile(returns_distribution, 95)
        
        # 胜率
        win_count = sum(1 for r in final_returns if r > 0)
        win_rate = win_count / len(final_returns) * 100
        loss_rate = 100 - win_rate
        
        # 最差/最好路径
        sorted_paths = sorted(zip(final_returns, paths), key=lambda x: x[0])
        worst_paths = [p for _, p in sorted_paths[:int(n_simulations * 0.1)]]
        best_paths = [p for _, p in sorted_paths[-int(n_simulations * 0.1):]]
        
        return SimulationResult(
            simulation_type=simulation_type.value,
            n_simulations=n_simulations,
            n_periods=n_periods,
            returns_distribution=returns_distribution,
            mean_return=mean_return,
            median_return=median_return,
            std_return=std_return,
            var_95=var_95,
            cvar_95=cvar_95,
            max_loss=max_loss,
            max_gain=max_gain,
            percentile_5=percentile_5,
            percentile_25=percentile_25,
            percentile_50=percentile_50,
            percentile_75=percentile_75,
            percentile_95=percentile_95,
            win_rate=win_rate,
            loss_rate=loss_rate,
            worst_paths=worst_paths,
            best_paths=best_paths
        )

    def _bootstrap_simulation(
        self,
        daily_returns: pd.Series,
        mean_return: float,
        std_return: float,
        n_simulations: int,
        n_periods: int,
        initial_capital: float
    ) -> List[List[float]]:
        """Bootstrap 重采样模拟"""
        returns_array = daily_returns.values
        n_history = len(returns_array)
        paths = []
        
        for _ in range(n_simulations):
            path = [initial_capital]
            for _ in range(n_periods):
                # 随机选择历史某一天的收益率
                sampled_return = random.choice(returns_array)
                new_equity = path[-1] * (1 + sampled_return)
                path.append(new_equity)
            paths.append(path)
        
        return paths

    def _shuffle_simulation(
        self,
        daily_returns: pd.Series,
        mean_return: float,
        std_return: float,
        n_simulations: int,
        n_periods: int,
        initial_capital: float
    ) -> List[List[float]]:
        """时间洗牌模拟"""
        returns_array = daily_returns.values.copy()
        n_history = len(returns_array)
        paths = []
        
        for _ in range(n_simulations):
            path = [initial_capital]
            # 随机打乱顺序
            shuffled = returns_array.copy()
            random.shuffle(shuffled)
            for i in range(n_periods):
                sampled_return = shuffled[i % n_history]
                new_equity = path[-1] * (1 + sampled_return)
                path.append(new_equity)
            paths.append(path)
        
        return paths

    def _gbm_simulation(
        self,
        daily_returns: pd.Series,
        mean_return: float,
        std_return: float,
        n_simulations: int,
        n_periods: int,
        initial_capital: float
    ) -> List[List[float]]:
        """
        几何布朗运动 (GBM) 模拟
        
        假设收益率服从对数正态分布：
        S(t+1) = S(t) * exp((mu - 0.5*sigma^2)*dt + sigma*sqrt(dt)*Z)
        其中 Z ~ N(0,1)
        """
        mu = mean_return  # 日均收益率
        sigma = std_return  # 日波动率
        
        paths = []
        for _ in range(n_simulations):
            path = [initial_capital]
            for _ in range(n_periods):
                # 生成标准正态随机数
                z = np.random.normal()
                # GBM 公式
                drift = mu - 0.5 * sigma ** 2
                diffusion = sigma * z
                daily_return = np.exp(drift + diffusion) - 1
                
                new_equity = path[-1] * (1 + daily_return)
                path.append(new_equity)
            paths.append(path)
        
        return paths

    def _empty_result(self, n_simulations: int, n_periods: int, sim_type: str) -> SimulationResult:
        """返回空结果"""
        return SimulationResult(
            simulation_type=sim_type,
            n_simulations=n_simulations,
            n_periods=n_periods,
            returns_distribution=[],
            mean_return=0,
            median_return=0,
            std_return=0,
            var_95=0,
            cvar_95=0,
            max_loss=0,
            max_gain=0,
            percentile_5=0,
            percentile_25=0,
            percentile_50=0,
            percentile_75=0,
            percentile_95=0,
            win_rate=0,
            loss_rate=0,
            worst_paths=[],
            best_paths=[]
        )

    def get_probability_distribution(
        self,
        result: SimulationResult,
        n_buckets: int = 20
    ) -> List[Dict]:
        """
        获取概率分布直方图数据
        
        Returns:
            [{range_start, range_end, count, percentage}, ...]
        """
        if not result.returns_distribution:
            return []
        
        min_val = min(result.returns_distribution)
        max_val = max(result.returns_distribution)
        bucket_size = (max_val - min_val) / n_buckets
        
        buckets = []
        for i in range(n_buckets):
            start = min_val + i * bucket_size
            end = start + bucket_size
            count = sum(1 for r in result.returns_distribution if start <= r < end)
            buckets.append({
                "range_start": round(start, 2),
                "range_end": round(end, 2),
                "count": count,
                "percentage": round(count / result.n_simulations * 100, 2)
            })
        
        return buckets

    def get_confidence_intervals(
        self,
        result: SimulationResult
    ) -> Dict:
        """
        获取置信区间
        
        Returns:
            {confidence_level: (lower, upper), ...}
        """
        return {
            "90%": (result.percentile_5, result.percentile_95),
            "50%": (result.percentile_25, result.percentile_75),
            "most_likely": (result.percentile_25, result.percentile_75),
        }

    def get_summary(self, result: SimulationResult) -> Dict:
        """
        获取模拟摘要
        
        Returns:
            摘要字典
        """
        return {
            "simulation_type": result.simulation_type,
            "n_simulations": result.n_simulations,
            "n_periods": result.n_periods,
            "expected_return": f"{result.mean_return:.2f}%",
            "median_return": f"{result.median_return:.2f}%",
            "std_deviation": f"{result.std_return:.2f}%",
            "worst_case": f"{result.max_loss:.2f}%",
            "best_case": f"{result.max_gain:.2f}%",
            "var_95": f"{result.var_95:.2f}%",
            "cvar_95": f"{result.cvar_95:.2f}%",
            "win_probability": f"{result.win_rate:.1f}%",
            "confidence_90": f"[{result.percentile_5:.1f}%, {result.percentile_95:.1f}%]",
            "risk_rating": self._get_risk_rating(result)
        }

    def _get_risk_rating(self, result: SimulationResult) -> str:
        """风险评级"""
        # 基于 VaR 和胜率
        if result.var_95 < -20 or result.win_rate < 35:
            return "高风险"
        elif result.var_95 < -10 or result.win_rate < 45:
            return "中风险"
        elif result.var_95 < 0 or result.win_rate < 50:
            return "一般"
        else:
            return "低风险"


def run_monte_carlo_simulation(
    equity_curve: List[Dict],
    n_simulations: int = 1000,
    initial_capital: float = 100000
) -> SimulationResult:
    """
    便捷函数：运行蒙特卡洛模拟
    
    Args:
        equity_curve: 历史权益曲线
        n_simulations: 模拟次数
        initial_capital: 初始资金
    
    Returns:
        SimulationResult
    """
    simulator = MonteCarloSimulator(seed=42)
    return simulator.simulate(
        equity_curve=equity_curve,
        n_simulations=n_simulations,
        simulation_type=SimulationType.BOOTSTRAP,
        initial_capital=initial_capital
    )
