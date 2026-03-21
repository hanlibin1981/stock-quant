"""
Web GUI 服务器
提供图形化界面访问量化工具
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

# 股票代码正则: 6位数字，以0/3/6开头
STOCK_CODE_PATTERN = re.compile(r'^(0|3|6)\d{5}$')


def _validate_stock_code(code: str) -> bool:
    """验证股票代码格式"""
    if not code or not isinstance(code, str):
        return False
    return bool(STOCK_CODE_PATTERN.match(code.strip()))


def _validate_strategy(strategy: str, valid_strategies: list) -> bool:
    """验证策略名是否有效"""
    return strategy in valid_strategies

# 添加虚拟env site-packages 到路径
venv_path = Path(__file__).parent.parent.parent / "venv" / "lib"
# 查找当前 Python 版本对应的 site-packages 目录
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
        "fast_ma",
        "slow_ma",
        "period",
        "lot_size",
        "atr_period",
        "volume_period",
        "min_factor_pass_count",
        "use_trend_factor",
        "use_momentum_factor",
        "use_reversion_factor",
        "use_volume_factor",
    }
    float_keys = {
        "oversold",
        "overbought",
        "buy_threshold",
        "sell_threshold",
        "trend_weight",
        "momentum_weight",
        "reversion_weight",
        "volume_weight",
        "initial_capital",
        "position_size",
        "commission_rate",
        "stamp_duty_rate",
        "slippage_rate",
        "risk_free_rate",
        "stop_loss_pct",
        "take_profit_pct",
        "trailing_stop_pct",
        "atr_stop_multiplier",
        "partial_take_profit_pct",
        "partial_take_profit_ratio",
    }

    params = {}
    for key in int_keys:
        value = args.get(key)
        if value not in (None, ""):
            params[key] = int(value)

    for key in float_keys:
        value = args.get(key)
        if value not in (None, ""):
            params[key] = float(value)

    return params


def _parse_optimize_param_ranges(args) -> dict:
    """解析优化参数范围，支持逗号分隔候选值"""
    range_keys = {
        "fast_ma": int,
        "slow_ma": int,
        "period": int,
        "min_factor_pass_count": int,
        "oversold": float,
        "overbought": float,
        "buy_threshold": float,
        "sell_threshold": float,
        "trend_weight": float,
        "momentum_weight": float,
        "reversion_weight": float,
        "volume_weight": float,
    }
    param_ranges = {}

    for key, caster in range_keys.items():
        raw_value = args.get(f"{key}_range")
        if raw_value in (None, ""):
            continue

        values = []
        for item in raw_value.split(","):
            item = item.strip()
            if not item:
                continue
            values.append(caster(item))

        if values:
            param_ranges[key] = values

    return param_ranges


def _parse_optimize_constraints(args) -> dict:
    """解析优化筛选约束"""
    constraint_keys = {
        "min_trades": int,
        "max_drawdown_limit": float,
        "min_sharpe": float,
        "min_excess_return": float,
    }
    constraints = {}
    for key, caster in constraint_keys.items():
        raw_value = args.get(key)
        if raw_value in (None, ""):
            continue
        constraints[key] = caster(raw_value)
    return constraints


def _parse_walkforward_config(args) -> dict:
    """解析滚动验证窗口参数"""
    config = {}
    for key in ("train_size", "test_size", "step_size", "max_evals"):
        raw_value = args.get(key)
        if raw_value in (None, ""):
            continue
        config[key] = int(raw_value)
    return config


def _parse_int_query(args, key, default=None, min_value=None, max_value=None) -> tuple[Optional[int], Optional[str]]:
    """从 query 中安全解析整数参数"""
    raw = args.get(key)
    if raw in (None, ""):
        return default, None
    try:
        value = int(raw)
    except (ValueError, TypeError):
        return None, f"{key} 必须为整数"
    if min_value is not None and value < min_value:
        return None, f"{key} 不能小于 {min_value}"
    if max_value is not None and value > max_value:
        return None, f"{key} 不能大于 {max_value}"
    return value, None


def _parse_float_query(args, key, default=None, min_value=None, max_value=None) -> tuple[Optional[float], Optional[str]]:
    """从 query 中安全解析浮点参数"""
    raw = args.get(key)
    if raw in (None, ""):
        return default, None
    try:
        value = float(raw)
    except (ValueError, TypeError):
        return None, f"{key} 必须为数字"
    if min_value is not None and value < min_value:
        return None, f"{key} 不能小于 {min_value}"
    if max_value is not None and value > max_value:
        return None, f"{key} 不能大于 {max_value}"
    return value, None


def _require_json_payload() -> tuple[dict, Optional[str]]:
    """从请求中提取 JSON payload，保证是字典"""
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return {}, "请求体必须是 JSON 对象"
    return payload, None


def _get_backtest_dataframe(code: str, days: int = 250):
    """获取回测所需K线数据"""
    df = None
    source = 'tushare'

    if tushare_client.is_available():
        df = tushare_client.get_kline(code, days=days)

    if df is None or df.empty:
        df = eastmoney_client.get_kline(code, days=days)
        source = 'eastmoney'

    if df is None or df.empty:
        df = tencent_client.get_kline(code, days=days)
        source = 'tencent'

    if df is None or df.empty:
        df = mock_generator.generate_kline(code, days=days)
        source = 'mock'

    return df, source


@app.route('/')
def index():
    """主页"""
    return render_template('index.html')


@app.route('/api/realtime')
def get_realtime():
    """获取实时行情（优先实时，失败则返回日K数据）"""
    code = request.args.get('code', '000002')
    
    data = None
    source = ''
    df = None
    
    # 优先使用 TuShare
    if tushare_client.is_available():
        data = tushare_client.get_realtime(code)
        if data:
            source = 'tushare'
    
    # 如果TuShare失败，使用腾讯财经
    if not data:
        data = tencent_client.get_realtime(code)
        if data:
            source = 'tencent'
    
    # 如果腾讯失败，使用东方财富
    if not data:
        data = eastmoney_client.get_realtime(code)
        if data:
            source = 'eastmoney'
    
    # 如果都没有，返回日K数据
    if not data:
        # 获取日K数据
        if tushare_client.is_available():
            df = tushare_client.get_kline(code, days=1)
        if df is None or (hasattr(df, 'empty') and df.empty):
            df = eastmoney_client.get_kline(code, days=1)
        if df is None or (hasattr(df, 'empty') and df.empty):
            df = mock_generator.generate_kline(code, days=1)
        
        if df is not None and not df.empty:
            latest = df.iloc[-1]
            data = {
                'code': code,
                'name': '股票',
                'price': float(latest['close']),
                'open': float(latest['open']),
                'high': float(latest['high']),
                'low': float(latest['low']),
                'close': float(latest['close']),
                'volume': float(latest['volume']),
                'amount': float(latest.get('amount', 0)),
                'change': 0,
                'change_amount': 0,
                'turnover': 0,
                'source': 'daily_kline'
            }
    
    # 最后使用模拟数据
    if not data:
        data = mock_generator.generate_realtime(code)
        data['source'] = 'mock'
    
    return jsonify(data)


@app.route('/api/status')
def get_status():
    """获取数据源状态"""
    return jsonify({
        'eastmoney': True,
        'tushare': tushare_client.is_available(),
        'mock': True
    })


@app.route('/api/kline')
def get_kline():
    """获取K线数据"""
    code = request.args.get('code', '000002')
    days, err = _parse_int_query(request.args, 'days', 60, min_value=1, max_value=500)
    if err:
        return jsonify({'success': False, 'error': err})

    # 参数验证
    if not _validate_stock_code(code):
        return jsonify({'success': False, 'error': f'无效的股票代码: {code}'})

    # 优先使用 TuShare
    df = None
    source = 'tushare'

    if tushare_client.is_available():
        df = tushare_client.get_kline(code, days=days)

    # 如果TuShare失败，使用东方财富
    if df is None or df.empty:
        df = eastmoney_client.get_kline(code, days=days)
        source = 'eastmoney'

    # 如果东方财富失败，使用腾讯财经
    if df is None or df.empty:
        df = tencent_client.get_kline(code, days=days)
        source = 'tencent'

    # 最后使用模拟数据
    if df is None or df.empty:
        df = mock_generator.generate_kline(code, days=days)
        source = 'mock'
    
    if df is not None and not df.empty:
        df = indicator_calc.calculate(df)
        return jsonify({
            'success': True,
            'data': _df_to_json_records(df),
            'source': source
        })
    
    return jsonify({
        'success': False,
        'error': '获取数据失败'
    })


@app.route('/api/indicators')
def get_indicators():
    """计算技术指标"""
    code = request.args.get('code', '000002')
    indicators = request.args.getlist('indicators')

    # 参数验证
    if not _validate_stock_code(code):
        return jsonify({'success': False, 'error': f'无效的股票代码: {code}'})

    if not indicators:
        indicators = ['ma', 'macd', 'rsi', 'boll']

    # 验证指标名称
    valid_indicators = ['ma', 'ema', 'macd', 'rsi', 'kdj', 'boll', 'cci', 'atr', 'obv', 'wr']
    for ind in indicators:
        if ind not in valid_indicators:
            return jsonify({'success': False, 'error': f'无效的指标: {ind}'})

    # 优先级: TuShare > 东方财富 > 腾讯财经 > 模拟
    df = None
    source = 'tushare'
    
    if tushare_client.is_available():
        df = tushare_client.get_kline(code, days=120)
    
    if df is None or df.empty:
        df = eastmoney_client.get_kline(code, days=120)
        source = 'eastmoney'

    if df is None or df.empty:
        df = tencent_client.get_kline(code, days=120)
        source = 'tencent'
    
    if df is None or df.empty:
        df = mock_generator.generate_kline(code, days=120)
        source = 'mock'
    
    if df is not None:
        df = indicator_calc.calculate(df, indicators)
        signals = indicator_calc.get_signals(df)
        
        return jsonify({
            'success': True,
            'data': _df_to_json_records(df),
            'signals': signals,
            'source': source,
        })
    
    return jsonify({'success': False, 'error': '获取数据失败'})


@app.route('/api/backtest')
def run_backtest():
    """运行回测"""
    code = request.args.get('code', '000002')
    strategy = request.args.get('strategy', 'multi_factor')
    params = _parse_backtest_params(request.args)

    # 验证股票代码
    if not _validate_stock_code(code):
        return jsonify({'success': False, 'error': f'无效的股票代码: {code}'})

    # 验证策略名
    valid_strategies = strategy_engine.get_available_strategies()
    if not _validate_strategy(strategy, valid_strategies):
        return jsonify({'success': False, 'error': f'无效的策略: {strategy}'})

    df, source = _get_backtest_dataframe(code, days=250)
    
    if df is None or df.empty:
        return jsonify({'success': False, 'error': '获取数据失败'})
    
    # 运行回测
    result = backtest_engine.run(df, strategy, params)
    
    if 'error' in result:
        return jsonify({'success': False, 'error': result['error']})
    
    return jsonify({
        'success': True,
        'metrics': {
            'total_trades': result['metrics'].total_trades,
            'win_rate': result['metrics'].win_rate,
            'total_return': result['metrics'].total_return,
            'annual_return': result['metrics'].annual_return,
            'max_drawdown': result['metrics'].max_drawdown,
            'sharpe_ratio': result['metrics'].sharpe_ratio,
            'profit_factor': result['metrics'].profit_factor,
            'end_capital': result['metrics'].end_capital,
        },
        'trades': result['trades'][-10:],  # 最近10笔交易
        'equity_curve': result['equity_curve'][-120:],
        'benchmark_curve': result['benchmark_curve'][-120:],
        'benchmark_metrics': result['benchmark_metrics'],
        'backtest_config': result['backtest_config'],
        'data_source': source,
        'strategy_diagnostics': {
            **result['strategy_diagnostics'],
            'factor_curve': result['strategy_diagnostics'].get('factor_curve', [])[-60:],
        } if result.get('strategy_diagnostics') else None,
    })


@app.route('/api/backtest/optimize')
def optimize_backtest():
    """优化回测参数"""
    code = request.args.get('code', '000002')
    strategy = request.args.get('strategy', 'multi_factor')
    metric = request.args.get('metric', 'total_return')
    top_n, err = _parse_int_query(request.args, 'top_n', 5, min_value=1, max_value=20)
    if err:
        return jsonify({'success': False, 'error': err})
    max_evals, err = _parse_int_query(request.args, 'max_evals', 50, min_value=1, max_value=200)
    if err:
        return jsonify({'success': False, 'error': err})
    params = _parse_backtest_params(request.args)
    param_ranges = _parse_optimize_param_ranges(request.args)
    constraints = _parse_optimize_constraints(request.args)

    # 参数验证
    if not _validate_stock_code(code):
        return jsonify({'success': False, 'error': f'无效的股票代码: {code}'})

    valid_strategies = strategy_engine.get_available_strategies()
    if not _validate_strategy(strategy, valid_strategies):
        return jsonify({'success': False, 'error': f'无效的策略: {strategy}'})

    df, source = _get_backtest_dataframe(code, days=250)
    if df is None or df.empty:
        return jsonify({'success': False, 'error': '获取数据失败'})

    result = backtest_engine.optimize(
        df,
        strategy,
        params=params,
        param_ranges=param_ranges,
        constraints=constraints,
        metric=metric,
        top_n=top_n,
        max_evals=max_evals,
    )
    if 'error' in result:
        return jsonify({'success': False, 'error': result['error']})

    return jsonify({'success': True, 'data_source': source, **result})


@app.route('/api/backtest/walkforward')
def walkforward_backtest():
    """滚动窗口验证"""
    code = request.args.get('code', '000002')
    strategy = request.args.get('strategy', 'multi_factor')
    metric = request.args.get('metric', 'balanced')
    params = _parse_backtest_params(request.args)
    param_ranges = _parse_optimize_param_ranges(request.args)
    constraints = _parse_optimize_constraints(request.args)
    walkforward_config = _parse_walkforward_config(request.args)

    # 参数验证
    if not _validate_stock_code(code):
        return jsonify({'success': False, 'error': f'无效的股票代码: {code}'})

    valid_strategies = strategy_engine.get_available_strategies()
    if not _validate_strategy(strategy, valid_strategies):
        return jsonify({'success': False, 'error': f'无效的策略: {strategy}'})

    df, source = _get_backtest_dataframe(code, days=500)
    if df is None or df.empty:
        return jsonify({'success': False, 'error': '获取数据失败'})

    result = backtest_engine.walk_forward(
        df,
        strategy,
        params=params,
        param_ranges=param_ranges,
        constraints=constraints,
        metric=metric,
        **walkforward_config,
    )
    if 'error' in result:
        return jsonify({'success': False, 'error': result['error']})

    return jsonify({
        'success': True,
        'strategy': result['strategy'],
        'metric': result['metric'],
        'segments': result['segments'],
        'stability_summary': result['stability_summary'],
        'metrics': {
            'total_trades': result['metrics'].total_trades,
            'win_rate': result['metrics'].win_rate,
            'total_return': result['metrics'].total_return,
            'annual_return': result['metrics'].annual_return,
            'max_drawdown': result['metrics'].max_drawdown,
            'sharpe_ratio': result['metrics'].sharpe_ratio,
            'profit_factor': result['metrics'].profit_factor,
            'end_capital': result['metrics'].end_capital,
        },
        'benchmark_metrics': result['benchmark_metrics'],
        'equity_curve': result['equity_curve'][-180:],
        'benchmark_curve': result['benchmark_curve'][-180:],
        'train_size': result['train_size'],
        'test_size': result['test_size'],
        'step_size': result['step_size'],
        'constraints': result['constraints'],
        'param_ranges': result['param_ranges'],
        'data_source': source,
    })


@app.route('/api/strategies')
def get_strategies():
    """获取可用策略列表"""
    strategies = strategy_engine.get_available_strategies()
    return jsonify(strategies)


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


@app.route('/api/search')
def search_stock():
    """搜索股票"""
    from urllib.parse import unquote
    keyword = request.args.get('keyword', '')
    keyword = unquote(keyword)  # URL解码

    # 参数验证 - 限制关键词长度和内容
    if not keyword:
        return jsonify({'success': False, 'error': '关键词不能为空'})
    if len(keyword) > 50:
        return jsonify({'success': False, 'error': '关键词过长'})
    # 允许中英文、数字和部分符号
    import re
    if not re.match(r'^[\w\u4e00-\u9fa5\s\.\-]+$', keyword):
        return jsonify({'success': False, 'error': '关键词包含非法字符'})

    results = eastmoney_client.search_stock(keyword)
    return jsonify(results)


# ==================== 交易信号 ====================

@app.route('/api/signal')
def get_signal():
    """获取交易信号"""
    code = request.args.get('code', '000002')
    days, err = _parse_int_query(request.args, 'days', 60, min_value=1, max_value=500)
    if err:
        return jsonify({'success': False, 'error': err})

    # 参数验证
    if not _validate_stock_code(code):
        return jsonify({'success': False, 'error': f'无效的股票代码: {code}'})

    # 获取K线数据
    df = None
    signal_source = 'tushare'
    if tushare_client.is_available():
        df = tushare_client.get_kline(code, days=days)
    
    if df is None or df.empty:
        df = eastmoney_client.get_kline(code, days=days)
        signal_source = 'eastmoney'

    if df is None or df.empty:
        df = tencent_client.get_kline(code, days=days)
        signal_source = 'tencent'
    
    if df is None or df.empty:
        df = mock_generator.generate_kline(code, days=days)
        signal_source = 'mock'
    
    if df is None or df.empty:
        return jsonify({'success': False, 'error': '获取数据失败'})
    
    # 计算指标
    df = indicator_calc.calculate(df)
    
    # 生成信号
    result = signal_generator.analyze(df)
    validation = signal_generator.validate_signal_history(df)

    realtime_price = None
    market_price_source = signal_source
    try:
        resp = tencent_client.get_realtime(code)
        if resp:
            realtime_price = float(resp.get('price', 0))
            market_price_source = 'tencent'
    except Exception:
        pass

    signal_price = float(df.iloc[-1]['close']) if len(df) > 0 else 0
    
    return jsonify({
        'success': True,
        'signal': result.get('signal', 'hold'),
        'reason': result.get('reason', ''),
        'strength': result.get('strength', 0),
        'trend': result.get('trend', 'unknown'),
        'details': result.get('details', {}),
        'signal_price': signal_price,
        'market_price': realtime_price if realtime_price else signal_price,
        'signal_date': str(df.iloc[-1]['date'])[:10] if len(df) > 0 else '',
        'signal_basis': '日线收盘信号',
        'market_price_basis': '实时价格，仅供参考' if realtime_price else '收盘价',
        'signal_data_source': signal_source,
        'market_price_source': market_price_source,
        'validation': validation,
    })


@app.route('/api/signals/history')
def get_signal_history():
    """获取历史信号"""
    code = request.args.get('code', '000002')
    days, err = _parse_int_query(request.args, 'days', 120, min_value=1, max_value=1000)
    if err:
        return jsonify({'success': False, 'error': err})

    # 参数验证
    if not _validate_stock_code(code):
        return jsonify({'success': False, 'error': f'无效的股票代码: {code}'})

    df = None
    source = 'tushare'
    if tushare_client.is_available():
        df = tushare_client.get_kline(code, days=days)

    if df is None or df.empty:
        df = eastmoney_client.get_kline(code, days=days)
        source = 'eastmoney'

    if df is None or df.empty:
        df = tencent_client.get_kline(code, days=days)
        source = 'tencent'

    if df is None or df.empty:
        df = mock_generator.generate_kline(code, days=days)
        source = 'mock'

    if df is None or df.empty:
        return jsonify({'success': False, 'error': '获取数据失败'})

    df = indicator_calc.calculate(df)
    validation = signal_generator.validate_signal_history(df)

    return jsonify({
        'success': True,
        'history': validation.get('recent_signals', []),
        'summary': validation.get('summary', {}),
        'buy_summary': validation.get('buy_summary', {}),
        'sell_summary': validation.get('sell_summary', {}),
        'signal_count': validation.get('signal_count', 0),
        'buy_count': validation.get('buy_count', 0),
        'sell_count': validation.get('sell_count', 0),
        'data_source': source,
    })


@app.route('/api/signals/monitor')
def get_monitor_signals():
    """获取监控股票的交易信号"""
    # 监控的股票列表
    watch_list = [
        ('000002', '万科A'),
        ('600036', '招商银行'),
    ]
    
    signals = []
    for code, name in watch_list:
        try:
            # 获取K线数据
            df = None
            if tushare_client.is_available():
                df = tushare_client.get_kline(code, days=60)
            
            if df is None or df.empty:
                df = eastmoney_client.get_kline(code, days=60)
            
            if df is None or df.empty:
                df = mock_generator.generate_kline(code, days=60)
            
            if df is None or df.empty:
                continue
            
            # 计算指标
            df = indicator_calc.calculate(df)
            
            # 生成信号
            result = signal_generator.analyze(df)
            
            # 获取实时价格
            realtime_price = None
            try:
                resp = tencent_client.get_realtime(code)
                if resp:
                    realtime_price = float(resp.get('price', 0))
            except (ValueError, TypeError, KeyError) as e:
                logger.warning(f"获取实时价格失败: {e}")
            
            price = realtime_price if realtime_price else float(df.iloc[-1]['close']) if len(df) > 0 else 0
            
            signals.append({
                'code': code,
                'name': name,
                'signal': result.get('signal', 'hold'),
                'reason': result.get('reason', ''),
                'strength': result.get('strength', 0),
                'trend': result.get('trend', 'unknown'),
                'price': price,
                'realtime': realtime_price is not None,
                'signal_basis': '日线收盘信号',
                'details': result.get('details', {})
            })
        except Exception as e:
            print(f"Error getting signal for {code}: {e}")
    
    return jsonify({
        'success': True,
        'signals': signals,
        'updated': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    })


# ==================== 交易接口 ====================

@app.route('/api/trading/status')
def trading_status():
    """获取交易状态"""
    return jsonify({
        'vnpy_connected': vnpy_client.connected,
        'stock_connected': stock_client.connected,
        'mock_connected': mock_trade_client.connected,
    })


@app.route('/api/trading/connect', methods=['POST'])
def trading_connect():
    """连接交易接口"""
    payload, err = _require_json_payload()
    if err:
        return jsonify({'success': False, 'error': err})

    gateway = payload.get('gateway', 'simnow')  # simnow模拟, ctp期货

    try:
        if gateway == 'simnow':
            success = stock_client.connect()
        else:
            success = vnpy_client.connect(gateway)
        
        return jsonify({
            'success': success,
            'gateway': gateway
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        })


@app.route('/api/trading/account')
def trading_account():
    """获取账户信息"""
    # 优先使用股票客户端
    account = stock_client.get_account()
    if not account:
        account = vnpy_client.get_account()
    if account:
        return jsonify({'success': True, 'account': account})
    return jsonify({'success': False, 'error': '未连接交易接口'})


@app.route('/api/trading/positions')
def trading_positions():
    """获取持仓"""
    positions = stock_client.get_positions()
    if not positions:
        positions = vnpy_client.get_positions()
    if not positions:
        positions = mock_trade_client.get_positions()
    return jsonify({'success': True, 'positions': positions})


@app.route('/api/trading/orders')
def trading_orders():
    """获取委托"""
    orders = stock_client.get_orders()
    if not orders:
        orders = vnpy_client.get_orders()
    if not orders:
        orders = mock_trade_client.get_orders()
    return jsonify({'success': True, 'orders': orders})


@app.route('/api/trading/trades')
def trading_trades():
    """获取成交"""
    trades = vnpy_client.get_trades()
    if not trades:
        trades = mock_trade_client.get_trades()
    return jsonify({'success': True, 'trades': trades})


@app.route('/api/trading/balance')
def trading_balance():
    """获取账户资金"""
    balance = mock_trade_client.get_balance()
    return jsonify({'success': True, 'balance': balance})


@app.route('/api/trading/order', methods=['POST'])
def trading_order():
    """下单"""
    payload, err = _require_json_payload()
    if err:
        return jsonify({'success': False, 'error': err})

    symbol = str(payload.get('symbol', '')).strip()
    direction = str(payload.get('direction', 'long')).lower()
    order_type = str(payload.get('type', 'limit')).lower()

    try:
        price = float(payload.get('price', 0))
    except (TypeError, ValueError):
        return jsonify({'success': False, 'error': '价格必须为数字'})

    try:
        volume = int(payload.get('volume', 0))
    except (TypeError, ValueError):
        return jsonify({'success': False, 'error': '数量必须为整数'})

    # 参数验证
    if not symbol:
        return jsonify({'success': False, 'error': '股票代码不能为空'})
    if not _validate_stock_code(symbol):
        return jsonify({'success': False, 'error': f'无效的股票代码: {symbol}'})
    if direction not in ['long', 'short', 'buy', 'sell']:
        return jsonify({'success': False, 'error': '无效的交易方向'})
    if price <= 0:
        return jsonify({'success': False, 'error': '价格必须大于0'})
    if volume <= 0 or volume % 100 != 0:
        return jsonify({'success': False, 'error': '数量必须是100的整数倍'})
    
    # 优先使用股票客户端
    order_id = stock_client.send_order(symbol, direction, price, volume, order_type)
    if not order_id:
        order_id = vnpy_client.send_order(symbol, direction, price, volume, order_type)
    
    # 如果都失败，使用模拟交易
    if not order_id:
        order_id = mock_trade_client.send_order(symbol, direction, price, volume, order_type)
    
    if order_id:
        return jsonify({'success': True, 'order_id': order_id, 'mode': 'mock' if not stock_client.connected and not vnpy_client.connected else 'live'})
    return jsonify({'success': False, 'error': '下单失败'})


@app.route('/api/trading/cancel', methods=['POST'])
def trading_cancel():
    """撤单"""
    payload, err = _require_json_payload()
    if err:
        return jsonify({'success': False, 'error': err})
    order_id = str(payload.get('order_id', '')).strip()

    if not order_id:
        return jsonify({'success': False, 'error': '订单ID不能为空'})

    if stock_client.cancel_order(order_id) or vnpy_client.cancel_order(order_id) or mock_trade_client.cancel_order(order_id):
        return jsonify({'success': True})
    return jsonify({'success': False, 'error': '撤单失败'})


@app.route('/api/trading/disconnect')
def trading_disconnect():
    """断开连接"""
    vnpy_client.disconnect()
    return jsonify({'success': True})


def run(host='0.0.0.0', port=5002):
    """运行服务器"""
    print(f"🚀 启动 StockQuant Pro Web UI")
    print(f"   本机访问: http://127.0.0.1:{port}")
    print(f"   局域网访问: http://192.168.31.9:{port}")
    app.run(host=host, port=port, debug=os.getenv('FLASK_DEBUG', 'False').lower() == 'true')


if __name__ == '__main__':
    run()
