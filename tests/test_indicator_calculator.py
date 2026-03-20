"""
指标计算器测试
"""

import unittest
import numpy as np
import pandas as pd

from src.core.indicator.calculator import IndicatorCalculator


def build_sample_df():
    """构建测试用 DataFrame"""
    dates = pd.date_range('2024-01-01', periods=50, freq='D')
    base = 10 + np.sin(np.linspace(0, 6 * np.pi, len(dates))) * 2
    return pd.DataFrame({
        'date': dates,
        'open': base,
        'high': base + 0.5,
        'low': base - 0.5,
        'close': base,
        'volume': [100000] * len(dates),
        'amount': base * 100000,
    })


class IndicatorCalculatorTestCase(unittest.TestCase):
    def setUp(self):
        self.calc = IndicatorCalculator()
        self.df = build_sample_df()

    def test_calculate_returns_dataframe(self):
        """测试返回 DataFrame"""
        result = self.calc.calculate(self.df)
        self.assertIsInstance(result, pd.DataFrame)
        self.assertEqual(len(result), len(self.df))

    def test_calculate_with_copy(self):
        """测试 copy 参数"""
        result = self.calc.calculate(self.df, copy=True)
        # 计算指标后列数应该增加（至少有一些指标被添加）
        self.assertGreater(len(result.columns), len(self.df.columns))

    def test_ma_calculations(self):
        """测试 MA 计算"""
        result = self.calc.calculate(self.df, indicators=['ma'])
        self.assertIn('ma5', result.columns)
        self.assertIn('ma10', result.columns)
        self.assertIn('ma20', result.columns)
        # MA5 应该有值
        self.assertFalse(result['ma5'].isna().all())

    def test_ema_calculations(self):
        """测试 EMA 计算"""
        result = self.calc.calculate(self.df, indicators=['ema'])
        self.assertIn('ema12', result.columns)
        self.assertIn('ema26', result.columns)

    def test_macd_calculations(self):
        """测试 MACD 计算"""
        result = self.calc.calculate(self.df, indicators=['macd'])
        self.assertIn('macd_dif', result.columns)
        self.assertIn('macd_dea', result.columns)
        self.assertIn('macd_hist', result.columns)

    def test_rsi_calculations(self):
        """测试 RSI 计算"""
        result = self.calc.calculate(self.df, indicators=['rsi'])
        self.assertIn('rsi6', result.columns)
        self.assertIn('rsi12', result.columns)
        self.assertIn('rsi24', result.columns)
        # RSI 值应该在 0-100 之间
        valid_rsi = result['rsi12'].dropna()
        self.assertTrue((valid_rsi >= 0).all())
        self.assertTrue((valid_rsi <= 100).all())

    def test_kdj_calculations(self):
        """测试 KDJ 计算"""
        result = self.calc.calculate(self.df, indicators=['kdj'])
        self.assertIn('kdj_k', result.columns)
        self.assertIn('kdj_d', result.columns)
        self.assertIn('kdj_j', result.columns)

    def test_boll_calculations(self):
        """测试布林带计算"""
        result = self.calc.calculate(self.df, indicators=['boll'])
        self.assertIn('boll_upper', result.columns)
        self.assertIn('boll_mid', result.columns)
        self.assertIn('boll_lower', result.columns)
        # 上轨应该大于中轨，下轨应该小于中轨
        valid_boll = result.dropna(subset=['boll_upper', 'boll_mid', 'boll_lower'])
        self.assertTrue((valid_boll['boll_upper'] >= valid_boll['boll_mid']).all())
        self.assertTrue((valid_boll['boll_lower'] <= valid_boll['boll_mid']).all())

    def test_cci_calculations(self):
        """测试 CCI 计算"""
        result = self.calc.calculate(self.df, indicators=['cci'])
        self.assertIn('cci', result.columns)

    def test_atr_calculations(self):
        """测试 ATR 计算"""
        result = self.calc.calculate(self.df, indicators=['atr'])
        self.assertIn('atr', result.columns)
        # ATR 应该为正
        valid_atr = result['atr'].dropna()
        self.assertTrue((valid_atr > 0).all())

    def test_obv_calculations(self):
        """测试 OBV 计算"""
        result = self.calc.calculate(self.df, indicators=['obv'])
        self.assertIn('obv', result.columns)

    def test_wr_calculations(self):
        """测试威廉指标计算"""
        result = self.calc.calculate(self.df, indicators=['wr'])
        self.assertIn('wr6', result.columns)
        self.assertIn('wr10', result.columns)

    def test_empty_dataframe(self):
        """测试空 DataFrame"""
        empty_df = pd.DataFrame()
        result = self.calc.calculate(empty_df)
        self.assertTrue(result.empty)

    def test_all_indicators(self):
        """测试计算所有指标"""
        result = self.calc.calculate(self.df)
        for indicator in self.calc.default_indicators:
            # 检查指标是否计算（指标名可能转换为小写）
            indicator_lower = indicator.lower()
            if indicator_lower == 'ma':
                self.assertTrue(any(col.startswith('ma') for col in result.columns))
            elif indicator_lower == 'ema':
                self.assertTrue(any(col.startswith('ema') for col in result.columns))
            elif indicator_lower == 'macd':
                self.assertIn('macd_dif', result.columns)
            elif indicator_lower == 'rsi':
                self.assertTrue(any(col.startswith('rsi') for col in result.columns))
            elif indicator_lower == 'kdj':
                self.assertIn('kdj_k', result.columns)
            elif indicator_lower == 'boll':
                self.assertIn('boll_mid', result.columns)
            elif indicator_lower == 'cci':
                self.assertIn('cci', result.columns)
            elif indicator_lower == 'atr':
                self.assertIn('atr', result.columns)
            elif indicator_lower == 'obv':
                self.assertIn('obv', result.columns)
            elif indicator_lower == 'wr':
                self.assertTrue(any(col.startswith('wr') for col in result.columns))

    def test_get_signals(self):
        """测试信号生成"""
        result = self.calc.calculate(self.df)
        signals = self.calc.get_signals(result)
        self.assertIsInstance(signals, dict)


