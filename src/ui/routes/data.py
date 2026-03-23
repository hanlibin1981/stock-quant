"""
数据路由模块 - 行情数据相关
"""

from flask import Blueprint, render_template, jsonify, request
import pandas as pd

data_bp = Blueprint('data', __name__, url_prefix='/api')


# 全局客户端引用（由 web_app.py 传入）
_clients = {}


def init_clients(clients_dict):
    """初始化客户端引用"""
    _clients.update(clients_dict)


@data_bp.route('/')
def index():
    """主页"""
    return render_template('index.html')


@data_bp.route('/realtime')
def get_realtime():
    """获取实时行情（优先实时，失败则返回日K数据）"""
    code = request.args.get('code', '000002')
    clients = _clients

    data = None
    source = ''

    # 优先使用 TuShare
    tushare = clients.get('tushare_client')
    if tushare and tushare.is_available():
        data = tushare.get_realtime(code)
        if data:
            source = 'tushare'

    # 如果TuShare失败，使用腾讯财经
    if not data:
        tencent = clients.get('tencent_client')
        if tencent:
            data = tencent.get_realtime(code)
            if data:
                source = 'tencent'

    # 如果腾讯失败，使用东方财富
    if not data:
        eastmoney = clients.get('eastmoney_client')
        if eastmoney:
            data = eastmoney.get_realtime(code)
            if data:
                source = 'eastmoney'

    # 如果都没有，返回日K数据
    if not data:
        df = None
        if tushare and tushare.is_available():
            df = tushare.get_kline(code, days=1)
        if df is None or (hasattr(df, 'empty') and df.empty):
            eastmoney = clients.get('eastmoney_client')
            if eastmoney:
                df = eastmoney.get_kline(code, days=1)
        if df is None or (hasattr(df, 'empty') and df.empty):
            mock = clients.get('mock_generator')
            if mock:
                df = mock.generate_kline(code, days=1)

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
        mock = clients.get('mock_generator')
        if mock:
            data = mock.generate_realtime(code)
            data['source'] = 'mock'

    return jsonify(data)


@data_bp.route('/status')
def get_status():
    """获取数据源状态"""
    clients = _clients
    tushare = clients.get('tushare_client')
    return jsonify({
        'eastmoney': True,
        'tushare': tushare.is_available() if tushare else False,
        'mock': True
    })


@data_bp.route('/kline')
def get_kline():
    """获取K线数据"""
    code = request.args.get('code', '000002')
    days = int(request.args.get('days', 60))
    clients = _clients

    df = None
    source = 'tushare'

    tushare = clients.get('tushare_client')
    if tushare and tushare.is_available():
        df = tushare.get_kline(code, days=days)

    if df is None or (hasattr(df, 'empty') and df.empty):
        eastmoney = clients.get('eastmoney_client')
        if eastmoney:
            df = eastmoney.get_kline(code, days=days)
            source = 'eastmoney'

    if df is None or (hasattr(df, 'empty') and df.empty):
        tencent = clients.get('tencent_client')
        if tencent:
            df = tencent.get_kline(code, days=days)
            source = 'tencent'

    if df is None or (hasattr(df, 'empty') and df.empty):
        mock = clients.get('mock_generator')
        if mock:
            df = mock.generate_kline(code, days=days)
            source = 'mock'

    if df is None or df.empty:
        return jsonify({'success': False, 'error': '获取数据失败'})

    from .utils import df_to_json_records
    return jsonify({
        'success': True,
        'data': df_to_json_records(df),
        'source': source,
        'count': len(df)
    })


@data_bp.route('/indicators')
def get_indicators():
    """获取技术指标"""
    code = request.args.get('code', '000002')
    days = int(request.args.get('days', 60))
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

    if df is None or df.empty:
        return jsonify({'success': False, 'error': '获取数据失败'})

    # 计算指标
    indicator_calc = clients.get('indicator_calc')
    if indicator_calc:
        df = indicator_calc.calculate(df)

    from .utils import df_to_json_records
    return jsonify({
        'success': True,
        'data': df_to_json_records(df),
        'count': len(df)
    })


@data_bp.route('/search')
def search_stock():
    """搜索股票"""
    keyword = request.args.get('keyword', '')
    if not keyword or len(keyword) < 1:
        return jsonify({'success': False, 'error': '关键词太短'})

    clients = _clients
    eastmoney = clients.get('eastmoney_client')

    # 使用东方财富搜索
    try:
        if eastmoney:
            results = eastmoney.search_stocks(keyword)
            return jsonify({'success': True, 'results': results})
        return jsonify({'success': False, 'error': '数据源不可用'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})
