"""
数据库模型定义
SQLAlchemy ORM 模型
"""

from sqlalchemy import Column, Integer, String, Float, DateTime, Boolean, Text, JSON, Date
from sqlalchemy.ext.declarative import declarative_base
from datetime import datetime

Base = declarative_base()


class BacktestResult(Base):
    """回测结果模型"""
    __tablename__ = 'backtest_results'

    id = Column(Integer, primary_key=True, autoincrement=True)
    strategy_name = Column(String(100), nullable=False, index=True)
    stock_code = Column(String(20), nullable=False, index=True)
    start_date = Column(String(20), nullable=False)
    end_date = Column(String(20), nullable=False)
    
    # 收益指标
    initial_capital = Column(Float, nullable=False)
    final_capital = Column(Float, nullable=False)
    total_return = Column(Float)  # 总收益率%
    annual_return = Column(Float)  # 年化收益率%
    sharpe_ratio = Column(Float)  # 夏普比率
    max_drawdown = Column(Float)  # 最大回撤%
    calmar_ratio = Column(Float)  # 卡玛比率
    
    # 交易统计
    win_rate = Column(Float)  # 胜率%
    profit_factor = Column(Float)  # 盈利因子
    total_trades = Column(Integer)  # 总交易次数
    avg_trade_return = Column(Float)  # 平均交易收益%
    
    # 参数和详细数据
    params = Column(JSON)  # 策略参数
    equity_curve = Column(JSON)  # 权益曲线
    trades = Column(JSON)  # 交易记录列表
    statistics = Column(JSON)  # 额外统计信息
    
    created_at = Column(DateTime, default=datetime.now, nullable=False)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)

    def __repr__(self):
        return f"<BacktestResult(id={self.id}, strategy={self.strategy_name}, stock={self.stock_code}, return={self.total_return:.2f}%)>"

    def to_dict(self):
        """转换为字典"""
        return {
            'id': self.id,
            'strategy_name': self.strategy_name,
            'stock_code': self.stock_code,
            'start_date': self.start_date,
            'end_date': self.end_date,
            'initial_capital': self.initial_capital,
            'final_capital': self.final_capital,
            'total_return': self.total_return,
            'annual_return': self.annual_return,
            'sharpe_ratio': self.sharpe_ratio,
            'max_drawdown': self.max_drawdown,
            'calmar_ratio': self.calmar_ratio,
            'win_rate': self.win_rate,
            'profit_factor': self.profit_factor,
            'total_trades': self.total_trades,
            'avg_trade_return': self.avg_trade_return,
            'params': self.params,
            'equity_curve': self.equity_curve,
            'trades': self.trades,
            'statistics': self.statistics,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }


class SignalHistory(Base):
    """信号历史模型"""
    __tablename__ = 'signal_history'

    id = Column(Integer, primary_key=True, autoincrement=True)
    stock_code = Column(String(20), nullable=False, index=True)
    signal_date = Column(String(20), nullable=False)
    signal_type = Column(String(20), nullable=False, index=True)  # buy, sell, hold
    signal_strength = Column(Float)  # 信号强度 0-100
    price = Column(Float)  # 信号发生时价格
    
    # 指标详情
    indicators = Column(JSON)
    
    # 信号来源
    source = Column(String(50))  # generator, manual, ml
    
    # 信号评估
    outcome = Column(String(20))  # pending, success, failed
    actual_return = Column(Float)  # 信号发出后的实际收益%
    
    generated_at = Column(DateTime, default=datetime.now, nullable=False)
    evaluated_at = Column(DateTime)

    def __repr__(self):
        return f"<SignalHistory(id={self.id}, stock={self.stock_code}, type={self.signal_type}, date={self.signal_date})>"

    def to_dict(self):
        return {
            'id': self.id,
            'stock_code': self.stock_code,
            'signal_date': self.signal_date,
            'signal_type': self.signal_type,
            'signal_strength': self.signal_strength,
            'price': self.price,
            'indicators': self.indicators,
            'source': self.source,
            'outcome': self.outcome,
            'actual_return': self.actual_return,
            'generated_at': self.generated_at.isoformat() if self.generated_at else None,
            'evaluated_at': self.evaluated_at.isoformat() if self.evaluated_at else None
        }


