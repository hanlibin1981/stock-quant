"""
K线图表可视化模块
使用 Plotly 生成交互式股票图表
"""

import pandas as pd
import numpy as np
from typing import Dict, List, Optional, Tuple
from pathlib import Path
import json

try:
    import plotly.graph_objects as go
    from plotly.subplots import make_subplots
    PLOTLY_AVAILABLE = True
except ImportError:
    PLOTLY_AVAILABLE = False


class StockChartGenerator:
    """
    股票K线图表生成器
    
    生成包含以下内容的交互式图表：
    - K线（蜡烛图）
    - 均线（MA5/MA10/MA20/MA60）
    - 成交量柱状图
    - 技术指标（MACD/RSI/KDJ等）
    - 买卖信号标记
    """

    def __init__(self):
        self.default_ma_periods = [5, 10, 20, 60]
        self.default_indicators = ['macd', 'rsi', 'kdj']

    def create_candlestick_chart(
        self,
        df: pd.DataFrame,
        stock_code: str = "",
        stock_name: str = "",
        show_volume: bool = True,
        show_ma: bool = True,
        ma_periods: List[int] = None,
        indicators: List[str] = None,
        signals: List[Dict] = None,
        title: str = None
    ) -> Optional["go.Figure"]:
        """
        创建完整的股票分析图表
        
        Args:
            df: OHLCV 数据
            stock_code: 股票代码
            stock_name: 股票名称
            show_volume: 是否显示成交量
            show_ma: 是否显示均线
            ma_periods: 均线周期列表
            indicators: 要显示的技术指标 ['macd', 'rsi', 'kdj', 'boll']
            signals: 买卖信号列表 [{'date', 'signal', 'price'}]
            title: 图表标题
        
        Returns:
            Plotly Figure 对象，失败返回 None
        """
        if not PLOTLY_AVAILABLE:
            print("Plotly 未安装，无法生成图表。请运行: pip install plotly")
            return None

        if df is None or df.empty or len(df) < 2:
            return None

        # 参数处理
        if ma_periods is None:
            ma_periods = self.default_ma_periods
        if indicators is None:
            indicators = self.default_indicators
        if title is None:
            title = f"{stock_name} ({stock_code})" if stock_name else stock_code

        # 判断是否需要子图
        has_subplots = show_volume or indicators

        if has_subplots:
            # 计算子图行数
            rows = 1
            row_heights = [0.6]
            if show_volume:
                rows += 1
                row_heights.append(0.15)
            if indicators:
                rows += len(indicators)
                row_heights.append(0.15 * len(indicators))
            
            fig = make_subplots(
                rows=rows,
                cols=1,
                shared_xaxes=True,
                vertical_spacing=0.05,
                row_heights=row_heights,
                subplot_titles=(['K线'] + 
                    (['成交量'] if show_volume else []) + 
                    [ind.upper() for ind in indicators])
            )
        else:
            fig = go.Figure()

        # 准备数据
        df = df.copy()
        if 'date' in df.columns:
            df['date'] = pd.to_datetime(df['date'])
        df = df.sort_values('date')

        # 1. K线图
        row_idx = 1
        fig.add_trace(
            self._create_candlestick_trace(df),
            row=row_idx, col=1
        )

        # 2. 均线
        if show_ma:
            for period in ma_periods:
                if len(df) >= period:
                    ma_trace = self._create_ma_trace(df, period)
                    fig.add_trace(ma_trace, row=row_idx, col=1)

        # 3. 布林带
        if 'boll_upper' in df.columns and 'boll_lower' in df.columns:
            boll_traces = self._create_boll_traces(df)
            for trace in boll_traces:
                fig.add_trace(trace, row=row_idx, col=1)

        # 4. 买卖信号标记
        if signals:
            signal_traces = self._create_signal_markers(df, signals)
            for trace in signal_traces:
                fig.add_trace(trace, row=row_idx, col=1)

        # 5. 成交量
        if show_volume:
            row_idx += 1
            fig.add_trace(
                self._create_volume_trace(df),
                row=row_idx, col=1
            )

        # 6. 技术指标
        for ind in indicators:
            row_idx += 1
            ind_trace = self._create_indicator_trace(df, ind)
            if ind_trace:
                fig.add_trace(ind_trace, row=row_idx, col=1)

        # 更新布局
        fig.update_layout(
            title=dict(
                text=title,
                x=0.5,
                font=dict(size=16)
            ),
            template="plotly_dark",
            showlegend=True,
            legend=dict(
                orientation="h",
                yanchor="bottom",
                y=1.02,
                xanchor="right",
                x=1
            ),
            hovermode="x unified",
            height=800 if has_subplots else 500,
            margin=dict(t=80, r=50, b=50, l=50)
        )

        # 更新坐标轴
        fig.update_xaxes(
            rangeslider_visible=False,
            showgrid=True,
            gridcolor='rgba(128,128,128,0.2)'
        )
        fig.update_yaxes(
            showgrid=True,
            gridcolor='rgba(128,128,128,0.2)',
            title_text="价格"
        )

        return fig

    def _create_candlestick_trace(self, df: pd.DataFrame) -> "go.Candlestick":
        """创建K线轨迹"""
        return go.Candlestick(
            x=df['date'] if 'date' in df.columns else df.index,
            open=df['open'],
            high=df['high'],
            low=df['low'],
            close=df['close'],
            name='K线',
            increasing_line_color='#26a69a',  # 绿色上涨
            decreasing_line_color='#ef5350',  # 红色下跌
            increasing_fillcolor='#26a69a',
            decreasing_fillcolor='#ef5350'
        )

    def _create_ma_trace(self, df: pd.DataFrame, period: int) -> "go.Scatter":
        """创建均线轨迹"""
        ma_values = df['close'].rolling(window=period).mean()
        colors = {5: '#ff6b6b', 10: '#ffd93d', 20: '#6bcb77', 60: '#4d96ff'}
        return go.Scatter(
            x=df['date'] if 'date' in df.columns else df.index,
            y=ma_values,
            mode='lines',
            name=f'MA{period}',
            line=dict(color=colors.get(period, '#888888'), width=1.5)
        )

    def _create_boll_traces(self, df: pd.DataFrame) -> List["go.Scatter"]:
        """创建布林带轨迹"""
        traces = []
        if 'boll_upper' in df.columns:
            traces.append(go.Scatter(
                x=df['date'] if 'date' in df.columns else df.index,
                y=df['boll_upper'],
                mode='lines',
                name='BOLL上轨',
                line=dict(color='rgba(255,255,0,0.5)', width=1, dash='dash')
            ))
        if 'boll_mid' in df.columns:
            traces.append(go.Scatter(
                x=df['date'] if 'date' in df.columns else df.index,
                y=df['boll_mid'],
                mode='lines',
                name='BOLL中轨',
                line=dict(color='rgba(255,255,0,0.8)', width=1)
            ))
        if 'boll_lower' in df.columns:
            traces.append(go.Scatter(
                x=df['date'] if 'date' in df.columns else df.index,
                y=df['boll_lower'],
                mode='lines',
                name='BOLL下轨',
                line=dict(color='rgba(255,255,0,0.5)', width=1, dash='dash'),
                fill='tonexty' if 'boll_upper' in df.columns else None,
                fillcolor='rgba(255,255,0,0.1)'
            ))
        return traces

    def _create_volume_trace(self, df: pd.DataFrame) -> "go.Bar":
        """创建成交量柱状图"""
        colors = np.where(df['close'] >= df['open'], '#26a69a', '#ef5350')
        return go.Bar(
            x=df['date'] if 'date' in df.columns else df.index,
            y=df['volume'],
            name='成交量',
            marker_color=colors,
            opacity=0.7
        )

    def _create_signal_markers(self, df: pd.DataFrame, signals: List[Dict]) -> List["go.Scatter"]:
        """创建买卖信号标记"""
        traces = []
        
        buy_dates, buy_prices = [], []
        sell_dates, sell_prices = [], []
        
        date_col = 'date' if 'date' in df.columns else df.index
        date_map = dict(zip(df.index, date_col)) if 'date' not in df.columns else dict(zip(date_col, date_col))
        
        for sig in signals:
            sig_date = sig.get('date', '')
            sig_signal = sig.get('signal', '')
            sig_price = sig.get('price', 0)
            
            if sig_signal == 'buy':
                buy_dates.append(sig_date)
                buy_prices.append(sig_price)
            elif sig_signal == 'sell':
                sell_dates.append(sig_date)
                sell_prices.append(sig_price)
        
        if buy_dates:
            traces.append(go.Scatter(
                x=buy_dates,
                y=buy_prices,
                mode='markers',
                name='买入信号',
                marker=dict(
                    symbol='triangle-up',
                    size=15,
                    color='#26a69a',
                    line=dict(width=2, color='#1a7a6e')
                )
            ))
        
        if sell_dates:
            traces.append(go.Scatter(
                x=sell_dates,
                y=sell_prices,
                mode='markers',
                name='卖出信号',
                marker=dict(
                    symbol='triangle-down',
                    size=15,
                    color='#ef5350',
                    line=dict(width=2, color='#c62828')
                )
            ))
        
        return traces

    def _create_indicator_trace(self, df: pd.DataFrame, indicator: str) -> Optional["go.Scatter"]:
        """创建技术指标轨迹"""
        if indicator == 'macd' and 'macd_dif' in df.columns:
            return go.Scatter(
                x=df['date'] if 'date' in df.columns else df.index,
                y=df['macd_dif'],
                mode='lines',
                name='DIF',
                line=dict(color='#2196f3', width=1.5)
            )
        elif indicator == 'rsi' and 'rsi12' in df.columns:
            return go.Scatter(
                x=df['date'] if 'date' in df.columns else df.index,
                y=df['rsi12'],
                mode='lines',
                name='RSI12',
                line=dict(color='#9c27b0', width=1.5)
            )
        elif indicator == 'kdj' and 'kdj_k' in df.columns:
            return go.Scatter(
                x=df['date'] if 'date' in df.columns else df.index,
                y=df['kdj_k'],
                mode='lines',
                name='KDJ_K',
                line=dict(color='#ff9800', width=1.5)
            )
        elif indicator == 'cci' and 'cci' in df.columns:
            return go.Scatter(
                x=df['date'] if 'date' in df.columns else df.index,
                y=df['cci'],
                mode='lines',
                name='CCI',
                line=dict(color='#00bcd4', width=1.5)
            )
        return None

    def save_html(self, fig: "go.Figure", filepath: str) -> bool:
        """
        保存图表为 HTML 文件
        
        Args:
            fig: Plotly Figure 对象
            filepath: 保存路径
        
        Returns:
            是否保存成功
        """
        if fig is None:
            return False
        try:
            # 确保目录存在
            Path(filepath).parent.mkdir(parents=True, exist_ok=True)
            fig.write_html(filepath, include_plotlyjs='cdn')
            return True
        except Exception as e:
            print(f"保存图表失败: {e}")
            return False

    def get_html(self, fig: "go.Figure") -> Optional[str]:
        """
        获取图表的 HTML 字符串
        
        Returns:
            HTML 字符串
        """
        if fig is None:
            return None
        try:
            return fig.to_html(full_html=False, include_plotlyjs='cdn')
        except Exception as e:
            print(f"生成HTML失败: {e}")
            return None

    def save_png(self, fig: "go.Figure", filepath: str, width: int = 1200, height: int = 800) -> bool:
        """
        保存图表为 PNG 图片
        
        Args:
            fig: Plotly Figure 对象
            filepath: 保存路径
            width: 图片宽度
            height: 图片高度
        
        Returns:
            是否保存成功
        """
        if fig is None:
            return False
        try:
            Path(filepath).parent.mkdir(parents=True, exist_ok=True)
            fig.write_image(filepath, width=width, height=height)
            return True
        except Exception as e:
            print(f"保存PNG失败 (需要 kaleido): {e}")
            return False


