"""
数据管理模块
负责股票数据的获取、存储和缓存
"""

import pandas as pd
import sqlite3
import json
from pathlib import Path
from datetime import datetime, timedelta
import requests
from typing import Optional


class StockDataManager:
    """股票数据管理器"""
    
    def __init__(self, data_dir: Path):
        self.data_dir = data_dir
        self.db_path = data_dir / "stocks.db"
        self._init_db()
    
    def _init_db(self):
        """初始化数据库"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # 股票日线数据表
        cursor.execute("""
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
        """)
        
        # 股票基本信息表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS stock_info (
                code TEXT PRIMARY KEY,
                name TEXT,
                industry TEXT,
                market TEXT,
                list_date TEXT
            )
        """)
        
        conn.commit()
        conn.close()
    
    def get_stock_data(self, code: str, start_date: str = None, end_date: str = None) -> Optional[pd.DataFrame]:
        """获取股票数据（优先从本地获取）"""
        conn = sqlite3.connect(self.db_path)
        
        query = "SELECT * FROM daily_kline WHERE code = ?"
        params = [code]
        
        if start_date:
            query += " AND date >= ?"
            params.append(start_date)
        if end_date:
            query += " AND date <= ?"
            params.append(end_date)
        
        query += " ORDER BY date ASC"
        
        df = pd.read_sql_query(query, conn, params=params)
        conn.close()
        
        if df.empty:
            return None
        
        # 转换日期列
        df['date'] = pd.to_datetime(df['date'])
        return df
    
    def save_stock_data(self, code: str, df: pd.DataFrame):
        """保存股票数据到本地"""
        conn = sqlite3.connect(self.db_path)
        
        # 确保数据格式正确
        df_save = df.copy()
        df_save['code'] = code
        df_save['date'] = df_save['date'].astype(str)
        
        df_save.to_sql('daily_kline', conn, if_exists='append', index=False)
        conn.close()
    
    def save_stock_info(self, code: str, name: str, industry: str = None, market: str = "A股"):
        """保存股票基本信息"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT OR REPLACE INTO stock_info (code, name, industry, market)
            VALUES (?, ?, ?, ?)
        """, (code, name, industry, market))
        
        conn.commit()
        conn.close()
    
    def get_stock_list(self, market: str = None) -> list:
        """获取股票列表"""
        conn = sqlite3.connect(self.db_path)
        
        if market:
            df = pd.read_sql_query(
                "SELECT * FROM stock_info WHERE market = ?", 
                conn, 
                params=[market]
            )
        else:
            df = pd.read_sql_query("SELECT * FROM stock_info", conn)
        
        conn.close()
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
