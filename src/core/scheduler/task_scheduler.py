"""
任务调度模块
支持定时任务、周期任务、异步任务队列
"""

import threading
import time
from typing import Callable, Dict, List, Optional, Any
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from abc import ABC, abstractmethod
import logging
import asyncio

logger = logging.getLogger(__name__)


class TaskStatus(Enum):
    """任务状态"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class TaskType(Enum):
    """任务类型"""
    ONE_TIME = "one_time"      # 单次执行
    CRON = "cron"              # Cron表达式
    INTERVAL = "interval"      # 固定间隔


@dataclass
class ScheduledTask:
    """调度任务"""
    name: str
    func: Callable
    task_type: TaskType
    status: TaskStatus = TaskStatus.PENDING
    
    # 触发条件
    trigger_time: datetime = None  # 一次性任务触发时间
    interval_seconds: int = None  # 间隔任务的间隔
    cron_expr: str = None         # Cron表达式
    
    # 配置
    enabled: bool = True
    max_retries: int = 3
    timeout_seconds: int = 300
    
    # 结果
    last_run: datetime = None
    last_result: Any = None
    last_error: str = None
    run_count: int = 0
    
    # 元数据
    description: str = ""
    tags: List[str] = field(default_factory=list)


@dataclass
class TaskResult:
    """任务执行结果"""
    task_name: str
    status: TaskStatus
    start_time: datetime
    end_time: datetime
    duration_ms: float
    result: Any = None
    error: str = None


class SlippageModel(ABC):
    """滑点模型基类"""
    
    @abstractmethod
    def calculate(self, order_price: float, volume: float, current_volume: float = None) -> float:
        """计算滑点后的成交价格"""
        pass


class FixedSlippage(SlippageModel):
    """固定滑点模型"""
    
    def __init__(self, slippage_ratio: float = 0.001):
        """
        Args:
            slippage_ratio: 滑点比例 (默认0.1% = 千分之一)
        """
        self.slippage_ratio = slippage_ratio
    
    def calculate(self, order_price: float, volume: float, current_volume: float = None) -> float:
        """固定滑点：成交价格 = 委托价格 * (1 ± 滑点比例)"""
        slippage = order_price * self.slippage_ratio
        # 买入向上滑，卖出向下滑
        return order_price + slippage


class VolumeSlippage(SlippageModel):
    """成交量比例滑点模型"""
    
    def __init__(
        self,
        base_slippage: float = 0.0005,
        volume_sensitivity: float = 0.1,
        max_slippage: float = 0.01
    ):
        """
        Args:
            base_slippage: 基础滑点比例
            volume_sensitivity: 成交量敏感度
            max_slippage: 最大滑点比例
        """
        self.base_slippage = base_slippage
        self.volume_sensitivity = volume_sensitivity
        self.max_slippage = max_slippage
    
    def calculate(self, order_price: float, volume: float, current_volume: float = None) -> float:
        """成交量滑点：根据委托量占市场份额计算滑点"""
        if current_volume is None or current_volume == 0:
            volume_ratio = 0
        else:
            volume_ratio = volume / current_volume
        
        # 滑点 = 基础滑点 + 成交量敏感度 * 成交量占比
        slippage_ratio = min(
            self.base_slippage + self.volume_sensitivity * volume_ratio,
            self.max_slippage
        )
        
        return order_price * (1 + slippage_ratio)


class PercentileSlippage(SlippageModel):
    """分位数滑点模型（基于历史数据）"""
    
    def __init__(
        self,
        price_history: List[float] = None,
        slippage_percentile: float = 95
    ):
        """
        Args:
            price_history: 历史价格列表
            slippage_percentile: 滑点分位数 (95表示95%的情况下滑点在X%以内)
        """
        self.price_history = price_history or []
        self.slippage_percentile = slippage_percentile / 100.0
    
    def calculate(self, order_price: float, volume: float, current_volume: float = None) -> float:
        """分位数滑点：基于历史价格波动率"""
        if len(self.price_history) < 10:
            return order_price
        
        # 计算历史收益率的标准差
        returns = []
        for i in range(1, len(self.price_history)):
            ret = (self.price_history[i] - self.price_history[i-1]) / self.price_history[i-1]
            returns.append(ret)
        
        if not returns:
            return order_price
        
        std_returns = sum(returns) / len(returns)
        # 使用分位数作为滑点
        sorted_returns = sorted(returns, key=abs)
        percentile_idx = int(len(sorted_returns) * self.slippage_percentile)
        slippage_ratio = abs(sorted_returns[percentile_idx]) if percentile_idx < len(sorted_returns) else std_returns
        
        return order_price * (1 + slippage_ratio)


class TaskScheduler:
    """
    任务调度器
    
    功能：
    1. 定时任务（指定时间执行一次）
    2. 周期任务（固定间隔执行）
    3. Cron任务（Cron表达式触发）
    4. 任务队列和优先级
    5. 执行日志和监控
    """

    def __init__(self, max_workers: int = 4):
        """
        Args:
            max_workers: 最大并发执行任务数
        """
        self.max_workers = max_workers
        self._tasks: Dict[str, ScheduledTask] = {}
        self._task_lock = threading.Lock()
        self._executor = threading.ThreadPoolExecutor(max_workers=max_workers)
        self._running = False
        self._scheduler_thread = None
        self._stop_event = threading.Event()
        
        self._listeners: List[Callable] = []

    def add_task(self, task: ScheduledTask) -> bool:
        """
        添加任务
        
        Args:
            task: 调度任务
        
        Returns:
            是否成功
        """
        with self._task_lock:
            if task.name in self._tasks:
                logger.warning(f"Task already exists: {task.name}")
                return False
            
            self._tasks[task.name] = task
            logger.info(f"Task added: {task.name} ({task.task_type.value})")
            return True

    def remove_task(self, name: str) -> bool:
        """移除任务"""
        with self._task_lock:
            if name in self._tasks:
                del self._tasks[name]
                logger.info(f"Task removed: {name}")
                return True
            return False

    def enable_task(self, name: str) -> bool:
        """启用任务"""
        with self._task_lock:
            if name in self._tasks:
                self._tasks[name].enabled = True
                return True
            return False

    def disable_task(self, name: str) -> bool:
        """禁用任务"""
        with self._task_lock:
            if name in self._tasks:
                self._tasks[name].enabled = False
                return True
            return False

    def get_task(self, name: str) -> Optional[ScheduledTask]:
        """获取任务信息"""
        with self._task_lock:
            return self._tasks.get(name)

    def list_tasks(self, status: TaskStatus = None, tag: str = None) -> List[ScheduledTask]:
        """
        列出任务
        
        Args:
            status: 按状态过滤
            tag: 按标签过滤
        
        Returns:
            任务列表
        """
        with self._task_lock:
            tasks = list(self._tasks.values())
        
        if status:
            tasks = [t for t in tasks if t.status == status]
        
        if tag:
            tasks = [t for t in tasks if tag in t.tags]
        
        return tasks

    def run_task_now(self, name: str) -> Optional[TaskResult]:
        """
        立即执行任务
        
        Args:
            name: 任务名称
        
        Returns:
            任务执行结果
        """
        task = self.get_task(name)
        if not task:
            logger.error(f"Task not found: {name}")
            return None
        
        return self._execute_task(task)

    def _execute_task(self, task: ScheduledTask) -> TaskResult:
        """执行单个任务"""
        task.status = TaskStatus.RUNNING
        start_time = datetime.now()
        
        logger.info(f"Task started: {task.name}")
        
        try:
            result = task.func()
            task.last_result = result
            task.last_error = None
            task.status = TaskStatus.COMPLETED
            task.run_count += 1
            task.last_run = datetime.now()
            
            duration_ms = (datetime.now() - start_time).total_seconds() * 1000
            
            result_obj = TaskResult(
                task_name=task.name,
                status=TaskStatus.COMPLETED,
                start_time=start_time,
                end_time=datetime.now(),
                duration_ms=duration_ms,
                result=result
            )
            
            self._notify_listeners(result_obj)
            return result_obj
            
        except Exception as e:
            task.last_error = str(e)
            task.status = TaskStatus.FAILED
            task.run_count += 1
            task.last_run = datetime.now()
            
            duration_ms = (datetime.now() - start_time).total_seconds() * 1000
            
            logger.error(f"Task failed: {task.name} - {e}")
            
            result_obj = TaskResult(
                task_name=task.name,
                status=TaskStatus.FAILED,
                start_time=start_time,
                end_time=datetime.now(),
                duration_ms=duration_ms,
                error=str(e)
            )
            
            self._notify_listeners(result_obj)
            return result_obj

    def _scheduler_loop(self):
        """调度器主循环"""
        while not self._stop_event.is_set():
            try:
                now = datetime.now()
                
                with self._task_lock:
                    tasks_to_run = []
                    
                    for task in self._tasks.values():
                        if not task.enabled:
                            continue
                        
                        if task.task_type == TaskType.ONE_TIME:
                            if task.trigger_time and now >= task.trigger_time:
                                tasks_to_run.append(task)
                        
                        elif task.task_type == TaskType.INTERVAL:
                            if task.last_run is None:
                                tasks_to_run.append(task)
                            elif task.interval_seconds:
                                elapsed = (now - task.last_run).total_seconds()
                                if elapsed >= task.interval_seconds:
                                    tasks_to_run.append(task)
                
                # 提交任务到线程池
                for task in tasks_to_run:
                    self._executor.submit(self._execute_task, task)
                
                # 休眠
                time.sleep(1)
                
            except Exception as e:
                logger.error(f"Scheduler loop error: {e}")
                time.sleep(5)

    def start(self):
        """启动调度器"""
        if self._running:
            return
        
        self._running = True
        self._stop_event.clear()
        self._scheduler_thread = threading.Thread(target=self._scheduler_loop, daemon=True)
        self._scheduler_thread.start()
        logger.info("Task scheduler started")

    def stop(self):
        """停止调度器"""
        if not self._running:
            return
        
        self._stop_event.set()
        self._running = False
        
        if self._scheduler_thread:
            self._scheduler_thread.join(timeout=5)
        
        logger.info("Task scheduler stopped")

    def add_listener(self, listener: Callable):
        """添加任务执行监听器"""
        self._listeners.append(listener)

    def _notify_listeners(self, result: TaskResult):
        """通知所有监听器"""
        for listener in self._listeners:
            try:
                listener(result)
            except Exception as e:
                logger.error(f"Listener error: {e}")

    def get_stats(self) -> Dict:
        """获取调度器统计"""
        with self._task_lock:
            total = len(self._tasks)
            enabled = sum(1 for t in self._tasks.values() if t.enabled)
            running = sum(1 for t in self._tasks.values() if t.status == TaskStatus.RUNNING)
            completed = sum(1 for t in self._tasks.values() if t.status == TaskStatus.COMPLETED)
            failed = sum(1 for t in self._tasks.values() if t.status == TaskStatus.FAILED)
        
        return {
            "total_tasks": total,
            "enabled_tasks": enabled,
            "running_tasks": running,
            "completed_tasks": completed,
            "failed_tasks": failed
        }

    def __del__(self):
        """清理资源"""
        self.stop()
        self._executor.shutdown(wait=False)


# 预置任务工厂函数

def create_signal_monitor_task(
    stock_codes: List[str],
    interval_seconds: int = 60
) -> ScheduledTask:
    """创建信号监控任务"""
    def signal_monitor():
        from src.core.signal.signal_generator import SignalGenerator
        from src.core.position.position_sync import get_position_sync_manager
        
        generator = SignalGenerator()
        sync_manager = get_position_sync_manager()
        
        results = {}
        for code in stock_codes:
            try:
                # 获取数据并生成信号
                from src.api.eastmoney.client import EastMoneyClient
                client = EastMoneyClient()
                df = client.get_kline(code, ktype='D', days=30)
                
                if df is not None and not df.empty:
                    signal = generator.analyze(df)
                    results[code] = signal
            except Exception as e:
                logger.debug(f"Signal monitor error for {code}: {e}")
        
        return results
    
    return ScheduledTask(
        name="signal_monitor",
        func=signal_monitor,
        task_type=TaskType.INTERVAL,
        interval_seconds=interval_seconds,
        description="定时监控股票信号",
        tags=["signal", "monitor"]
    )


def create_data_backup_task(
    backup_interval_hours: int = 24
) -> ScheduledTask:
    """创建数据备份任务"""
    def data_backup():
        from src.core.database.connection_pool import get_engine
        import shutil
        import os
        
        engine = get_engine()
        if engine is None:
            return {"success": False, "reason": "No database engine"}
        
        # 备份 SQLite 数据库
        db_path = "stock_quant.db"
        if os.path.exists(db_path):
            backup_path = f"backup/backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db"
            os.makedirs("backup", exist_ok=True)
            shutil.copy2(db_path, backup_path)
            return {"success": True, "backup_path": backup_path}
        
        return {"success": False, "reason": "Database file not found"}
    
    return ScheduledTask(
        name="data_backup",
        func=data_backup,
        task_type=TaskType.INTERVAL,
        interval_seconds=backup_interval_hours * 3600,
        description="定时备份数据库",
        tags=["backup", "database"]
    )


def create_cache_cleanup_task(
    cleanup_interval_hours: int = 6
) -> ScheduledTask:
    """创建缓存清理任务"""
    def cache_cleanup():
        from src.core.cache.redis_cache import get_cache
        
        cache = get_cache()
        stats = cache.get_stats()
        
        # 清理过期缓存
        if hasattr(cache, '_fallback_cache'):
            now = datetime.now()
            expired_keys = []
            with cache._fallback_lock:
                for key, entry in cache._fallback_cache.items():
                    if entry["expires_at"] < now:
                        expired_keys.append(key)
                
                for key in expired_keys:
                    del cache._fallback_cache[key]
        
        return {
            "cleaned_entries": len(expired_keys) if 'expired_keys' in dir() else 0,
            "stats": stats
        }
    
    return ScheduledTask(
        name="cache_cleanup",
        func=cache_cleanup,
        task_type=TaskType.INTERVAL,
        interval_seconds=cleanup_interval_hours * 3600,
        description="定时清理过期缓存",
        tags=["cache", "cleanup"]
    )


# 全局调度器实例
_global_scheduler: Optional[TaskScheduler] = None


def get_scheduler() -> TaskScheduler:
    """获取全局调度器"""
    global _global_scheduler
    
    if _global_scheduler is None:
        _global_scheduler = TaskScheduler()
        _global_scheduler.start()
    
    return _global_scheduler


def shutdown_scheduler():
    """关闭全局调度器"""
    global _global_scheduler
    
    if _global_scheduler:
        _global_scheduler.stop()
        _global_scheduler = None