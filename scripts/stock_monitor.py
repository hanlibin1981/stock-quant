#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
股票信号监控脚本 - 优化版
用于定时任务执行
"""

import os
import sys
import json
import requests
from datetime import datetime

# 飞书配置
APP_ID = "cli_a933a6038e795cee"
APP_SECRET = "BbEax5s72y1hQDLoEKkWlaJDfHdrrRYC"
USER_ID = "162611g9"

# 监控的股票列表 (代码: 名称)
WATCH_LIST = [
    ('000002', '万科A'),
    ('600036', '招商银行'),
]

# 添加项目路径
sys.path.insert(0, '/Users/mac/openclaw-projects/stock-quant/src')

_cached_token = None

def get_token():
    global _cached_token
    if _cached_token:
        return _cached_token
    
    url = "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal"
    try:
        resp = requests.post(url, json={"app_id": APP_ID, "app_secret": APP_SECRET}, timeout=10)
        result = resp.json()
        if result.get('code') == 0:
            _cached_token = result.get('tenant_access_token')
            return _cached_token
    except:
        pass
    return None

def get_signal(code):
    try:
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
        
        # 获取实时价格
        realtime_price = None
        try:
            resp = tencent.get_realtime(code)
            if resp:
                realtime_price = float(resp.get('price', 0))
        except Exception as e:
            print(f"Error fetching realtime for {code}: {e}")
        
        df = None
        if tushare.is_available():
            df = tushare.get_kline(code, days=60)
        if df is None or (hasattr(df, 'empty') and df.empty):
            df = eastmoney.get_kline(code, days=60)
        if df is None or (hasattr(df, 'empty') and df.empty):
            df = mock.generate_kline(code, days=60)
        
        if df is None or (hasattr(df, 'empty') and df.empty):
            return None
        
        # 计算所有指标
        df = indicator.calculate(df)
        result = signal_gen.analyze(df)
        
        # 优先使用实时价格，否则用收盘价
        price = realtime_price if realtime_price else float(df.iloc[-1]['close']) if len(df) > 0 else 0
        
        return {
            'code': code,
            'signal': result.get('signal', 'hold'),
            'reason': result.get('reason', ''),
            'strength': result.get('strength', 0),
            'trend': result.get('trend', 'unknown'),
            'price': price,
            'realtime_price': realtime_price is not None,
            'details': result.get('details', {})
        }
    except Exception as e:
        import traceback
        print(f"Error getting signal for {code}: {e}")
        traceback.print_exc()
        return None

def send_message(token, msg):
    url = "https://open.feishu.cn/open-apis/im/v1/messages"
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    params = {"receive_id_type": "user_id"}
    data = {"receive_id": USER_ID, "msg_type": "text", "content": json.dumps({"text": msg})}
    try:
        resp = requests.post(url, headers=headers, json=data, params=params, timeout=10)
        return resp.json().get('code') == 0
    except:
        return False

def is_trading_hours():
    now = datetime.now()
    if now.weekday() >= 5:
        return False
    current_time = now.hour * 60 + now.minute
    return (570 <= current_time <= 690) or (780 <= current_time <= 900)

def format_signal_message(signals, now_str):
    """优化格式的交易信号消息"""
    trend_emoji = {
        'up': '📈',
        'down': '📉',
        'sideways': '➡️',
        'unknown': '❓'
    }
    
    # 服务访问地址
    web_url = "http://192.168.31.9:5002"
    
    msg = f"📊 股票信号监控 ({now_str})\n"
    msg += "=" * 40 + "\n\n"
    
    for s in signals:
        name = s.get('name', s['code'])
        trend = s.get('trend', 'unknown')
        trend_ico = trend_emoji.get(trend, '❓')
        
        # 信号判断
        if s['signal'] == 'buy':
            emoji = "🟢"
            txt = "买入"
        elif s['signal'] == 'sell':
            emoji = "🔴"
            txt = "卖出"
        else:
            emoji = "➡️"
            txt = "观望"
        
        msg += f"{emoji} {s['code']} {name}\n"
        msg += f"   信号: {txt} | 强度: {s['strength']*100:.0f}% | 趋势: {trend_ico}{trend}\n"
        msg += f"   原因: {s['reason']}\n"
        msg += f"   现价: ¥{s['price']:.2f}"
        if s.get('realtime_price'):
            msg += " (实时)"
        msg += "\n"
        
        # 添加关键技术指标
        details = s.get('details', {})
        if details:
            msg += f"   技术: "
            parts = []
            if details.get('rsi12'):
                parts.append(f"RSI{details['rsi12']:.0f}")
            if details.get('kdj_k'):
                parts.append(f"K{details['kdj_k']:.0f}")
            if details.get('macd_dif') and details.get('macd_dea'):
                diff = details['macd_dif'] - details['macd_dea']
                parts.append(f"MACD{'+' if diff > 0 else ''}{diff:.2f}")
            if details.get('cci'):
                parts.append(f"CCI{details['cci']:.0f}")
            msg += " | ".join(parts) + "\n"
        
        # 支撑/压力位
        if details:
            sup = details.get('support')
            res = details.get('resistance')
            if sup or res:
                msg += f"   区间: "
                if sup:
                    msg += f"支撑¥{sup:.2f} "
                if res:
                    msg += f"压力¥{res:.2f}"
                msg += "\n"
        
        msg += "\n"
    
    # 添加服务访问地址
    msg += f"🌐 Web界面: {web_url}\n"
    
    return msg

def main():
    print(f"[{datetime.now()}] 股票信号监控开始 (优化版)")
    
    if not is_trading_hours():
        print("不在交易时间，跳过")
        return
    
    signals = []
    for code, name in WATCH_LIST:
        s = get_signal(code)
        if s:
            s['name'] = name
            signals.append(s)
            print(f"{code} {name}: {s['signal']} - {s['reason']}")
    
    if not signals:
        print("无信号")
        return
    
    now = datetime.now().strftime('%Y-%m-%d %H:%M')
    msg = format_signal_message(signals, now)
    
    print("\n消息内容:")
    print(msg)
    
    token = get_token()
    if token and send_message(token, msg):
        print("\n✅ 发送成功")
    else:
        print("\n⚠️ 发送失败")

if __name__ == '__main__':
    main()
