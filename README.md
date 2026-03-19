# StockQuant Pro

[![CI](https://github.com/hanlibin1981/stock-quant/actions/workflows/ci.yml/badge.svg)](https://github.com/hanlibin1981/stock-quant/actions/workflows/ci.yml)

股票量化交易与信号分析系统，包含数据获取、技术指标、策略回测、参数优化、滚动验证、信号监控和 Web 界面。

## 当前能力

- 多数据源行情链路
  - `TuShare`
  - `EastMoney`
  - `Tencent`
  - `mock` 回退
- 技术指标
  - `MA / EMA / MACD / RSI / KDJ / BOLL / CCI / ATR / OBV / WR`
- 回测与优化
  - 手续费、印花税、滑点、仓位、最小交易单位
  - 固定止损、止盈、移动止损、ATR 止损、分批止盈
  - 参数优化
  - `walk-forward` 滚动验证
  - 成本敏感性分析
  - 批量回测
  - JSON / CSV 导出
- 策略
  - `multi_factor`
  - `dual_ma`
  - `macd`
  - `breakout`
  - `rsi`
  - `boll_reversion`
  - `turtle_breakout`
  - `volume_breakout`
- 交易信号
  - 当前信号
  - 指标详情
  - 历史验证
  - 最近信号复盘
  - 数据来源透明展示
- Web 部署
  - Flask 页面
  - macOS `launchd` 常驻服务
  - 发布包构建与健康检查

## 环境要求

- Python 3.12+
- macOS 或 Linux
- 建议使用虚拟环境

## 安装

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
pip install -r requirements-gui.txt
```

## TuShare 配置

项目中的 `TuShare` 客户端从环境变量 `TUSHARE_TOKEN` 读取 token。

本地开发可以直接导出：

```bash
export TUSHARE_TOKEN=your_token_here
```

生产模式推荐写入：

```bash
config/production.env
```

示例文件见 [production.env.example](/Users/mac/openclaw-projects/stock-quant/config/production.env.example)。

## 常用命令

获取实时行情：

```bash
./venv/bin/python -m src.main fetch --code 000002
```

分析技术指标：

```bash
./venv/bin/python -m src.main analyze --code 000002
```

运行回测：

```bash
./venv/bin/python -m src.main backtest --code 000002 --strategy multi_factor
```

参数优化：

```bash
./venv/bin/python -m src.main optimize --code 000002 --strategy multi_factor --metric balanced
```

滚动验证：

```bash
./venv/bin/python -m src.main walkforward --code 000002 --strategy multi_factor
```

成本敏感性分析：

```bash
./venv/bin/python -m src.main sensitivity --code 000002 --strategy dual_ma
```

批量回测：

```bash
./venv/bin/python -m src.main batchbacktest --codes 000001,000002,600036 --strategy multi_factor
```

## Web 界面

开发方式启动：

```bash
./venv/bin/python -m src.ui.web_app
```

生产方式启动：

```bash
chmod +x scripts/run_production.sh
./scripts/run_production.sh
```

默认生产地址：

```text
http://127.0.0.1:5004
```

## 正式部署

安装 `launchd` 常驻服务：

```bash
chmod +x scripts/install_launchd_service.sh scripts/run_production.sh
./scripts/install_launchd_service.sh
```

常用命令：

```bash
launchctl unload ~/Library/LaunchAgents/com.stockquant.web.plist
launchctl load ~/Library/LaunchAgents/com.stockquant.web.plist
tail -f logs/stockquant.stdout.log
tail -f logs/stockquant.stderr.log
```

## 构建与校验

推荐流程：

```bash
make verify
make build-release
make install-service
make healthcheck
```

说明：

- `make verify`：语法检查与核心单元测试
- `make build-release`：生成发布包
- `make install-service`：安装 `launchd` 服务
- `make healthcheck`：检查生产服务接口

## GitHub Actions

仓库已配置最小 CI，自动执行：

- Python 语法检查
- `tests.test_backtest_engine`

工作流文件见 [ci.yml](/Users/mac/openclaw-projects/stock-quant/.github/workflows/ci.yml)。

## 项目结构

```text
stock-quant/
├── config/                  # 环境配置
├── deploy/                  # 部署模板
├── scripts/                 # 构建、部署、监控脚本
├── src/
│   ├── api/                 # 数据源接入
│   ├── core/                # 回测、指标、信号、策略核心
│   ├── ui/                  # Flask Web 界面
│   └── main.py              # CLI 入口
├── tests/                   # 单元测试
├── Makefile
└── README.md
```

## 已知说明

- `requirements.txt` 中的 `sqlite3` 是 Python 内置模块，不需要额外安装系统包。
- 没有可用外部数据源时，系统会自动回退到 `mock` 数据；Web 页面会显示当前数据来源。
- 监控脚本会自动尝试加载 `config/production.env`，避免单独运行时丢失 `TUSHARE_TOKEN`。

## 许可证

MIT License
