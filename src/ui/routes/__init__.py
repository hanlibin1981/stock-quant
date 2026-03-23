"""
Web 路由模块
按功能域划分的 Flask 路由
"""

from .data import data_bp
from .backtest import backtest_bp
from .trading import trading_bp
from .signal import signal_bp

__all__ = ['data_bp', 'backtest_bp', 'trading_bp', 'signal_bp']
