#!/usr/bin/env python3
"""
股票信号监控脚本
每5分钟执行，获取股票信号并发送到飞书
"""

import os
import sys
import json
import requests
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SRC_ROOT = PROJECT_ROOT / 'src'
ENV_FILE = PROJECT_ROOT / 'config' / 'production.env'

# 添加项目路径
sys.path.insert(0, str(SRC_ROOT))

# 飞书配置 - 使用用户允许列表中的ID
APP_ID = "cli_a933a6038e795cee"
APP_SECRET = "BbEax5s72y1hQDLoEKkWlaJDfHdrrRYC"
USER_ID = "162611g9"  # 用户ID

# 监控的股票列表
WATCH_LIST = ['000002', '600519', '600036', '000858', '000001']

# 缓存token
_cached_token = None
_token_expires_at = 0


def load_env_file():
    """加载本地生产环境变量，确保脚本模式下也能读取 TUSHARE_TOKEN。"""
    if not ENV_FILE.exists():
        return

    for raw_line in ENV_FILE.read_text(encoding='utf-8').splitlines():
        line = raw_line.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        key, value = line.split('=', 1)
        os.environ.setdefault(key.strip(), value.strip())


def get_tenant_access_token():
    """获取飞书 tenant_access_token"""
    global _cached_token, _token_expires_at
    
    import time
    if _cached_token and time.time() < _token_expires_at:
        return _cached_token
    
    url = "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal"
    data = {"app_id": APP_ID, "app_secret": APP_SECRET}
    try:
        resp = requests.post(url, json=data, timeout=10)
        result = resp.json()
        if result.get('code') == 0:
            _cached_token = result.get('tenant_access_token')
            _token_expires_at = time.time() + 7000  # 约2小时后过期
            return _cached_token
    except Exception as e:
        print(f"获取token失败: {e}")
    return None


def send_feishu_message(token, message):
    """发送飞书消息 - 多种方式尝试"""
    
    # 方式1: 使用 IM API 发送文本消息
    url = "https://open.feishu.cn/open-apis/im/v1/messages"
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    
    # 尝试发送给用户 (open_id)
    for id_type, receive_id in [("open_id", None), ("user_id", USER_ID)]:
        if receive_id is None:
            # 先获取用户的 open_id
            get_url = f"https://open.feishu.cn/open-apis/contact/v3/users/{receive_id or USER_ID}"
            try:
                resp = requests.get(get_url, headers=headers, timeout=10)
                result = resp.json()
                if result.get('code') == 0:
                    receive_id = result.get('data', {}).get('user', {}).get('open_id')
            except:
                pass
        
        if receive_id:
            params = {"receive_id_type": id_type}
            data = {"receive_id": receive_id, "msg_type": "text", "content": json.dumps({"text": message})}
            try:
                resp = requests.post(url, headers=headers, json=data, params=params, timeout=10)
                result = resp.json()
                if result.get('code') == 0:
                    return True
                print(f"发送失败 ({id_type}): {result.get('msg')}")
            except Exception as e:
                print(f"发送异常: {e}")
    
    return False


def get_stock_signal(code):
    """获取股票信号"""
    from api.eastmoney import EastMoneyClient
    from api.tushare import get_tushare_client
    from api.mock_data import MockDataGenerator
    from api.tencent import get_tencent_client
    from core.indicator import IndicatorCalculator
    from core.signal import get_signal_generator
    
    tushare = get_tushare_client()
    eastmoney = EastMoneyClient()
    tencent = get_tencent_client()
    mock = MockDataGenerator()
    indicator = IndicatorCalculator()
    signal_gen = get_signal_generator()
    
    df = None
    kline_source = 'tushare'
    if tushare.is_available():
        df = tushare.get_kline(code, days=60)
    if df is None or df.empty:
        df = eastmoney.get_kline(code, days=60)
        kline_source = 'eastmoney'
    if df is None or df.empty:
        df = tencent.get_kline(code, days=60)
        kline_source = 'tencent'
    if df is None or df.empty:
        df = mock.generate_kline(code, days=60)
        kline_source = 'mock'
    if df is None or df.empty:
        return None
    
    df = indicator.calculate(df)
    result = signal_gen.analyze(df)
    
    return {
        'code': code,
        'signal': result.get('signal', 'hold'),
        'reason': result.get('reason', ''),
        'strength': result.get('strength', 0),
        'price': float(df.iloc[-1]['close']) if len(df) > 0 else 0,
        'kline_source': kline_source,
    }


def is_trading_day():
    now = datetime.now()
    return now.weekday() < 5


def is_trading_hours():
    # 交易时间: 9:30-11:30, 13:00-15:00
    now = datetime.now()
    current_time = now.hour * 60 + now.minute
    return (570 <= current_time <= 690) or (780 <= current_time <= 900)


def main():
    load_env_file()
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 股票信号监控任务开始")
    
    if not is_trading_day():
        print("今天不是交易日，跳过")
        return
    
    if not is_trading_hours():
        print("不在交易时间，跳过")
        return
    
    signals = []
    for code in WATCH_LIST:
        try:
            signal = get_stock_signal(code)
            if signal:
                signals.append(signal)
                print(
                    f"股票 {code}: {signal['signal']} - {signal['reason']} "
                    f"[kline={signal.get('kline_source', 'unknown')}]"
                )
        except Exception as e:
            print(f"获取 {code} 信号失败: {e}")
    
    if not signals:
        print("未获取到任何信号")
        return
    
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    message = f"📈 股票信号播报 ({now})\n\n"
    
    for s in signals:
        emoji = "🟢" if s['signal'] == 'buy' else "🔴" if s['signal'] == 'sell' else "➡️"
        signal_text = "买入" if s['signal'] == 'buy' else "卖出" if s['signal'] == 'sell' else "观望"
        message += f"{emoji} {s['code']}: {signal_text} (强度:{s['strength']*100:.0f}%)\n"
        message += f"   原因: {s['reason']}\n"
        message += f"   现价: ¥{s['price']:.2f}\n\n"
    
    print("\n发送消息到飞书...")
    token = get_tenant_access_token()
    if token and send_feishu_message(token, message):
        print("✅ 发送成功")
    else:
        print("⚠️ 发送失败，请检查飞书应用权限")


if __name__ == '__main__':
    main()
