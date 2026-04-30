"""
桌面通知模块
支持 plyer 桌面通知和飞书 Webhook 推送
"""

import os
import sys
import logging
import threading
from pathlib import Path
from typing import Optional, Dict, List
from dataclasses import dataclass
from enum import Enum
from datetime import datetime

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from src.utils.logger import get_logger

logger = get_logger(__name__)


class NotificationType(Enum):
    """通知类型"""
    SIGNAL_BUY = "signal_buy"
    SIGNAL_SELL = "signal_sell"
    SIGNAL_ALERT = "signal_alert"
    SYSTEM_INFO = "system_info"
    ERROR = "error"


@dataclass
class Notification:
    """通知对象"""
    title: str
    message: str
    type: NotificationType
    stock_code: str = ""
    stock_name: str = ""
    signal_strength: float = 0.0
    timestamp: str = ""
    
    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")


class DesktopNotifier:
    """
    桌面通知器
    
    支持:
    - plyer 桌面通知
    - 飞书 Webhook
    - 控制台日志
    """
    
    def __init__(self, config: Dict = None):
        self.config = config or {}
        self._plyer = None
        self._feishu_enabled = False
        self._feishu_webhook = self.config.get('feishu_webhook', '')
        
        if self._feishu_webhook:
            self._feishu_enabled = True
            logger.info("飞书通知已启用")
        else:
            # 检查环境变量
            feishu_webhook_env = os.environ.get('FEISHU_WEBHOOK', '')
            if feishu_webhook_env:
                self._feishu_webhook = feishu_webhook_env
                self._feishu_enabled = True
                logger.info("飞书通知已启用(环境变量)")

    def _init_plyer(self):
        """延迟初始化 plyer"""
        if self._plyer is None:
            try:
                from plyer import Notification as PlyerNotification
                self._plyer = PlyerNotification
                logger.debug("plyer 初始化成功")
            except ImportError:
                logger.warning("plyer 未安装，桌面通知不可用。请运行: pip install plyer")
            except Exception as e:
                logger.error(f"plyer 初始化失败: {e}")

    def notify(self, notification: Notification) -> bool:
        """
        发送通知
        
        Args:
            notification: 通知对象
        
        Returns:
            是否发送成功
        """
        success = False
        
        # 飞书通知
        if self._feishu_enabled:
            try:
                self._send_feishu(notification)
                success = True
            except Exception as e:
                logger.error(f"飞书通知发送失败: {e}")
        
        # 桌面通知（ plyer）
        try:
            self._send_desktop(notification)
            success = True
        except Exception as e:
            logger.debug(f"桌面通知发送失败: {e}")
        
        # 控制台日志（总是输出）
        self._log_to_console(notification)
        
        return success

    def _send_desktop(self, notification: Notification):
        """发送桌面通知"""
        self._init_plyer()
        if self._plyer is None:
            return
        
        try:
            self._plyer(
                title=notification.title,
                message=notification.message,
                app_name='StockQuant Pro',
                timeout=10
            )
            logger.debug(f"桌面通知已发送: {notification.title}")
        except Exception as e:
            logger.error(f"桌面通知发送失败: {e}")

    def _send_feishu(self, notification: Notification):
        """发送飞书通知"""
        if not self._feishu_webhook:
            return
        
        import requests
        
        # 根据通知类型构建消息
        if notification.type == NotificationType.SIGNAL_BUY:
            color = "red"  # 买入-红色
            emoji = "🔴"
        elif notification.type == NotificationType.SIGNAL_SELL:
            color = "green"  # 卖出-绿色
            emoji = "🟢"
        else:
            color = "blue"
            emoji = "🔵"
        
        # 构建卡片消息
        card = {
            "msg_type": "interactive",
            "card": {
                "header": {
                    "title": f"{emoji} {notification.title}",
                    "template": color
                },
                "elements": [
                    {
                        "tag": "markdown",
                        "content": f"**股票**: {notification.stock_name} ({notification.stock_code})\n"
                                  f"**信号**: {notification.message}\n"
                                  f"**强度**: {notification.signal_strength:.2f}\n"
                                  f"**时间**: {notification.timestamp}"
                    }
                ]
            }
        }
        
        try:
            resp = requests.post(
                self._feishu_webhook,
                json=card,
                timeout=10,
                headers={'Content-Type': 'application/json'}
            )
            if resp.status_code == 200:
                logger.debug(f"飞书通知已发送: {notification.title}")
            else:
                logger.warning(f"飞书通知发送失败: {resp.status_code} - {resp.text}")
        except Exception as e:
            logger.error(f"飞书通知发送失败: {e}")

    def _log_to_console(self, notification: Notification):
        """输出到控制台"""
        emoji_map = {
            NotificationType.SIGNAL_BUY: "🔴",
            NotificationType.SIGNAL_SELL: "🟢",
            NotificationType.SIGNAL_ALERT: "⚠️",
            NotificationType.SYSTEM_INFO: "ℹ️",
            NotificationType.ERROR: "❌"
        }
        emoji = emoji_map.get(notification.type, "📌")
        logger.info(f"{emoji} [{notification.type.value}] {notification.title}: {notification.message}")

    def notify_signal(
        self,
        signal: str,
        stock_code: str,
        stock_name: str,
        strength: float,
        reason: str
    ) -> bool:
        """
        发送交易信号通知
        
        Args:
            signal: 信号类型 'buy'/'sell'/'hold'
            stock_code: 股票代码
            stock_name: 股票名称
            strength: 信号强度 0-1
            reason: 信号原因
        
        Returns:
            是否发送成功
        """
        if signal == 'hold':
            return False
        
        if signal == 'buy':
            notif_type = NotificationType.SIGNAL_BUY
            title = f"买入信号 {stock_name}"
            message = f"{reason} (强度: {strength:.2f})"
        else:
            notif_type = NotificationType.SIGNAL_SELL
            title = f"卖出信号 {stock_name}"
            message = f"{reason} (强度: {strength:.2f})"
        
        notification = Notification(
            title=title,
            message=message,
            type=notif_type,
            stock_code=stock_code,
            stock_name=stock_name,
            signal_strength=strength,
            timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        )
        
        return self.notify(notification)

    def notify_error(self, error_msg: str, context: str = "") -> bool:
        """发送错误通知"""
        notification = Notification(
            title=f"系统错误 {context}" if context else "系统错误",
            message=error_msg,
            type=NotificationType.ERROR,
            timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        )
        return self.notify(notification)


# 全局通知器实例
_notifier = None
_notifier_lock = threading.Lock()


def get_notifier(config: Dict = None) -> DesktopNotifier:
    """获取通知器单例"""
    global _notifier
    if _notifier is None:
        with _notifier_lock:
            if _notifier is None:
                _notifier = DesktopNotifier(config)
    return _notifier


def send_signal_notification(
    signal: str,
    stock_code: str,
    stock_name: str = "",
    strength: float = 0.0,
    reason: str = ""
) -> bool:
    """
    便捷函数：发送信号通知
    
    Args:
        signal: 'buy'/'sell'/'hold'
        stock_code: 股票代码
        stock_name: 股票名称
        strength: 信号强度
        reason: 信号原因
    
    Returns:
        是否发送成功
    """
    notifier = get_notifier()
    return notifier.notify_signal(signal, stock_code, stock_name, strength, reason)
