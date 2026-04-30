"""
结构化日志模块
JSON格式日志 + 日志聚合支持
"""

import json
import logging
import sys
import threading
import traceback
from datetime import datetime
from typing import Any, Dict, Optional
from enum import Enum
from collections import deque
import io


class LogLevel(Enum):
    """日志级别"""
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class StructuredFormatter(logging.Formatter):
    """结构化日志格式化器"""

    def __init__(self, include_stacktrace: bool = False):
        super().__init__()
        self.include_stacktrace = include_stacktrace

    def format(self, record: logging.LogRecord) -> str:
        """格式化为 JSON"""
        log_entry = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
            "thread_id": record.thread,
            "thread_name": record.threadName,
            "process_id": record.process
        }

        # 添加额外字段
        if hasattr(record, 'extra_data'):
            log_entry["data"] = record.extra_data

        if hasattr(record, 'request_id'):
            log_entry["request_id"] = record.request_id

        if hasattr(record, 'user_id'):
            log_entry["user_id"] = record.user_id

        # 添加异常信息
        if record.exc_info:
            log_entry["exception"] = {
                "type": record.exc_info[0].__name__ if record.exc_info[0] else None,
                "message": str(record.exc_info[1]) if record.exc_info[1] else None,
                "stacktrace": traceback.format_exception(*record.exc_info) if self.include_stacktrace else None
            }

        # 性能相关
        if hasattr(record, 'duration_ms'):
            log_entry["duration_ms"] = record.duration_ms

        if hasattr(record, 'operation'):
            log_entry["operation"] = record.operation

        return json.dumps(log_entry, ensure_ascii=False)


class ColoredFormatter(logging.Formatter):
    """带颜色的控制台格式化器"""

    COLORS = {
        "DEBUG": "\033[36m",    # 青色
        "INFO": "\033[32m",     # 绿色
        "WARNING": "\033[33m", # 黄色
        "ERROR": "\033[31m",    # 红色
        "CRITICAL": "\033[35m",# 紫色
    }
    RESET = "\033[0m"

    def __init__(self, use_colors: bool = True):
        super().__init__()
        self.use_colors = use_colors

    def format(self, record: logging.LogRecord) -> str:
        """格式化为带颜色的文本"""
        color = self.COLORS.get(record.levelname, self.RESET)
        reset = self.RESET if self.use_colors else ""

        # 基础格式
        timestamp = datetime.fromtimestamp(record.created).strftime("%Y-%m-%d %H:%M:%S")
        level = record.levelname.ljust(8)
        name = record.name[:30].ljust(30)
        message = record.getMessage()

        # 添加额外数据（如果有）
        extra_info = ""
        if hasattr(record, 'extra_data'):
            extra_info = f" | {record.extra_data}"

        if record.exc_info:
            message += "\n" + self.formatException(record.exc_info)

        return f"{color}[{timestamp}] [{level}] [{name}]{reset} {message}{extra_info}"


class LogCapture:
    """日志捕获器（用于测试和调试）"""

    _instance = None
    _lock = threading.Lock()

    def __init__(self, max_size: int = 1000):
        self.max_size = max_size
        self._logs = deque(maxlen=max_size)
        self._capture_enabled = False

    @classmethod
    def get_instance(cls) -> 'LogCapture':
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    def capture(self, level: str, message: str, extra: Dict = None):
        """捕获日志"""
        if not self._capture_enabled:
            return

        entry = {
            "timestamp": datetime.now().isoformat(),
            "level": level,
            "message": message,
            "extra": extra or {}
        }
        self._logs.append(entry)

    def start_capture(self):
        """开始捕获"""
        self._capture_enabled = True
        self._logs.clear()

    def stop_capture(self) -> list:
        """停止捕获并返回结果"""
        self._capture_enabled = False
        return list(self._logs)

    def get_recent(self, count: int = 10) -> list:
        """获取最近的日志"""
        return list(self._logs)[-count:]


