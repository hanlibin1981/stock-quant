"""
数据库模块

包含：
- connection_pool: 数据库连接池管理
- models: SQLAlchemy ORM 模型
"""

from src.core.database.connection_pool import (
    get_engine,
    get_session,
    session_scope,
    init_database,
    BacktestResultRepository,
    close_engine,
    get_pool_status,
    DBConfig
)

from src.core.database.models import (
    Base,
    BacktestResult,
    SignalHistory,
    Position,
    CacheEntry,
    OptimizationTask,
    Portfolio
)

__all__ = [
    # connection_pool
    'get_engine',
    'get_session',
    'session_scope',
    'init_database',
    'BacktestResultRepository',
    'close_engine',
    'get_pool_status',
    'DBConfig',
    # models
    'Base',
    'BacktestResult',
    'SignalHistory',
    'Position',
    'CacheEntry',
    'OptimizationTask',
    'Portfolio'
]