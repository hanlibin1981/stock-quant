"""
增强风险指标模块
添加 Omega 比率、kappa 统计量等高级风险指标
"""

import pandas as pd
import numpy as np
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass


@dataclass
class EnhancedRiskMetrics:
    """增强版风险指标"""
    # 基础指标
    total_return: float
    annual_return: float
    volatility: float
    max_drawdown: float
    
    # 风险调整收益
    sharpe_ratio: float
    sortino_ratio: float
    calmar_ratio: float
    omega_ratio: float  # 新增
    
    # 盈利分析
    win_rate: float
    avg_profit: float
    avg_loss: float
    profit_factor: float
    
    # 分布指标
    skewness: float  # 偏度
    kurtosis: float  # 峰度
    var_95: float  # 95% VaR
    cvar_95: float  # 95% CVaR (Expected Shortfall)
    
    # 高频指标
    daily_loss_probability: float  # 日亏损概率
    avg_consecutive_losses: float  # 平均连续亏损次数
    max_consecutive_losses: int  # 最大连续亏损次数
    recovery_factor: float  # 恢复因子
    
    # 尾部指标
    tail_ratio: float  # 尾部比率
    gain_to_pain_ratio: float  # 痛苦比率


class EnhancedRiskAnalyzer:
    """
    增强版风险分析器
    
    计算高级风险指标：
    - Omega 比率
    - VaR / CVaR
    - 偏度和峰度
    - 尾部比率
    - 连续亏损分析
    """

    def __init__(self, risk_free_rate: float = 0.03):
        """
        Args:
            risk_free_rate: 无风险利率（年化），默认 3%
        """
        self.risk_free_rate = risk_free_rate

    def analyze(
        self,
        equity_curve: List[Dict],
        trades: List[Dict],
        initial_capital: float = 100000
    ) -> EnhancedRiskMetrics:
        """
        分析风险指标
        
        Args:
            equity_curve: 每日权益曲线 [{date, equity}]
            trades: 交易记录 [{date, profit, entry_price, exit_price}]
            initial_capital: 初始资金
        
        Returns:
            增强版风险指标
        """
        if not equity_curve or len(equity_curve) < 2:
            return self._empty_metrics()

        equity_series = pd.Series([point["equity"] for point in equity_curve], dtype=float)
        dates = pd.to_datetime([point["date"] for point in equity_curve])
        
        # 基础计算
        end_capital = float(equity_series.iloc[-1])
        total_return = ((end_capital / initial_capital) - 1) * 100 if initial_capital > 0 else 0.0
        total_days = max((dates[-1] - dates[0]).days, 1)
        annual_return = (((end_capital / initial_capital) ** (365 / total_days) - 1) * 100 
                        if initial_capital > 0 and end_capital > 0 else 0.0)
        
        # 日收益率
        daily_returns = equity_series.pct_change().replace([np.inf, -np.inf], np.nan).dropna()
        volatility = float(daily_returns.std() * np.sqrt(252) * 100) if len(daily_returns) > 1 else 0.0
        
        # 最大回撤
        running_peak = equity_series.cummax().replace(0, np.nan)
        drawdown = ((running_peak - equity_series) / running_peak).fillna(0) * 100
        max_drawdown = float(drawdown.max()) if not drawdown.empty else 0.0
        
        # 风险调整收益
        sharpe = self._calc_sharpe(daily_returns)
        sortino = self._calc_sortino(daily_returns)
        calmar = annual_return / max_drawdown if max_drawdown > 0.01 else 0.0
        omega = self._calc_omega(daily_returns)
        
        # 交易统计
        total_trades = len(trades)
        winning_trades = sum(1 for t in trades if t["profit"] > 0)
        losing_trades = sum(1 for t in trades if t["profit"] <= 0)
        win_rate = (winning_trades / total_trades * 100) if total_trades > 0 else 0.0
        
        profits = [t["profit"] for t in trades if t["profit"] > 0]
        losses = [t["profit"] for t in trades if t["profit"] <= 0]
        avg_profit = float(np.mean(profits)) if profits else 0.0
        avg_loss = float(np.mean(losses)) if losses else 0.0
        
        total_profit_sum = float(sum(profits)) if profits else 0.0
        total_loss_sum = float(abs(sum(losses))) if losses else 0.0
        profit_factor = (total_profit_sum / total_loss_sum) if total_loss_sum > 0 else 0.0
        
        # 分布指标
        skewness = float(daily_returns.skew()) if len(daily_returns) > 2 else 0.0
        kurtosis = float(daily_returns.kurt()) if len(daily_returns) > 3 else 0.0
        
        # VaR / CVaR
        var_95, cvar_95 = self._calc_var_cvar(daily_returns, confidence=0.95)
        
        # 连续亏损分析
        daily_loss_prob, avg_consec_loss, max_consec_loss = self._calc_consecutive_losses(daily_returns)
        
        # 恢复因子
        recovery_factor = total_return / max_drawdown if max_drawdown > 0.01 else 0.0
        
        # 尾部比率
        tail_ratio = self._calc_tail_ratio(daily_returns)
        
        # 痛苦比率
        gain_to_pain = self._calc_gain_to_pain_ratio(trades)
        
        return EnhancedRiskMetrics(
            total_return=total_return,
            annual_return=annual_return,
            volatility=volatility,
            max_drawdown=max_drawdown,
            sharpe_ratio=sharpe,
            sortino_ratio=sortino,
            calmar_ratio=calmar,
            omega_ratio=omega,
            win_rate=win_rate,
            avg_profit=avg_profit,
            avg_loss=avg_loss,
            profit_factor=profit_factor,
            skewness=skewness,
            kurtosis=kurtosis,
            var_95=var_95,
            cvar_95=cvar_95,
            daily_loss_probability=daily_loss_prob,
            avg_consecutive_losses=avg_consec_loss,
            max_consecutive_losses=max_consec_loss,
            recovery_factor=recovery_factor,
            tail_ratio=tail_ratio,
            gain_to_pain_ratio=gain_to_pain
        )

    def _empty_metrics(self) -> EnhancedRiskMetrics:
        """返回空指标"""
        return EnhancedRiskMetrics(
            total_return=0, annual_return=0, volatility=0, max_drawdown=0,
            sharpe_ratio=0, sortino_ratio=0, calmar_ratio=0, omega_ratio=0,
            win_rate=0, avg_profit=0, avg_loss=0, profit_factor=0,
            skewness=0, kurtosis=0, var_95=0, cvar_95=0,
            daily_loss_probability=0, avg_consecutive_losses=0,
            max_consecutive_losses=0, recovery_factor=0,
            tail_ratio=0, gain_to_pain_ratio=0
        )

    def _calc_sharpe(self, daily_returns: pd.Series) -> float:
        """计算夏普比率"""
        if len(daily_returns) < 2 or daily_returns.std(ddof=0) == 0:
            return 0.0
        daily_rf = self.risk_free_rate / 252
        excess_returns = daily_returns - daily_rf
        return float(excess_returns.mean() / daily_returns.std(ddof=0) * np.sqrt(252))

    def _calc_sortino(self, daily_returns: pd.Series) -> float:
        """计算索提诺比率"""
        if len(daily_returns) < 2:
            return 0.0
        daily_rf = self.risk_free_rate / 252
        excess_returns = daily_returns - daily_rf
        negative_returns = excess_returns[excess_returns < 0]
        if len(negative_returns) < 2 or negative_returns.std(ddof=0) == 0:
            return 0.0
        return float(excess_returns.mean() / negative_returns.std(ddof=0) * np.sqrt(252))

    def _calc_omega(self, daily_returns: pd.Series) -> float:
        """
        计算 Omega 比率
        
        Omega = (收益之和 for returns > threshold) / (|损失之和| for returns < threshold)
        
        默认 threshold = 0
        """
        if len(daily_returns) < 2:
            return 0.0
        
        gains = daily_returns[daily_returns > 0].sum()
        losses = abs(daily_returns[daily_returns < 0].sum())
        
        if losses == 0:
            return float('inf') if gains > 0 else 0.0
        
        return float(gains / losses)

    def _calc_var_cvar(self, daily_returns: pd.Series, confidence: float = 0.95) -> Tuple[float, float]:
        """
        计算 VaR 和 CVaR (Expected Shortfall)
        
        VaR: 在 confidence 置信度下的最大损失
        CVaR: VaR 条件下的平均损失（尾部期望）
        """
        if len(daily_returns) < 10:
            return 0.0, 0.0
        
        sorted_returns = daily_returns.sort_values()
        var_index = int(len(sorted_returns) * (1 - confidence))
        var = float(sorted_returns.iloc[var_index]) if var_index < len(sorted_returns) else 0.0
        
        # CVaR: VaR 尾部的平均
        tail_returns = sorted_returns.iloc[:var_index + 1]
        cvar = float(tail_returns.mean()) if len(tail_returns) > 0 else var
        
        return var, cvar

    def _calc_consecutive_losses(
        self, daily_returns: pd.Series
    ) -> Tuple[float, float, int]:
        """
        计算连续亏损统计
        
        Returns:
            (日亏损概率, 平均连续亏损次数, 最大连续亏损次数)
        """
        if len(daily_returns) < 2:
            return 0.0, 0.0, 0
        
        # 日亏损概率
        loss_count = (daily_returns < 0).sum()
        loss_prob = float(loss_count / len(daily_returns) * 100)
        
        # 连续亏损
        is_loss = (daily_returns < 0).astype(int).values
        consecutive_losses = []
        current_streak = 0
        
        for val in is_loss:
            if val == 1:
                current_streak += 1
            else:
                if current_streak > 0:
                    consecutive_losses.append(current_streak)
                current_streak = 0
        
        if current_streak > 0:
            consecutive_losses.append(current_streak)
        
        avg_consec = float(np.mean(consecutive_losses)) if consecutive_losses else 0.0
        max_consec = max(consecutive_losses) if consecutive_losses else 0
        
        return loss_prob, avg_consec, max_consec

    def _calc_tail_ratio(self, daily_returns: pd.Series) -> float:
        """
        计算尾部比率
        
        tail_ratio = (95th percentile returns) / (5th percentile returns)
        
        用于衡量收益分布的非对称性
        """
        if len(daily_returns) < 20:
            return 0.0
        
        sorted_returns = daily_returns.sort_values()
        upper_95 = sorted_returns.iloc[int(len(sorted_returns) * 0.95)]
        lower_5 = sorted_returns.iloc[int(len(sorted_returns) * 0.05)]
        
        if abs(lower_5) < 1e-10:
            return 0.0
        
        return float(upper_95 / abs(lower_5))

    def _calc_gain_to_pain_ratio(self, trades: List[Dict]) -> float:
        """
        计算痛苦比率 (Gain-to-Pain Ratio)
        
        = 总收益 / 总亏损（亏损取绝对值）
        
        类似于 profit_factor，但是考虑所有交易的总收益/总亏损
        """
        if not trades:
            return 0.0
        
        total_gain = sum(t["profit"] for t in trades if t["profit"] > 0)
        total_loss = abs(sum(t["profit"] for t in trades if t["profit"] < 0))
        
        if total_loss == 0:
            return float('inf') if total_gain > 0 else 0.0
        
        return float(total_gain / total_loss)

    def get_risk_summary(self, metrics: EnhancedRiskMetrics) -> Dict:
        """
        获取风险摘要
        
        Returns:
            风险等级和描述
        """
        # 综合评分
        score = 0.0
        
        # 夏普比率得分 (0-100, >2 优秀, >1.5 良好, >1 及格)
        if metrics.sharpe_ratio > 2:
            score += 30
        elif metrics.sharpe_ratio > 1.5:
            score += 20
        elif metrics.sharpe_ratio > 1:
            score += 10
        
        # Omega 比率得分 (>1.5 优秀, >1.2 良好, >1 及格)
        if metrics.omega_ratio > 1.5:
            score += 20
        elif metrics.omega_ratio > 1.2:
            score += 15
        elif metrics.omega_ratio > 1:
            score += 10
        
        # 最大回撤得分 (<10% 优秀, <15% 良好, <20% 及格)
        if metrics.max_drawdown < 10:
            score += 25
        elif metrics.max_drawdown < 15:
            score += 15
        elif metrics.max_drawdown < 20:
            score += 10
        
        # 盈利概率得分
        if metrics.win_rate > 60:
            score += 15
        elif metrics.win_rate > 50:
            score += 10
        
        # VaR 得分 (<2% 优秀, <3% 良好, <5% 及格)
        if abs(metrics.var_95) < 0.02:
            score += 10
        elif abs(metrics.var_95) < 0.03:
            score += 5
        
        # 风险等级
        if score >= 80:
            risk_level = "A"
            risk_desc = "优秀"
        elif score >= 60:
            risk_level = "B"
            risk_desc = "良好"
        elif score >= 40:
            risk_level = "C"
            risk_desc = "一般"
        else:
            risk_level = "D"
            risk_desc = "较差"
        
        return {
            "score": min(score, 100),
            "risk_level": risk_level,
            "risk_description": risk_desc,
            "metrics": metrics
        }


def analyze_risk(
    equity_curve: List[Dict],
    trades: List[Dict],
    initial_capital: float = 100000
) -> Dict:
    """
    便捷函数：风险分析
    
    Args:
        equity_curve: 每日权益曲线
        trades: 交易记录
        initial_capital: 初始资金
    
    Returns:
        风险分析结果
    """
    analyzer = EnhancedRiskAnalyzer()
    metrics = analyzer.analyze(equity_curve, trades, initial_capital)
    return analyzer.get_risk_summary(metrics)
