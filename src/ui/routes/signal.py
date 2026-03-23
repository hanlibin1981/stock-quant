"""
信号路由模块
"""

from flask import Blueprint, jsonify, request
from datetime import datetime, timedelta

signal_bp = Blueprint('signal', __name__, url_prefix='/api')

_clients = {}


def init_clients(clients_dict):
    """初始化客户端引用"""
    _clients.update(clients_dict)


def _get_kline_dataframe(code, days=60):
    """获取K线数据"""
    clients = _clients
    tushare = clients.get('tushare_client')
    eastmoney = clients.get('eastmoney_client')
    mock = clients.get('mock_generator')

    df = None
    if tushare and tushare.is_available():
        df = tushare.get_kline(code, days=days)

    if df is None or (hasattr(df, 'empty') and df.empty):
        if eastmoney:
            df = eastmoney.get_kline(code, days=days)

    if df is None or (hasattr(df, 'empty') and df.empty):
        if mock:
            df = mock.generate_kline(code, days=days)

    return df


@signal_bp.route('/signal')
def get_signal():
    """获取股票信号"""
    code = request.args.get('code', '000002')

    clients = _clients
    indicator_calc = clients.get('indicator_calc')
    signal_gen = clients.get('signal_generator')

    if not indicator_calc or not signal_gen:
        return jsonify({'success': False, 'error': '信号生成器未初始化'})

    df = _get_kline_dataframe(code, days=60)
    if df is None or df.empty:
        return jsonify({'success': False, 'error': '获取数据失败'})

    df = indicator_calc.calculate(df)
    result = signal_gen.analyze(df)

    price = float(df.iloc[-1]['close']) if len(df) > 0 else 0

    return jsonify({
        'success': True,
        'code': code,
        'signal': result.get('signal', 'hold'),
        'reason': result.get('reason', ''),
        'strength': result.get('strength', 0),
        'trend': result.get('trend', 'unknown'),
        'price': price,
        'details': result.get('details', {})
    })


@signal_bp.route('/signals/history')
def get_signal_history():
    """获取历史信号"""
    code = request.args.get('code', '000002')
    days = int(request.args.get('days', 30))

    clients = _clients
    indicator_calc = clients.get('indicator_calc')
    signal_gen = clients.get('signal_generator')

    if not indicator_calc or not signal_gen:
        return jsonify({'success': False, 'error': '信号生成器未初始化'})

    df = _get_kline_dataframe(code, days=days * 2)
    if df is None or df.empty:
        return jsonify({'success': False, 'error': '获取数据失败'})

    df = indicator_calc.calculate(df)

    # 生成每日信号
    signals = []
    for i in range(min(30, len(df) - 1)):
        row = df.iloc[i]
        next_row = df.iloc[i + 1]

        # 简单的信号生成逻辑
        signal = 'hold'
        reason = ''

        if i > 0:
            prev_row = df.iloc[i - 1]

            # 基于MA的简单信号
            if (row.get('ma5') and prev_row.get('ma5') and
                row.get('ma10') and prev_row.get('ma10')):
                if row['ma5'] > row['ma10'] and prev_row['ma5'] <= prev_row['ma10']:
                    signal = 'buy'
                    reason = 'MA金叉'
                elif row['ma5'] < row['ma10'] and prev_row['ma5'] >= prev_row['ma10']:
                    signal = 'sell'
                    reason = 'MA死叉'

        signals.append({
            'date': str(row.name) if hasattr(row, 'name') else i,
            'signal': signal,
            'reason': reason,
            'close': float(row['close']),
            'volume': float(row.get('volume', 0))
        })

    return jsonify({
        'success': True,
        'code': code,
        'signals': signals[-days:] if len(signals) > days else signals
    })


@signal_bp.route('/signals/monitor')
def get_monitor_signals():
    """获取监控列表中所有股票的信号"""
    # 导入监控列表
    import sys
    from pathlib import Path
    project_root = Path(__file__).parent.parent.parent
    sys.path.insert(0, str(project_root / 'scripts'))
    try:
        from watch_stocks import WATCH_LIST
    except ImportError:
        WATCH_LIST = [('000002', '万科A'), ('600036', '招商银行')]  # 默认值

    clients = _clients
    indicator_calc = clients.get('indicator_calc')
    signal_gen = clients.get('signal_generator')

    if not indicator_calc or not signal_gen:
        return jsonify({'success': False, 'error': '信号生成器未初始化'})

    signals = []
    for code, name in WATCH_LIST:
        try:
            df = _get_kline_dataframe(code, days=60)
            if df is None or df.empty:
                continue

            df = indicator_calc.calculate(df)
            result = signal_gen.analyze(df)

            price = float(df.iloc[-1]['close']) if len(df) > 0 else 0

            signals.append({
                'code': code,
                'name': name,
                'signal': result.get('signal', 'hold'),
                'reason': result.get('reason', ''),
                'strength': result.get('strength', 0),
                'trend': result.get('trend', 'unknown'),
                'price': price,
            })
        except Exception as e:
            pass

    return jsonify({
        'success': True,
        'signals': signals,
        'count': len(signals)
    })


@signal_bp.route('/strategies')
def get_strategies():
    """获取可用策略列表"""
    clients = _clients
    strategy_engine = clients.get('strategy_engine')

    if not strategy_engine:
        return jsonify({'success': False, 'error': '策略引擎未初始化'})

    strategies = strategy_engine.get_available_strategies()
    return jsonify(strategies)
