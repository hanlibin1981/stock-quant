from .logger import setup_logger, default_logger

# 向后兼容别名
get_logger = setup_logger

__all__ = ["setup_logger", "default_logger", "get_logger"]
