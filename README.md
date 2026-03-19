# StockQuant Pro

股票量化交易工具 - 数据分析、策略回测、信号生成，支持与同花顺软件数据互通，集成VN.py实现实盘交易。

## 功能特性

### 📊 数据模块
- 实时/历史行情获取（东方财富 + TuShare 双数据源）
- 日线/周线/月线/分钟线数据支持
- 数据本地 SQLite 存储与缓存
- 同花顺数据导入（.otd / .h5 / .xlsx / .csv 格式）
- TuShare 专业数据接口（需配置 Token）
- 模拟数据后备（API不可用时）

### 📈 分析模块
- 常用技术指标：MA, EMA, MACD, RSI, KDJ, BOLL, CCI, ATR, OBV, WR
- 自定义指标公式
- 多股票对比分析

### 🎯 策略模块
- 经典策略模板：
  - 双均线策略
  - MACD 策略
  - 突破策略
  - RSI 策略
- 策略回测引擎
- 收益统计（收益率、夏普比率、最大回撤）

### 🚀 实盘交易 (VN.py)
- VN.py 交易框架集成
- 支持 CTP/券商API
- 订单管理（下单/撤单/持仓）
- 账户资金查询

### 🔔 交易信号
- 买入/卖出信号生成
- 信号记录与复盘

### 🌐 Web 界面
- 实时行情查看
- 技术指标分析
- 策略回测
- K线数据浏览

## 安装

```bash
cd ~/openclaw-projects/stock-quant
pip install -r requirements.txt
```

## 使用方法

### 获取股票实时行情
```bash
python -m src.main fetch --code 000002
```

### 分析股票（计算指标）
```bash
python -m src.main analyze --code 000002
```

### 运行回测
```bash
python -m src.main backtest --code 000002 --strategy dual_ma
```

### 导入同花顺数据
```bash
python -m src.main import --file /path/to/data.csv
```

## 正式部署

### 本机生产启动
```bash
cd ~/openclaw-projects/stock-quant
chmod +x scripts/run_production.sh
STOCKQUANT_PORT=5004 ./scripts/run_production.sh
```

默认地址:
```text
http://127.0.0.1:5004
```

### macOS launchd 常驻服务
```bash
cd ~/openclaw-projects/stock-quant
mkdir -p logs
chmod +x scripts/install_launchd_service.sh scripts/run_production.sh
./scripts/install_launchd_service.sh
```

首次安装后可在 `config/production.env` 中统一管理端口和主机配置。

常用管理命令:
```bash
launchctl unload ~/Library/LaunchAgents/com.stockquant.web.plist
launchctl load ~/Library/LaunchAgents/com.stockquant.web.plist
tail -f ~/openclaw-projects/stock-quant/logs/stockquant.stdout.log
tail -f ~/openclaw-projects/stock-quant/logs/stockquant.stderr.log
```

### 构建策略

推荐使用下面的固定流程:

```bash
cd ~/openclaw-projects/stock-quant
make verify
make build-release
make install-service
make healthcheck
```

说明:
- `make verify`: 运行语法检查和核心单元测试，确保发布前可用
- `make build-release`: 生成 `dist/stockquant-<timestamp>.tar.gz` 发布包
- `make install-service`: 渲染并安装 `launchd` 服务文件
- `make healthcheck`: 验证生产服务接口是否正常响应

### Python 代码调用

```python
from src.main import StockQuantPro

app = StockQuantPro()

# 获取实时行情
data = app.fetch_realtime('000002')
print(f"万科A现价: {data['price']}")

# 获取历史数据
df = app.get_stock_data('000002', start_date='20250101')

# 计算指标
df = app.calculate_indicators(df, ['ma', 'macd', 'rsi'])

# 运行回测
result = app.run_backtest(df, 'dual_ma', fast_ma=5, slow_ma=20)

# 导入同花顺数据
df = app.import_tonghuashun('/path/to/file.csv')
```

## 项目结构

```
stock-quant/
├── src/
│   ├── main.py                 # 主入口
│   ├── core/                   # 核心引擎
│   │   ├── data/              # 数据模块
│   │   │   └── stock_data.py  # 数据管理器
│   │   ├── indicator/         # 指标模块
│   │   │   └── calculator.py  # 指标计算器
│   │   ├── strategy/          # 策略模块
│   │   │   └── strategy.py    # 策略引擎
│   │   └── backtest/          # 回测模块
│   │       └── backtest.py    # 回测引擎
│   └── api/                   # 外部接口
│       ├── eastmoney/         # 东方财富API
│       └── tonghuashun/       # 同花顺兼容
├── requirements.txt
├── SPEC.md
└── README.md
```

## 待实现

- [ ] 图形界面 (PyQt6)
- [ ] 实盘交易对接
- [ ] 策略参数优化
- [ ] 更多数据源（新浪、腾讯）
- [ ] 策略信号桌面通知

## 许可证

MIT License