class IndicatorCalculatorSignalsTestCase(unittest.TestCase):
    """指标信号测试"""

    def setUp(self):
        self.calc = IndicatorCalculator()

    def test_macd_golden_cross_signal(self):
        """测试 MACD 金叉信号"""
        dates = pd.date_range('2024-01-01', periods=30, freq='D')
        # 构造 MACD 金叉数据
        close = [10] * 15 + [12] * 15
        df = pd.DataFrame({
            'date': dates,
            'open': close,
            'high': close,
            'low': close,
            'close': close,
            'volume': [100000] * 30,
        })
        result = self.calc.calculate(df, indicators=['macd'])
        signals = self.calc.get_signals(result)
        self.assertIn('macd', signals)

    def test_rsi_overbought_signal(self):
        """测试 RSI 超买信号"""
        dates = pd.date_range('2024-01-01', periods=30, freq='D')
        # 构造超买数据
        close = [20] * 30
        df = pd.DataFrame({
            'date': dates,
            'open': close,
            'high': close,
            'low': close,
            'close': close,
            'volume': [100000] * 30,
        })
        result = self.calc.calculate(df, indicators=['rsi'])
        signals = self.calc.get_signals(result)
        self.assertIn('rsi', signals)
        self.assertEqual(signals['rsi'], 'overbought')

    def test_rsi_oversold_signal(self):
        """测试 RSI 超卖信号"""
        dates = pd.date_range('2024-01-01', periods=30, freq='D')
        # 构造持续下跌的数据，使得 RSI 达到超卖区域
        close = list(np.linspace(15, 5, 30))
        df = pd.DataFrame({
            'date': dates,
            'open': close,
            'high': [c + 0.5 for c in close],
            'low': [c - 0.5 for c in close],
            'close': close,
            'volume': [100000] * 30,
        })
        result = self.calc.calculate(df, indicators=['rsi'])
        signals = self.calc.get_signals(result)
        self.assertIn('rsi', signals)
        # 持续下跌应该产生超卖信号
        self.assertEqual(signals['rsi'], 'oversold')


if __name__ == '__main__':
    unittest.main()
