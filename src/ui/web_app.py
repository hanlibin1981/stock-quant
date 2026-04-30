"""
Web GUI 服务器
提供图形化界面访问量化工具

此文件作为应用入口和蓝图注册中心，路由逻辑已拆分到 routes/ 模块
"""

import sys
import os
import re
import logging
import tempfile
from pathlib import Path
from datetime import datetime
import pandas as pd
from typing import Optional, Tuple

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def _validate_strategy(strategy: str, valid_strategies: list) -> bool:
    """验证策略名是否有效"""
    return strategy in valid_strategies


# 添加虚拟env site-packages 到路径
venv_path = Path(__file__).parent.parent.parent / "venv" / "lib"
current_version = f"python{sys.version_info.major}.{sys.version_info.minor}"
found = False
if venv_path.exists():
    for p in venv_path.iterdir():
        if p.is_dir() and p.name == current_version:
            sys.path.insert(0, str(p / "site-packages"))
            found = True
            break

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent.parent
src_root = Path(__file__).parent.parent
sys.path.insert(0, str(src_root))

from flask import Flask, render_template, jsonify, request
from src.utils.validation import validate_stock_code
from src.core.data.stock_data import StockDataManager
from src.core.indicator.calculator import IndicatorCalculator
from src.core.strategy.strategy import StrategyEngine
from src.core.backtest.backtest import BacktestEngine
from src.api.eastmoney.client import EastMoneyClient
from src.api.tonghuashun.importer import TonghuashunImporter
from src.api.tushare import get_tushare_client
from src.api.vnpy import get_vnpy_client, get_stock_client
from src.api.mock_data import MockDataGenerator
from src.api.mock_trade import get_mock_trade_client
from src.api.tencent import get_tencent_client
from src.core.signal import get_signal_generator

app = Flask(__name__,
            template_folder=str(Path(__file__).parent / 'templates'),
            static_folder=str(Path(__file__).parent / 'static'))

# 初始化各模块
data_dir = Path.home() / ".stockquant" / "data"
data_dir.mkdir(parents=True, exist_ok=True)
data_manager = StockDataManager(data_dir)
eastmoney_client = EastMoneyClient()
tushare_client = get_tushare_client()
mock_generator = MockDataGenerator()
vnpy_client = get_vnpy_client()
stock_client = get_stock_client()
mock_trade_client = get_mock_trade_client()
tencent_client = get_tencent_client()
indicator_calc = IndicatorCalculator()
signal_generator = get_signal_generator()
strategy_engine = StrategyEngine()
backtest_engine = BacktestEngine()
tonghuashun_importer = TonghuashunImporter()

# 客户端字典，用于传递给蓝图
_clients = {
    'eastmoney_client': eastmoney_client,
    'tushare_client': tushare_client,
    'mock_generator': mock_generator,
    'vnpy_client': vnpy_client,
    'stock_client': stock_client,
    'mock_trade_client': mock_trade_client,
    'tencent_client': tencent_client,
    'indicator_calc': indicator_calc,
    'signal_generator': signal_generator,
    'strategy_engine': strategy_engine,
    'backtest_engine': backtest_engine,
    'tonghuashun_importer': tonghuashun_importer,
}


def _df_to_json_records(df):
    """把 DataFrame 转成前端可解析的 JSON 记录，避免 NaN 破坏 JSON"""
    if df is None:
        return []
    safe_df = df.copy().astype(object)
    safe_df = safe_df.where(pd.notna(safe_df), None)
    return safe_df.to_dict('records')


def _parse_backtest_params(args) -> dict:
    """从请求参数中提取回测和策略参数"""
    int_keys = {
        "fast_ma", "slow_ma", "period", "lot_size", "atr_period",
        "volume_period", "min_factor_pass_count"
    }
    float_keys = {
        "initial_capital", "commission", "slippage", "risk_free_rate"
    }
    bool_keys = {
        "use_trend_factor", "use_momentum_factor", "use_reversion_factor",
        "stop_loss", "take_profit", "trailing_stop"
    }

    params = {}
    for key in int_keys:
        if key in args:
            try:
                params[key] = int(args.get(key))
            except (ValueError, TypeError):
                pass

    for key in float_keys:
        if key in args:
            try:
                params[key] = float(args.get(key))
            except (ValueError, TypeError):
                pass

    for key in bool_keys:
        params[key] = args.get(key, '').lower() == 'true'

    return params


def _parse_optimize_param_ranges(args):
    """解析参数优化范围"""
    ranges = {}
    for key, val in args.items():
        if key.startswith('range_'):
            param_name = key[6:]
            try:
                parts = val.split(',')
                if len(parts) == 3:
                    ranges[param_name] = {
                        'start': float(parts[0]),
                        'end': float(parts[1]),
                        'step': float(parts[2])
                    }
            except (ValueError, IndexError):
                pass
    return ranges


