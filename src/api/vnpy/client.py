"""
VN.py 交易接口集成
用于实盘交易执行
"""

import os
import sys
from pathlib import Path
from typing import Optional, Dict, List
from datetime import datetime

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))


class VnpyClient:
    """VN.py 交易客户端"""
    
    def __init__(self):
        self.engine = None
        self.gateway = None
        self.connected = False
        
    def connect(self, gateway_name: str = 'ctp') -> bool:
        """
        连接交易接口
        
        Args:
            gateway_name: 交易接口名称
                - ctp: 期货CTP
                - futu: 港股富途
                - ib: 美股IB
                - tdx: 、通达信
                - xspeed: 极速交易
        
        Returns:
            是否连接成功
        """
        try:
            # 尝试导入vnpy
            from vnpy.trader.engine import MainEngine
            from vnpy.gateway.ctp import CtpGateway
            
            self.engine = MainEngine()
            
            # 根据gateway_name加载不同的交易接口
            if gateway_name == 'ctp':
                self.engine.add_gateway(CtpGateway, 'ctp')
                self.gateway = self.engine.get_gateway('ctp')
            
            self.connected = True
            return True
            
        except ImportError:
            print("Warning: vnpy not installed")
            return False
        except Exception as e:
            print(f"Error connecting to vnpy: {e}")
            return False
    
    def disconnect(self):
        """断开连接"""
        if self.engine:
            self.engine.close()
            self.connected = False
    
    def get_account(self) -> Optional[Dict]:
        """获取账户信息"""
        if not self.connected or not self.gateway:
            return None
        
        # 获取账户数据
        try:
            account_data = self.engine.get_all_account_data()
            if account_data:
                account = account_data[0]
                return {
                    'account_id': account.account_id,
                    'balance': account.balance,
                    'available': account.available,
                    'margin': account.margin,
                    'close_profit': account.close_profit,
                    'position_profit': account.position_profit,
                }
        except:
            pass
        
        return None
    
    def get_positions(self) -> List[Dict]:
        """获取持仓信息"""
        if not self.connected:
            return []
        
        try:
            positions = self.engine.get_all_position_data()
            return [{
                'symbol': p.symbol,
                'exchange': p.exchange,
                'volume': p.volume,
                'frozen': p.frozen,
                'price': p.price,
                'pnl': p.pnl,
            } for p in positions]
        except:
            pass
        
        return []
    
    def send_order(self, symbol: str, direction: str, price: float, volume: int, order_type: str = 'limit') -> Optional[str]:
        """
        发送订单
        
        Args:
            symbol: 合约代码 (如 'IF2106')
            direction: 方向 ('long' 或 'short')
            price: 价格
            volume: 数量
            order_type: 订单类型 ('limit' 或 'market')
        
        Returns:
            订单ID 或 None
        """
        if not self.connected:
            return None
        
        try:
            from vnpy.trader.constant import Direction, OrderType, Exchange
            
            # 转换方向
            if direction == 'long':
                dir_enum = Direction.LONG
            else:
                dir_enum = Direction.SHORT
            
            # 转换订单类型
            if order_type == 'market':
                type_enum = OrderType.MARKET
            else:
                type_enum = OrderType.LIMIT
            
            # 解析合约代码
            parts = symbol.split('.')
            vt_symbol = symbol
            
            # 发送委托
            vt_orderid = self.gateway.send_order(
                vt_symbol, dir_enum, type_enum, price, volume
            )
            
            return vt_orderid
            
        except Exception as e:
            print(f"Error sending order: {e}")
            return None
    
    def cancel_order(self, order_id: str) -> bool:
        """撤单"""
        if not self.connected:
            return False
        
        try:
            self.gateway.cancel_order(order_id)
            return True
        except:
            return False
    
    def get_orders(self) -> List[Dict]:
        """获取委托记录"""
        if not self.connected:
            return []
        
        try:
            orders = self.engine.get_all_order_data()
            return [{
                'order_id': o.orderid,
                'symbol': o.symbol,
                'direction': o.direction.value if hasattr(o.direction, 'value') else str(o.direction),
                'price': o.price,
                'volume': o.volume,
                'traded': o.traded,
                'status': o.status.value if hasattr(o.status, 'value') else str(o.status),
                'time': o.time,
            } for o in orders]
        except:
            pass
        
        return []
    
    def get_trades(self) -> List[Dict]:
        """获取成交记录"""
        if not self.connected:
            return []
        
        try:
            trades = self.engine.get_all_trade_data()
            return [{
                'trade_id': t.tradeid,
                'order_id': t.orderid,
                'symbol': t.symbol,
                'direction': t.direction.value if hasattr(t.direction, 'value') else str(t.direction),
                'price': t.price,
                'volume': t.volume,
                'time': t.time,
            } for t in trades]
        except:
            pass
        
        return []