class StructuredLogger:
    """
    结构化日志记录器
    
    支持：
    1. JSON 格式日志
    2. 控制台彩色输出
    3. 日志级别过滤
    4. 性能追踪
    5. 请求上下文
    """

    def __init__(
        self,
        name: str,
        level: str = "INFO",
        json_format: bool = False,
        include_stacktrace: bool = False
    ):
        self.logger = logging.getLogger(name)
        self.logger.setLevel(getattr(logging, level.upper(), logging.INFO))
        self.logger.handlers.clear()

        # 添加处理器
        if json_format:
            handler = logging.StreamHandler(sys.stdout)
            handler.setFormatter(StructuredFormatter(include_stacktrace=include_stacktrace))
            self.logger.addHandler(handler)
        else:
            handler = logging.StreamHandler(sys.stdout)
            handler.setFormatter(ColoredFormatter())
            self.logger.addHandler(handler)

        self._context = {}

    def set_context(self, **kwargs):
        """设置日志上下文"""
        self._context.update(kwargs)

    def clear_context(self):
        """清除日志上下文"""
        self._context = {}

    def _make_extra(self, extra: Dict = None) -> Dict:
        """合并额外数据"""
        result = {"extra_data": extra or {}}
        result["extra_data"].update(self._context)
        return {"extra_data": result["extra_data"]}

    def debug(self, message: str, **kwargs):
        """Debug 级别"""
        extra = self._make_extra(kwargs)
        self.logger.debug(message, extra=extra)

    def info(self, message: str, **kwargs):
        """Info 级别"""
        extra = self._make_extra(kwargs)
        self.logger.info(message, extra=extra)

    def warning(self, message: str, **kwargs):
        """Warning 级别"""
        extra = self._make_extra(kwargs)
        self.logger.warning(message, extra=extra)

    def error(self, message: str, **kwargs):
        """Error 级别"""
        extra = self._make_extra(kwargs)
        self.logger.error(message, extra=extra)

    def critical(self, message: str, **kwargs):
        """Critical 级别"""
        extra = self._make_extra(kwargs)
        self.logger.critical(message, extra=extra)

    def performance(self, operation: str, duration_ms: float, **kwargs):
        """记录性能日志"""
        extra = self._make_extra(kwargs)
        extra["duration_ms"] = duration_ms
        extra["operation"] = operation
        self.logger.info(f"Performance: {operation} took {duration_ms:.2f}ms", extra=extra)

    def log_api_call(
        self,
        api_name: str,
        duration_ms: float,
        status_code: int = None,
        error: str = None,
        **kwargs
    ):
        """记录 API 调用"""
        extra = self._make_extra(kwargs)
        extra["operation"] = "api_call"
        extra["api_name"] = api_name
        extra["duration_ms"] = duration_ms
        extra["status_code"] = status_code
        extra["error"] = error

        if error or (status_code and status_code >= 400):
            self.logger.error(f"API Call Failed: {api_name}", extra=extra)
        else:
            self.logger.info(f"API Call: {api_name} ({duration_ms:.2f}ms)", extra=extra)

    def log_signal(
        self,
        stock_code: str,
        signal_type: str,
        strength: float,
        price: float,
        **kwargs
    ):
        """记录交易信号"""
        extra = self._make_extra(kwargs)
        extra["operation"] = "signal"
        extra["stock_code"] = stock_code
        extra["signal_type"] = signal_type
        extra["signal_strength"] = strength
        extra["price"] = price

        self.logger.info(
            f"Signal Generated: {signal_type} {stock_code} @ {price} (strength: {strength}%)",
            extra=extra
        )

    def log_backtest(
        self,
        strategy_name: str,
        total_return: float,
        sharpe_ratio: float,
        max_drawdown: float,
        **kwargs
    ):
        """记录回测结果"""
        extra = self._make_extra(kwargs)
        extra["operation"] = "backtest"
        extra["strategy_name"] = strategy_name
        extra["total_return"] = total_return
        extra["sharpe_ratio"] = sharpe_ratio
        extra["max_drawdown"] = max_drawdown

        self.logger.info(
            f"Backtest: {strategy_name} | Return: {total_return:.2f}% | Sharpe: {sharpe_ratio:.2f} | DD: {max_drawdown:.2f}%",
            extra=extra
        )


class LogAggregator:
    """
    日志聚合器（用于日志分析和统计）
    """

    def __init__(self):
        self._stats = {
            "total_logs": 0,
            "by_level": {},
            "by_module": {},
            "errors": [],
            "warnings": []
        }
        self._lock = threading.Lock()

    def add_log(self, level: str, module: str, message: str, error: str = None):
        """添加日志统计"""
        with self._lock:
            self._stats["total_logs"] += 1

            # 按级别统计
            if level not in self._stats["by_level"]:
                self._stats["by_level"][level] = 0
            self._stats["by_level"][level] += 1

            # 按模块统计
            if module not in self._stats["by_module"]:
                self._stats["by_module"][module] = 0
            self._stats["by_module"][module] += 1

            # 记录错误和警告
            if level == "ERROR" and error:
                self._stats["errors"].append({
                    "module": module,
                    "message": message,
                    "error": error,
                    "timestamp": datetime.now().isoformat()
                })
            elif level == "WARNING":
                self._stats["warnings"].append({
                    "module": module,
                    "message": message,
                    "timestamp": datetime.now().isoformat()
                })

    def get_stats(self) -> Dict:
        """获取统计信息"""
        with self._lock:
            return {
                "total_logs": self._stats["total_logs"],
                "by_level": dict(self._stats["by_level"]),
                "by_module": dict(self._stats["by_module"]),
                "recent_errors": self._stats["errors"][-10:],
                "recent_warnings": self._stats["warnings"][-10:]
            }

    def reset(self):
        """重置统计"""
        with self._lock:
            self._stats = {
                "total_logs": 0,
                "by_level": {},
                "by_module": {},
                "errors": [],
                "warnings": []
            }


# 全局限流器
_log_aggregator = LogAggregator()


def get_logger(
    name: str,
    level: str = "INFO",
    json_format: bool = False
) -> StructuredLogger:
    """
    获取结构化日志记录器
    
    Args:
        name: 日志记录器名称
        level: 日志级别
        json_format: 是否 JSON 格式输出
    
    Returns:
        StructuredLogger 实例
    """
    return StructuredLogger(name, level, json_format)


def get_log_aggregator() -> LogAggregator:
    """获取日志聚合器"""
    return _log_aggregator


class PerformanceTracker:
    """性能追踪器"""

    def __init__(self, logger: StructuredLogger = None):
        self.logger = logger or get_logger("performance")
        self._timings = {}

    def start(self, operation: str):
        """开始计时"""
        self._timings[operation] = {
            "start": datetime.now(),
            "stack": traceback.extract_stack()[-3:-1]
        }

    def end(self, operation: str):
        """结束计时"""
        if operation not in self._timings:
            return

        start_time = self._timings[operation]["start"]
        duration_ms = (datetime.now() - start_time).total_seconds() * 1000

        self.logger.performance(operation, duration_ms)

        del self._timings[operation]
        return duration_ms

    def measure(self, operation: str, func, *args, **kwargs):
        """测量函数执行时间"""
        self.start(operation)
        try:
            result = func(*args, **kwargs)
            return result
        finally:
            self.end(operation)


# 全局性能追踪器
_global_tracker = None


def get_performance_tracker() -> PerformanceTracker:
    """获取全局性能追踪器"""
    global _global_tracker
    if _global_tracker is None:
        _global_tracker = PerformanceTracker()
    return _global_tracker