def _parse_optimize_constraints(args):
    """解析优化约束条件"""
    constraints = {}
    for key, val in args.items():
        if key.startswith('constraint_'):
            constraint_name = key[11:]
            try:
                constraints[constraint_name] = float(val)
            except (ValueError, TypeError):
                pass
    return constraints


def _parse_walkforward_config(args):
    """解析滚动验证配置"""
    return {
        'train_period': int(args.get('train_period', 120)),
        'test_period': int(args.get('test_period', 20)),
        'rebalance_frequency': args.get('rebalance_frequency', 'weekly')
    }


def _parse_int_query(args, key, default, min_value=None, max_value=None):
    """解析整数查询参数"""
    try:
        val = int(args.get(key, default))
        if min_value is not None:
            val = max(val, min_value)
        if max_value is not None:
            val = min(val, max_value)
        return val, None
    except (ValueError, TypeError):
        return default, None


def _parse_float_query(args, key, default):
    """解析浮点数查询参数"""
    try:
        return float(args.get(key, default)), None
    except (ValueError, TypeError):
        return default, None


def _require_json_payload():
    """从请求中解析 JSON payload"""
    if not request.is_json:
        return None, "请求必须是 JSON 格式"
    try:
        return request.get_json(), None
    except Exception as e:
        return None, f"JSON 解析失败: {str(e)}"


def _get_backtest_dataframe(code, days=250):
    """获取回测用的数据"""
    df = None
    source = 'tushare'

    if tushare_client.is_available():
        df = tushare_client.get_kline(code, days=days)

    if df is None or (hasattr(df, 'empty') and df.empty):
        df = eastmoney_client.get_kline(code, days=days)
        source = 'eastmoney'

    if df is None or (hasattr(df, 'empty') and df.empty):
        df = tencent_client.get_kline(code, days=days)
        source = 'tencent'

    if df is None or (hasattr(df, 'empty') and df.empty):
        df = mock_generator.generate_kline(code, days=days)
        source = 'mock'

    return df, source


# =============================================================================
# 注册蓝图路由
# =============================================================================
from src.ui.routes import data_bp, backtest_bp, trading_bp, signal_bp
from src.ui.routes import data as data_module, backtest as backtest_module
from src.ui.routes import trading as trading_module, signal as signal_module

# 初始化蓝图的客户端引用
data_module.init_clients(_clients)
backtest_module.init_clients(_clients)
trading_module.init_clients(_clients)
signal_module.init_clients(_clients)

# 注册蓝图
app.register_blueprint(data_bp)
app.register_blueprint(backtest_bp)
app.register_blueprint(trading_bp)
app.register_blueprint(signal_bp)


# =============================================================================
# 保留的原有路由（用于数据导入和搜索）
# =============================================================================

@app.route('/api/import', methods=['POST'])
def import_data():
    """导入同花顺数据"""
    if 'file' not in request.files:
        return jsonify({'success': False, 'error': '没有文件'})

    file = request.files['file']
    # 防止路径遍历攻击 - 验证文件名
    filename = os.path.basename(file.filename)
    if not filename or '..' in filename or '/' in filename or '\\' in filename:
        return jsonify({'success': False, 'error': '无效的文件名'})

    # 使用安全的临时目录
    temp_dir = tempfile.mkdtemp(prefix='stockquant_import_')
    filepath = os.path.join(temp_dir, filename)
    try:
        file.save(filepath)
        df = tonghuashun_importer.import_file(filepath)

        if df is not None:
            return jsonify({
                'success': True,
                'rows': len(df),
                'columns': list(df.columns)
            })

        return jsonify({'success': False, 'error': '导入失败'})
    finally:
        # 确保临时文件被清理
        try:
            os.remove(filepath)
            os.rmdir(temp_dir)
        except OSError:
            pass


# =============================================================================
# SPA Fallback - 所有非 API/static 路由都返回 index.html
# =============================================================================

@app.route('/', defaults={'path': ''})
@app.route('/<path:path>')
def serve_spa(path):
    # API 路由已由蓝图处理，能走到这里说明是前端路由
    # 直接返回 index.html，由前端 router 处理
    return render_template('index.html')


# =============================================================================
# 运行服务器
# =============================================================================

def run(host='0.0.0.0', port=5004, debug=False):
    """运行服务器"""
    app.run(host=host, port=port, debug=debug)


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='StockQuant Web Server')
    parser.add_argument('--host', default='0.0.0.0', help='Host to bind')
    parser.add_argument('--port', type=int, default=5004, help='Port to bind')
    parser.add_argument('--debug', default=False, help='Enable debug mode')
    args = parser.parse_args()

    run(host=args.host, port=args.port, debug=args.debug)
