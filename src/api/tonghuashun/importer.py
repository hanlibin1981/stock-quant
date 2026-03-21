"""
同花顺数据导入模块
支持导入同花顺导出的数据文件
"""

import pandas as pd
import os
import logging
from pathlib import Path
from typing import Optional, List, Dict
import struct

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class TonghuashunImporter:
    """同花顺数据导入器"""
    
    # 支持的文件格式
    SUPPORTED_EXTENSIONS = ['.otd', '.h5', '.xlsx', '.xls', '.csv', '.txt']
    
    def __init__(self):
        self.imported_stocks = []
    
    def import_file(self, filepath: str) -> Optional[pd.DataFrame]:
        """
        导入同花顺数据文件
        
        Args:
            filepath: 文件路径
        
        Returns:
            DataFrame or None
        """
        path = Path(filepath)
        
        if not path.exists():
            print(f"File not found: {filepath}")
            return None
        
        ext = path.suffix.lower()
        
        if ext == '.otd':
            return self._import_otd(filepath)
        elif ext == '.h5':
            return self._import_h5(filepath)
        elif ext in ['.xlsx', '.xls']:
            return self._import_excel(filepath)
        elif ext == '.csv':
            return self._import_csv(filepath)
        elif ext == '.txt':
            return self._import_txt(filepath)
        else:
            print(f"Unsupported file format: {ext}")
            return None
    
    def _import_otd(self, filepath: str) -> Optional[pd.DataFrame]:
        """
        导入 .otd 格式（同花顺自定义格式）

        OTD 是同花顺的专有二进制格式，文件结构：
        - 文件头: 64 字节（含字段说明，数量等元信息）
        - 数据记录: 每条 32 字节

        注意: OTD 二进制格式未经公开文档验证，当前的二进制解析是尽力而为。
        如果解析失败会自动 fallback 到文本解析。真实场景下建议导出为 CSV
        或使用同花顺官方工具转码后再导入。
        """
        try:
            with open(filepath, 'rb') as f:
                header = f.read(64)
                if len(header) < 64:
                    raise ValueError("OTD 文件头不完整")

                records = []

                while True:
                    data = f.read(32)
                    if not data or len(data) < 32:
                        break

                    try:
                        # 以下为基于观察经验的猜测性解析，并非官方文档确认
                        # 实际 OTD 格式可能因版本而异
                        year = struct.unpack('<H', data[0:2])[0]  # 小端序 ushort
                        month = data[2]
                        day = data[3]
                        if year < 1990 or year > 2100 or month < 1 or month > 12 or day < 1 or day > 31:
                            # 字段解析异常，尝试当作文本处理
                            break

                        date_str = f"{year:04d}-{month:02d}-{day:02d}"
                        close = struct.unpack('<I', data[4:8])[0] / 100.0  # 整数形式价格
                        open_price = struct.unpack('<I', data[8:12])[0] / 100.0
                        high = struct.unpack('<I', data[12:16])[0] / 100.0
                        low = struct.unpack('<I', data[16:20])[0] / 100.0
                        volume = struct.unpack('<I', data[20:24])[0]

                        records.append({
                            'date': date_str,
                            'open': open_price,
                            'close': close,
                            'high': high,
                            'low': low,
                            'volume': volume,
                        })
                    except (struct.error, ValueError, KeyError) as e:
                        logger.debug(f"OTD 二进制解析跳过: {e}")
                        break

                if records:
                    return pd.DataFrame(records)

        except Exception as e:
            logger.warning(f"OTD 二进制解析失败 ({e})，尝试文本解析")

        # Fallback: 当作文本处理
        return self._import_txt(filepath)
    
    def _import_h5(self, filepath: str) -> Optional[pd.DataFrame]:
        """导入 HDF5 格式"""
        try:
            import h5py
            
            with h5py.File(filepath, 'r') as f:
                # 遍历HDF5结构
                data_dict = {}
                
                def visit_items(name, obj):
                    if isinstance(obj, h5py.Dataset):
                        data_dict[name] = obj[:]
                
                f.visititems(visit_items)
                
                if data_dict:
                    # 尝试构建DataFrame
                    for key, value in data_dict.items():
                        if len(value) > 0:
                            print(f"Found dataset: {key}")
                    
                    # 实际处理需要根据具体HDF5结构
                    
        except ImportError:
            print("h5py not installed, trying as text file")
            return self._import_txt(filepath)
        except Exception as e:
            print(f"Error importing H5 file: {e}")
        
        return None
    
    def _import_excel(self, filepath: str) -> Optional[pd.DataFrame]:
        """导入 Excel 格式"""
        try:
            df = pd.read_excel(filepath)
            return self._normalize_dataframe(df)
        except Exception as e:
            print(f"Error importing Excel file: {e}")
        return None
    
    def _import_csv(self, filepath: str) -> Optional[pd.DataFrame]:
        """导入 CSV 格式"""
        try:
            # 尝试不同编码
            for encoding in ['utf-8', 'gbk', 'gb2312', 'gb18030']:
                try:
                    df = pd.read_csv(filepath, encoding=encoding)
                    return self._normalize_dataframe(df)
                except (ValueError, KeyError, TypeError) as e:
                    logger.debug(f"数据处理跳过: {e}")
                    continue
            
            print("Failed to read CSV with common encodings")
        except Exception as e:
            print(f"Error importing CSV file: {e}")
        
        return None
    
    def _import_txt(self, filepath: str) -> Optional[pd.DataFrame]:
        """导入 TXT 格式（同花顺导出文本）"""
        try:
            # 尝试不同编码
            for encoding in ['utf-8', 'gbk', 'gb2312', 'gb18030']:
                try:
                    # 尝试读取，TXT可能有不同分隔符
                    for sep in [',', '\t', '|', ';']:
                        try:
                            df = pd.read_csv(filepath, encoding=encoding, sep=sep)
                            if len(df.columns) >= 6:  # 至少有 OHLCAV
                                return self._normalize_dataframe(df)
                        except (ValueError, KeyError) as e:
                            logger.debug(f"数据解析跳过: {e}")
                            continue
                except (ValueError, KeyError, TypeError) as e:
                    logger.debug(f"数据处理跳过: {e}")
                    continue
            
            print("Failed to parse TXT file")
        except Exception as e:
            print(f"Error importing TXT file: {e}")
        
        return None
    
    def _normalize_dataframe(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        标准化 DataFrame 格式
        
        同花顺导出的数据可能列名不一致，这里做标准化处理
        """
        if df is None or df.empty:
            return df
        
        # 列名映射
        column_mapping = {
            '日期': 'date',
            '股票代码': 'code',
            '股票名称': 'name',
            '开盘': 'open',
            '收盘': 'close',
            '最高': 'high',
            '最低': 'low',
            '成交量': 'volume',
            '成交额': 'amount',
            '振幅': 'amplitude',
            '涨跌幅': 'change_pct',
            '涨跌额': 'change',
            '换手率': 'turnover',
        }
        
        # 重命名列
        df.columns = [column_mapping.get(c, c) for c in df.columns]
        
        # 确保必要的列存在
        required_cols = ['date', 'open', 'high', 'low', 'close', 'volume']
        missing = [c for c in required_cols if c not in df.columns]
        
        if missing:
            print(f"Warning: Missing columns: {missing}")
            # 尝试自动识别
            if 'close' not in df.columns and len(df.columns) >= 4:
                # 假设最后一列是收盘价
                df['close'] = df.iloc[:, -2]
        
        # 转换日期
        if 'date' in df.columns:
            try:
                df['date'] = pd.to_datetime(df['date'])
            except (ValueError, KeyError) as e:
                logger.warning(f"日期转换失败: {e}")
        
        # 确保数值列是数值类型
        numeric_cols = ['open', 'high', 'low', 'close', 'volume', 'amount']
        for col in numeric_cols:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce')
        
        return df
    
    def import_directory(self, dirpath: str) -> Dict[str, pd.DataFrame]:
        """
        批量导入目录下所有数据文件
        
        Args:
            dirpath: 目录路径
        
        Returns:
            股票代码到 DataFrame 的字典
        """
        results = {}
        path = Path(dirpath)
        
        if not path.is_dir():
            print(f"Not a directory: {dirpath}")
            return results
        
        for filepath in path.iterdir():
            if filepath.suffix.lower() in self.SUPPORTED_EXTENSIONS:
                print(f"Importing: {filepath.name}")
                df = self.import_file(str(filepath))
                
                if df is not None and not df.empty:
                    # 尝试获取股票代码
                    code = None
                    if 'code' in df.columns:
                        code = str(df['code'].iloc[0])
                    elif 'name' in df.columns:
                        code = filepath.stem
                    
                    if code:
                        results[code] = df
        
        return results
    
    def export_to_tonghuashun_format(self, df: pd.DataFrame, output_path: str, code: str = None, name: str = None):
        """
        导出为同花顺可导入的格式
        
        Args:
            df: 数据 DataFrame
            output_path: 输出路径
            code: 股票代码
            name: 股票名称
        """
        # 创建标准格式
        export_df = df.copy()
        
        # 确保列顺序
        columns = ['日期', '股票代码', '股票名称', '开盘', '收盘', '最高', '最低', '成交量', '成交额']
        export_df.columns = columns
        
        # 保存为 CSV（通用格式，同花顺可导入）
        export_df.to_csv(output_path, index=False, encoding='utf-8-sig')
        print(f"Exported to: {output_path}")
