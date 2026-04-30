"""
数据回补模块
检测并修复历史数据缺失
"""

import pandas as pd
import numpy as np
from typing import List, Dict, Optional, Tuple, Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)


@dataclass
class DataGap:
    """数据缺口"""
    code: str
    start_date: str
    end_date: str
    gap_days: int
    severity: str  # "minor" (< 5天), "major" (5-30天), "critical" (> 30天)


@dataclass
class DataIntegrityReport:
    """数据完整性报告"""
    code: str
    total_days: int
    missing_days: int
    completeness: float  # 0-100%
    gaps: List[DataGap]
    first_date: str
    last_date: str


class DataRecoveryManager:
    """
    数据回补管理器
    
    功能：
    1. 检测数据缺口
    2. 评估缺失严重程度
    3. 自动回补数据
    4. 验证修复结果
    """

    def __init__(
        self,
        data_loader: Callable[[str, str, str], pd.DataFrame] = None,
        data_saver: Callable[[str, pd.DataFrame], bool] = None
    ):
        """
        Args:
            data_loader: 数据加载函数 (code, start_date, end_date) -> DataFrame
            data_saver: 数据保存函数 (code, DataFrame) -> bool
        """
        self.data_loader = data_loader
        self.data_saver = data_saver

    def check_integrity(
        self,
        df: pd.DataFrame,
        code: str,
        trading_days: List[str] = None
    ) -> DataIntegrityReport:
        """
        检查数据完整性
        
        Args:
            df: 股票数据
            code: 股票代码
            trading_days: 预期交易日列表（用于判断缺失）
        
        Returns:
            DataIntegrityReport
        """
        if df.empty or 'date' not in df.columns:
            return DataIntegrityReport(
                code=code,
                total_days=0,
                missing_days=0,
                completeness=0.0,
                gaps=[],
                first_date="",
                last_date=""
            )

        df = df.copy()
        df['date'] = pd.to_datetime(df['date'])
        df = df.sort_values('date')
        
        first_date = df['date'].min().strftime('%Y%m%d')
        last_date = df['date'].max().strftime('%Y%m%d')
        
        # 计算交易日历
        actual_dates = set(df['date'].dt.strftime('%Y%m%d'))
        
        if trading_days:
            # 使用提供的交易日历
            expected_dates = set(trading_days)
        else:
            # 生成完整的日期范围
            date_range = pd.date_range(start=df['date'].min(), end=df['date'].max(), freq='B')  # 工作日
            expected_dates = set(date_range.strftime('%Y%m%d'))
        
        # 找出缺失的日期
        missing_dates = expected_dates - actual_dates
        
        # 识别连续缺口
        gaps = self._identify_gaps(missing_dates, code)
        
        # 计算完整性
        total_days = len(expected_dates)
        missing_count = len(missing_dates)
        completeness = (total_days - missing_count) / total_days * 100 if total_days > 0 else 0
        
        return DataIntegrityReport(
            code=code,
            total_days=total_days,
            missing_days=missing_count,
            completeness=round(completeness, 2),
            gaps=gaps,
            first_date=first_date,
            last_date=last_date
        )

    def _identify_gaps(self, missing_dates: set, code: str) -> List[DataGap]:
        """识别连续的缺失区间"""
        if not missing_dates:
            return []
        
        sorted_dates = sorted(missing_dates)
        gaps = []
        current_start = sorted_dates[0]
        current_end = sorted_dates[0]
        
        for i in range(1, len(sorted_dates)):
            current = sorted_dates[i]
            prev = sorted_dates[i - 1]
            
            # 检查是否连续（相差1天）
            prev_dt = datetime.strptime(prev, '%Y%m%d')
            curr_dt = datetime.strptime(current, '%Y%m%d')
            
            if (curr_dt - prev_dt).days <= 2:  # 允许1天周末/假日
                current_end = current
            else:
                # 保存当前缺口，开始新的
                gap_days = (datetime.strptime(current_end, '%Y%m%d') - 
                           datetime.strptime(current_start, '%Y%m%d')).days + 1
                severity = self._get_severity(gap_days)
                gaps.append(DataGap(
                    code=code,
                    start_date=current_start,
                    end_date=current_end,
                    gap_days=gap_days,
                    severity=severity
                ))
                current_start = current
                current_end = current
        
        # 保存最后一个缺口
        gap_days = (datetime.strptime(current_end, '%Y%m%d') - 
                   datetime.strptime(current_start, '%Y%m%d')).days + 1
        severity = self._get_severity(gap_days)
        gaps.append(DataGap(
            code=code,
            start_date=current_start,
            end_date=current_end,
            gap_days=gap_days,
            severity=severity
        ))
        
        return gaps

    def _get_severity(self, gap_days: int) -> str:
        """判断缺口严重程度"""
        if gap_days < 5:
            return "minor"
        elif gap_days < 30:
            return "major"
        else:
            return "critical"

    def recover_data(
        self,
        code: str,
        start_date: str,
        end_date: str,
        priority: str = "major"
    ) -> Tuple[bool, pd.DataFrame]:
        """
        回补指定日期范围的数据
        
        Args:
            code: 股票代码
            start_date: 开始日期
            end_date: 结束日期
            priority: 优先级（minor/major/critical）
        
        Returns:
            (是否成功, 回补的数据)
        """
        if not self.data_loader:
            logger.warning("No data loader configured, cannot recover data")
            return False, pd.DataFrame()
        
        try:
            logger.info(f"Recovering data for {code}: {start_date} - {end_date}")
            recovered_df = self.data_loader(code, start_date, end_date)
            
            if recovered_df.empty:
                logger.warning(f"No data recovered for {code}: {start_date}-{end_date}")
                return False, pd.DataFrame()
            
            # 保存回补的数据
            if self.data_saver:
                self.data_saver(code, recovered_df)
            
            return True, recovered_df
            
        except Exception as e:
            logger.error(f"Data recovery failed for {code}: {e}")
            return False, pd.DataFrame()

    def auto_recover(
        self,
        df: pd.DataFrame,
        code: str,
        trading_days: List[str] = None,
        max_gaps_to_fix: int = 5
    ) -> Tuple[pd.DataFrame, List[DataGap]]:
        """
        自动回补数据
        
        Args:
            df: 现有数据
            code: 股票代码
            trading_days: 预期交易日
            max_gaps_to_fix: 最大修复缺口数
        
        Returns:
            (修复后的数据, 修复的缺口列表)
        """
        if not self.data_loader:
            return df, []
        
        # 检查完整性
        report = self.check_integrity(df, code, trading_days)
        
        if report.completeness >= 99.5:  # 99.5% 以上认为完整
            logger.info(f"{code}: Data integrity is sufficient ({report.completeness}%)")
            return df, []
        
        # 按严重程度排序
        sorted_gaps = sorted(
            [g for g in report.gaps if g.severity in ["critical", "major"]],
            key=lambda x: (x.severity == "minor", x.gap_days),
            reverse=True
        )[:max_gaps_to_fix]
        
        if not sorted_gaps:
            logger.info(f"{code}: No major gaps to fix")
            return df, []
        
        # 修复每个缺口
        fixed_gaps = []
        all_recovered_data = []
        
        for gap in sorted_gaps:
            logger.info(f"Fixing gap: {gap.start_date} - {gap.end_date} ({gap.gap_days} days)")
            
            success, recovered_df = self.recover_data(
                code=code,
                start_date=gap.start_date,
                end_date=gap.end_date,
                priority=gap.severity
            )
            
            if success and not recovered_df.empty:
                all_recovered_data.append(recovered_df)
                fixed_gaps.append(gap)
        
        if not all_recovered_data:
            return df, []
        
        # 合并数据
        if 'date' in df.columns:
            recovered_combined = pd.concat(all_recovered_data, ignore_index=True)
            df_combined = pd.concat([df, recovered_combined], ignore_index=True)
            df_combined = df_combined.drop_duplicates(subset=['date'], keep='last')
            df_combined = df_combined.sort_values('date').reset_index(drop=True)
            
            logger.info(f"{code}: Fixed {len(fixed_gaps)} gaps, recovered {len(recovered_combined)} rows")
            return df_combined, fixed_gaps
        
        return df, fixed_gaps

    def get_recovery_plan(self, reports: List[DataIntegrityReport]) -> Dict:
        """
        生成回补计划
        
        Args:
            reports: 多个股票的数据完整性报告
        
        Returns:
            回补计划 {code: [gap, ...]}
        """
        plan = {}
        
        for report in reports:
            critical_gaps = [g for g in report.gaps if g.severity == "critical"]
            major_gaps = [g for g in report.gaps if g.severity == "major"]
            
            if critical_gaps or major_gaps:
                plan[report.code] = {
                    "completeness": report.completeness,
                    "critical_count": len(critical_gaps),
                    "major_count": len(major_gaps),
                    "gaps": critical_gaps + major_gaps
                }
        
        return plan


