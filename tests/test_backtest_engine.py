import unittest

import numpy as np
import pandas as pd

from src.core.backtest.backtest import BacktestEngine
from src.core.strategy.strategy import StrategyEngine
from src.main import _extract_csv_rows, _parse_codes_arg


def build_sample_df():
    prices = [10, 10, 10, 10, 10, 11, 12, 13, 14, 15, 16, 17, 16, 15, 14, 13, 12, 11, 10, 9, 8, 8, 8, 8, 8]
    return pd.DataFrame(
        {
            "date": pd.date_range("2024-01-01", periods=len(prices), freq="D"),
            "open": prices,
            "high": [p + 0.5 for p in prices],
            "low": [p - 0.5 for p in prices],
            "close": prices,
            "volume": [100000] * len(prices),
            "amount": [p * 100000 for p in prices],
        }
    )


def build_walkforward_df():
    dates = pd.date_range("2024-01-01", periods=240, freq="D")
    base = 12 + np.sin(np.linspace(0, 12 * np.pi, len(dates))) * 2
    trend = np.linspace(0, 3, len(dates))
    prices = base + trend
    return pd.DataFrame(
        {
            "date": dates,
            "open": prices,
            "high": prices + 0.6,
            "low": prices - 0.6,
            "close": prices,
            "volume": [100000] * len(dates),
            "amount": prices * 100000,
        }
    )


def build_strategy_signal_df():
    dates = pd.date_range("2024-01-01", periods=80, freq="D")
    close = np.concatenate([
        np.linspace(10, 10, 20),
        np.linspace(10, 8, 10),
        np.linspace(8, 11, 15),
        np.linspace(11, 14, 15),
        np.linspace(14, 12, 20),
    ])
    volume = np.concatenate([
        np.full(60, 100000),
        np.full(10, 250000),
        np.full(10, 120000),
    ])
    return pd.DataFrame(
        {
            "date": dates,
            "open": close,
            "high": close + 0.8,
            "low": close - 0.8,
            "close": close,
            "volume": volume,
            "amount": close * volume,
        }
    )


def build_turtle_signal_df():
    prices = [10] * 25 + [11, 12, 13, 14, 15, 16, 17, 16, 15, 14, 13, 12, 11, 10, 9]
    dates = pd.date_range("2024-01-01", periods=len(prices), freq="D")
    return pd.DataFrame(
        {
            "date": dates,
            "open": prices,
            "high": [p + 0.5 for p in prices],
            "low": [p - 0.5 for p in prices],
            "close": prices,
            "volume": [100000] * len(prices),
            "amount": np.array(prices) * 100000,
        }
    )


def build_volume_breakout_signal_df():
    prices = [10] * 20 + [10.2, 10.3, 10.1, 10.2, 10.4, 11.2, 11.8, 12.1, 11.5, 10.7, 10.2]
    volumes = [100000] * 25 + [250000, 280000, 260000, 150000, 120000, 110000]
    dates = pd.date_range("2024-01-01", periods=len(prices), freq="D")
    return pd.DataFrame(
        {
            "date": dates,
            "open": prices,
            "high": [p + 0.4 for p in prices],
            "low": [p - 0.4 for p in prices],
            "close": prices,
            "volume": volumes,
            "amount": np.array(prices) * np.array(volumes),
        }
    )


def build_atr_stop_df():
    prices = [10, 10, 10, 11, 12, 11, 10.2, 10.1, 10.0]
    dates = pd.date_range("2024-02-01", periods=len(prices), freq="D")
    return pd.DataFrame(
        {
            "date": dates,
            "open": prices,
            "high": [p + 0.5 for p in prices],
            "low": [p - 0.5 for p in prices],
            "close": prices,
            "volume": [100000] * len(prices),
            "amount": np.array(prices) * 100000,
        }
    )


def build_multi_factor_df():
    prices = [10] * 20 + [10.2, 10.4, 10.8, 11.2, 11.8, 12.2, 12.6, 12.9, 13.2, 13.4, 13.0, 12.5, 12.0, 11.6, 11.1, 10.8]
    volumes = [100000] * 20 + [110000, 115000, 130000, 150000, 170000, 200000, 220000, 230000, 240000, 250000, 180000, 160000, 150000, 145000, 140000, 135000]
    dates = pd.date_range("2024-03-01", periods=len(prices), freq="D")
    return pd.DataFrame(
        {
            "date": dates,
            "open": prices,
            "high": [p + 0.4 for p in prices],
            "low": [p - 0.4 for p in prices],
            "close": prices,
            "volume": volumes,
            "amount": np.array(prices) * np.array(volumes),
        }
    )


