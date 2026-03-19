"""
模拟交易客户端
用于测试和演示，不涉及真实资金
"""

import uuid
from datetime import datetime
from typing import Dict, List, Optional


class MockTradeClient:
    """模拟交易客户端"""
    
    def __init__(self):
        self.connected = True
        self.orders = {}  # order_id -> order info
        self.positions = {}  # symbol -> position info
        self.trades = {}  # trade_id -> trade info
        self.balance = 1000000.0  # 模拟资金 100万
        
    def send_order(self, symbol: str, direction: str, price: float, 
                   volume: int, order_type: str = 'limit') -> str:
        """发送订单"""
        order_id = f"MOCK_{uuid.uuid4().hex[:8].upper()}"
        
        order = {
            'order_id': order_id,
            'symbol': symbol,
            'direction': direction,  # long / short
            'price': price,
            'volume': volume,
            'traded': 0,
            'status': 'submitting',
            'type': order_type,
            'time': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }
        
        self.orders[order_id] = order
        
        # 模拟成交（立即成交）
        self._simulate_fill(order_id)
        
        return order_id
    
    def _simulate_fill(self, order_id: str):
        """模拟成交"""
        order = self.orders.get(order_id)
        if not order:
            return
            
        trade_id = f"TRADE_{uuid.uuid4().hex[:8].upper()}"
        trade = {
            'trade_id': trade_id,
            'order_id': order_id,
            'symbol': order['symbol'],
            'direction': order['direction'],
            'price': order['price'],
            'volume': order['volume'],
            'time': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }
        
        self.trades[trade_id] = trade
        order['status'] = 'all_traded'
        order['traded'] = order['volume']
        
        # 更新持仓
        self._update_position(order['symbol'], order['direction'], 
                             order['price'], order['volume'])
    
    def _update_position(self, symbol: str, direction: str, price: float, volume: int):
        """更新持仓"""
        if symbol not in self.positions:
            self.positions[symbol] = {
                'symbol': symbol,
                'volume': 0,
                'cost': 0,
                'pnl': 0
            }
        
        pos = self.positions[symbol]
        
        if direction == 'long':
            # 买入
            old_cost = pos['cost']
            old_vol = pos['volume']
            new_vol = old_vol + volume
            
            if old_vol > 0:
                pos['cost'] = (old_cost + price * volume) / new_vol
            else:
                pos['cost'] = price
            
            pos['volume'] = new_vol
        else:
            # 卖出
            pos['volume'] -= volume
            if pos['volume'] < 0:
                pos['volume'] = 0
                pos['cost'] = 0
    
    def cancel_order(self, order_id: str) -> bool:
        """撤单"""
        if order_id in self.orders:
            order = self.orders[order_id]
            if order['status'] in ['submitting', 'not_traded']:
                order['status'] = 'cancelled'
                return True
        return False
    
    def get_orders(self) -> List[Dict]:
        """获取委托列表"""
        return list(self.orders.values())
    
    def get_positions(self) -> List[Dict]:
        """获取持仓列表"""
        return [p for p in self.positions.values() if p['volume'] > 0]
    
    def get_trades(self) -> List[Dict]:
        """获取成交列表"""
        return list(self.trades.values())
    
    def get_balance(self) -> Dict:
        """获取账户资金"""
        # 计算持仓市值
        position_value = sum(
            p['volume'] * p['cost'] for p in self.positions.values()
        )
        
        return {
            'balance': self.balance,
            'position_value': position_value,
            'total': self.balance + position_value
        }
    
    def disconnect(self) -> bool:
        """断开连接"""
        self.connected = False
        return True


# 全局实例
_mock_trade_client = None

def get_mock_trade_client() -> MockTradeClient:
    """获取模拟交易客户端实例"""
    global _mock_trade_client
    if _mock_trade_client is None:
        _mock_trade_client = MockTradeClient()
    return _mock_trade_client
