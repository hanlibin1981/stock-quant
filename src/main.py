"""
StockQuant Pro - 股票量化交易工具
主入口文件
"""

import sys
import argparse
import csv
import json
from pathlib import Path
from dataclasses import asdict, is_dataclass

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.core.data.stock_data import StockDataManager
from src.core.indicator.calculator import IndicatorCalculator
from src.core.strategy.strategy import StrategyEngine
from src.core.backtest.backtest import BacktestEngine
from src.api.eastmoney.client import EastMoneyClient
from src.api.tonghuashun.importer import TonghuashunImporter


def _collect_backtest_params(args) -> dict:
    """收集回测和策略参数"""
    params = {}
    for key in [
        "fast_ma",
        "slow_ma",
        "period",
        "oversold",
        "overbought",
        "buy_threshold",
        "sell_threshold",
        "volume_period",
        "min_factor_pass_count",
        "use_trend_factor",
        "use_momentum_factor",
        "use_reversion_factor",
        "use_volume_factor",
        "trend_weight",
        "momentum_weight",
        "reversion_weight",
        "volume_weight",
        "initial_capital",
        "position_size",
        "commission_rate",
        "stamp_duty_rate",
        "slippage_rate",
        "risk_free_rate",
        "lot_size",
        "stop_loss_pct",
        "take_profit_pct",
        "trailing_stop_pct",
        "atr_period",
        "atr_stop_multiplier",
        "partial_take_profit_pct",
        "partial_take_profit_ratio",
    ]:
        value = getattr(args, key, None)
        if value is not None:
            params[key] = value
    return params


def _collect_optimize_param_ranges(args) -> dict:
    """收集优化参数候选值"""
    param_ranges = {}
    range_keys = {
        "fast_ma_range": int,
        "slow_ma_range": int,
        "period_range": int,
        "min_factor_pass_count_range": int,
        "oversold_range": float,
        "overbought_range": float,
        "buy_threshold_range": float,
        "sell_threshold_range": float,
        "trend_weight_range": float,
        "momentum_weight_range": float,
        "reversion_weight_range": float,
        "volume_weight_range": float,
    }

    for key, caster in range_keys.items():
        value = getattr(args, key, None)
        if not value:
            continue
        parts = [part.strip() for part in value.split(",") if part.strip()]
        if parts:
            param_ranges[key.removesuffix("_range")] = [caster(part) for part in parts]

    return param_ranges


def _parse_float_range_arg(value: str) -> list[float]:
    """解析逗号分隔浮点候选值"""
    return [float(part.strip()) for part in value.split(",") if part.strip()]


def _parse_codes_arg(value: str | None) -> list[str]:
    """解析逗号分隔股票代码"""
    if not value:
        return []
    return [part.strip() for part in value.split(",") if part.strip()]


def _collect_optimize_constraints(args) -> dict:
    """收集优化筛选约束"""
    constraints = {}
    for key in ["min_trades", "max_drawdown_limit", "min_sharpe", "min_excess_return"]:
        value = getattr(args, key, None)
        if value is not None:
            constraints[key] = value
    return constraints


def _collect_walkforward_config(args) -> dict:
    """收集滚动验证窗口参数"""
    config = {}
    for key in ["train_size", "test_size", "step_size", "max_evals"]:
        value = getattr(args, key, None)
        if value is not None:
            config[key] = value
    return config


def _serialize_for_json(value):
    """把结果对象转成可写入 JSON 的结构"""
    if is_dataclass(value):
        return {key: _serialize_for_json(val) for key, val in asdict(value).items()}
    if isinstance(value, dict):
        return {key: _serialize_for_json(val) for key, val in value.items()}
    if isinstance(value, list):
        return [_serialize_for_json(item) for item in value]
    return value


def _write_output_file(output_file: str, payload: dict):
    """按扩展名写出结果文件"""
    path = Path(output_file)
    path.parent.mkdir(parents=True, exist_ok=True)
    serialized = _serialize_for_json(payload)

    if path.suffix.lower() == ".csv":
        rows = _extract_csv_rows(serialized)
        if not rows:
            raise ValueError("当前结果没有可导出的表格数据")
        fieldnames = []
        for row in rows:
            for key in row.keys():
                if key not in fieldnames:
                    fieldnames.append(key)
        with path.open("w", newline="", encoding="utf-8") as file:
            writer = csv.DictWriter(file, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)
        return

    path.write_text(json.dumps(serialized, ensure_ascii=False, indent=2), encoding="utf-8")


