"""
回测引擎模块
"""

from collections import Counter
from dataclasses import dataclass
from itertools import product
from typing import Dict, List, Optional

import numpy as np
import pandas as pd


@dataclass
class BacktestResult:
    """回测结果"""

    total_trades: int
    winning_trades: int
    losing_trades: int
    win_rate: float
    total_return: float
    annual_return: float
    max_drawdown: float
    sharpe_ratio: float
    avg_profit: float
    avg_loss: float
    profit_factor: float
    end_capital: float


class BacktestEngine:
    """单标的日线回测引擎"""

    def __init__(self, initial_capital: float = 100000):
        self.initial_capital = initial_capital

    def run(self, df: pd.DataFrame, strategy_name: str, params: Dict = None) -> Dict:
        """
        运行回测

        Args:
            df: 股票数据
            strategy_name: 策略名称
            params: 回测与策略参数

        Returns:
            回测结果字典
        """
        from src.core.strategy.strategy import StrategyEngine

        config = self._build_config(params)
        prepared_df = self._prepare_dataframe(df, config["atr_period"])
        if prepared_df.empty:
            return {"error": "No data available for backtest"}

        engine = StrategyEngine()
        strategy = engine.create_strategy(strategy_name, config["strategy_params"])
        signals = strategy.generate_signals(prepared_df.copy())
        if not signals:
            return {"error": "No signals generated"}
        diagnostics = strategy.get_diagnostics(prepared_df.copy())

        simulation = self._simulate_trades(prepared_df, signals, config)
        trades = simulation["trades"]
        equity_curve = simulation["equity_curve"]
        benchmark_curve = self._build_benchmark_curve(prepared_df, config["initial_capital"])

        result = self._calculate_metrics(trades, equity_curve, config["initial_capital"])
        benchmark_metrics = self._calculate_benchmark_metrics(benchmark_curve, config["initial_capital"])

        return {
            "strategy": strategy_name,
            "params": config["strategy_params"],
            "backtest_config": config["backtest_config"],
            "trades": trades,
            "metrics": result,
            "equity_curve": equity_curve,
            "benchmark_curve": benchmark_curve,
            "benchmark_metrics": benchmark_metrics,
            "strategy_diagnostics": diagnostics,
        }

    def optimize(
        self,
        df: pd.DataFrame,
        strategy_name: str,
        params: Dict = None,
        param_ranges: Dict = None,
        constraints: Dict = None,
        metric: str = "total_return",
        top_n: int = 5,
        max_evals: int = 50,
    ) -> Dict:
        """使用默认参数网格做简单参数搜索"""
        from src.core.strategy.strategy import StrategyEngine

        strategy_engine = StrategyEngine()
        default_ranges = strategy_engine.get_strategy_param_ranges(strategy_name)
        param_ranges = param_ranges or default_ranges
        constraints = constraints or {}
        if not param_ranges:
            return {"error": f"Strategy '{strategy_name}' has no optimizable parameters"}

        base_params = dict(params or {})
        keys = list(param_ranges.keys())
        combinations = []
        for values in product(*(param_ranges[key] for key in keys)):
            candidate = dict(zip(keys, values))
            if strategy_name == "dual_ma" and candidate["fast_ma"] >= candidate["slow_ma"]:
                continue
            if strategy_name == "rsi" and candidate["oversold"] >= candidate["overbought"]:
                continue
            if (
                strategy_name == "multi_factor"
                and (
                    candidate.get("fast_ma", 0) >= candidate.get("slow_ma", float("inf"))
                    or candidate.get("buy_threshold", 1.0) <= candidate.get("sell_threshold", 0.0)
                )
            ):
                continue
            combinations.append(candidate)

        if not combinations:
            return {"error": "No valid parameter combinations found"}

        results = []
        filtered_out = 0
        for candidate in combinations[:max_evals]:
            merged = {**base_params, **candidate}
            if strategy_name == "multi_factor":
                enabled_factor_count = sum(
                    int(bool(merged.get(key, 1)))
                    for key in (
                        "use_trend_factor",
                        "use_momentum_factor",
                        "use_reversion_factor",
                        "use_volume_factor",
                    )
                )
                if enabled_factor_count <= 0:
                    continue
                if merged.get("min_factor_pass_count", 2) > enabled_factor_count:
                    continue
            backtest_result = self.run(df, strategy_name, merged)
            if "error" in backtest_result:
                continue

            metrics = backtest_result["metrics"]
            benchmark_metrics = backtest_result["benchmark_metrics"]
            score = self._calculate_optimization_score(metrics, benchmark_metrics, metric)
            if score is None:
                return {"error": f"Unsupported optimize metric: {metric}"}

            if not self._passes_optimization_constraints(metrics, benchmark_metrics, constraints):
                filtered_out += 1
                continue

            results.append(
                {
                    "params": candidate,
                    "score": float(score),
                    "metrics": {
                        "total_return": metrics.total_return,
                        "annual_return": metrics.annual_return,
                        "sharpe_ratio": metrics.sharpe_ratio,
                        "max_drawdown": metrics.max_drawdown,
                        "win_rate": metrics.win_rate,
                        "profit_factor": metrics.profit_factor,
                        "end_capital": metrics.end_capital,
                        "total_trades": metrics.total_trades,
                        "excess_return": metrics.total_return - benchmark_metrics["total_return"],
                    },
                }
            )

        reverse = metric not in {"max_drawdown"}
        results.sort(key=lambda item: item["score"], reverse=reverse)
        best = results[0] if results else None

        return {
            "strategy": strategy_name,
            "metric": metric,
            "evaluated": len(results),
            "filtered_out": filtered_out,
            "best": best,
            "top_results": results[:top_n],
            "param_ranges": param_ranges,
            "constraints": constraints,
            "stability_summary": self._summarize_param_stability(results),
        }

    def walk_forward(
        self,
        df: pd.DataFrame,
        strategy_name: str,
        params: Dict = None,
        param_ranges: Dict = None,
        constraints: Dict = None,
        metric: str = "balanced",
        train_size: int = 120,
        test_size: int = 60,
        step_size: Optional[int] = None,
        max_evals: int = 50,
    ) -> Dict:
        """滚动窗口参数优化 + 样本外验证"""
        prepared_df = self._prepare_dataframe(df)
        if prepared_df.empty:
            return {"error": "No data available for walk-forward"}

        step_size = step_size or test_size
        if train_size <= 0 or test_size <= 0 or step_size <= 0:
            return {"error": "train_size, test_size, step_size must be positive"}
        if len(prepared_df) < train_size + test_size:
            return {"error": "Not enough data for walk-forward analysis"}

        base_params = dict(params or {})
        constraints = constraints or {}
        current_capital = float(base_params.get("initial_capital", self.initial_capital))

        segments = []
        all_trades: List[Dict] = []
        combined_equity_curve: List[Dict] = []
        combined_benchmark_curve: List[Dict] = []
        start = 0

        while start + train_size + test_size <= len(prepared_df):
            train_df = prepared_df.iloc[start:start + train_size].copy()
            test_df = prepared_df.iloc[start + train_size:start + train_size + test_size].copy()

            optimize_result = self.optimize(
                train_df,
                strategy_name,
                params={**base_params, "initial_capital": current_capital},
                param_ranges=param_ranges,
                constraints=constraints,
                metric=metric,
                top_n=1,
                max_evals=max_evals,
            )
            if "error" in optimize_result:
                return optimize_result

            best = optimize_result.get("best")
            if not best:
                start += step_size
                continue

            selected_params = {**base_params, **best["params"], "initial_capital": current_capital}
            test_result = self.run(test_df, strategy_name, selected_params)
            if "error" in test_result:
                start += step_size
                continue

            segment_metrics = test_result["metrics"]
            segment_benchmark_metrics = test_result["benchmark_metrics"]
            segment_info = {
                "train_start": train_df.iloc[0]["date"].strftime("%Y-%m-%d"),
                "train_end": train_df.iloc[-1]["date"].strftime("%Y-%m-%d"),
                "test_start": test_df.iloc[0]["date"].strftime("%Y-%m-%d"),
                "test_end": test_df.iloc[-1]["date"].strftime("%Y-%m-%d"),
                "best_params": best["params"],
                "optimize_score": best["score"],
                "metrics": {
                    "total_return": segment_metrics.total_return,
                    "annual_return": segment_metrics.annual_return,
                    "max_drawdown": segment_metrics.max_drawdown,
                    "sharpe_ratio": segment_metrics.sharpe_ratio,
                    "end_capital": segment_metrics.end_capital,
                    "total_trades": segment_metrics.total_trades,
                    "excess_return": segment_metrics.total_return - segment_benchmark_metrics["total_return"],
                },
            }
            segments.append(segment_info)

            all_trades.extend(test_result["trades"])
            combined_equity_curve.extend(test_result["equity_curve"])
            combined_benchmark_curve.extend(test_result["benchmark_curve"])
            current_capital = segment_metrics.end_capital
            start += step_size

        if not segments:
            return {"error": "No valid walk-forward segments produced"}

        initial_capital = float(base_params.get("initial_capital", self.initial_capital))
        aggregate_metrics = self._calculate_metrics(all_trades, combined_equity_curve, initial_capital)
        aggregate_benchmark = self._calculate_benchmark_metrics(combined_benchmark_curve, initial_capital)

        return {
            "strategy": strategy_name,
            "metric": metric,
            "segments": segments,
            "metrics": aggregate_metrics,
            "benchmark_metrics": aggregate_benchmark,
            "equity_curve": combined_equity_curve,
            "benchmark_curve": combined_benchmark_curve,
            "train_size": train_size,
            "test_size": test_size,
            "step_size": step_size,
            "param_ranges": param_ranges,
            "constraints": constraints,
            "stability_summary": self._summarize_segment_stability(segments),
        }

    def sensitivity_analysis(
        self,
        df: pd.DataFrame,
        strategy_name: str,
        params: Dict = None,
        commission_rates: Optional[List[float]] = None,
        slippage_rates: Optional[List[float]] = None,
        stamp_duty_rates: Optional[List[float]] = None,
    ) -> Dict:
        """交易成本敏感性分析"""
        commission_rates = commission_rates or [0.0001, 0.0003, 0.0005, 0.001]
        slippage_rates = slippage_rates or [0.0, 0.0005, 0.001, 0.002]
        stamp_duty_rates = stamp_duty_rates or [0.001]

        rows = []
        for commission_rate, slippage_rate, stamp_duty_rate in product(
            commission_rates, slippage_rates, stamp_duty_rates
        ):
            current_params = {
                **(params or {}),
                "commission_rate": commission_rate,
                "slippage_rate": slippage_rate,
                "stamp_duty_rate": stamp_duty_rate,
            }
            result = self.run(df, strategy_name, current_params)
            if "error" in result:
                continue

            metrics = result["metrics"]
            benchmark = result["benchmark_metrics"]
            rows.append(
                {
                    "commission_rate": commission_rate,
                    "slippage_rate": slippage_rate,
                    "stamp_duty_rate": stamp_duty_rate,
                    "total_return": metrics.total_return,
                    "annual_return": metrics.annual_return,
                    "max_drawdown": metrics.max_drawdown,
                    "sharpe_ratio": metrics.sharpe_ratio,
                    "profit_factor": metrics.profit_factor,
                    "end_capital": metrics.end_capital,
                    "total_trades": metrics.total_trades,
                    "excess_return": metrics.total_return - benchmark["total_return"],
                }
            )

        if not rows:
            return {"error": "No valid sensitivity results produced"}

        rows.sort(key=lambda item: item["total_return"], reverse=True)
        return {
            "strategy": strategy_name,
            "rows": rows,
            "best": rows[0],
            "worst": rows[-1],
            "commission_rates": commission_rates,
            "slippage_rates": slippage_rates,
            "stamp_duty_rates": stamp_duty_rates,
        }

    def _build_config(self, params: Optional[Dict]) -> Dict:
        """拆分策略参数和回测参数"""
        params = dict(params or {})
        initial_capital = float(params.pop("initial_capital", self.initial_capital))
        position_size = float(params.pop("position_size", 0.95))
        commission_rate = float(params.pop("commission_rate", 0.0003))
        stamp_duty_rate = float(params.pop("stamp_duty_rate", 0.001))
        slippage_rate = float(params.pop("slippage_rate", 0.0005))
        lot_size = int(params.pop("lot_size", 100))
        risk_free_rate = float(params.pop("risk_free_rate", 0.02))
        stop_loss_pct = float(params.pop("stop_loss_pct", 0.0))
        take_profit_pct = float(params.pop("take_profit_pct", 0.0))
        trailing_stop_pct = float(params.pop("trailing_stop_pct", 0.0))
        atr_period = int(params.pop("atr_period", 14))
        atr_stop_multiplier = float(params.pop("atr_stop_multiplier", 0.0))
        partial_take_profit_pct = float(params.pop("partial_take_profit_pct", 0.0))
        partial_take_profit_ratio = float(params.pop("partial_take_profit_ratio", 0.5))

        position_size = min(max(position_size, 0.0), 1.0)
        commission_rate = max(commission_rate, 0.0)
        stamp_duty_rate = max(stamp_duty_rate, 0.0)
        slippage_rate = max(slippage_rate, 0.0)
        lot_size = max(lot_size, 1)
        stop_loss_pct = max(stop_loss_pct, 0.0)
        take_profit_pct = max(take_profit_pct, 0.0)
        trailing_stop_pct = max(trailing_stop_pct, 0.0)
        atr_period = max(atr_period, 1)
        atr_stop_multiplier = max(atr_stop_multiplier, 0.0)
        partial_take_profit_pct = max(partial_take_profit_pct, 0.0)
        partial_take_profit_ratio = min(max(partial_take_profit_ratio, 0.0), 1.0)

        return {
            "initial_capital": initial_capital,
            "position_size": position_size,
            "commission_rate": commission_rate,
            "stamp_duty_rate": stamp_duty_rate,
            "slippage_rate": slippage_rate,
            "lot_size": lot_size,
            "risk_free_rate": risk_free_rate,
            "stop_loss_pct": stop_loss_pct,
            "take_profit_pct": take_profit_pct,
            "trailing_stop_pct": trailing_stop_pct,
            "atr_period": atr_period,
            "atr_stop_multiplier": atr_stop_multiplier,
            "partial_take_profit_pct": partial_take_profit_pct,
            "partial_take_profit_ratio": partial_take_profit_ratio,
            "strategy_params": params,
            "backtest_config": {
                "initial_capital": initial_capital,
                "position_size": position_size,
                "commission_rate": commission_rate,
                "stamp_duty_rate": stamp_duty_rate,
                "slippage_rate": slippage_rate,
                "lot_size": lot_size,
                "risk_free_rate": risk_free_rate,
                "stop_loss_pct": stop_loss_pct,
                "take_profit_pct": take_profit_pct,
                "trailing_stop_pct": trailing_stop_pct,
                "atr_period": atr_period,
                "atr_stop_multiplier": atr_stop_multiplier,
                "partial_take_profit_pct": partial_take_profit_pct,
                "partial_take_profit_ratio": partial_take_profit_ratio,
            },
        }

    def _prepare_dataframe(self, df: pd.DataFrame, atr_period: int = 14) -> pd.DataFrame:
        """标准化回测输入数据"""
        required_columns = {"date", "close"}
        if df is None or df.empty or not required_columns.issubset(df.columns):
            return pd.DataFrame()

        prepared = df.copy()
        prepared["date"] = pd.to_datetime(prepared["date"])
        prepared = prepared.sort_values("date").drop_duplicates(subset=["date"], keep="last")

        for column in ("open", "high", "low", "close", "volume", "amount"):
            if column in prepared.columns:
                prepared[column] = pd.to_numeric(prepared[column], errors="coerce")

        prepared = prepared.dropna(subset=["close"]).reset_index(drop=True)
        if {"high", "low", "close"}.issubset(prepared.columns):
            high_low = prepared["high"] - prepared["low"]
            high_close = (prepared["high"] - prepared["close"].shift()).abs()
            low_close = (prepared["low"] - prepared["close"].shift()).abs()
            true_range = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
            prepared["atr"] = true_range.rolling(window=max(int(atr_period), 1)).mean()
        return prepared

    def _simulate_trades(self, df: pd.DataFrame, signals, config: Dict) -> Dict:
        """模拟逐日交易和权益变化"""
        trades: List[Dict] = []
        equity_curve: List[Dict] = []

        initial_capital = config["initial_capital"]
        position_size = config["position_size"]
        commission_rate = config["commission_rate"]
        stamp_duty_rate = config["stamp_duty_rate"]
        slippage_rate = config["slippage_rate"]
        lot_size = config["lot_size"]
        stop_loss_pct = config["stop_loss_pct"]
        take_profit_pct = config["take_profit_pct"]
        trailing_stop_pct = config["trailing_stop_pct"]
        atr_stop_multiplier = config["atr_stop_multiplier"]
        partial_take_profit_pct = config["partial_take_profit_pct"]
        partial_take_profit_ratio = config["partial_take_profit_ratio"]

        cash = initial_capital
        position = None

        signal_map = {}
        for signal in signals:
            signal_map[pd.Timestamp(signal.date)] = signal

        for row in df.itertuples(index=False):
            trade_date = pd.Timestamp(row.date)
            close_price = float(row.close)
            high_price = float(getattr(row, "high", close_price))
            low_price = float(getattr(row, "low", close_price))
            atr_value = float(getattr(row, "atr", np.nan)) if hasattr(row, "atr") else np.nan
            signal = signal_map.get(trade_date)

            if position is not None:
                position["highest_price"] = max(position["highest_price"], high_price)

                stop_price = None
                stop_reason = None
                if stop_loss_pct > 0:
                    static_stop = position["entry_price"] * (1 - stop_loss_pct)
                    stop_price = static_stop
                    stop_reason = f"止损触发({stop_loss_pct * 100:.1f}%)"
                if trailing_stop_pct > 0:
                    trailing_stop = position["highest_price"] * (1 - trailing_stop_pct)
                    if stop_price is None or trailing_stop > stop_price:
                        stop_price = trailing_stop
                        stop_reason = f"移动止损触发({trailing_stop_pct * 100:.1f}%)"
                if atr_stop_multiplier > 0 and not np.isnan(atr_value):
                    atr_stop = position["entry_price"] - atr_value * atr_stop_multiplier
                    if stop_price is None or atr_stop > stop_price:
                        stop_price = atr_stop
                        stop_reason = f"ATR止损触发({atr_stop_multiplier:.2f}x)"

                if stop_price is not None and low_price <= stop_price:
                    trade = self._execute_exit(
                        position,
                        position["shares"],
                        trade_date,
                        stop_price,
                        close_price,
                        commission_rate,
                        stamp_duty_rate,
                        slippage_rate,
                        stop_reason,
                    )
                    cash += trade["net_amount"]
                    trades.append(self._normalize_trade_record(trade))
                    position = None

                elif (
                    partial_take_profit_pct > 0
                    and partial_take_profit_ratio > 0
                    and not position.get("partial_take_profit_done")
                ):
                    partial_target = position["entry_price"] * (1 + partial_take_profit_pct)
                    if high_price >= partial_target and position["shares"] > lot_size:
                        shares_to_sell = int(position["shares"] * partial_take_profit_ratio / lot_size) * lot_size
                        shares_to_sell = min(max(shares_to_sell, lot_size), position["shares"] - lot_size)
                        if shares_to_sell > 0:
                            trade = self._execute_exit(
                                position,
                                shares_to_sell,
                                trade_date,
                                partial_target,
                                close_price,
                                commission_rate,
                                stamp_duty_rate,
                                slippage_rate,
                                f"分批止盈触发({partial_take_profit_pct * 100:.1f}%)",
                            )
                            cash += trade["net_amount"]
                            trades.append(self._normalize_trade_record(trade))
                            self._reduce_position(position, trade)
                            position["partial_take_profit_done"] = True

                elif take_profit_pct > 0:
                    target_price = position["entry_price"] * (1 + take_profit_pct)
                    if high_price >= target_price:
                        trade = self._execute_exit(
                            position,
                            position["shares"],
                            trade_date,
                            target_price,
                            close_price,
                            commission_rate,
                            stamp_duty_rate,
                            slippage_rate,
                            f"止盈触发({take_profit_pct * 100:.1f}%)",
                        )
                        cash += trade["net_amount"]
                        trades.append(self._normalize_trade_record(trade))
                        position = None

            if signal and signal.signal.value == 1 and position is None:
                execution_price = close_price * (1 + slippage_rate)
                target_cash = cash * position_size
                shares = int(target_cash / execution_price / lot_size) * lot_size

                if shares > 0:
                    gross_amount = shares * execution_price
                    commission = gross_amount * commission_rate
                    total_cost = gross_amount + commission

                    while shares > 0 and total_cost > cash:
                        shares -= lot_size
                        if shares <= 0:
                            break
                        gross_amount = shares * execution_price
                        commission = gross_amount * commission_rate
                        total_cost = gross_amount + commission

                    if shares > 0:
                        cash -= total_cost
                        position = {
                            "entry_date": trade_date,
                            "entry_price": execution_price,
                            "entry_close_price": close_price,
                            "shares": shares,
                            "entry_amount": gross_amount,
                            "entry_fee": commission,
                            "entry_reason": signal.reason,
                            "highest_price": high_price,
                            "partial_take_profit_done": False,
                        }

            elif signal and signal.signal.value == -1 and position is not None:
                trade = self._execute_exit(
                    position,
                    position["shares"],
                    trade_date,
                    close_price,
                    close_price,
                    commission_rate,
                    stamp_duty_rate,
                    slippage_rate,
                    signal.reason,
                )
                cash += trade["net_amount"]
                trades.append(self._normalize_trade_record(trade))
                position = None

            market_value = 0.0
            if position is not None:
                market_value = position["shares"] * close_price

            total_equity = cash + market_value
            equity_curve.append(
                {
                    "date": trade_date.strftime("%Y-%m-%d"),
                    "cash": cash,
                    "position_value": market_value,
                    "equity": total_equity,
                }
            )

        if position is not None:
            last_row = df.iloc[-1]
            trade_date = pd.Timestamp(last_row["date"])
            close_price = float(last_row["close"])
            trade = self._execute_exit(
                position,
                position["shares"],
                trade_date,
                close_price,
                close_price,
                commission_rate,
                stamp_duty_rate,
                slippage_rate,
                "回测结束强制平仓",
            )
            cash += trade["net_amount"]
            trades.append(self._normalize_trade_record(trade))

            if equity_curve:
                equity_curve[-1] = {
                    "date": trade_date.strftime("%Y-%m-%d"),
                    "cash": cash,
                    "position_value": 0.0,
                    "equity": cash,
                }

        return {"trades": trades, "equity_curve": equity_curve}

    def _execute_exit(
        self,
        position: Dict,
        shares_to_sell: int,
        trade_date: pd.Timestamp,
        signal_price: float,
        close_price: float,
        commission_rate: float,
        stamp_duty_rate: float,
        slippage_rate: float,
        exit_reason: str,
    ) -> Dict:
        """按统一口径执行部分或全部卖出"""
        execution_price = signal_price * (1 - slippage_rate)
        gross_amount = shares_to_sell * execution_price
        commission = gross_amount * commission_rate
        stamp_duty = gross_amount * stamp_duty_rate
        net_amount = gross_amount - commission - stamp_duty

        entry_amount_allocated = position["entry_amount"] * shares_to_sell / position["shares"]
        entry_fee_allocated = position["entry_fee"] * shares_to_sell / position["shares"]
        total_cost = entry_amount_allocated + entry_fee_allocated
        profit = net_amount - total_cost
        profit_pct = (profit / total_cost * 100) if total_cost > 0 else 0.0
        holding_days = max((trade_date - position["entry_date"]).days, 1)

        return {
            "entry_date": position["entry_date"].strftime("%Y-%m-%d"),
            "entry_price": position["entry_price"],
            "entry_close_price": position["entry_close_price"],
            "exit_date": trade_date.strftime("%Y-%m-%d"),
            "exit_price": execution_price,
            "exit_close_price": close_price,
            "shares": shares_to_sell,
            "buy_fee": entry_fee_allocated,
            "sell_fee": commission + stamp_duty,
            "profit": profit,
            "profit_pct": profit_pct,
            "holding_days": holding_days,
            "entry_reason": position["entry_reason"],
            "exit_reason": exit_reason,
            "net_amount": net_amount,
            "entry_amount_allocated": entry_amount_allocated,
            "entry_fee_allocated": entry_fee_allocated,
        }

    def _normalize_trade_record(self, trade: Dict) -> Dict:
        """移除内部字段，返回对外成交记录"""
        trade = dict(trade)
        trade.pop("net_amount", None)
        trade.pop("entry_amount_allocated", None)
        trade.pop("entry_fee_allocated", None)
        return trade

    def _reduce_position(self, position: Dict, trade: Dict):
        """部分止盈后减少剩余持仓成本"""
        shares_sold = trade["shares"]
        position["shares"] -= shares_sold
        position["entry_amount"] -= trade["entry_amount_allocated"]
        position["entry_fee"] -= trade["entry_fee_allocated"]

    def _calculate_metrics(
        self, trades: List[Dict], equity_curve: List[Dict], initial_capital: float
    ) -> BacktestResult:
        """基于逐日权益和成交记录计算指标"""
        if not equity_curve:
            return BacktestResult(
                total_trades=0,
                winning_trades=0,
                losing_trades=0,
                win_rate=0,
                total_return=0,
                annual_return=0,
                max_drawdown=0,
                sharpe_ratio=0,
                avg_profit=0,
                avg_loss=0,
                profit_factor=0,
                end_capital=initial_capital,
            )

        total_trades = len(trades)
        winning_trades = sum(1 for t in trades if t["profit"] > 0)
        losing_trades = sum(1 for t in trades if t["profit"] <= 0)
        win_rate = (winning_trades / total_trades * 100) if total_trades > 0 else 0.0

        equity_series = pd.Series([point["equity"] for point in equity_curve], dtype=float)
        end_capital = float(equity_series.iloc[-1])
        total_return = ((end_capital / initial_capital) - 1) * 100 if initial_capital > 0 else 0.0

        dates = pd.to_datetime([point["date"] for point in equity_curve])
        total_days = max((dates[-1] - dates[0]).days, 1) if len(dates) > 1 else 1
        annual_return = (
            ((end_capital / initial_capital) ** (365 / total_days) - 1) * 100
            if initial_capital > 0 and end_capital > 0 and total_days > 0
            else 0.0
        )

        running_peak = equity_series.cummax().replace(0, np.nan)
        drawdown = ((running_peak - equity_series) / running_peak).fillna(0) * 100
        max_drawdown = float(drawdown.max()) if not drawdown.empty else 0.0

        daily_returns = equity_series.pct_change().replace([np.inf, -np.inf], np.nan).dropna()
        if len(daily_returns) > 1 and daily_returns.std(ddof=0) > 0:
            sharpe_ratio = float((daily_returns.mean() / daily_returns.std(ddof=0)) * np.sqrt(252))
        else:
            sharpe_ratio = 0.0

        profits = [t["profit"] for t in trades if t["profit"] > 0]
        losses = [t["profit"] for t in trades if t["profit"] <= 0]
        avg_profit = float(np.mean(profits)) if profits else 0.0
        avg_loss = float(np.mean(losses)) if losses else 0.0

        total_profit_sum = float(sum(profits)) if profits else 0.0
        total_loss_sum = float(abs(sum(losses))) if losses else 0.0
        profit_factor = (total_profit_sum / total_loss_sum) if total_loss_sum > 0 else 0.0

        return BacktestResult(
            total_trades=total_trades,
            winning_trades=winning_trades,
            losing_trades=losing_trades,
            win_rate=win_rate,
            total_return=total_return,
            annual_return=annual_return,
            max_drawdown=max_drawdown,
            sharpe_ratio=sharpe_ratio,
            avg_profit=avg_profit,
            avg_loss=avg_loss,
            profit_factor=profit_factor,
            end_capital=end_capital,
        )

    def _build_benchmark_curve(self, df: pd.DataFrame, initial_capital: float) -> List[Dict]:
        """构建买入并持有基准曲线"""
        if df.empty:
            return []

        first_close = float(df.iloc[0]["close"])
        if first_close <= 0:
            return []

        shares = initial_capital / first_close
        benchmark_curve = []
        for row in df.itertuples(index=False):
            equity = shares * float(row.close)
            benchmark_curve.append(
                {
                    "date": pd.Timestamp(row.date).strftime("%Y-%m-%d"),
                    "equity": equity,
                }
            )
        return benchmark_curve

    def _calculate_benchmark_metrics(self, benchmark_curve: List[Dict], initial_capital: float) -> Dict:
        """计算基准收益指标"""
        if not benchmark_curve:
            return {
                "total_return": 0.0,
                "annual_return": 0.0,
                "max_drawdown": 0.0,
                "end_capital": initial_capital,
            }

        equity_series = pd.Series([point["equity"] for point in benchmark_curve], dtype=float)
        end_capital = float(equity_series.iloc[-1])
        total_return = ((end_capital / initial_capital) - 1) * 100 if initial_capital > 0 else 0.0
        dates = pd.to_datetime([point["date"] for point in benchmark_curve])
        total_days = max((dates[-1] - dates[0]).days, 1) if len(dates) > 1 else 1
        annual_return = (
            ((end_capital / initial_capital) ** (365 / total_days) - 1) * 100
            if initial_capital > 0 and end_capital > 0 and total_days > 0
            else 0.0
        )
        running_peak = equity_series.cummax().replace(0, np.nan)
        drawdown = ((running_peak - equity_series) / running_peak).fillna(0) * 100
        max_drawdown = float(drawdown.max()) if not drawdown.empty else 0.0

        return {
            "total_return": total_return,
            "annual_return": annual_return,
            "max_drawdown": max_drawdown,
            "end_capital": end_capital,
        }

    def _calculate_optimization_score(self, metrics: BacktestResult, benchmark_metrics: Dict, metric: str) -> Optional[float]:
        """计算参数优化排序得分"""
        if hasattr(metrics, metric):
            return float(getattr(metrics, metric))

        excess_return = metrics.total_return - benchmark_metrics.get("total_return", 0.0)
        max_drawdown = max(metrics.max_drawdown, 0.01)

        composite_metrics = {
            "excess_return": excess_return,
            "return_over_drawdown": metrics.total_return / max_drawdown,
            "excess_over_drawdown": excess_return / max_drawdown,
            "balanced": metrics.sharpe_ratio * 10 + metrics.total_return - max_drawdown,
        }
        return composite_metrics.get(metric)

    def _passes_optimization_constraints(self, metrics: BacktestResult, benchmark_metrics: Dict, constraints: Dict) -> bool:
        """检查优化筛选约束"""
        if not constraints:
            return True

        min_trades = constraints.get("min_trades")
        max_drawdown_limit = constraints.get("max_drawdown_limit")
        min_sharpe = constraints.get("min_sharpe")
        min_excess_return = constraints.get("min_excess_return")

        excess_return = metrics.total_return - benchmark_metrics.get("total_return", 0.0)

        if min_trades is not None and metrics.total_trades < min_trades:
            return False
        if max_drawdown_limit is not None and metrics.max_drawdown > max_drawdown_limit:
            return False
        if min_sharpe is not None and metrics.sharpe_ratio < min_sharpe:
            return False
        if min_excess_return is not None and excess_return < min_excess_return:
            return False
        return True

    def _summarize_param_stability(self, results: List[Dict]) -> List[Dict]:
        """统计优化结果中的参数稳定性"""
        counter = Counter(tuple(sorted(item["params"].items())) for item in results)
        summary = []
        for param_items, count in counter.most_common(10):
            summary.append(
                {
                    "params": dict(param_items),
                    "count": count,
                }
            )
        return summary

    def _summarize_segment_stability(self, segments: List[Dict]) -> List[Dict]:
        """统计滚动验证中各参数获胜次数"""
        counter = Counter(tuple(sorted(item["best_params"].items())) for item in segments)
        summary = []
        for param_items, count in counter.most_common(10):
            summary.append(
                {
                    "params": dict(param_items),
                    "count": count,
                }
            )
        return summary

    def print_result(self, result: Dict):
        """打印回测结果"""
        if "error" in result:
            print(f"Error: {result['error']}")
            return

        metrics = result["metrics"]

        print(f"\n{'=' * 50}")
        print(f"回测结果 - {result['strategy']}")
        print(f"{'=' * 50}")
        print(f"总交易次数: {metrics.total_trades}")
        print(f"盈利次数: {metrics.winning_trades}")
        print(f"亏损次数: {metrics.losing_trades}")
        print(f"胜率: {metrics.win_rate:.2f}%")
        print(f"总收益率: {metrics.total_return:.2f}%")
        print(f"年化收益率: {metrics.annual_return:.2f}%")
        print(f"期末资金: {metrics.end_capital:.2f}")
        print(f"最大回撤: {metrics.max_drawdown:.2f}%")
        print(f"夏普比率: {metrics.sharpe_ratio:.2f}")
        print(f"平均盈利: {metrics.avg_profit:.2f}")
        print(f"平均亏损: {metrics.avg_loss:.2f}")
        print(f"盈亏比: {metrics.profit_factor:.2f}")
        print(f"{'=' * 50}\n")
