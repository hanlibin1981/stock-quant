"""
风控管理模块
实盘风控：止损、止盈、仓位管理
"""

import pandas as pd
import numpy as np
from typing import Dict, List, Optional, Tuple, Callable
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
import logging

logger = logging.getLogger(__name__)


class RiskLevel(Enum):
    """风险等级"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class OrderSide(Enum):
    """交易方向"""
    BUY = "buy"
    SELL = "sell"


@dataclass
class Position:
    """持仓信息"""
    code: str
    quantity: float  # 持仓数量
    avg_cost: float  # 平均成本
    current_price: float  # 当前价格
    market_value: float  # 市值

    @property
    def profit_loss(self) -> float:
        """浮动盈亏"""
        return (self.current_price - self.avg_cost) * self.quantity

    @property
    def profit_loss_ratio(self) -> float:
        """盈亏比例"""
        cost = self.avg_cost * self.quantity
        if cost == 0:
            return 0.0
        return self.profit_loss / cost * 100


@dataclass
class RiskRule:
    """风控规则"""
    name: str
    enabled: bool = True
    priority: int = 0  # 优先级，数字越小优先级越高


@dataclass
class StopLossRule(RiskRule):
    """止损规则"""
    type: str = "fixed"  # "fixed" 固定百分比, "trailing" 跟踪止损
    threshold: float = 7.0  # 止损阈值（百分比）
    trailing_distance: float = 5.0  # 跟踪止损距离（百分比）
    activation_profit: float = 3.0  # 激活跟踪止损的利润门槛（百分比）


@dataclass
class TakeProfitRule(RiskRule):
    """止盈规则"""
    type: str = "fixed"  # "fixed" 固定比例, "分段止盈"
    threshold: float = 15.0  # 止盈阈值（百分比）
    trailing_enabled: bool = False
    trailing_distance: float = 8.0


@dataclass
class PositionSizingRule(RiskRule):
    """仓位管理规则"""
    max_position_per_stock: float = 0.2  # 单只股票最大仓位比例
    max_total_position: float = 0.95  # 总仓位上限
    min_position_per_trade: float = 0.01  # 最小买入比例


@dataclass
class RiskCheckResult:
    """风控检查结果"""
    allowed: bool
    blocked_reason: str = ""
    risk_level: RiskLevel = RiskLevel.LOW
    suggestions: List[str] = field(default_factory=list)
    adjusted_quantity: float = None  # 调整后的数量


class RiskManager:
    """
    风控管理器
    
    功能：
    1. 止损/止盈管理
    2. 仓位控制
    3. 风险敞口监控
    4. 自动平仓触发
    """

    def __init__(
        self,
        total_capital: float = 100000,
        stop_loss_rule: StopLossRule = None,
        take_profit_rule: TakeProfitRule = None,
        position_rule: PositionSizingRule = None
    ):
        """
        Args:
            total_capital: 总资金
            stop_loss_rule: 止损规则
            take_profit_rule: 止盈规则
            position_rule: 仓位规则
        """
        self.total_capital = total_capital
        self.stop_loss_rule = stop_loss_rule or StopLossRule()
        self.take_profit_rule = take_profit_rule or TakeProfitRule()
        self.position_rule = position_rule or PositionSizingRule()
        
        self._positions: Dict[str, Position] = {}
        self._peak_equity = total_capital  # 最高权益（用于跟踪止损）
        self._peak_prices: Dict[str, float] = {}  # 各持仓的最高价

    def update_position(
        self,
        code: str,
        quantity: float,
        avg_cost: float,
        current_price: float
    ):
        """更新持仓信息"""
        if quantity <= 0:
            if code in self._positions:
                del self._positions[code]
            if code in self._peak_prices:
                del self._peak_prices[code]
            return
        
        market_value = quantity * current_price
        self._positions[code] = Position(
            code=code,
            quantity=quantity,
            avg_cost=avg_cost,
            current_price=current_price,
            market_value=market_value
        )
        
        # 更新最高价（用于跟踪止损）
        if code not in self._peak_prices:
            self._peak_prices[code] = current_price
        else:
            self._peak_prices[code] = max(self._peak_prices[code], current_price)
        
        # 更新最高权益
        self._peak_equity = max(self._peak_equity, self.get_total_equity())

    def get_position(self, code: str) -> Optional[Position]:
        """获取持仓"""
        return self._positions.get(code)

    def get_all_positions(self) -> List[Position]:
        """获取所有持仓"""
        return list(self._positions.values())

    def get_total_equity(self) -> float:
        """获取总权益"""
        positions_value = sum(p.market_value for p in self._positions.values())
        cash = self.total_capital - sum(p.avg_cost * p.quantity for p in self._positions.values())
        return positions_value + cash

    def check_buy(
        self,
        code: str,
        quantity: float,
        price: float,
        current_positions: Dict[str, Position] = None
    ) -> RiskCheckResult:
        """
        检查买入是否允许
        
        Args:
            code: 股票代码
            quantity: 买入数量
            price: 买入价格
            current_positions: 当前持仓（可选，默认使用内部持仓）
        
        Returns:
            RiskCheckResult
        """
        if quantity <= 0:
            return RiskCheckResult(
                allowed=False,
                blocked_reason="Quantity must be positive"
            )

        positions = current_positions or self._positions
        order_value = quantity * price
        
        # 检查单只股票仓位限制
        current_position = positions.get(code)
        current_quantity = current_position.quantity if current_position else 0
        new_total_quantity = current_quantity + quantity
        total_capital = self.get_total_equity()
        
        # 计算当前该股票总市值
        current_value = current_quantity * (current_position.current_price if current_position else price)
        new_value = new_total_quantity * price
        
        stock_ratio = new_value / total_capital if total_capital > 0 else 0
        
        if stock_ratio > self.position_rule.max_position_per_stock:
            max_quantity = (total_capital * self.position_rule.max_position_per_stock) / price
            return RiskCheckResult(
                allowed=True,
                risk_level=RiskLevel.MEDIUM,
                blocked_reason=f"单只股票仓位超限 ({stock_ratio*100:.1f}% > {self.position_rule.max_position_per_stock*100}%)",
                adjusted_quantity=max_quantity,
                suggestions=[f"建议买入数量: {max_quantity:.0f}股"]
            )

        # 检查总仓位限制
        total_position_value = sum(p.avg_cost * p.quantity for p in positions.values())
        current_cash = total_capital - total_position_value
        
        if order_value > current_cash:
            max_affordable = current_cash / price
            return RiskCheckResult(
                allowed=True,
                risk_level=RiskLevel.MEDIUM,
                blocked_reason=f"资金不足 (需要 ¥{order_value:.2f}, 可用 ¥{current_cash:.2f})",
                adjusted_quantity=max_affordable,
                suggestions=[f"建议买入数量: {max_affordable:.0f}股"]
            )
        
        # 检查最小买入比例
        if quantity / (total_capital / price) < self.position_rule.min_position_per_trade:
            return RiskCheckResult(
                allowed=False,
                blocked_reason=f"买入数量过小 (占比 {quantity * price / total_capital * 100:.2f}% < {self.position_rule.min_position_per_trade * 100}%)",
                risk_level=RiskLevel.HIGH
            )
        
        return RiskCheckResult(allowed=True)

    def check_sell(
        self,
        code: str,
        quantity: float,
        current_positions: Dict[str, Position] = None
    ) -> RiskCheckResult:
        """
        检查卖出是否允许
        
        Args:
            code: 股票代码
            quantity: 卖出数量
            current_positions: 当前持仓
        
        Returns:
            RiskCheckResult
        """
        if quantity <= 0:
            return RiskCheckResult(allowed=False, blocked_reason="Quantity must be positive")
        
        positions = current_positions or self._positions
        position = positions.get(code)
        
        if not position:
            return RiskCheckResult(
                allowed=False,
                blocked_reason=f"无持仓: {code}"
            )
        
        if quantity > position.quantity:
            return RiskCheckResult(
                allowed=True,
                blocked_reason=f"卖出数量超过持仓 (持仓 {position.quantity}, 卖出 {quantity})",
                adjusted_quantity=position.quantity,
                suggestions=[f"建议卖出数量: {position.quantity:.0f}股"]
            )
        
        return RiskCheckResult(allowed=True)

    def should_stop_loss(self, code: str) -> Tuple[bool, str]:
        """
        检查是否应该止损
        
        Args:
            code: 股票代码
        
        Returns:
            (是否止损, 原因)
        """
        position = self._positions.get(code)
        if not position:
            return False, ""
        
        rule = self.stop_loss_rule
        if not rule.enabled:
            return False, ""
        
        peak_price = self._peak_prices.get(code, position.avg_cost)
        
        if rule.type == "fixed":
            # 固定止损
            loss_ratio = (position.current_price - position.avg_cost) / position.avg_cost * 100
            
            if loss_ratio <= -rule.threshold:
                return True, f"固定止损触发 (亏损 {loss_ratio:.1f}% > -{rule.threshold}%)"
        
        elif rule.type == "trailing":
            # 跟踪止损
            current_profit_ratio = (position.current_price - position.avg_cost) / position.avg_cost * 100
            
            # 检查是否已盈利到激活门槛
            if current_profit_ratio >= rule.activation_profit:
                # 计算从最高点的回撤
                drawdown_from_peak = (peak_price - position.current_price) / peak_price * 100
                
                if drawdown_from_peak >= rule.trailing_distance:
                    return True, f"跟踪止损触发 (从峰值回撤 {drawdown_from_peak:.1f}% > {rule.trailing_distance}%)"
        
        return False, ""

    def should_take_profit(self, code: str) -> Tuple[bool, str]:
        """
        检查是否应该止盈
        
        Args:
            code: 股票代码
        
        Returns:
            (是否止盈, 原因)
        """
        position = self._positions.get(code)
        if not position:
            return False, ""
        
        rule = self.take_profit_rule
        if not rule.enabled:
            return False, ""
        
        profit_ratio = (position.current_price - position.avg_cost) / position.avg_cost * 100
        
        if rule.type == "fixed":
            if profit_ratio >= rule.threshold:
                return True, f"固定止盈触发 (盈利 {profit_ratio:.1f}% >= {rule.threshold}%)"
        
        elif rule.trailing_enabled:
            # 跟踪止盈
            peak_price = self._peak_prices.get(code, position.current_price)
            drawdown = (peak_price - position.current_price) / peak_price * 100
            
            if drawdown >= rule.trailing_distance:
                return True, f"跟踪止盈触发 (从峰值回撤 {drawdown:.1f}% >= {rule.trailing_distance}%)"
        
        return False, ""

    def get_portfolio_risk(self) -> Dict:
        """
        获取组合风险状况
        
        Returns:
            风险报告
        """
        total_equity = self.get_total_equity()
        positions_value = sum(p.market_value for p in self._positions.values())
        
        # 计算总仓位
        total_position_ratio = positions_value / total_equity if total_equity > 0 else 0
        
        # 找出风险最大的持仓
        risk_signals = []
        for code, position in self._positions.items():
            profit_ratio = position.profit_loss_ratio
            
            # 止损信号
            should_stop, reason = self.should_stop_loss(code)
            if should_stop:
                risk_signals.append({
                    "code": code,
                    "type": "stop_loss",
                    "reason": reason,
                    "profit_ratio": profit_ratio
                })
            
            # 止盈信号
            should_profit, reason = self.should_take_profit(code)
            if should_profit:
                risk_signals.append({
                    "code": code,
                    "type": "take_profit",
                    "reason": reason,
                    "profit_ratio": profit_ratio
                })
        
        # 风险等级评估
        if total_position_ratio > 0.9:
            risk_level = RiskLevel.CRITICAL
        elif total_position_ratio > 0.8:
            risk_level = RiskLevel.HIGH
        elif len(self._positions) > 10:
            risk_level = RiskLevel.MEDIUM
        else:
            risk_level = RiskLevel.LOW
        
        return {
            "total_equity": round(total_equity, 2),
            "positions_value": round(positions_value, 2),
            "cash": round(total_equity - positions_value, 2),
            "total_position_ratio": round(total_position_ratio * 100, 2),
            "position_count": len(self._positions),
            "risk_level": risk_level.value,
            "risk_signals": risk_signals,
            "peak_equity": round(self._peak_equity, 2),
            "max_drawdown_from_peak": round((total_equity - self._peak_equity) / self._peak_equity * 100, 2) if self._peak_equity > 0 else 0
        }

    def force_close_all(self) -> List[Tuple[str, float, str]]:
        """
        强制平仓所有持仓
        
        Returns:
            [(code, quantity, reason), ...]
        """
        close_orders = []
        
        for code, position in list(self._positions.items()):
            # 优先平亏损的
            if position.profit_loss < 0:
                close_orders.append((code, position.quantity, "风险控制强制平仓"))
        
        # 再平盈利的
        for code, position in list(self._positions.items()):
            if position not in [p for p, _, _ in close_orders]:
                close_orders.append((code, position.quantity, "风险控制强制平仓"))
        
        return close_orders

    def reset(self):
        """重置风控状态（用于新回测周期）"""
        self._positions.clear()
        self._peak_prices.clear()
        self._peak_equity = self.total_capital