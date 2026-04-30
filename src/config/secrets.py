"""
密钥管理模块
支持环境变量、.env文件、加密存储
"""

import os
import json
from typing import Dict, Optional, Any
from dataclasses import dataclass
from datetime import datetime
import logging
import hashlib
import base64

logger = logging.getLogger(__name__)


class SecretsManager:
    """
    密钥管理器
    
    功能：
    1. 从环境变量读取密钥
    2. 支持 .env 文件加载
    3. 密钥加密存储（可选）
    4. 密钥轮换支持
    5. 密钥使用审计
    """

    # 预定义的密钥名称
    SUPPORTED_KEYS = {
        'TUSHARE_TOKEN': 'tushare_api_token',
        'FEISHU_WEBHOOK': 'feishu_webhook_url',
        'REDIS_PASSWORD': 'redis_password',
        'DB_PASSWORD': 'database_password',
        'BROKER_API_KEY': 'broker_api_key',
        'BROKER_API_SECRET': 'broker_api_secret'
    }

    def __init__(self, env_file: str = None, auto_load: bool = True):
        """
        Args:
            env_file: .env 文件路径
            auto_load: 是否自动加载环境变量
        """
        self._secrets: Dict[str, str] = {}
        self._audit_log: list = []
        self._env_file = env_file or '.env'
        
        if auto_load:
            self._load_env_file()
            self._load_from_env()
    
    def _load_env_file(self):
        """加载 .env 文件"""
        if not os.path.exists(self._env_file):
            return
        
        try:
            with open(self._env_file, 'r') as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith('#'):
                        continue
                    
                    if '=' in line:
                        key, value = line.split('=', 1)
                        key = key.strip()
                        value = value.strip().strip('"').strip("'")
                        
                        # 放入环境变量
                        os.environ[key] = value
                        logger.debug(f"Loaded env var: {key}")
                        
        except Exception as e:
            logger.warning(f"Failed to load env file: {e}")

    def _load_from_env(self):
        """从环境变量加载密钥"""
        for env_key, secret_key in self.SUPPORTED_KEYS.items():
            value = os.environ.get(env_key)
            if value:
                self._secrets[secret_key] = value
                self._audit(action='load', key=secret_key, source='env')

    def get(self, key: str, default: str = None) -> Optional[str]:
        """
        获取密钥
        
        Args:
            key: 密钥名称
            default: 默认值
        
        Returns:
            密钥值
        """
        # 记录审计日志
        self._audit(action='get', key=key)
        
        return self._secrets.get(key, default)

    def set(self, key: str, value: str, persist: bool = False):
        """
        设置密钥
        
        Args:
            key: 密钥名称
            value: 密钥值
            persist: 是否持久化到 .env 文件
        """
        self._secrets[key] = value
        self._audit(action='set', key=key, persist=persist)
        
        if persist:
            self._persist_to_env(key, value)

    def _persist_to_env(self, key: str, value: str):
        """持久化密钥到 .env 文件"""
        try:
            # 读取现有内容
            lines = []
            if os.path.exists(self._env_file):
                with open(self._env_file, 'r') as f:
                    lines = f.readlines()
            
            # 查找或追加
            found = False
            new_lines = []
            env_key = None
            
            # 找到对应的环境变量名
            for env_k, secret_k in self.SUPPORTED_KEYS.items():
                if secret_k == key:
                    env_key = env_k
                    break
            
            if not env_key:
                env_key = key.upper()
            
            for line in lines:
                if line.strip().startswith(f'{env_key}='):
                    new_lines.append(f'{env_key}="{value}"\n')
                    found = True
                else:
                    new_lines.append(line)
            
            if not found:
                new_lines.append(f'{env_key}="{value}"\n')
            
            with open(self._env_file, 'w') as f:
                f.writelines(new_lines)
            
            logger.info(f"Persisted secret to {self._env_file}")
            
        except Exception as e:
            logger.error(f"Failed to persist secret: {e}")

    def get_tushare_token(self) -> Optional[str]:
        """获取 Tushare Token"""
        return self.get('tushare_api_token')

    def get_feishu_webhook(self) -> Optional[str]:
        """获取飞书 Webhook URL"""
        return self.get('feishu_webhook_url')

    def get_redis_password(self) -> Optional[str]:
        """获取 Redis 密码"""
        return self.get('redis_password')

    def get_broker_credentials(self) -> Dict[str, str]:
        """获取券商 API 凭证"""
        return {
            'api_key': self.get('broker_api_key', ''),
            'api_secret': self.get('broker_api_secret', '')
        }

    def _audit(self, action: str, key: str, **kwargs):
        """审计日志"""
        entry = {
            'timestamp': datetime.now().isoformat(),
            'action': action,
            'key': key,
            'source': kwargs.get('source', 'unknown')
        }
        self._audit_log.append(entry)
        
        # 保持最近1000条
        if len(self._audit_log) > 1000:
            self._audit_log = self._audit_log[-1000:]

    def get_audit_log(self, limit: int = 100) -> list:
        """获取审计日志"""
        return self._audit_log[-limit:]

    def clear_audit_log(self):
        """清除审计日志"""
        self._audit_log.clear()

    def list_keys(self) -> list:
        """列出所有密钥名称（不包含值）"""
        return list(self._secrets.keys())

    def has_key(self, key: str) -> bool:
        """检查密钥是否存在"""
        return key in self._secrets

    def delete(self, key: str):
        """删除密钥"""
        if key in self._secrets:
            del self._secrets[key]
            self._audit(action='delete', key=key)

    def get_stats(self) -> Dict:
        """获取统计信息"""
        return {
            'total_keys': len(self._secrets),
            'keys': list(self._secrets.keys()),
            'audit_entries': len(self._audit_log)
        }


