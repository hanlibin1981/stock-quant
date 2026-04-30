"""
持仓同步模块
从券商API同步实盘持仓
"""

import pandas as pd
import numpy as np
from typing import Dict, List, Optional, Tuple, Callable
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from abc import ABC, abstractmethod
import logging

logger = logging.getLogger(__name__)


class PositionSource(Enum):
    """持仓来源"""
    MANUAL = "manual"  # 手动录入
    BROKER_API = "broker_api"  # 券商API
    BACKTEST = "backtest"  # 回测模拟


@dataclass
class Position:
    """持仓信息"""
    code: str
    name: str = ""
    quantity: float = 0.0
    avg_cost: float = 0.0  # 买入均价
    current_price: float = 0.0
    market_value: float = 0.0
    profit_loss: float = 0.0
    profit_loss_ratio: float = 0.0
    today_change: float = 0.0  # 今日涨跌
    source: PositionSource = PositionSource.MANUAL
    last_updated: datetime = field(default_factory=datetime.now)
    
    def update_price(self, price: float):
        """更新价格"""
        self.current_price = price
        self.market_value = self.quantity * price
        self.profit_loss = (price - self.avg_cost) * self.quantity
        if self.avg_cost > 0:
            self.profit_loss_ratio = (price - self.avg_cost) / self.avg_cost * 100
        self.last_updated = datetime.now()
    
    def update_from_trade(self, quantity: float, price: float, is_buy: bool):
        """
        根据交易更新持仓
        
        Args:
            quantity: 交易数量
            price: 交易价格
            is_buy: 是否买入
        """
        if is_buy:
            # 买入：增加持仓
            total_cost = self.avg_cost * self.quantity + price * quantity
            self.quantity += quantity
            self.avg_cost = total_cost / self.quantity if self.quantity > 0 else 0
        else:
            # 卖出：减少持仓
            self.quantity -= min(quantity, self.quantity)
            if self.quantity == 0:
                self.avg_cost = 0
        
        self.update_price(price)


@dataclass
class PositionSyncConfig:
    """持仓同步配置"""
    broker_type: str = "simulated"  # simulated, futu, tora, xq
    api_key: str = ""
    api_secret: str = ""
    enable_auto_sync: bool = False
    sync_interval_seconds: int = 60
    cache_enabled: bool = True


class BrokerConnector(ABC):
    """券商连接器抽象基类"""
    
    @abstractmethod
    def connect(self) -> bool:
        """连接券商"""
        pass
    
    @abstractmethod
    def get_positions(self) -> List[Dict]:
        """获取持仓列表"""
        pass
    
    @abstractmethod
    def get_account_info(self) -> Dict:
        """获取账户信息"""
        pass
    
    @abstractmethod
    def place_order(self, code: str, quantity: int, price: float, side: str) -> Dict:
        """下单"""
        pass
    
    @abstractmethod
    def get_orders(self, status: str = None) -> List[Dict]:
        """获取订单列表"""
        pass


class SimulatedBroker(BrokerConnector):
    """模拟券商（用于测试）"""
    
    def __init__(self):
        self._positions = {}
        self._cash = 100000.0
        self._orders = []
    
    def connect(self) -> bool:
        logger.info("Simulated broker connected")
        return True
    
    def get_positions(self) -> List[Dict]:
        return [
            {
                "code": code,
                "name": self._get_stock_name(code),
                "quantity": pos.quantity,
                "avg_cost": pos.avg_cost,
                "current_price": pos.current_price,
                "market_value": pos.market_value,
                "profit_loss": pos.profit_loss,
                "profit_loss_ratio": pos.profit_loss_ratio
            }
            for code, pos in self._positions.items()
        ]
    
    def get_account_info(self) -> Dict:
        total_value = sum(p.market_value for p in self._positions.values())
        return {
            "cash": self._cash,
            "total_assets": self._cash + total_value,
            "positions_value": total_value,
            "position_count": len(self._positions)
        }
    
    def place_order(self, code: str, quantity: int, price: float, side: str) -> Dict:
        order_id = f"ORDER_{len(self._orders) + 1}_{datetime.now().strftime('%Y%m%d%H%M%S')}"
        
        order = {
            "order_id": order_id,
            "code": code,
            "quantity": quantity,
            "price": price,
            "side": side,
            "status": "pending",
            "filled_quantity": 0,
            "created_at": datetime.now().isoformat()
        }
        self._orders.append(order)
        
        # 模拟成交
        if side == "buy" and self._cash >= price * quantity:
            self._cash -= price * quantity
            if code in self._positions:
                self._positions[code].update_from_trade(quantity, price, True)
            else:
                pos = Position(code=code)
                pos.update_from_trade(quantity, price, True)
                pos.name = self._get_stock_name(code)
                self._positions[code] = pos
            
            order["status"] = "filled"
            order["filled_quantity"] = quantity
        
        elif side == "sell":
            if code in self._positions and self._positions[code].quantity >= quantity:
                self._cash += price * quantity
                self._positions[code].update_from_trade(quantity, price, False)
                
                order["status"] = "filled"
                order["filled_quantity"] = quantity
        
        return order
    
    def get_orders(self, status: str = None) -> List[Dict]:
        if status:
            return [o for o in self._orders if o["status"] == status]
        return self._orders
    
    def _get_stock_name(self, code: str) -> str:
        # 简化的股票名称映射
        names = {
            "000001": "平安银行",
            "000002": "万科A",
            "600000": "浦发银行",
            "600036": "招商银行",
            "000858": "五粮液"
        }
        return names.get(code, f"股票{code}")