def create_stock_chart(
    df: pd.DataFrame,
    stock_code: str = "",
    stock_name: str = "",
    indicators: List[str] = None,
    signals: List[Dict] = None
) -> Optional["go.Figure"]:
    """
    便捷函数：创建股票图表
    
    Args:
        df: OHLCV 数据
        stock_code: 股票代码
        stock_name: 股票名称
        indicators: 要显示的指标
        signals: 买卖信号
    
    Returns:
        Plotly Figure 对象
    """
    generator = StockChartGenerator()
    return generator.create_candlestick_chart(
        df=df,
        stock_code=stock_code,
        stock_name=stock_name,
        show_volume=True,
        show_ma=True,
        indicators=indicators or ['macd', 'rsi'],
        signals=signals
    )


def save_chart_html(
    df: pd.DataFrame,
    filepath: str,
    stock_code: str = "",
    stock_name: str = "",
    indicators: List[str] = None,
    signals: List[Dict] = None
) -> bool:
    """
    便捷函数：创建并保存股票图表为 HTML
    
    Args:
        df: OHLCV 数据
        filepath: 保存路径
        stock_code: 股票代码
        stock_name: 股票名称
        indicators: 要显示的指标
        signals: 买卖信号
    
    Returns:
        是否保存成功
    """
    generator = StockChartGenerator()
    fig = generator.create_candlestick_chart(
        df=df,
        stock_code=stock_code,
        stock_name=stock_name,
        indicators=indicators or ['macd', 'rsi'],
        signals=signals
    )
    return generator.save_html(fig, filepath)
