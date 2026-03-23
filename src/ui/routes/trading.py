"""
交易路由模块
"""

from flask import Blueprint, jsonify, request

trading_bp = Blueprint('trading', __name__, url_prefix='/api/trading')

_clients = {}


def init_clients(clients_dict):
    """初始化客户端引用"""
    _clients.update(clients_dict)


def _require_json_payload():
    """从请求中解析 JSON payload"""
    if not request.is_json:
        return None, "请求必须是 JSON 格式"
    try:
        return request.get_json(), None
    except Exception as e:
        return None, f"JSON 解析失败: {str(e)}"


@trading_bp.route('/status')
def trading_status():
    """获取交易接口连接状态"""
    clients = _clients
    vnpy = clients.get('vnpy_client')
    stock = clients.get('stock_client')
    mock = clients.get('mock_trade_client')

    return jsonify({
        'vnpy_connected': vnpy.connected if vnpy else False,
        'stock_connected': stock.connected if stock else False,
        'mock_connected': mock.connected if mock else False,
    })


@trading_bp.route('/connect', methods=['POST'])
def trading_connect():
    """连接交易接口"""
    payload, err = _require_json_payload()
    if err:
        return jsonify({'success': False, 'error': err})

    gateway = payload.get('gateway', 'simnow')
    clients = _clients

    try:
        if gateway == 'simnow':
            stock = clients.get('stock_client')
            success = stock.connect() if stock else False
        else:
            vnpy = clients.get('vnpy_client')
            success = vnpy.connect(gateway) if vnpy else False

        return jsonify({'success': success, 'gateway': gateway})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


@trading_bp.route('/account')
def trading_account():
    """获取账户信息"""
    clients = _clients
    stock = clients.get('stock_client')
    vnpy = clients.get('vnpy_client')

    account = None
    if stock:
        account = stock.get_account()
    if not account and vnpy:
        account = vnpy.get_account()

    if account:
        return jsonify({'success': True, 'account': account})
    return jsonify({'success': False, 'error': '未连接交易接口'})


@trading_bp.route('/positions')
def trading_positions():
    """获取持仓"""
    clients = _clients
    stock = clients.get('stock_client')
    vnpy = clients.get('vnpy_client')
    mock = clients.get('mock_trade_client')

    positions = None
    if stock:
        positions = stock.get_positions()
    if not positions and vnpy:
        positions = vnpy.get_positions()
    if not positions and mock:
        positions = mock.get_positions()

    return jsonify({'success': True, 'positions': positions or []})


@trading_bp.route('/orders')
def trading_orders():
    """获取委托"""
    clients = _clients
    stock = clients.get('stock_client')
    vnpy = clients.get('vnpy_client')
    mock = clients.get('mock_trade_client')

    orders = None
    if stock:
        orders = stock.get_orders()
    if not orders and vnpy:
        orders = vnpy.get_orders()
    if not orders and mock:
        orders = mock.get_orders()

    return jsonify({'success': True, 'orders': orders or []})


@trading_bp.route('/trades')
def trading_trades():
    """获取成交"""
    clients = _clients
    vnpy = clients.get('vnpy_client')
    mock = clients.get('mock_trade_client')

    trades = None
    if vnpy:
        trades = vnpy.get_trades()
    if not trades and mock:
        trades = mock.get_trades()

    return jsonify({'success': True, 'trades': trades or []})


@trading_bp.route('/balance')
def trading_balance():
    """获取账户资金"""
    clients = _clients
    mock = clients.get('mock_trade_client')

    balance = None
    if mock:
        balance = mock.get_balance()

    return jsonify({'success': True, 'balance': balance})


@trading_bp.route('/order', methods=['POST'])
def trading_order():
    """下单"""
    payload, err = _require_json_payload()
    if err:
        return jsonify({'success': False, 'error': err})

    symbol = str(payload.get('symbol', '')).strip()
    direction = str(payload.get('direction', 'long')).strip().lower()
    order_type = str(payload.get('type', 'limit')).strip().lower()
    price = float(payload.get('price', 0))
    volume = int(payload.get('volume', 0))

    if not symbol:
        return jsonify({'success': False, 'error': '合约代码不能为空'})
    if volume <= 0:
        return jsonify({'success': False, 'error': '数量必须大于0'})

    clients = _clients
    stock = clients.get('stock_client')
    vnpy = clients.get('vnpy_client')
    mock = clients.get('mock_trade_client')

    result = None
    if stock and stock.connected:
        result = stock.send_order(symbol, direction, order_type, price, volume)
    elif vnpy and vnpy.connected:
        result = vnpy.send_order(symbol, direction, order_type, price, volume)
    elif mock:
        result = mock.send_order(symbol, direction, order_type, price, volume)

    if result:
        return jsonify({'success': True, 'order': result})
    return jsonify({'success': False, 'error': '下单失败'})


@trading_bp.route('/cancel', methods=['POST'])
def trading_cancel():
    """撤单"""
    payload, err = _require_json_payload()
    if err:
        return jsonify({'success': False, 'error': err})

    order_id = str(payload.get('order_id', '')).strip()
    if not order_id:
        return jsonify({'success': False, 'error': '委托ID不能为空'})

    clients = _clients
    stock = clients.get('stock_client')
    vnpy = clients.get('vnpy_client')
    mock = clients.get('mock_trade_client')

    success = False
    if stock and stock.connected:
        success = stock.cancel_order(order_id)
    elif vnpy and vnpy.connected:
        success = vnpy.cancel_order(order_id)
    elif mock:
        success = mock.cancel_order(order_id)

    return jsonify({'success': success})


@trading_bp.route('/disconnect')
def trading_disconnect():
    """断开交易接口"""
    clients = _clients
    stock = clients.get('stock_client')
    vnpy = clients.get('vnpy_client')
    mock = clients.get('mock_trade_client')

    if stock:
        stock.disconnect()
    if vnpy:
        vnpy.disconnect()
    if mock:
        mock.disconnect()

    return jsonify({'success': True})