def _extract_csv_rows(payload: dict) -> list[dict]:
    """从不同结果结构里抽取适合导出的表格行"""
    if isinstance(payload, dict):
        if payload.get("rows"):
            return [_flatten_dict(row) for row in payload["rows"]]
        if payload.get("top_results"):
            return [_flatten_dict(row) for row in payload["top_results"]]
        if payload.get("segments"):
            return [_flatten_dict(row) for row in payload["segments"]]
        if payload.get("trades"):
            return [_flatten_dict(row) for row in payload["trades"]]
        if payload.get("equity_curve"):
            return [_flatten_dict(row) for row in payload["equity_curve"]]
    return []


def _flatten_dict(value: dict, prefix: str = "") -> dict:
    """拍平嵌套字典，便于 CSV 导出"""
    flattened = {}
    for key, item in value.items():
        new_key = f"{prefix}.{key}" if prefix else str(key)
        if isinstance(item, dict):
            flattened.update(_flatten_dict(item, new_key))
        else:
            flattened[new_key] = item
    return flattened


class StockQuantPro:
    """量化交易工具主类"""
    
    def __init__(self, data_dir: str = None):
        self.data_dir = Path(data_dir) if data_dir else Path.home() / ".stockquant" / "data"
        self.data_dir.mkdir(parents=True, exist_ok=True)
        
        # 初始化各模块
        self.data_manager = StockDataManager(self.data_dir)
        self.eastmoney = EastMoneyClient()
        self.indicator = IndicatorCalculator()
        self.strategy = StrategyEngine()
        self.backtest = BacktestEngine()
        self.tonghuashun = TonghuashunImporter()
    
    def get_stock_data(self, code: str, start_date: str = None, end_date: str = None):
        """获取股票数据"""
        return self.data_manager.get_stock_data(code, start_date, end_date)
    
    def fetch_realtime(self, code: str):
        """获取实时行情"""
        return self.eastmoney.get_realtime(code)
    
    def calculate_indicators(self, df, indicators: list = None):
        """计算技术指标"""
        if indicators is None:
            indicators = ['ma', 'ema', 'macd', 'rsi', 'boll']
        return self.indicator.calculate(df, indicators)
    
    def run_backtest(self, df, strategy_name: str, **params):
        """运行回测"""
        return self.backtest.run(df, strategy_name, params)

    def optimize_backtest(self, df, strategy_name: str, metric: str = "total_return", **params):
        """优化回测参数"""
        optimize_ranges = params.pop("param_ranges", None)
        optimize_constraints = params.pop("constraints", None)
        return self.backtest.optimize(
            df,
            strategy_name,
            params=params,
            param_ranges=optimize_ranges,
            constraints=optimize_constraints,
            metric=metric,
        )

    def walkforward_backtest(self, df, strategy_name: str, metric: str = "balanced", **params):
        """滚动窗口验证"""
        optimize_ranges = params.pop("param_ranges", None)
        optimize_constraints = params.pop("constraints", None)
        walkforward_config = params.pop("walkforward_config", None) or {}
        return self.backtest.walk_forward(
            df,
            strategy_name,
            params=params,
            param_ranges=optimize_ranges,
            constraints=optimize_constraints,
            metric=metric,
            **walkforward_config,
        )

    def sensitivity_backtest(
        self,
        df,
        strategy_name: str,
        commission_rates: list[float] | None = None,
        slippage_rates: list[float] | None = None,
        stamp_duty_rates: list[float] | None = None,
        **params,
    ):
        """交易成本敏感性分析"""
        return self.backtest.sensitivity_analysis(
            df,
            strategy_name,
            params=params,
            commission_rates=commission_rates,
            slippage_rates=slippage_rates,
            stamp_duty_rates=stamp_duty_rates,
        )
    
    def import_tonghuashun(self, filepath: str):
        """导入同花顺数据"""
        return self.tonghuashun.import_file(filepath)


