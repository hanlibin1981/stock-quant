"""
组合回测模块
支持多标的组合策略回测
"""

import pandas as pd
import numpy as np
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass, field
from itertools import combinations


@dataclass
class PortfolioComponent:
    """组合成分"""
    code: str
    name: str
    weight: float  # 权重 (0-1)
    data: pd.DataFrame = None  # 历史数据


@dataclass
class PortfolioBacktestResult:
    """组合回测结果"""
    # 组合整体收益
    total_return: float
    annual_return: float
    volatility: float
    sharpe_ratio: float
    max_drawdown: float
    
    # 成分分析
    component_returns: Dict[str, float]  # 各成分收益率
    component_weights: Dict[str, float]  # 最终权重
    correlation_matrix: Dict[str, Dict[str, float]]  # 相关性矩阵
    
    # 再平衡分析
    rebalance_count: int  # 再平衡次数
    final_weights: Dict[str, float]  # 最终权重
    
    # 风险贡献
    risk_contribution: Dict[str, float]  # 各成分风险贡献
    component_max_drawdown: Dict[str, float]  # 各成分最大回撤


class PortfolioBacktestEngine:
    """
    组合回测引擎
    
    支持：
    1. 多标的等权组合
    2. 多标的加权组合
    3. 动态再平衡
    4. 相关性分析
    5. 风险贡献分析
    """

    def __init__(self, initial_capital: float = 100000):
        """
        Args:
            initial_capital: 初始资金
        """
        self.initial_capital = initial_capital

    def run(
        self,
        components: List[PortfolioComponent],
        rebalance_period: int = 20,  # 再平衡周期（交易日）
        rebalance_threshold: float = 0.05,  # 再平衡阈值（权重偏离5%触发）
        min_periods: int = 30  # 最少历史数据要求
    ) -> PortfolioBacktestResult:
        """
        运行组合回测
        
        Args:
            components: 组合成分列表
            rebalance_period: 再平衡周期
            rebalance_threshold: 再平衡阈值
            min_periods: 最少历史数据要求
        
        Returns:
            PortfolioBacktestResult
        """
        if not components or len(components) == 0:
            return self._empty_result()
        
        # 过滤没有数据的成分
        valid_components = [c for c in components if c.data is not None and len(c.data) >= min_periods]
        if not valid_components:
            return self._empty_result()
        
        # 对齐数据到同一时间轴
        aligned_data = self._align_data(valid_components)
        if aligned_data.empty:
            return self._empty_result()
        
        n_components = len(valid_components)
        n_days = len(aligned_data)
        
        # 初始权重
        target_weights = {c.code: 1.0 / n_components for c in valid_components}
        current_weights = target_weights.copy()
        
        # 每日组合价值
        portfolio_values = [self.initial_capital]
        component_values = {c.code: [self.initial_capital * current_weights[c.code]] for c in valid_components}
        
        # 再平衡记录
        rebalance_count = 0
        
        # 回测循环
        for day_idx in range(1, n_days):
            day_weights = current_weights.copy()
            
            # 更新各成分价值
            for component in valid_components:
                col_name = component.code
                if col_name in aligned_data.columns:
                    daily_return = aligned_data[col_name].iloc[day_idx] if not pd.isna(aligned_data[col_name].iloc[day_idx]) else 0
                    prev_value = component_values[component.code][-1]
                    new_value = prev_value * (1 + daily_return)
                    component_values[component.code].append(new_value)
                else:
                    component_values[component.code].append(component_values[component.code][-1])
            
            # 检查是否需要再平衡
            need_rebalance = False
            total_portfolio = sum(component_values[c.code][-1] for c in valid_components)
            
            if rebalance_count == 0 or (day_idx % rebalance_period == 0):
                need_rebalance = True
            else:
                # 检查权重偏离
                for c in valid_components:
                    current_w = component_values[c.code][-1] / total_portfolio
                    target_w = target_weights[c.code]
                    if abs(current_w - target_w) > rebalance_threshold:
                        need_rebalance = True
                        break
            
            if need_rebalance and total_portfolio > 0:
                # 再平衡
                new_weights = {}
                for c in valid_components:
                    new_weights[c.code] = target_weights[c.code]
                
                # 按目标权重分配
                for c in valid_components:
                    current_weights[c.code] = new_weights[c.code]
                
                rebalance_count += 1
            
            # 计算组合总价值
            portfolio_value = sum(component_values[c.code][-1] for c in valid_components)
            portfolio_values.append(portfolio_value)
        
        # 计算收益率
        portfolio_series = pd.Series(portfolio_values)
        daily_returns = portfolio_series.pct_change().replace([np.inf, -np.inf], np.nan).dropna()
        
        # 组合指标
        end_capital = portfolio_values[-1]
        total_return = (end_capital / self.initial_capital - 1) * 100
        annual_return = (((end_capital / self.initial_capital) ** (365.0 / max(n_days, 1))) - 1.0) * 100.0
        volatility = daily_returns.std() * np.sqrt(252) * 100
        sharpe = self._calc_sharpe(daily_returns)
        
        # 最大回撤
        running_peak = portfolio_series.cummax()
        drawdown = ((running_peak - portfolio_series) / running_peak).fillna(0) * 100
        max_drawdown = drawdown.max()
        
        # 各成分收益率
        component_returns = {}
        for c in valid_components:
            initial = self.initial_capital * target_weights[c.code]
            final = component_values[c.code][-1]
            component_returns[c.code] = (final / initial - 1) * 100 if initial > 0 else 0
        
        # 最终权重
        total_final = sum(component_values[c.code][-1] for c in valid_components)
        final_weights = {c.code: component_values[c.code][-1] / total_final for c in valid_components}
        
        # 相关性矩阵
        correlation_matrix = self._calc_correlation_matrix(aligned_data, valid_components)
        
        # 各成分最大回撤
        component_max_drawdown = {}
        for c in valid_components:
            values = pd.Series(component_values[c.code])
            peak = values.cummax()
            dd = ((peak - values) / peak).fillna(0) * 100
            component_max_drawdown[c.code] = dd.max()
        
        # 风险贡献（简化版：按权重和波动率计算）
        risk_contribution = self._calc_risk_contribution(
            aligned_data, valid_components, target_weights
        )
        
        return PortfolioBacktestResult(
            total_return=total_return,
            annual_return=annual_return,
            volatility=volatility,
            sharpe_ratio=sharpe,
            max_drawdown=max_drawdown,
            component_returns=component_returns,
            component_weights=final_weights,
            correlation_matrix=correlation_matrix,
            rebalance_count=rebalance_count,
            final_weights=final_weights,
            risk_contribution=risk_contribution,
            component_max_drawdown=component_max_drawdown
        )

    def _align_data(self, components: List[PortfolioComponent]) -> pd.DataFrame:
        """对齐所有成分数据到同一时间轴"""
        if not components:
            return pd.DataFrame()
        
        # 以第一个成分为基准
        base_data = components[0].data.copy()
        if 'date' in base_data.columns:
            base_data['date'] = pd.to_datetime(base_data['date'])
            base_data = base_data.set_index('date')
        
        result = pd.DataFrame(index=base_data.index)
        
        for component in components:
            df = component.data.copy()
            if 'date' in df.columns:
                df['date'] = pd.to_datetime(df['date'])
                df = df.set_index('date')
            
            # 计算每日收益率
            if 'close' in df.columns:
                returns = df['close'].pct_change()
            else:
                continue
            
            result[component.code] = returns
        
        return result.dropna(how='all')

    def _calc_sharpe(self, daily_returns: pd.Series) -> float:
        """计算夏普比率"""
        if len(daily_returns) < 2 or daily_returns.std() == 0:
            return 0.0
        return float(daily_returns.mean() / daily_returns.std() * np.sqrt(252))

    def _calc_correlation_matrix(
        self,
        aligned_data: pd.DataFrame,
        components: List[PortfolioComponent]
    ) -> Dict[str, Dict[str, float]]:
        """计算相关性矩阵"""
        corr_matrix = {}
        codes = [c.code for c in components if c.code in aligned_data.columns]
        
        for code1 in codes:
            corr_matrix[code1] = {}
            for code2 in codes:
                if code1 == code2:
                    corr_matrix[code1][code2] = 1.0
                else:
                    corr = aligned_data[code1].corr(aligned_data[code2])
                    corr_matrix[code1][code2] = float(corr) if not pd.isna(corr) else 0.0
        
        return corr_matrix

    def _calc_risk_contribution(
        self,
        aligned_data: pd.DataFrame,
        components: List[PortfolioComponent],
        weights: Dict[str, float]
    ) -> Dict[str, float]:
        """计算各成分的风险贡献"""
        risk_contrib = {}
        total_variance = 0.0
        component_volatilities = {}
        
        codes = [c.code for c in components if c.code in aligned_data.columns]
        
        # 计算各成分波动率
        for code in codes:
            vol = aligned_data[code].std() * np.sqrt(252) if len(aligned_data) > 1 else 0
            component_volatilities[code] = vol
            total_variance += vol ** 2
        
        total_vol = np.sqrt(total_variance) if total_variance > 0 else 1
        
        # 简化版风险贡献：波动率 * 权重
        for code in codes:
            vol = component_volatilities.get(code, 0)
            w = weights.get(code, 0)
            # 风险贡献 = 权重 * 波动率 / 总波动率
            risk_contrib[code] = round(w * vol / total_vol * 100, 2) if total_vol > 0 else 0
        
        return risk_contrib

    def _empty_result(self) -> PortfolioBacktestResult:
        """返回空结果"""
        return PortfolioBacktestResult(
            total_return=0, annual_return=0, volatility=0,
            sharpe_ratio=0, max_drawdown=0,
            component_returns={}, component_weights={},
            correlation_matrix={}, rebalance_count=0,
            final_weights={}, risk_contribution={}, component_max_drawdown={}
        )

    def find_optimal_weights(
        self,
        components: List[PortfolioComponent],
        target_volatility: float = 0.15,
        min_weight: float = 0.05,
        max_weight: float = 0.5
    ) -> Dict[str, float]:
        """
        简化版最优权重计算（基于风险平价）
        
        Args:
            components: 组合成分
            target_volatility: 目标波动率
            min_weight: 最小权重
            max_weight: 最大权重
        
        Returns:
            最优权重字典
        """
        if not components:
            return {}
        
        valid_components = [c for c in components if c.data is not None and len(c.data) >= 30]
        if not valid_components:
            return {}
        
        # 对齐数据
        aligned_data = self._align_data(valid_components)
        if aligned_data.empty:
            return {}
        
        # 计算各成分波动率
        volatilities = {}
        for code in aligned_data.columns:
            vol = aligned_data[code].std() * np.sqrt(252)
            volatilities[code] = vol if vol > 0 else 0.01
        
        # 风险平价：各成分对组合风险的贡献相等
        # weight_i = target_vol / volatility_i
        total_inverse_vol = sum(1 / v for v in volatilities.values())
        
        optimal_weights = {}
        for code, vol in volatilities.items():
            weight = target_volatility / vol / total_inverse_vol if vol > 0 else 0
            # 限制在 min-max 范围内
            optimal_weights[code] = max(min_weight, min(max_weight, weight))
        
        # 归一化
        total = sum(optimal_weights.values())
        if total > 0:
            optimal_weights = {k: v / total for k, v in optimal_weights.items()}
        
        return optimal_weights

    def get_summary(self, result: PortfolioBacktestResult) -> Dict:
        """获取组合回测摘要"""
        return {
            "total_return": f"{result.total_return:.2f}%",
            "annual_return": f"{result.annual_return:.2f}%",
            "volatility": f"{result.volatility:.2f}%",
            "sharpe_ratio": f"{result.sharpe_ratio:.2f}",
            "max_drawdown": f"{result.max_drawdown:.2f}%",
            "rebalance_count": result.rebalance_count,
            "top_performer": max(result.component_returns.items(), key=lambda x: x[1])[0] if result.component_returns else None,
            "worst_performer": min(result.component_returns.items(), key=lambda x: x[1])[0] if result.component_returns else None,
        }


def run_portfolio_backtest(
    stock_data: Dict[str, pd.DataFrame],
    weights: Dict[str, float] = None,
    initial_capital: float = 100000
) -> PortfolioBacktestResult:
    """
    便捷函数：运行组合回测
    
    Args:
        stock_data: {code: DataFrame} 股票数据字典
        weights: {code: weight} 权重字典，None则为等权
        initial_capital: 初始资金
    
    Returns:
        PortfolioBacktestResult
    """
    components = []
    
    if weights:
        for code, df in stock_data.items():
            w = weights.get(code, 1.0 / len(stock_data))
            components.append(PortfolioComponent(
                code=code,
                name=code,
                weight=w,
                data=df
            ))
    else:
        equal_weight = 1.0 / len(stock_data)
        for code, df in stock_data.items():
            components.append(PortfolioComponent(
                code=code,
                name=code,
                weight=equal_weight,
                data=df
            ))
    
    engine = PortfolioBacktestEngine(initial_capital=initial_capital)
    return engine.run(components)
