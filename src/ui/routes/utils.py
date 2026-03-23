"""
路由公共工具函数
"""

import logging
from flask import request, jsonify
import pandas as pd

logger = logging.getLogger(__name__)


def df_to_json_records(df):
    """把 DataFrame 转成前端可解析的 JSON 记录，避免 NaN 破坏 JSON"""
    if df is None:
        return []
    safe_df = df.copy().astype(object)
    safe_df = safe_df.where(pd.notna(safe_df), None)
    return safe_df.to_dict('records')


def require_json_payload():
    """从请求中解析 JSON payload"""
    if not request.is_json:
        return None, "请求必须是 JSON 格式"
    try:
        return request.get_json(), None
    except Exception as e:
        return None, f"JSON 解析失败: {str(e)}"


def parse_int_query(key, default=0):
    """解析整数查询参数"""
    try:
        val = request.args.get(key)
        return int(val) if val is not None else default
    except (ValueError, TypeError):
        return default


def parse_float_query(key, default=0.0):
    """解析浮点数查询参数"""
    try:
        val = request.args.get(key)
        return float(val) if val is not None else default
    except (ValueError, TypeError):
        return default
