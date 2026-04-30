"""
数据库连接池模块
支持 PostgreSQL/MySQL + SQLAlchemy 连接池
"""

from typing import Optional, Dict, Any, List
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

# 延迟导入
_engine = None
_session_factory = None


@dataclass
class DBConfig:
    """数据库配置"""
    type: str = "sqlite"  # "sqlite", "postgresql", "mysql"
    host: str = "localhost"
    port: int = 5432
    database: str = "stock_quant.db"
    username: str = ""
    password: str = ""
    pool_size: int = 10  # 连接池大小
    max_overflow: int = 20  # 最大溢出连接
    pool_timeout: int = 30  # 获取连接超时
    pool_recycle: int = 3600  # 连接回收时间（秒）
    echo: bool = False  # 是否打印SQL


def get_engine(config: DBConfig = None):
    """获取数据库引擎（单例）"""
    global _engine
    
    if _engine is not None:
        return _engine
    
    if config is None:
        config = DBConfig()
    
    try:
        from sqlalchemy import create_engine, event
        from sqlalchemy.pool import QueuePool, NullPool
        
        if config.type == "sqlite":
            # SQLite 配置
            db_path = config.database
            # 添加foreign keys支持
            connection_args = {
                "check_same_thread": False,
            }
            _engine = create_engine(
                f"sqlite:///{db_path}",
                echo=config.echo,
                poolclass=QueuePool,
                pool_size=config.pool_size,
                max_overflow=config.max_overflow,
                pool_timeout=config.pool_timeout,
                pool_recycle=config.pool_recycle,
                connect_args=connection_args
            )
            
            @event.listens_for(_engine, "connect")
            def set_sqlite_pragma(dbapi_conn, connection_record):
                cursor = dbapi_conn.cursor()
                cursor.execute("PRAGMA foreign_keys=ON")
                cursor.execute("PRAGMA journal_mode=WAL")  # WAL 模式提升并发
                cursor.close()
                
        elif config.type == "postgresql":
            _engine = create_engine(
                f"postgresql://{config.username}:{config.password}@{config.host}:{config.port}/{config.database}",
                echo=config.echo,
                poolclass=QueuePool,
                pool_size=config.pool_size,
                max_overflow=config.max_overflow,
                pool_timeout=config.pool_timeout,
                pool_recycle=config.pool_recycle
            )
            
        elif config.type == "mysql":
            _engine = create_engine(
                f"mysql+pymysql://{config.username}:{config.password}@{config.host}:{config.port}/{config.database}",
                echo=config.echo,
                poolclass=QueuePool,
                pool_size=config.pool_size,
                max_overflow=config.max_overflow,
                pool_timeout=config.pool_timeout,
                pool_recycle=config.pool_recycle
            )
        
        logger.info(f"Database engine initialized: {config.type}")
        return _engine
        
    except ImportError as e:
        logger.warning(f"SQLAlchemy not installed, using fallback: {e}")
        return None
    except Exception as e:
        logger.error(f"Failed to create database engine: {e}")
        return None


def get_session():
    """获取数据库会话（用于当前线程）"""
    engine = get_engine()
    if engine is None:
        return None
    
    try:
        from sqlalchemy.orm import sessionmaker
        global _session_factory
        
        if _session_factory is None:
            _session_factory = sessionmaker(bind=engine)
        
        return _session_factory()
    except Exception as e:
        logger.error(f"Failed to create session: {e}")
        return None


@contextmanager
def session_scope():
    """
    数据库会话上下文管理器
    
    用法:
        with session_scope() as session:
            session.query(...)
    """
    session = get_session()
    if session is None:
        yield None
        return
    
    try:
        yield session
        session.commit()
    except Exception as e:
        session.rollback()
        logger.error(f"Session error: {e}")
        raise
    finally:
        session.close()


def init_database():
    """初始化数据库表结构"""
    engine = get_engine()
    if engine is None:
        logger.warning("No database engine, skipping init")
        return False
    
    try:
        from sqlalchemy import MetaData, Table, Column, Integer, String, Float, DateTime, Boolean, Text, JSON
        from sqlalchemy.orm import mapper
        
        metadata = MetaData()
        
        # 回测结果表
        backtest_results = Table(
            'backtest_results', metadata,
            Column('id', Integer, primary_key=True),
            Column('strategy_name', String(100)),
            Column('stock_code', String(20)),
            Column('start_date', String(20)),
            Column('end_date', String(20)),
            Column('initial_capital', Float),
            Column('final_capital', Float),
            Column('total_return', Float),
            Column('annual_return', Float),
            Column('sharpe_ratio', Float),
            Column('max_drawdown', Float),
            Column('win_rate', Float),
            Column('total_trades', Integer),
            Column('params', JSON),  # 策略参数
            Column('equity_curve', JSON),  # 权益曲线
            Column('trades', JSON),  # 交易记录
            Column('created_at', DateTime, default=datetime.now),
            Column('updated_at', DateTime, default=datetime.now, onupdate=datetime.now)
        )
        
        # 信号历史表
        signal_history = Table(
            'signal_history', metadata,
            Column('id', Integer, primary_key=True),
            Column('stock_code', String(20)),
            Column('signal_date', String(20)),
            Column('signal_type', String(20)),  # buy, sell, hold
            Column('signal_strength', Float),
            Column('price', Float),
            Column('indicators', JSON),
            Column('generated_at', DateTime, default=datetime.now)
        )
        
        # 持仓记录表
        positions = Table(
            'positions', metadata,
            Column('id', Integer, primary_key=True),
            Column('stock_code', String(20)),
            Column('quantity', Float),
            Column('avg_cost', Float),
            Column('current_price', Float),
            Column('market_value', Float),
            Column('profit_loss', Float),
            Column('profit_loss_ratio', Float),
            Column('updated_at', DateTime, default=datetime.now, onupdate=datetime.now)
        )
        
        # 缓存记录表（用于持久化热点数据）
        cache_entries = Table(
            'cache_entries', metadata,
            Column('id', Integer, primary_key=True),
            Column('cache_key', String(255), unique=True),
            Column('cache_value', Text),  # JSON 序列化
            Column('ttl_seconds', Integer),
            Column('created_at', DateTime, default=datetime.now),
            Column('expires_at', DateTime)
        )
        
        metadata.create_all(engine)
        logger.info("Database tables initialized")
        return True
        
    except Exception as e:
        logger.error(f"Failed to init database: {e}")
        return False