class Position(Base):
    """持仓记录模型"""
    __tablename__ = 'positions'

    id = Column(Integer, primary_key=True, autoincrement=True)
    stock_code = Column(String(20), nullable=False, unique=True, index=True)
    stock_name = Column(String(100))
    
    quantity = Column(Float, nullable=False)
    avg_cost = Column(Float, nullable=False)  # 平均成本
    current_price = Column(Float)
    market_value = Column(Float)
    
    profit_loss = Column(Float)  # 浮动盈亏
    profit_loss_ratio = Column(Float)  # 盈亏比例%
    
    # 来源
    source = Column(String(50))  # manual, sync, backtest
    
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)

    def __repr__(self):
        return f"<Position(stock={self.stock_code}, qty={self.quantity}, p/l={self.profit_loss:.2f})>"

    def to_dict(self):
        return {
            'id': self.id,
            'stock_code': self.stock_code,
            'stock_name': self.stock_name,
            'quantity': self.quantity,
            'avg_cost': self.avg_cost,
            'current_price': self.current_price,
            'market_value': self.market_value,
            'profit_loss': self.profit_loss,
            'profit_loss_ratio': self.profit_loss_ratio,
            'source': self.source,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }


class CacheEntry(Base):
    """缓存记录模型（用于持久化热点数据）"""
    __tablename__ = 'cache_entries'

    id = Column(Integer, primary_key=True, autoincrement=True)
    cache_key = Column(String(255), nullable=False, unique=True, index=True)
    cache_value = Column(Text, nullable=False)  # JSON 序列化
    ttl_seconds = Column(Integer)
    hit_count = Column(Integer, default=0)  # 命中次数统计
    
    created_at = Column(DateTime, default=datetime.now, nullable=False)
    expires_at = Column(DateTime, index=True)

    def __repr__(self):
        return f"<CacheEntry(key={self.cache_key}, ttl={self.ttl_seconds}s)>"

    def is_expired(self) -> bool:
        """检查是否过期"""
        if self.expires_at is None:
            return False
        return datetime.now() > self.expires_at


class OptimizationTask(Base):
    """参数优化任务模型"""
    __tablename__ = 'optimization_tasks'

    id = Column(Integer, primary_key=True, autoincrement=True)
    strategy_name = Column(String(100), nullable=False, index=True)
    stock_code = Column(String(20))
    
    # 参数空间
    param_space = Column(JSON)  # 参数空间定义
    
    # 优化配置
    algorithm = Column(String(50))  # grid_search, genetic, bayesian
    max_iterations = Column(Integer)
    
    # 结果
    best_params = Column(JSON)
    best_score = Column(Float)
    all_results = Column(JSON)
    
    status = Column(String(20))  # pending, running, completed, failed
    error_message = Column(Text)
    
    started_at = Column(DateTime)
    completed_at = Column(DateTime)
    created_at = Column(DateTime, default=datetime.now, nullable=False)

    def __repr__(self):
        return f"<OptimizationTask(id={self.id}, strategy={self.strategy_name}, status={self.status})>"

    def to_dict(self):
        return {
            'id': self.id,
            'strategy_name': self.strategy_name,
            'stock_code': self.stock_code,
            'param_space': self.param_space,
            'algorithm': self.algorithm,
            'max_iterations': self.max_iterations,
            'best_params': self.best_params,
            'best_score': self.best_score,
            'status': self.status,
            'error_message': self.error_message,
            'started_at': self.started_at.isoformat() if self.started_at else None,
            'completed_at': self.completed_at.isoformat() if self.completed_at else None
        }


class Portfolio(Base):
    """组合持仓模型"""
    __tablename__ = 'portfolios'

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), nullable=False)
    description = Column(Text)
    
    # 组合配置
    initial_capital = Column(Float, nullable=False)
    positions = Column(JSON)  # [{code, weight, ...}]
    
    # 风险配置
    max_position_ratio = Column(Float)  # 最大仓位比例
    stop_loss_threshold = Column(Float)  # 止损阈值%
    take_profit_threshold = Column(Float)  # 止盈阈值%
    
    created_at = Column(DateTime, default=datetime.now, nullable=False)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)

    def __repr__(self):
        return f"<Portfolio(id={self.id}, name={self.name}, capital={self.initial_capital})>"