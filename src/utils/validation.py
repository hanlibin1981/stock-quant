"""
共享验证函数模块
提供跨模块的统一样验证逻辑
"""

import re
from typing import Optional

# 股票代码正则: 6位数字，以0/3/6开头
STOCK_CODE_PATTERN = re.compile(r'^(0|3|6)\d{5}$')


def validate_stock_code(code: str) -> bool:
    """
    验证股票代码格式

    Args:
        code: 股票代码

    Returns:
        bool: 是否有效
    """
    if not code or not isinstance(code, str):
        return False
    return bool(STOCK_CODE_PATTERN.match(code.strip()))


def normalize_stock_code(code: str) -> Optional[str]:
    """
    规范化股票代码格式

    Args:
        code: 股票代码

    Returns:
        规范化后的代码，无效返回None
    """
    if not validate_stock_code(code):
        return None
    return code.strip()


def validate_stock_code_with_exchange(code: str) -> Optional[tuple[str, str]]:
    """
    验证并转换股票代码为 (code, exchange) 格式

    Args:
        code: 股票代码

    Returns:
        (code, exchange) 元组，无效返回None
        exchange: "SH" (上海) 或 "SZ" (深圳)
    """
    if not validate_stock_code(code):
        return None

    code = code.strip()
    if code.startswith('6'):
        return (code, "SH")
    elif code.startswith('0') or code.startswith('3'):
        return (code, "SZ")
    else:
        return (code, "SZ")
