"""
回测路由模块
"""

from flask import Blueprint, jsonify, request
import tempfile
import os

backtest_bp = Blueprint('backtest', __name__, url_prefix='/api/backtest')

_clients = {}


def init_clients(clients_dict):
    """初始化客户端引用"""
    _clients.update(clients_dict)


def _validate_strategy(strategy, valid_strategies):
    """验证策略名是否有效"""
    return strategy in valid_strategies


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


def _get_backtest_dataframe(code, days=250):
    """获取回测用的数据"""
    clients = _clients
    tushare = clients.get('tushare_client')
    eastmoney = clients.get('eastmoney_client')
    mock = clients.get('mock_generator')

    df = None
    source = 'tushare'

    if tushare and tushare.is_available():
        df = tushare.get_kline(code, days=days)

    if df is None or (hasattr(df, 'empty') and df.empty):
        if eastmoney:
            df = eastmoney.get_kline(code, days=days)
            source = 'eastmoney'

    if df is None or (hasattr(df, 'empty') and df.empty):
        if mock:
            df = mock.generate_kline(code, days=days)
            source = 'mock'

    return df, source


@backtest_bp.route('')
def run_backtest():
    """运行回测"""
    code = request.args.get('code', '000002')
    strategy = request.args.get('strategy', 'dual_ma')
    params = _parse_backtest_params(request.args)

    from src.utils.validation import validate_stock_code

    if not validate_stock_code(code):
        return jsonify({'success': False, 'error': f'无效的股票代码: {code}'})

    clients = _clients
    strategy_engine = clients.get('strategy_engine')
    backtest_engine = clients.get('backtest_engine')

    if not strategy_engine:
        return jsonify({'success': False, 'error': '策略引擎未初始化'})

    valid_strategies = strategy_engine.get_available_strategies()
    if not _validate_strategy(strategy, valid_strategies):
        return jsonify({'success': False, 'error': f'无效的策略: {strategy}'})

    df, source = _get_backtest_dataframe(code, days=250)
    if df is None or df.empty:
        return jsonify({'success': False, 'error': '获取数据失败'})

    result = backtest_engine.run(df, strategy, params=params)
    if 'error' in result:
        return jsonify({'success': False, 'error': result['error']})

    return jsonify({
        'success': True,
        'trades': result.get('trades', []),
        'metrics': result.get('metrics', {}),
        'benchmark': result.get('benchmark', {}),
        'data_source': source,
    })


@backtest_bp.route('/optimize')
def optimize_backtest():
    """优化回测参数"""
    code = request.args.get('code', '000002')
    strategy = request.args.get('strategy', 'multi_factor')
    metric = request.args.get('metric', 'total_return')

    try:
        top_n = int(request.args.get('top_n', 5))
        top_n = max(1, min(20, top_n))
    except (ValueError, TypeError):
        top_n = 5

    try:
        max_evals = int(request.args.get('max_evals', 50))
        max_evals = max(1, min(200, max_evals))
    except (ValueError, TypeError):
        max_evals = 50

    clients = _clients
    strategy_engine = clients.get('strategy_engine')
    backtest_engine = clients.get('backtest_engine')

    if not strategy_engine or not backtest_engine:
        return jsonify({'success': False, 'error': '引擎未初始化'})

    params = _parse_backtest_params(request.args)
    param_ranges = _parse_optimize_param_ranges(request.args)
    constraints = _parse_optimize_constraints(request.args)

    from src.utils.validation import validate_stock_code

    if not validate_stock_code(code):
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


@backtest_bp.route('/walkforward')
def walkforward_backtest():
    """滚动窗口验证"""
    code = request.args.get('code', '000002')
    strategy = request.args.get('strategy', 'multi_factor')
    metric = request.args.get('metric', 'balanced')

    clients = _clients
    strategy_engine = clients.get('strategy_engine')
    backtest_engine = clients.get('backtest_engine')

    if not strategy_engine or not backtest_engine:
        return jsonify({'success': False, 'error': '引擎未初始化'})

    params = _parse_backtest_params(request.args)
    param_ranges = _parse_optimize_param_ranges(request.args)
    constraints = _parse_optimize_constraints(request.args)
    walkforward_config = _parse_walkforward_config(request.args)

    from src.utils.validation import validate_stock_code

    if not validate_stock_code(code):
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
        },
        'data_source': source,
    })
