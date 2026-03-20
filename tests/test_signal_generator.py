"""
信号生成器测试
"""

import unittest
import numpy as np
import pandas as pd

from src.core.signal.signal_generator import SignalGenerator, get_signal_generator


def build_sample_df():
    """构建测试用 DataFrame"""
    dates = pd.date_range('2024-01-01', periods=60, freq='D')
    # 构造一个上涨后下跌的行情
    close = [10] * 20 + list(np.linspace(10, 15, 20)) + list(np.linspace(15, 8, 20))
    return pd.DataFrame({
        'date': dates,
        'open': close,
        'high': [c + 0.5 for c in close],
        'low': [c - 0.5 for c in close],
        'close': close,
        'volume': [100000] * len(close),
        'amount': [c * 100000 for c in close],
    })


class SignalGeneratorTestCase(unittest.TestCase):
    def setUp(self):
        self.generator = SignalGenerator()
        self.df = build_sample_df()

    def test_analyze_returns_dict(self):
        """测试 analyze 返回字典"""
        result = self.generator.analyze(self.df)
        self.assertIsInstance(result, dict)
        self.assertIn('signal', result)
        self.assertIn('reason', result)
        self.assertIn('strength', result)

    def test_analyze_validates_data_length(self):
        """测试数据不足时返回 hold"""
        short_df = pd.DataFrame({
            'date': pd.date_range('2024-01-01', periods=10, freq='D'),
            'close': range(10),
        })
        result = self.generator.analyze(short_df)
        self.assertEqual(result['signal'], 'hold')
        self.assertIn('数据不足', result['reason'])

    def test_analyze_signal_values(self):
        """测试信号值为 buy/sell/hold"""
        result = self.generator.analyze(self.df)
        self.assertIn(result['signal'], ['buy', 'sell', 'hold'])

    def test_analyze_includes_trend(self):
        """测试结果包含趋势信息"""
        result = self.generator.analyze(self.df)
        self.assertIn('trend', result)
        self.assertIn(result['trend'], ['up', 'down', 'sideways'])

    def test_analyze_includes_details(self):
        """测试结果包含详细信息"""
        result = self.generator.analyze(self.df)
        if result['signal'] != 'hold':
            self.assertIn('details', result)

    def test_validate_signal_history(self):
        """测试历史信号验证"""
        result = self.generator.validate_signal_history(self.df)
        self.assertIn('signal_count', result)
        self.assertIn('buy_count', result)
        self.assertIn('sell_count', result)
        self.assertIn('summary', result)

    def test_validate_signal_history_short_data(self):
        """测试数据不足时的历史验证"""
        short_df = pd.DataFrame({
            'date': pd.date_range('2024-01-01', periods=20, freq='D'),
            'close': range(20),
        })
        result = self.generator.validate_signal_history(short_df)
        self.assertEqual(result['signal_count'], 0)

    def test_validate_signal_history_with_custom_horizons(self):
        """测试自定义视野范围"""
        result = self.generator.validate_signal_history(self.df, horizons=[5, 10])
        self.assertIn('summary', result)
        self.assertIn('5', result['summary'])
        self.assertIn('10', result['summary'])


class SignalGeneratorMultiPeriodTestCase(unittest.TestCase):
    """多周期信号测试"""

    def test_analyze_multi_period_basic(self):
        """测试多周期分析基本功能"""
        generator = SignalGenerator()
        code = '000001'

        # 构造多周期数据（包含必要的 OHLCV 列）
        close_prices = [10] * 60
        daily_df = pd.DataFrame({
            'date': pd.date_range('2024-01-01', periods=60, freq='D'),
            'open': close_prices,
            'high': [c + 0.5 for c in close_prices],
            'low': [c - 0.5 for c in close_prices],
            'close': close_prices,
            'volume': [100000] * 60,
            'amount': [c * 100000 for c in close_prices],
        })
        weekly_close = [10] * 12
        weekly_df = pd.DataFrame({
            'date': pd.date_range('2024-01-01', periods=12, freq='W'),
            'open': weekly_close,
            'high': [c + 0.5 for c in weekly_close],
            'low': [c - 0.5 for c in weekly_close],
            'close': weekly_close,
            'volume': [100000] * 12,
            'amount': [c * 100000 for c in weekly_close],
        })
        monthly_close = [10] * 6
        monthly_df = pd.DataFrame({
            'date': pd.date_range('2024-01-01', periods=6, freq='ME'),
            'open': monthly_close,
            'high': [c + 0.5 for c in monthly_close],
            'low': [c - 0.5 for c in monthly_close],
            'close': monthly_close,
            'volume': [100000] * 6,
            'amount': [c * 100000 for c in monthly_close],
        })

        data_sources = {
            'D': daily_df,
            'W': weekly_df,
            'M': monthly_df,
        }

        result = generator.analyze_multi_period(code, data_sources)
        self.assertIn('signal', result)
        self.assertIn('period_results', result)

    def test_analyze_multi_period_empty_data(self):
        """测试多周期分析空数据"""
        generator = SignalGenerator()
        result = generator.analyze_multi_period('000001', {})
        self.assertEqual(result['signal'], 'hold')


class GetSignalGeneratorTestCase(unittest.TestCase):
    """单例测试"""

    def test_get_signal_generator_returns_same_instance(self):
        """测试单例返回相同实例"""
        gen1 = get_signal_generator()
        gen2 = get_signal_generator()
        self.assertIs(gen1, gen2)

    def test_get_signal_generator_returns_signal_generator(self):
        """测试返回类型"""
        gen = get_signal_generator()
        self.assertIsInstance(gen, SignalGenerator)


if __name__ == '__main__':
    unittest.main()