def generate_trading_calendar(
    start_date: str,
    end_date: str,
    exclude_dates: List[str] = None
) -> List[str]:
    """
    生成交易日历（简化版，排除周末）
    
    Args:
        start_date: 开始日期
        end_date: 结束日期
        exclude_dates: 额外排除的日期
    
    Returns:
        交易日列表
    """
    exclude_set = set(exclude_dates or [])
    
    dates = pd.date_range(start=start_date, end=end_date, freq='B')  # 工作日
    trading_days = []
    
    for d in dates:
        date_str = d.strftime('%Y%m%d')
        day_of_week = d.dayofweek
        
        # 排除周末（5=Saturday, 6=Sunday）
        if day_of_week < 5 and date_str not in exclude_set:
            trading_days.append(date_str)
    
    return trading_days


def validate_recovered_data(
    original_df: pd.DataFrame,
    recovered_df: pd.DataFrame,
    tolerance: float = 0.01
) -> Dict:
    """
    验证回补数据的质量
    
    Args:
        original_df: 原始数据
        recovered_df: 回补的数据
        tolerance: 允许的差异（用于价格验证）
    
    Returns:
        验证结果
    """
    if recovered_df.empty:
        return {"valid": False, "reason": "Empty recovered data"}
    
    # 基本结构检查
    required_cols = ['date', 'open', 'high', 'low', 'close', 'volume']
    missing_cols = [c for c in required_cols if c not in recovered_df.columns]
    if missing_cols:
        return {"valid": False, "reason": f"Missing columns: {missing_cols}"}
    
    # 价格合理性检查
    price_issues = []
    for idx, row in recovered_df.iterrows():
        if row['high'] < row['low']:
            price_issues.append(f"Row {idx}: high < low")
        if row['high'] < row['close'] or row['high'] < row['open']:
            price_issues.append(f"Row {idx}: high < open/close")
        if row['low'] > row['close'] or row['low'] > row['open']:
            price_issues.append(f"Row {idx}: low > open/close")
        if row['volume'] < 0:
            price_issues.append(f"Row {idx}: negative volume")
    
    if price_issues:
        return {
            "valid": False,
            "reason": "Price validation failed",
            "issues": price_issues[:10]  # 只返回前10个问题
        }
    
    # 与原始数据重叠检查
    if not original_df.empty and 'date' in original_df.columns:
        original_dates = set(original_df['date'].astype(str))
        recovered_dates = set(recovered_df['date'].astype(str))
        overlap = original_dates & recovered_dates
        
        if overlap:
            # 检查重叠数据的差异
            overlap_count = len(overlap)
            total_recovered = len(recovered_df)
            overlap_ratio = overlap_count / total_recovered if total_recovered > 0 else 0
            
            return {
                "valid": True,
                "overlap_ratio": overlap_ratio,
                "new_rows": total_recovered - overlap_count
            }
    
    return {"valid": True, "new_rows": len(recovered_df)}