class PositionSyncManager:
    """
    持仓同步管理器
    
    功能：
    1. 从多个券商API同步持仓
    2. 持仓数据缓存和去重
    3. 与回测持仓对比
    4. 信号与实盘联动
    """

    def __init__(self, config: PositionSyncConfig = None):
        self.config = config or PositionSyncConfig()
        self._brokers: Dict[str, BrokerConnector] = {}
        self._positions: Dict[str, Position] = {}
        self._last_sync: Dict[str, datetime] = {}
        self._cache: Dict[str, any] = {}
        self._sync_listeners: List[Callable] = []
        
        self._init_broker()

    def _init_broker(self):
        """初始化券商连接"""
        if self.config.broker_type == "simulated":
            self._brokers["simulated"] = SimulatedBroker()
            self._brokers["simulated"].connect()
        elif self.config.broker_type == "futu":
            # TODO: 实现富途连接
            logger.warning("Futu broker not implemented yet")
        elif self.config.broker_type == "xq":
            # TODO: 实现雪球连接
            logger.warning("Xueqiu broker not implemented yet")
    
    def sync_positions(self, broker_name: str = "simulated") -> List[Position]:
        """
        同步持仓
        
        Args:
            broker_name: 券商名称
        
        Returns:
            持仓列表
        """
        broker = self._brokers.get(broker_name)
        if not broker:
            logger.error(f"Broker not found: {broker_name}")
            return []
        
        try:
            positions_data = broker.get_positions()
            
            # 转换为 Position 对象
            self._positions.clear()
            for data in positions_data:
                pos = Position(
                    code=data["code"],
                    name=data.get("name", ""),
                    quantity=data["quantity"],
                    avg_cost=data["avg_cost"],
                    current_price=data["current_price"],
                    market_value=data.get("market_value", 0),
                    profit_loss=data.get("profit_loss", 0),
                    profit_loss_ratio=data.get("profit_loss_ratio", 0),
                    source=PositionSource.BROKER_API
                )
                self._positions[data["code"]] = pos
            
            self._last_sync[broker_name] = datetime.now()
            
            # 通知监听器
            self._notify_sync()
            
            logger.info(f"Synced {len(self._positions)} positions from {broker_name}")
            return list(self._positions.values())
            
        except Exception as e:
            logger.error(f"Failed to sync positions: {e}")
            return list(self._positions.values())

    def get_positions(self) -> List[Position]:
        """获取所有持仓"""
        return list(self._positions.values())

    def get_position(self, code: str) -> Optional[Position]:
        """获取指定持仓"""
        return self._positions.get(code)

    def get_total_assets(self) -> float:
        """获取总资产"""
        broker = list(self._brokers.values())[0] if self._brokers else None
        if broker:
            try:
                return broker.get_account_info()["total_assets"]
            except Exception:
                pass
        
        # fallback: 计算持仓市值 + 现金
        positions_value = sum(p.market_value for p in self._positions.values())
        return positions_value

    def get_cash(self) -> float:
        """获取可用资金"""
        broker = list(self._brokers.values())[0] if self._brokers else None
        if broker:
            try:
                return broker.get_account_info()["cash"]
            except Exception:
                pass
        return 0.0

    def can_buy(self, code: str, quantity: int, price: float) -> Tuple[bool, str]:
        """
        检查是否可以买入
        
        Returns:
            (是否可买入, 原因)
        """
        total_cost = quantity * price
        cash = self.get_cash()
        
        if total_cost > cash:
            return False, f"资金不足: 需要 ¥{total_cost:.2f}, 可用 ¥{cash:.2f}"
        
        # 检查仓位限制
        position = self._positions.get(code)
        if position:
            new_total_value = sum(p.market_value for p in self._positions.values()) + total_cost
            total_assets = self.get_total_assets()
            position_ratio = (position.market_value + total_cost) / total_assets if total_assets > 0 else 0
            
            if position_ratio > 0.3:  # 单只股票最大30%
                return False, f"单只股票仓位超限: {position_ratio*100:.1f}% > 30%"
        
        return True, ""

    def place_buy_order(self, code: str, quantity: int, price: float = None) -> Optional[Dict]:
        """
        下买入单
        
        Args:
            code: 股票代码
            quantity: 数量
            price: 价格（None=市价）
        
        Returns:
            订单结果
        """
        can_buy, reason = self.can_buy(code, quantity, price or 0)
        if not can_buy:
            logger.warning(f"Cannot buy {code}: {reason}")
            return {"success": False, "reason": reason}
        
        broker = list(self._brokers.values())[0]
        order = broker.place_order(code, quantity, price or 0, "buy")
        
        if order.get("status") == "filled":
            self.sync_positions()  # 同步持仓
        
        return {"success": True, "order": order}

    def place_sell_order(self, code: str, quantity: int, price: float = None) -> Optional[Dict]:
        """
        下卖出单
        
        Args:
            code: 股票代码
            quantity: 数量
            price: 价格（None=市价）
        
        Returns:
            订单结果
        """
        position = self._positions.get(code)
        if not position:
            return {"success": False, "reason": f"无持仓: {code}"}
        
        if position.quantity < quantity:
            return {"success": False, "reason": f"持仓不足: 持有{position.quantity}, 卖出{quantity}"}
        
        broker = list(self._brokers.values())[0]
        order = broker.place_order(code, quantity, price or 0, "sell")
        
        if order.get("status") == "filled":
            self.sync_positions()
        
        return {"success": True, "order": order}

    def compare_with_backtest(self, backtest_positions: Dict[str, Position]) -> Dict:
        """
        与回测持仓对比
        
        Args:
            backtest_positions: 回测持仓字典
        
        Returns:
            对比报告
        """
        real_codes = set(self._positions.keys())
        backtest_codes = set(backtest_positions.keys())
        
        common = real_codes & backtest_codes
        only_real = real_codes - backtest_codes
        only_backtest = backtest_codes - real_codes
        
        differences = []
        for code in common:
            real = self._positions[code]
            backtest = backtest_positions[code]
            
            qty_diff = real.quantity - backtest.quantity
            cost_diff = real.avg_cost - backtest.avg_cost
            
            if abs(qty_diff) > 0.01 or abs(cost_diff) > 0.01:
                differences.append({
                    "code": code,
                    "real_qty": real.quantity,
                    "backtest_qty": backtest.quantity,
                    "qty_diff": qty_diff,
                    "real_cost": real.avg_cost,
                    "backtest_cost": backtest.avg_cost,
                    "cost_diff": cost_diff
                })
        
        return {
            "common_count": len(common),
            "only_real_count": len(only_real),
            "only_backtest_count": len(only_backtest),
            "differences": differences,
            "match_ratio": len(common) / max(len(real_codes | backtest_codes), 1)
        }

    def update_prices(self, price_data: Dict[str, float]):
        """
        批量更新持仓价格
        
        Args:
            price_data: {code: price}
        """
        for code, price in price_data.items():
            if code in self._positions:
                self._positions[code].update_price(price)

    def add_sync_listener(self, listener: Callable):
        """添加同步监听器"""
        self._sync_listeners.append(listener)

    def _notify_sync(self):
        """通知所有监听器"""
        for listener in self._sync_listeners:
            try:
                listener(self._positions)
            except Exception as e:
                logger.error(f"Sync listener error: {e}")

    def get_summary(self) -> Dict:
        """获取持仓摘要"""
        positions = list(self._positions.values())
        
        if not positions:
            return {
                "total_assets": 0,
                "positions_value": 0,
                "cash": 0,
                "position_count": 0,
                "total_profit_loss": 0,
                "best_position": None,
                "worst_position": None
            }
        
        total_profit = sum(p.profit_loss for p in positions)
        best = max(positions, key=lambda x: x.profit_loss_ratio)
        worst = min(positions, key=lambda x: x.profit_loss_ratio)
        
        return {
            "total_assets": self.get_total_assets(),
            "positions_value": sum(p.market_value for p in positions),
            "cash": self.get_cash(),
            "position_count": len(positions),
            "total_profit_loss": total_profit,
            "best_position": {"code": best.code, "profit_ratio": best.profit_loss_ratio},
            "worst_position": {"code": worst.code, "profit_ratio": worst.profit_loss_ratio}
        }


# 全局持仓管理器
_global_sync_manager: Optional[PositionSyncManager] = None


def get_position_sync_manager(config: PositionSyncConfig = None) -> PositionSyncManager:
    """获取全局持仓同步管理器"""
    global _global_sync_manager
    
    if _global_sync_manager is None:
        _global_sync_manager = PositionSyncManager(config)
    
    return _global_sync_manager


def init_position_sync(config: PositionSyncConfig) -> PositionSyncManager:
    """初始化持仓同步（带配置）"""
    global _global_sync_manager
    
    _global_sync_manager = PositionSyncManager(config)
    return _global_sync_manager