def _load_backtest_dataframe(app: StockQuantPro, code: str, days: int):
    """优先本地、失败回退网络和模拟数据"""
    df = app.get_stock_data(code)
    source = "local"

    if df is None or df.empty:
        client = EastMoneyClient()
        df = client.get_kline(code, days=days)
        source = "eastmoney"

    if df is None or df.empty:
        from src.api.mock_data import MockDataGenerator
        mock = MockDataGenerator()
        df = mock.generate_kline(code, days=days)
        source = "mock"

    return df, source


def main():
    parser = argparse.ArgumentParser(description="StockQuant Pro - 股票量化交易工具")
    parser.add_argument("command", choices=["fetch", "backtest", "batchbacktest", "optimize", "walkforward", "sensitivity", "import", "analyze"], 
                        help="命令: fetch(获取数据) | backtest(回测) | batchbacktest(批量回测) | optimize(参数优化) | walkforward(滚动验证) | sensitivity(成本敏感性) | import(导入) | analyze(分析)")
    parser.add_argument("--code", "-c", help="股票代码")
    parser.add_argument("--codes", help="多个股票代码，逗号分隔")
    parser.add_argument("--file", "-f", help="文件路径")
    parser.add_argument("--strategy", "-s", help="策略名称")
    parser.add_argument("--fast-ma", type=int, dest="fast_ma", help="双均线快线周期")
    parser.add_argument("--slow-ma", type=int, dest="slow_ma", help="双均线慢线周期")
    parser.add_argument("--period", type=int, help="突破/RSI策略周期")
    parser.add_argument("--oversold", type=float, help="RSI超卖阈值")
    parser.add_argument("--overbought", type=float, help="RSI超买阈值")
    parser.add_argument("--buy-threshold", type=float, dest="buy_threshold", help="多因子买入阈值")
    parser.add_argument("--sell-threshold", type=float, dest="sell_threshold", help="多因子卖出阈值")
    parser.add_argument("--volume-period", type=int, dest="volume_period", help="量能均线周期")
    parser.add_argument("--min-factor-pass-count", type=int, dest="min_factor_pass_count", help="最少通过因子数")
    parser.add_argument("--use-trend-factor", type=int, dest="use_trend_factor", help="是否启用趋势因子，1/0")
    parser.add_argument("--use-momentum-factor", type=int, dest="use_momentum_factor", help="是否启用动量因子，1/0")
    parser.add_argument("--use-reversion-factor", type=int, dest="use_reversion_factor", help="是否启用均值回归因子，1/0")
    parser.add_argument("--use-volume-factor", type=int, dest="use_volume_factor", help="是否启用量能因子，1/0")
    parser.add_argument("--trend-weight", type=float, dest="trend_weight", help="趋势因子权重")
    parser.add_argument("--momentum-weight", type=float, dest="momentum_weight", help="动量因子权重")
    parser.add_argument("--reversion-weight", type=float, dest="reversion_weight", help="均值回归因子权重")
    parser.add_argument("--volume-weight", type=float, dest="volume_weight", help="量能因子权重")
    parser.add_argument("--initial-capital", type=float, dest="initial_capital", help="初始资金")
    parser.add_argument("--position-size", type=float, dest="position_size", help="单次开仓资金占比，0-1")
    parser.add_argument("--commission-rate", type=float, dest="commission_rate", help="手续费率")
    parser.add_argument("--stamp-duty-rate", type=float, dest="stamp_duty_rate", help="卖出印花税率")
    parser.add_argument("--slippage-rate", type=float, dest="slippage_rate", help="滑点率")
    parser.add_argument("--risk-free-rate", type=float, dest="risk_free_rate", help="无风险利率")
    parser.add_argument("--lot-size", type=int, dest="lot_size", help="最小交易手数")
    parser.add_argument("--stop-loss-pct", type=float, dest="stop_loss_pct", help="固定止损比例，如 0.08")
    parser.add_argument("--take-profit-pct", type=float, dest="take_profit_pct", help="固定止盈比例，如 0.15")
    parser.add_argument("--trailing-stop-pct", type=float, dest="trailing_stop_pct", help="移动止损比例，如 0.1")
    parser.add_argument("--atr-period", type=int, dest="atr_period", help="ATR 周期")
    parser.add_argument("--atr-stop-multiplier", type=float, dest="atr_stop_multiplier", help="ATR 止损倍数，如 2.0")
    parser.add_argument(
        "--partial-take-profit-pct",
        type=float,
        dest="partial_take_profit_pct",
        help="分批止盈触发比例，如 0.1",
    )
    parser.add_argument(
        "--partial-take-profit-ratio",
        type=float,
        dest="partial_take_profit_ratio",
        help="分批止盈卖出比例，0-1",
    )
    parser.add_argument("--metric", default="total_return", help="优化排序指标")
    parser.add_argument("--fast-ma-range", dest="fast_ma_range", help="快线候选值，逗号分隔")
    parser.add_argument("--slow-ma-range", dest="slow_ma_range", help="慢线候选值，逗号分隔")
    parser.add_argument("--period-range", dest="period_range", help="周期候选值，逗号分隔")
    parser.add_argument("--min-factor-pass-count-range", dest="min_factor_pass_count_range", help="最少通过因子数候选")
    parser.add_argument("--oversold-range", dest="oversold_range", help="RSI超卖候选值，逗号分隔")
    parser.add_argument("--overbought-range", dest="overbought_range", help="RSI超买候选值，逗号分隔")
    parser.add_argument("--buy-threshold-range", dest="buy_threshold_range", help="多因子买入阈值候选")
    parser.add_argument("--sell-threshold-range", dest="sell_threshold_range", help="多因子卖出阈值候选")
    parser.add_argument("--trend-weight-range", dest="trend_weight_range", help="趋势因子权重候选")
    parser.add_argument("--momentum-weight-range", dest="momentum_weight_range", help="动量因子权重候选")
    parser.add_argument("--reversion-weight-range", dest="reversion_weight_range", help="均值回归因子权重候选")
    parser.add_argument("--volume-weight-range", dest="volume_weight_range", help="量能因子权重候选")
    parser.add_argument("--min-trades", type=int, dest="min_trades", help="最少成交次数约束")
    parser.add_argument("--max-drawdown-limit", type=float, dest="max_drawdown_limit", help="最大回撤上限")
    parser.add_argument("--min-sharpe", type=float, dest="min_sharpe", help="最小夏普比率")
    parser.add_argument("--min-excess-return", type=float, dest="min_excess_return", help="最小超额收益")
    parser.add_argument("--train-size", type=int, dest="train_size", help="滚动训练窗口大小")
    parser.add_argument("--test-size", type=int, dest="test_size", help="滚动测试窗口大小")
    parser.add_argument("--step-size", type=int, dest="step_size", help="滚动步长")
    parser.add_argument("--max-evals", type=int, dest="max_evals", help="单次优化最大评估数")
    parser.add_argument("--output-file", dest="output_file", help="导出结果文件，支持 .json 或 .csv")
    parser.add_argument("--days", type=int, default=250, help="历史数据天数")
    parser.add_argument("--commission-rate-range", dest="commission_rate_range", help="手续费候选值，逗号分隔")
    parser.add_argument("--slippage-rate-range", dest="slippage_rate_range", help="滑点候选值，逗号分隔")
    parser.add_argument("--stamp-duty-rate-range", dest="stamp_duty_rate_range", help="印花税候选值，逗号分隔")
    
    args = parser.parse_args()
    
    app = StockQuantPro()
    
    if args.command == "fetch":
        if args.code:
            data = app.fetch_realtime(args.code)
            
            # 如果东方财富失败，尝试腾讯财经
            if data is None:
                from src.api.tencent.client import TencentFinanceClient
                client = TencentFinanceClient()
                data = client.get_realtime(args.code)
            
            # 如果还是失败，使用模拟数据
            if data is None:
                from src.api.mock_data import MockDataGenerator
                mock = MockDataGenerator()
                data = mock.generate_realtime(args.code)
                print(f"[模拟数据] ", end="")
            
            if data:
                print(f"股票: {data.get('name', '')} | 现价: {data.get('price')} | 涨跌: {data.get('change')}%")
            else:
                print("获取数据失败")
        else:
            print("请指定股票代码: --code 000002")
    
    elif args.command == "analyze":
        if args.code:
            df = app.get_stock_data(args.code)
            
            # 本地没有则从网络获取
            if df is None or df.empty:
                print(f"本地没有 {args.code} 的数据，正在从网络获取...")
                client = EastMoneyClient()
                df = client.get_kline(args.code, days=120)
                
                if df is None or df.empty:
                    from src.api.tencent.client import TencentFinanceClient
                    client = TencentFinanceClient()
                    df = client.get_kline(args.code, days=120)
                
                if df is None or df.empty:
                    from src.api.mock_data import MockDataGenerator
                    mock = MockDataGenerator()
                    df = mock.generate_kline(args.code, days=120)
                    print("[使用模拟数据]")
            
            if df is not None and not df.empty:
                df = app.calculate_indicators(df)
                print(df.tail(10))
            else:
                print("无法获取数据")
        else:
            print("请指定股票代码: --code 000002")
    
    elif args.command == "import":
        if args.file:
            app.import_tonghuashun(args.file)
        else:
            print("请指定文件路径: --file path/to/file")
    
    elif args.command == "backtest":
        if not args.code:
            print("请指定股票代码: --code 000002")
            return
        
        strategy = args.strategy or "dual_ma"
        backtest_params = _collect_backtest_params(args)
        
        df, source = _load_backtest_dataframe(app, args.code, args.days)
        if source != "local":
            print(f"本地没有 {args.code} 的数据，正在从网络获取...")
            if source == "mock":
                print("使用模拟数据")
        
        if df is not None and not df.empty:
            # 计算指标
            df = app.calculate_indicators(df)
            
            # 运行回测
            result = app.run_backtest(df, strategy, **backtest_params)
            
            if 'error' in result:
                print(f"回测错误: {result['error']}")
            else:
                app.backtest.print_result(result)
                benchmark = result.get('benchmark_metrics', {})
                if benchmark:
                    print("基准对比:")
                    print(f"买入持有收益率: {benchmark.get('total_return', 0):.2f}%")
                    print(f"超额收益: {result['metrics'].total_return - benchmark.get('total_return', 0):.2f}%")
                if args.output_file:
                    _write_output_file(args.output_file, result)
                    print(f"结果已导出: {args.output_file}")
        else:
            print("无法获取数据，回测失败")

    elif args.command == "batchbacktest":
        codes = _parse_codes_arg(args.codes)
        if not codes:
            print("请指定股票代码列表: --codes 000001,000002,600036")
            return

        strategy = args.strategy or "dual_ma"
        backtest_params = _collect_backtest_params(args)
        rows = []

        for code in codes:
            df, source = _load_backtest_dataframe(app, code, args.days)
            if df is None or df.empty:
                rows.append({"code": code, "error": "无法获取数据", "source": source})
                continue

            result = app.run_backtest(df, strategy, **backtest_params)
            if "error" in result:
                rows.append({"code": code, "error": result["error"], "source": source})
                continue

            metrics = result["metrics"]
            benchmark = result["benchmark_metrics"]
            rows.append(
                {
                    "code": code,
                    "source": source,
                    "strategy": strategy,
                    "total_return": metrics.total_return,
                    "annual_return": metrics.annual_return,
                    "max_drawdown": metrics.max_drawdown,
                    "sharpe_ratio": metrics.sharpe_ratio,
                    "win_rate": metrics.win_rate,
                    "profit_factor": metrics.profit_factor,
                    "end_capital": metrics.end_capital,
                    "total_trades": metrics.total_trades,
                    "benchmark_return": benchmark["total_return"],
                    "excess_return": metrics.total_return - benchmark["total_return"],
                }
            )

        valid_rows = [row for row in rows if "error" not in row]
        valid_rows.sort(key=lambda item: item["total_return"], reverse=True)
        payload = {
            "strategy": strategy,
            "rows": valid_rows + [row for row in rows if "error" in row],
            "evaluated": len(valid_rows),
            "failed": len(rows) - len(valid_rows),
        }

        print(f"\n批量回测结果 - {strategy}")
        print(f"成功: {payload['evaluated']} | 失败: {payload['failed']}")
        print("Top:")
        for index, row in enumerate(valid_rows[:10], start=1):
            print(f"{index}. {row['code']} return={row['total_return']:.2f}% excess={row['excess_return']:.2f}% drawdown={row['max_drawdown']:.2f}% sharpe={row['sharpe_ratio']:.2f}")
        failed_rows = [row for row in rows if "error" in row]
        if failed_rows:
            print("失败项:")
            for row in failed_rows[:10]:
                print(f"- {row['code']}: {row['error']}")
        if args.output_file:
            _write_output_file(args.output_file, payload)
            print(f"结果已导出: {args.output_file}")

    elif args.command == "optimize":
        if not args.code:
            print("请指定股票代码: --code 000002")
            return

        strategy = args.strategy or "dual_ma"
        backtest_params = _collect_backtest_params(args)
        optimize_ranges = _collect_optimize_param_ranges(args)
        optimize_constraints = _collect_optimize_constraints(args)
        if optimize_ranges:
            backtest_params["param_ranges"] = optimize_ranges
        if optimize_constraints:
            backtest_params["constraints"] = optimize_constraints

        df = app.get_stock_data(args.code)
        if df is None or df.empty:
            print(f"本地没有 {args.code} 的数据，正在从网络获取...")
            client = EastMoneyClient()
            df = client.get_kline(args.code, days=250)

            if df is None or df.empty:
                from src.api.mock_data import MockDataGenerator
                mock = MockDataGenerator()
                df = mock.generate_kline(args.code, days=250)
                print("使用模拟数据")

        if df is not None and not df.empty:
            result = app.optimize_backtest(df, strategy, metric=args.metric, **backtest_params)
            if 'error' in result:
                print(f"优化错误: {result['error']}")
            else:
                print(f"\n优化结果 - {strategy} | 指标: {result['metric']}")
                print(f"评估组合数: {result['evaluated']}")
                print(f"过滤组合数: {result.get('filtered_out', 0)}")
                print(f"搜索范围: {result.get('param_ranges', {})}")
                print(f"筛选约束: {result.get('constraints', {})}")
                best = result['best']
                if best:
                    print(f"最佳参数: {best['params']}")
                    print(f"最佳得分: {best['score']:.4f}")
                else:
                    print("没有符合当前约束的参数组合")
                print("\nTop 5:")
                for index, item in enumerate(result['top_results'], start=1):
                    print(f"{index}. params={item['params']} score={item['score']:.4f} return={item['metrics']['total_return']:.2f}% excess={item['metrics']['excess_return']:.2f}% drawdown={item['metrics']['max_drawdown']:.2f}% sharpe={item['metrics']['sharpe_ratio']:.2f}")
                if result.get('stability_summary'):
                    print("\n参数稳定性:")
                    for item in result['stability_summary'][:5]:
                        print(f"- {item['params']} 出现 {item['count']} 次")
                if args.output_file:
                    _write_output_file(args.output_file, result)
                    print(f"结果已导出: {args.output_file}")
        else:
            print("无法获取数据，参数优化失败")

    elif args.command == "walkforward":
        if not args.code:
            print("请指定股票代码: --code 000002")
            return

        strategy = args.strategy or "dual_ma"
        backtest_params = _collect_backtest_params(args)
        optimize_ranges = _collect_optimize_param_ranges(args)
        optimize_constraints = _collect_optimize_constraints(args)
        walkforward_config = _collect_walkforward_config(args)
        if optimize_ranges:
            backtest_params["param_ranges"] = optimize_ranges
        if optimize_constraints:
            backtest_params["constraints"] = optimize_constraints
        if walkforward_config:
            backtest_params["walkforward_config"] = walkforward_config

        df = app.get_stock_data(args.code)
        if df is None or df.empty:
            print(f"本地没有 {args.code} 的数据，正在从网络获取...")
            client = EastMoneyClient()
            df = client.get_kline(args.code, days=500)

            if df is None or df.empty:
                from src.api.mock_data import MockDataGenerator
                mock = MockDataGenerator()
                df = mock.generate_kline(args.code, days=500)
                print("使用模拟数据")

        if df is not None and not df.empty:
            result = app.walkforward_backtest(df, strategy, metric=args.metric, **backtest_params)
            if 'error' in result:
                print(f"滚动验证错误: {result['error']}")
            else:
                print(f"\n滚动验证结果 - {strategy} | 指标: {result['metric']}")
                print(f"窗口: train={result['train_size']} test={result['test_size']} step={result['step_size']}")
                print(f"总段数: {len(result['segments'])}")
                print(f"总收益: {result['metrics'].total_return:.2f}% | 基准: {result['benchmark_metrics']['total_return']:.2f}%")
                print(f"最大回撤: {result['metrics'].max_drawdown:.2f}% | 夏普: {result['metrics'].sharpe_ratio:.2f}")
                if result.get('stability_summary'):
                    print("参数稳定性:")
                    for item in result['stability_summary'][:5]:
                        print(f"- {item['params']} 获胜 {item['count']} 段")
                print("\nSegments:")
                for index, item in enumerate(result['segments'], start=1):
                    print(f"{index}. train={item['train_start']}~{item['train_end']} test={item['test_start']}~{item['test_end']} params={item['best_params']} return={item['metrics']['total_return']:.2f}% excess={item['metrics']['excess_return']:.2f}%")
                if args.output_file:
                    _write_output_file(args.output_file, result)
                    print(f"结果已导出: {args.output_file}")
        else:
            print("无法获取数据，滚动验证失败")

    elif args.command == "sensitivity":
        if not args.code:
            print("请指定股票代码: --code 000002")
            return

        strategy = args.strategy or "dual_ma"
        backtest_params = _collect_backtest_params(args)
        commission_rates = _parse_float_range_arg(args.commission_rate_range) if args.commission_rate_range else None
        slippage_rates = _parse_float_range_arg(args.slippage_rate_range) if args.slippage_rate_range else None
        stamp_duty_rates = _parse_float_range_arg(args.stamp_duty_rate_range) if args.stamp_duty_rate_range else None

        df = app.get_stock_data(args.code)
        if df is None or df.empty:
            print(f"本地没有 {args.code} 的数据，正在从网络获取...")
            client = EastMoneyClient()
            df = client.get_kline(args.code, days=250)

            if df is None or df.empty:
                from src.api.mock_data import MockDataGenerator
                mock = MockDataGenerator()
                df = mock.generate_kline(args.code, days=250)
                print("使用模拟数据")

        if df is not None and not df.empty:
            result = app.sensitivity_backtest(
                df,
                strategy,
                commission_rates=commission_rates,
                slippage_rates=slippage_rates,
                stamp_duty_rates=stamp_duty_rates,
                **backtest_params,
            )
            if "error" in result:
                print(f"敏感性分析错误: {result['error']}")
            else:
                print(f"\n成本敏感性分析 - {strategy}")
                print(f"手续费候选: {result['commission_rates']}")
                print(f"滑点候选: {result['slippage_rates']}")
                print(f"印花税候选: {result['stamp_duty_rates']}")
                print(f"最佳: commission={result['best']['commission_rate']:.4f} slippage={result['best']['slippage_rate']:.4f} return={result['best']['total_return']:.2f}%")
                print(f"最差: commission={result['worst']['commission_rate']:.4f} slippage={result['worst']['slippage_rate']:.4f} return={result['worst']['total_return']:.2f}%")
                print("\nTop 5:")
                for index, item in enumerate(result['rows'][:5], start=1):
                    print(f"{index}. commission={item['commission_rate']:.4f} slippage={item['slippage_rate']:.4f} stamp={item['stamp_duty_rate']:.4f} return={item['total_return']:.2f}% excess={item['excess_return']:.2f}% drawdown={item['max_drawdown']:.2f}% sharpe={item['sharpe_ratio']:.2f}")
                if args.output_file:
                    _write_output_file(args.output_file, result)
                    print(f"结果已导出: {args.output_file}")
        else:
            print("无法获取数据，敏感性分析失败")


if __name__ == "__main__":
    main()