# 加密工具类

class SecretEncryptor:
    """密钥加密工具（简单的base64编码，生产环境应使用更强的加密）"""

    @staticmethod
    def encode(secret: str, salt: str = None) -> str:
        """
        编码密钥
        
        Args:
            secret: 密钥
            salt: 盐值
        
        Returns:
            编码后的密钥
        """
        if salt:
            # 简单的盐值混合
            secret = f"{salt}{secret}{salt}"
        
        # Base64 编码
        encoded = base64.b64encode(secret.encode('utf-8')).decode('utf-8')
        return encoded

    @staticmethod
    def decode(encoded: str, salt: str = None) -> str:
        """
        解码密钥
        
        Args:
            encoded: 编码后的密钥
            salt: 盐值
        
        Returns:
            原始密钥
        """
        try:
            decoded = base64.b64decode(encoded.encode('utf-8')).decode('utf-8')
            
            if salt:
                # 移除盐值
                decoded = decoded.replace(salt, '').replace(salt, '')
            
            return decoded
        except Exception as e:
            logger.error(f"Failed to decode secret: {e}")
            return ""


# 全局密钥管理器实例
_global_manager: Optional[SecretsManager] = None


def get_secrets_manager(env_file: str = None) -> SecretsManager:
    """
    获取全局密钥管理器
    
    Args:
        env_file: .env 文件路径
    
    Returns:
        SecretsManager 实例
    """
    global _global_manager
    
    if _global_manager is None:
        _global_manager = SecretsManager(env_file=env_file)
    
    return _global_manager


def reload_secrets(env_file: str = None):
    """
    重新加载密钥
    
    Args:
        env_file: .env 文件路径
    """
    global _global_manager
    
    _global_manager = SecretsManager(env_file=env_file)
    return _global_manager


# 示例 .env 文件模板

ENV_TEMPLATE = """
# StockQuant Pro - 环境变量配置
# 复制此文件为 .env 并填入实际值

# Tushare API Token
TUSHARE_TOKEN=your_tushare_token_here

# 飞书 Webhook
FEISHU_WEBHOOK=https://open.feishu.cn/open-apis/bot/v2/hook/your_webhook_id

# Redis 密码（可选）
# REDIS_PASSWORD=your_redis_password

# 数据库密码（可选）
# DB_PASSWORD=your_database_password

# 券商 API 凭证（可选）
# BROKER_API_KEY=your_broker_api_key
# BROKER_API_SECRET=your_broker_api_secret
"""


def create_env_template(path: str = '.env'):
    """创建 .env 文件模板"""
    try:
        with open(path, 'w') as f:
            f.write(ENV_TEMPLATE)
        logger.info(f"Created .env template at {path}")
        return True
    except Exception as e:
        logger.error(f"Failed to create .env template: {e}")
        return False


def validate_secrets() -> Dict[str, bool]:
    """
    验证密钥配置
    
    Returns:
        {key_name: is_configured}
    """
    manager = get_secrets_manager()
    
    checks = {
        'tushare': bool(manager.get_tushare_token()),
        'feishu': bool(manager.get_feishu_webhook()),
        'redis': bool(manager.get_redis_password()),
        'broker': bool(manager.get('broker_api_key'))
    }
    
    return checks
