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

# 添加项目路径
project_root = Path('/Users/mac/openclaw-projects/stock-quant')
sys.path.insert(0, str(project_root / 'src'))

# 飞书配置
APP_ID = "cli_a933a6038e795cee"
APP_SECRET = "BbEax5s72y1hQDLoEKkWlaJDfHdrrRYC"
USER_ID = "162611g9"  # 用户ID

# 监控的股票列表（从共用配置导入）
from watch_stocks import WATCH_LIST

# 缓存token
_cached_token = None
_token_expires_at = 0


def _load_env_file():
    """加载环境变量，确保能读取 TUSHARE_TOKEN"""
    env_file = project_root / 'config' / 'production.env'
    if not env_file.exists():
        return
    for line in env_file.read_text(encoding='utf-8').splitlines():
        line = line.strip()
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
    """发送飞书消息到用户（通过 user_id）"""
    url = "https://open.feishu.cn/open-apis/im/v1/messages"
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    params = {"receive_id_type": "user_id"}
    data = {
        "receive_id": USER_ID,
        "msg_type": "text",
        "content": json.dumps({"text": message}, ensure_ascii=False)
    }
    try:
        resp = requests.post(url, headers=headers, json=data, params=params, timeout=10)
        result = resp.json()
        if result.get('code') == 0:
            return True
        print(f"发送失败: {result.get('msg')} (code={result.get('code')})")
        return False
    except Exception as e:
        print(f"发送异常: {e}")
        return False


def get_stock_signal(code):
    """获取股票信号 - 多周期验证版"""
    from api.eastmoney import EastMoneyClient
    from api.tushare import get_tushare_client
    from api.mock_data import MockDataGenerator
    from core.indicator import IndicatorCalculator
    from core.signal import get_signal_generator
    
    tushare = get_tushare_client()
    eastmoney = EastMoneyClient()
    mock = MockDataGenerator()
    indicator = IndicatorCalculator()
    signal_gen = get_signal_generator()
    
    # 获取各周期数据
    data_sources = {}
    
    # 日线 (D) - 60天
    df_daily = None
    if tushare.is_available():
        df_daily = tushare.get_kline(code, days=60, ktype='D')
    if df_daily is None or df_daily.empty:
        df_daily = eastmoney.get_kline(code, days=60)
    if df_daily is None or df_daily.empty:
        df_daily = mock.generate_kline(code, days=60)
    if df_daily is not None and not df_daily.empty:
        data_sources['D'] = df_daily
    
    # 周线 (W) - 40周
    if tushare.is_available():
        df_weekly = tushare.get_kline(code, days=280, ktype='W')
        if df_weekly is not None and not df_weekly.empty:
            data_sources['W'] = df_weekly
    
    # 月线 (M) - 24月
    if tushare.is_available():
        df_monthly = tushare.get_kline(code, days=720, ktype='M')
        if df_monthly is not None and not df_monthly.empty:
            data_sources['M'] = df_monthly
    
    if not data_sources:
        return None
    
    # 多周期分析
    if len(data_sources) > 1:
        # 多周期验证
        result = signal_gen.analyze_multi_period(code, data_sources)
        # 标记是否为多周期信号
        is_multi = len(data_sources) > 1
    else:
        # 单周期分析
        df = indicator.calculate(data_sources.get('D', list(data_sources.values())[0]))
        result = signal_gen.analyze(df)
        is_multi = False
    
    # 获取当前价格
    price = 0
    if 'D' in data_sources:
        price = float(data_sources['D'].iloc[-1]['close']) if len(data_sources['D']) > 0 else 0
    
    return {
        'code': code, 
        'signal': result.get('signal', 'hold'), 
        'reason': result.get('reason', ''), 
        'strength': result.get('strength', 0),
        'price': price,
        'is_multi_period': is_multi,
        'period_results': result.get('period_results', {})
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
    _load_env_file()
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 股票信号监控任务开始")
    
    if not is_trading_day():
        print("今天不是交易日，跳过")
        return
    
    if not is_trading_hours():
        print("不在交易时间，跳过")
        return
    
    signals = []
    for code, name in WATCH_LIST:
        try:
            signal = get_stock_signal(code)
            if signal:
                signal['name'] = name
                signals.append(signal)
                print(f"股票 {code} {name}: {signal['signal']} - {signal['reason']}")
        except Exception as e:
            print(f"获取 {code} 信号失败: {e}")
    
    if not signals:
        print("未获取到任何信号")
        return
    
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    
    # 检查是否有任何多周期信号
    has_multi = any(s.get('is_multi_period', False) for s in signals)
    title = "📈 多周期验证信号播报" if has_multi else "📈 股票信号播报"
    message = f"{title} ({now})\n\n"
    
    for s in signals:
        emoji = "🟢" if s['signal'] == 'buy' else "🔴" if s['signal'] == 'sell' else "➡️"
        signal_text = "买入" if s['signal'] == 'buy' else "卖出" if s['signal'] == 'sell' else "观望"
        
        # 多周期标记
        multi_tag = " [多周期✅]" if s.get('is_multi_period', False) else ""
        
        message += f"{emoji} {s['code']} {s.get('name', '')}: {signal_text}{multi_tag} (强度:{s['strength']*100:.0f}%)\n"
        message += f"   原因: {s['reason']}\n"
        
        # 显示各周期信号
        if s.get('period_results'):
            periods = []
            for p, r in s['period_results'].items():
                p_name = {'D': '日', 'W': '周', 'M': '月'}.get(p, p)
                p_signal = {'buy': '↑', 'sell': '↓', 'hold': '→'}.get(r['signal'], '?')
                p_trend = {'up': '↗', 'down': '↘', 'sideways': '→'}.get(r['trend'], '?')
                periods.append(f"{p_name}{p_signal}{p_trend}")
            message += f"   周期: {' '.join(periods)}\n"
        
        message += f"   现价: ¥{s['price']:.2f}\n\n"
    
    print("\n发送消息到飞书...")
    token = get_tenant_access_token()
    if token and send_feishu_message(token, message):
        print("✅ 发送成功")
    else:
        print("⚠️ 发送失败，请检查飞书应用权限")


if __name__ == '__main__':
    main()