class BacktestEngineTestCase(unittest.TestCase):
    def test_dual_ma_backtest_without_fees_matches_expected_trade(self):
        engine = BacktestEngine(initial_capital=100000)
        df = build_sample_df()

        result = engine.run(
            df,
            "dual_ma",
            {
                "fast_ma": 3,
                "slow_ma": 5,
                "position_size": 1.0,
                "commission_rate": 0.0,
                "stamp_duty_rate": 0.0,
                "slippage_rate": 0.0,
                "lot_size": 1,
            },
        )

        self.assertNotIn("error", result)
        self.assertEqual(len(result["trades"]), 1)

        trade = result["trades"][0]
        metrics = result["metrics"]

        self.assertEqual(trade["entry_date"], "2024-01-06")
        self.assertEqual(trade["exit_date"], "2024-01-15")
        self.assertEqual(trade["shares"], 9090)
        self.assertAlmostEqual(trade["profit"], 27270.0, places=2)
        self.assertAlmostEqual(metrics.end_capital, 127270.0, places=2)
        self.assertAlmostEqual(metrics.total_return, 27.27, places=2)
        self.assertEqual(len(result["equity_curve"]), len(df))
        self.assertIn("benchmark_metrics", result)
        self.assertIn("benchmark_curve", result)
        self.assertEqual(len(result["benchmark_curve"]), len(df))

    def test_fees_reduce_end_capital_and_equity_curve_keeps_daily_points(self):
        engine = BacktestEngine(initial_capital=100000)
        df = build_sample_df()

        baseline = engine.run(
            df,
            "dual_ma",
            {
                "fast_ma": 3,
                "slow_ma": 5,
                "position_size": 1.0,
                "commission_rate": 0.0,
                "stamp_duty_rate": 0.0,
                "slippage_rate": 0.0,
                "lot_size": 1,
            },
        )
        with_fees = engine.run(
            df,
            "dual_ma",
            {
                "fast_ma": 3,
                "slow_ma": 5,
                "position_size": 1.0,
                "commission_rate": 0.001,
                "stamp_duty_rate": 0.001,
                "slippage_rate": 0.001,
                "lot_size": 1,
            },
        )

        self.assertLess(with_fees["metrics"].end_capital, baseline["metrics"].end_capital)
        self.assertEqual(with_fees["equity_curve"][0]["date"], "2024-01-01")
        self.assertEqual(with_fees["equity_curve"][-1]["date"], "2024-01-25")
        self.assertIn("commission_rate", with_fees["backtest_config"])

    def test_take_profit_exits_trade_early(self):
        engine = BacktestEngine(initial_capital=100000)
        df = build_sample_df()

        result = engine.run(
            df,
            "dual_ma",
            {
                "fast_ma": 3,
                "slow_ma": 5,
                "position_size": 1.0,
                "commission_rate": 0.0,
                "stamp_duty_rate": 0.0,
                "slippage_rate": 0.0,
                "take_profit_pct": 0.1,
                "lot_size": 1,
            },
        )

        self.assertNotIn("error", result)
        self.assertEqual(len(result["trades"]), 1)
        trade = result["trades"][0]
        self.assertEqual(trade["exit_date"], "2024-01-07")
        self.assertIn("止盈触发", trade["exit_reason"])

    def test_partial_take_profit_splits_trade_before_final_exit(self):
        engine = BacktestEngine(initial_capital=100000)
        df = build_sample_df()

        result = engine.run(
            df,
            "dual_ma",
            {
                "fast_ma": 3,
                "slow_ma": 5,
                "position_size": 1.0,
                "commission_rate": 0.0,
                "stamp_duty_rate": 0.0,
                "slippage_rate": 0.0,
                "partial_take_profit_pct": 0.1,
                "partial_take_profit_ratio": 0.5,
                "lot_size": 1,
            },
        )

        self.assertNotIn("error", result)
        self.assertEqual(len(result["trades"]), 2)
        self.assertIn("分批止盈触发", result["trades"][0]["exit_reason"])
        self.assertEqual(result["trades"][0]["shares"], result["trades"][1]["shares"])
        self.assertIn("死叉", result["trades"][1]["exit_reason"])

    def test_atr_stop_exits_position_before_signal_exit(self):
        engine = BacktestEngine(initial_capital=100000)
        df = build_atr_stop_df()

        result = engine.run(
            df,
            "dual_ma",
            {
                "fast_ma": 2,
                "slow_ma": 3,
                "position_size": 1.0,
                "commission_rate": 0.0,
                "stamp_duty_rate": 0.0,
                "slippage_rate": 0.0,
                "atr_period": 2,
                "atr_stop_multiplier": 0.5,
                "lot_size": 1,
            },
        )

        self.assertNotIn("error", result)
        self.assertEqual(len(result["trades"]), 1)
        self.assertIn("ATR止损触发", result["trades"][0]["exit_reason"])

    def test_multi_factor_strategy_generates_trades(self):
        engine = BacktestEngine(initial_capital=100000)
        df = build_multi_factor_df()

        result = engine.run(
            df,
            "multi_factor",
            {
                "fast_ma": 3,
                "slow_ma": 8,
                "period": 5,
                "volume_period": 5,
                "buy_threshold": 0.55,
                "sell_threshold": 0.4,
                "position_size": 1.0,
                "commission_rate": 0.0,
                "stamp_duty_rate": 0.0,
                "slippage_rate": 0.0,
                "lot_size": 1,
            },
        )

        self.assertNotIn("error", result)
        self.assertGreaterEqual(len(result["trades"]), 1)
        self.assertIn("多因子", result["trades"][0]["entry_reason"])
        self.assertIn("T", result["trades"][0]["entry_reason"])
        self.assertIn("/4", result["trades"][0]["entry_reason"])
        self.assertIn("strategy_diagnostics", result)
        self.assertGreaterEqual(len(result["strategy_diagnostics"]["factor_curve"]), 1)

    def test_multi_factor_supports_factor_switches_and_min_pass_count(self):
        engine = BacktestEngine(initial_capital=100000)
        df = build_multi_factor_df()

        result = engine.run(
            df,
            "multi_factor",
            {
                "fast_ma": 3,
                "slow_ma": 8,
                "period": 5,
                "volume_period": 5,
                "buy_threshold": 0.5,
                "sell_threshold": 0.4,
                "min_factor_pass_count": 1,
                "use_trend_factor": 1,
                "use_momentum_factor": 0,
                "use_reversion_factor": 0,
                "use_volume_factor": 0,
                "trend_weight": 1.0,
                "momentum_weight": 0.0,
                "reversion_weight": 0.0,
                "volume_weight": 0.0,
                "position_size": 1.0,
                "commission_rate": 0.0,
                "stamp_duty_rate": 0.0,
                "slippage_rate": 0.0,
                "lot_size": 1,
            },
        )

        self.assertNotIn("error", result)
        self.assertGreaterEqual(len(result["trades"]), 1)
        self.assertIn("1/1", result["trades"][0]["entry_reason"])

    def test_optimize_returns_ranked_candidates(self):
        engine = BacktestEngine(initial_capital=100000)
        df = build_sample_df()

        result = engine.optimize(
            df,
            "dual_ma",
            params={
                "position_size": 1.0,
                "commission_rate": 0.0,
                "stamp_duty_rate": 0.0,
                "slippage_rate": 0.0,
                "lot_size": 1,
            },
            metric="total_return",
            top_n=3,
            max_evals=20,
        )

        self.assertNotIn("error", result)
        self.assertGreater(result["evaluated"], 0)
        self.assertLessEqual(len(result["top_results"]), 3)
        self.assertIsNotNone(result["best"])
        best_params = result["best"]["params"]
        self.assertLess(best_params["fast_ma"], best_params["slow_ma"])
        self.assertIn("stability_summary", result)

    def test_optimize_accepts_custom_ranges_and_composite_metric(self):
        engine = BacktestEngine(initial_capital=100000)
        df = build_sample_df()

        result = engine.optimize(
            df,
            "dual_ma",
            params={
                "position_size": 1.0,
                "commission_rate": 0.0,
                "stamp_duty_rate": 0.0,
                "slippage_rate": 0.0,
                "lot_size": 1,
            },
            param_ranges={
                "fast_ma": [3, 5],
                "slow_ma": [10, 20],
            },
            metric="balanced",
            top_n=2,
            max_evals=10,
        )

        self.assertNotIn("error", result)
        self.assertEqual(result["param_ranges"]["fast_ma"], [3, 5])
        self.assertEqual(result["param_ranges"]["slow_ma"], [10, 20])
        self.assertLessEqual(len(result["top_results"]), 2)
        self.assertIn("excess_return", result["top_results"][0]["metrics"])

    def test_optimize_constraints_filter_candidates(self):
        engine = BacktestEngine(initial_capital=100000)
        df = build_sample_df()

        result = engine.optimize(
            df,
            "dual_ma",
            params={
                "position_size": 1.0,
                "commission_rate": 0.0,
                "stamp_duty_rate": 0.0,
                "slippage_rate": 0.0,
                "lot_size": 1,
            },
            param_ranges={
                "fast_ma": [3, 5],
                "slow_ma": [10, 20],
            },
            constraints={
                "min_trades": 1,
                "max_drawdown_limit": 5.0,
            },
            metric="total_return",
            top_n=5,
            max_evals=10,
        )

        self.assertNotIn("error", result)
        self.assertGreaterEqual(result["filtered_out"], 1)
        for item in result["top_results"]:
            self.assertLessEqual(item["metrics"]["max_drawdown"], 5.0)

    def test_walk_forward_produces_segments_and_summary(self):
        engine = BacktestEngine(initial_capital=100000)
        df = build_walkforward_df()

        result = engine.walk_forward(
            df,
            "dual_ma",
            params={
                "position_size": 1.0,
                "commission_rate": 0.0,
                "stamp_duty_rate": 0.0,
                "slippage_rate": 0.0,
                "lot_size": 1,
            },
            param_ranges={
                "fast_ma": [3, 5],
                "slow_ma": [10, 20],
            },
            metric="balanced",
            train_size=80,
            test_size=40,
            step_size=40,
            max_evals=10,
        )

        self.assertNotIn("error", result)
        self.assertGreaterEqual(len(result["segments"]), 1)
        self.assertIn("metrics", result)
        self.assertIn("benchmark_metrics", result)
        self.assertIn("stability_summary", result)

    def test_sensitivity_analysis_orders_by_return(self):
        engine = BacktestEngine(initial_capital=100000)
        df = build_sample_df()

        result = engine.sensitivity_analysis(
            df,
            "dual_ma",
            params={
                "fast_ma": 3,
                "slow_ma": 5,
                "position_size": 1.0,
                "lot_size": 1,
            },
            commission_rates=[0.0, 0.002],
            slippage_rates=[0.0],
            stamp_duty_rates=[0.0],
        )

        self.assertNotIn("error", result)
        self.assertEqual(len(result["rows"]), 2)
        self.assertGreaterEqual(result["rows"][0]["total_return"], result["rows"][1]["total_return"])
        self.assertEqual(result["best"]["commission_rate"], 0.0)

    def test_extract_csv_rows_prefers_rows_table(self):
        rows = _extract_csv_rows(
            {
                "rows": [
                    {"commission_rate": 0.0003, "total_return": 12.3},
                    {"commission_rate": 0.001, "total_return": 10.1},
                ]
            }
        )
        self.assertEqual(len(rows), 2)
        self.assertIn("commission_rate", rows[0])

    def test_parse_codes_arg_splits_and_trims(self):
        codes = _parse_codes_arg("000001, 000002 ,600036")
        self.assertEqual(codes, ["000001", "000002", "600036"])

    def test_new_strategies_registered(self):
        engine = StrategyEngine()
        strategies = engine.get_available_strategies()
        self.assertIn("boll_reversion", strategies)
        self.assertIn("turtle_breakout", strategies)
        self.assertIn("volume_breakout", strategies)
        self.assertIn("multi_factor", strategies)

    def test_new_strategies_generate_signals(self):
        engine = StrategyEngine()
        boll_df = build_strategy_signal_df()
        turtle_df = build_turtle_signal_df()
        volume_df = build_volume_breakout_signal_df()
        multi_factor_df = build_multi_factor_df()

        boll_signals = engine.run_strategy(boll_df.copy(), "boll_reversion", {"period": 20, "oversold": 35, "overbought": 65})
        turtle_signals = engine.run_strategy(turtle_df.copy(), "turtle_breakout", {"period": 20, "exit_period": 10})
        volume_signals = engine.run_strategy(volume_df.copy(), "volume_breakout", {"period": 20, "volume_period": 10, "volume_multiplier": 1.2})
        multi_factor_signals = engine.run_strategy(
            multi_factor_df.copy(),
            "multi_factor",
            {"fast_ma": 3, "slow_ma": 8, "period": 5, "volume_period": 5, "buy_threshold": 0.55, "sell_threshold": 0.4},
        )

        self.assertGreaterEqual(len(boll_signals), 1)
        self.assertGreaterEqual(len(turtle_signals), 1)
        self.assertGreaterEqual(len(volume_signals), 1)
        self.assertGreaterEqual(len(multi_factor_signals), 1)


if __name__ == "__main__":
    unittest.main()
