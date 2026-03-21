"""
数据管理模块
负责股票数据的获取、存储和缓存
"""

import pandas as pd
import sqlite3
import json
import threading
import logging
from pathlib import Path
from datetime import datetime, timedelta
import requests
from typing import Optional

from src.utils.logger import get_logger

logger = get_logger(__name__)

# 数据库读写锁 (SQLite并发控制)
# 注：SQLite 在多线程下同一连接不能跨线程使用，
# 因此所有数据库访问都必须串行化
_db_lock = threading.Lock()


class StockDataManager:
    """股票数据管理器"""
    
    def __init__(self, data_dir: Path):
        self.data_dir = data_dir
        self.db_path = data_dir / "stocks.db"
        self._init_db()
    
    def _init_db(self):
        """初始化数据库（带版本迁移）"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()

            # Schema 版本表
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS schema_version (
                    version INTEGER PRIMARY KEY,
                    applied_at TEXT
                )
            """)

            # 获取当前版本
            cursor.execute("SELECT MAX(version) FROM schema_version")
            current_version = cursor.fetchone()[0] or 0

            migrations = [
                # Version 1: 初始版本
                {
                    "version": 1,
                    "sql": [
                        """
                        CREATE TABLE IF NOT EXISTS daily_kline (
                            code TEXT,
                            date TEXT,
                            open REAL,
                            high REAL,
                            low REAL,
                            close REAL,
                            volume REAL,
                            amount REAL,
                            PRIMARY KEY (code, date)
                        )
                        """,
                        """
                        CREATE TABLE IF NOT EXISTS stock_info (
                            code TEXT PRIMARY KEY,
                            name TEXT,
                            industry TEXT,
                            market TEXT,
                            list_date TEXT
                        )
                        """,
                    ]
                },
            ]

            for migration in migrations:
                v = migration["version"]
                if v > current_version:
                    for sql in migration["sql"]:
                        cursor.execute(sql)
                    cursor.execute(
                        "INSERT INTO schema_version (version, applied_at) VALUES (?, ?)",
                        (v, datetime.now().isoformat())
                    )
                    logger.info(f"数据库迁移 v{v} 完成")
                    current_version = v

            conn.commit()
    
    def get_stock_data(self, code: str, start_date: str = None, end_date: str = None) -> Optional[pd.DataFrame]:
        """获取股票数据（优先从本地获取）"""
        query = "SELECT * FROM daily_kline WHERE code = ?"
        params = [code]

        if start_date:
            query += " AND date >= ?"
            params.append(start_date)
        if end_date:
            query += " AND date <= ?"
            params.append(end_date)

        query += " ORDER BY date ASC"

        with _db_lock:
            with sqlite3.connect(self.db_path) as conn:
                df = pd.read_sql_query(query, conn, params=params)

        if df.empty:
            return None

        # 转换日期列
        df['date'] = pd.to_datetime(df['date'])
        return df
    
    def save_stock_data(self, code: str, df: pd.DataFrame):
        """保存股票数据到本地（线程安全）"""
        # 确保数据格式正确
        df_save = df.copy()
        df_save['code'] = code
        df_save['date'] = df_save['date'].astype(str)

        if df_save.empty:
            return

        columns = ['code', 'date', 'open', 'high', 'low', 'close', 'volume', 'amount']
        records = df_save[columns].to_dict('records')
        rows = []
        for record in records:
            row = []
            for col in columns:
                value = record.get(col)
                row.append(None if pd.isna(value) else value)
            rows.append(tuple(row))

        insert_sql = """
            INSERT OR REPLACE INTO daily_kline (code, date, open, high, low, close, volume, amount)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """
        with _db_lock:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.executemany(insert_sql, rows)
                conn.commit()
    
    def save_stock_info(self, code: str, name: str, industry: str = None, market: str = "A股"):
        """保存股票基本信息（线程安全）"""
        with _db_lock:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT OR REPLACE INTO stock_info (code, name, industry, market)
                    VALUES (?, ?, ?, ?)
                """, (code, name, industry, market))
                conn.commit()
    
    def get_stock_list(self, market: str = None) -> list:
        """获取股票列表"""
        with sqlite3.connect(self.db_path) as conn:
            if market:
                df = pd.read_sql_query(
                    "SELECT * FROM stock_info WHERE market = ?",
                    conn,
                    params=[market]
                )
            else:
                df = pd.read_sql_query("SELECT * FROM stock_info", conn)

        return df.to_dict('records') if not df.empty else []
    
    def fetch_and_cache(self, code: str, days: int = 250) -> pd.DataFrame:
        """从网络获取数据并缓存"""
        from src.api.eastmoney.client import EastMoneyClient
        
        client = EastMoneyClient()
        df = client.get_kline(code, days=days)
        
        if df is not None and not df.empty:
            self.save_stock_data(code, df)
            
            # 保存基本信息
            realtime = client.get_realtime(code)
            if realtime:
                self.save_stock_info(
                    code, 
                    realtime.get('name', ''),
                    realtime.get('industry', '')
                )
        
        return df