class BacktestResultRepository:
    """回测结果仓库"""

    def __init__(self):
        self._table_name = 'backtest_results'

    def save(self, result: Dict) -> bool:
        """保存回测结果"""
        try:
            with session_scope() as session:
                from sqlalchemy import insert
                from src.core.database.models import BacktestResult
                
                record = BacktestResult(
                    strategy_name=result.get('strategy_name'),
                    stock_code=result.get('stock_code'),
                    start_date=result.get('start_date'),
                    end_date=result.get('end_date'),
                    initial_capital=result.get('initial_capital'),
                    final_capital=result.get('final_capital'),
                    total_return=result.get('total_return'),
                    annual_return=result.get('annual_return'),
                    sharpe_ratio=result.get('sharpe_ratio'),
                    max_drawdown=result.get('max_drawdown'),
                    win_rate=result.get('win_rate'),
                    total_trades=result.get('total_trades'),
                    params=result.get('params'),
                    equity_curve=result.get('equity_curve'),
                    trades=result.get('trades')
                )
                session.add(record)
                session.flush()
                result['id'] = record.id
                return True
        except Exception as e:
            logger.error(f"Failed to save backtest result: {e}")
            return False

    def find_by_id(self, id: int) -> Optional[Dict]:
        """根据ID查询"""
        try:
            with session_scope() as session:
                from src.core.database.models import BacktestResult
                record = session.query(BacktestResult).filter_by(id=id).first()
                if record:
                    return self._to_dict(record)
                return None
        except Exception as e:
            logger.error(f"Failed to find backtest result: {e}")
            return None

    def find_by_stock(self, stock_code: str, limit: int = 10) -> List[Dict]:
        """查询某股票的回测历史"""
        try:
            with session_scope() as session:
                from src.core.database.models import BacktestResult
                records = session.query(BacktestResult)\
                    .filter_by(stock_code=stock_code)\
                    .order_by(BacktestResult.created_at.desc())\
                    .limit(limit)\
                    .all()
                return [self._to_dict(r) for r in records]
        except Exception as e:
            logger.error(f"Failed to find backtest results: {e}")
            return []

    def find_by_strategy(self, strategy_name: str, limit: int = 20) -> List[Dict]:
        """查询某策略的回测历史"""
        try:
            with session_scope() as session:
                from src.core.database.models import BacktestResult
                records = session.query(BacktestResult)\
                    .filter_by(strategy_name=strategy_name)\
                    .order_by(BacktestResult.total_return.desc())\
                    .limit(limit)\
                    .all()
                return [self._to_dict(r) for r in records]
        except Exception as e:
            logger.error(f"Failed to find backtest results: {e}")
            return []

    def _to_dict(self, record) -> Dict:
        """转换为字典"""
        return {
            'id': record.id,
            'strategy_name': record.strategy_name,
            'stock_code': record.stock_code,
            'start_date': record.start_date,
            'end_date': record.end_date,
            'initial_capital': record.initial_capital,
            'final_capital': record.final_capital,
            'total_return': record.total_return,
            'annual_return': record.annual_return,
            'sharpe_ratio': record.sharpe_ratio,
            'max_drawdown': record.max_drawdown,
            'win_rate': record.win_rate,
            'total_trades': record.total_trades,
            'params': record.params,
            'equity_curve': record.equity_curve,
            'trades': record.trades,
            'created_at': record.created_at.isoformat() if record.created_at else None
        }


def close_engine():
    """关闭数据库引擎"""
    global _engine, _session_factory
    
    if _engine:
        _engine.dispose()
        _engine = None
        _session_factory = None
        logger.info("Database engine closed")


def get_pool_status() -> Dict:
    """获取连接池状态"""
    engine = get_engine()
    if engine is None:
        return {"status": "not_initialized"}
    
    try:
        pool = engine.pool
        return {
            "pool_size": pool.size(),
            "checked_in": pool.checkedin(),
            "checked_out": pool.checkedout(),
            "overflow": pool.overflow(),
            "timeout": pool.timeout()
        }
    except Exception as e:
        logger.debug(f"Cannot get pool status: {e}")
        return {"status": "unknown"}