class StockVnpyClient(VnpyClient):
    """股票交易客户端 (继承自VnpyClient)"""
    
    def __init__(self):
        super().__init__()
        self.gateway_name = 'stock'
        self._simulate_mode = True
        self._mock_orders = []
        self._mock_positions = []
        self._mock_account = {
            'account_id': 'SIM001',
            'balance': 1000000.0,
            'available': 1000000.0,
            'margin': 0.0,
            'close_profit': 0.0,
            'position_profit': 0.0,
        }
    
    def connect(self) -> bool:
        """连接股票交易接口（模拟模式）"""
        print("Stock trading: Simulation mode")
        self.connected = True
        return True
    
    def get_account(self):
        """获取模拟账户信息"""
        if self._simulate_mode and self.connected:
            return self._mock_account.copy()
        return None
    
    def get_positions(self):
        """获取模拟持仓"""
        if self._simulate_mode and self.connected:
            return self._mock_positions
        return []
    
    def send_order(self, symbol: str, direction: str, price: float, volume: int, order_type: str = 'limit') -> Optional[str]:
        """模拟下单"""
        if self._simulate_mode and self.connected:
            import uuid
            order_id = f"SIM_{uuid.uuid4().hex[:8]}"
            
            self._mock_orders.append({
                'order_id': order_id,
                'symbol': symbol,
                'direction': direction,
                'price': price,
                'volume': volume,
                'traded': 0,
                'status': 'submitting',
            })
            
            # 模拟成交
            self._mock_orders[-1]['status'] = 'all_traded'
            self._mock_orders[-1]['traded'] = volume
            
            # 更新持仓
            self._update_mock_position(symbol, direction, price, volume)
            
            return order_id
        return None
    
    def _update_mock_position(self, symbol: str, direction: str, price: float, volume: int):
        """更新模拟持仓"""
        for pos in self._mock_positions:
            if pos['symbol'] == symbol:
                if direction == 'long':
                    pos['volume'] += volume
                    pos['price'] = (pos['price'] * (pos['volume'] - volume) + price * volume) / pos['volume']
                else:
                    pos['volume'] -= volume
                return
        
        if direction == 'long':
            self._mock_positions.append({
                'symbol': symbol,
                'exchange': 'SSE',
                'volume': volume,
                'frozen': 0,
                'price': price,
                'pnl': 0.0,
            })
    
    def get_orders(self):
        """获取模拟委托"""
        if self._simulate_mode and self.connected:
            return self._mock_orders
        return []
    
    def cancel_order(self, order_id: str) -> bool:
        """模拟撤单"""
        if self._simulate_mode and self.connected:
            for order in self._mock_orders:
                if order['order_id'] == order_id and order['status'] == 'submitting':
                    order['status'] = 'cancelled'
                    return True
        return False


# 单例实例
_vnpy_client = None

def get_vnpy_client() -> VnpyClient:
    """获取VN.py客户端单例"""
    global _vnpy_client
    if _vnpy_client is None:
        _vnpy_client = VnpyClient()
    return _vnpy_client


def get_stock_client() -> StockVnpyClient:
    """获取股票交易客户端"""
    return StockVnpyClient()
