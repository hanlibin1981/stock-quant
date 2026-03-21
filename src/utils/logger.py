"""
统一日志模块
"""
import logging
import sys
import json
from datetime import datetime


class JSONFormatter(logging.Formatter):
    """JSON 格式日志（支持 Unicode）"""

    def format(self, record: logging.LogRecord) -> str:
        log_data = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)
        # 使用 ensure_ascii=False 保证中文等非 ASCII 字符不被转义
        return json.dumps(log_data, ensure_ascii=False)


def setup_logger(name: str = "stock_quant", level: int = logging.INFO) -> logging.Logger:
    """获取配置好的 logger"""
    logger = logging.getLogger(name)
    logger.setLevel(level)
    logger.handlers.clear()

    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(level)
    handler.setFormatter(JSONFormatter())
    logger.addHandler(handler)

    return logger


# 默认 logger
default_logger = setup_logger()

# 向后兼容别名
get_logger = setup_logger
