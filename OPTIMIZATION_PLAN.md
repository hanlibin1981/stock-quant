# StockQuant Pro - 优化计划

## 优化优先级排序

### 🔴 P0 - 关键问题（已完成 ✅）

| # | 问题 | 影响 | 状态 |
|---|------|------|------|
| 1 | **API重试机制缺失** | 网络不稳定时API调用失败 | ✅ 装饰器 + 429限流处理 |
| 2 | **数据缓存机制不完善** | 浪费资源且触发限流 | ✅ TushareCache LRU |
| 3 | **指标计算重复** | 每次分析重复计算指标 | ✅ IndicatorCalculator 缓存 |

### 🟠 P1 - 重要功能（已完成 ✅）

| # | 功能 | 影响 | 状态 |
|---|------|------|------|
| 4 | **背离检测** | MACD/RSI/KDJ顶底背离 | ✅ divergence_detector.py |
| 5 | **自适应权重** | 市场状态动态调整权重 | ✅ adaptive_weight.py |
| 6 | **更多技术指标** | 13个新指标 | ✅ SKDJ/DMI/VR/MI/PVI/NVI/TRIX... |
| 7 | **数据增量更新** | 减少API调用 | ✅ incremental_update.py |

### 🟡 P2 - 增强功能（已完成 ✅）

| # | 功能 | 影响 | 状态 |
|---|------|------|------|
| 8 | **桌面通知** | 桌面弹窗通知 | ✅ notifier.py + plyer |
| 9 | **飞书推送** | 飞书群Webhook | ✅ notifier.py |
| 10 | **图表可视化** | K线+指标绑定展示 | ✅ chart.py (Plotly) |
| 11 | **风险指标增强** | Omega/VaR/CVaR | ✅ risk_metrics.py |

### 🟢 P3 - 长期优化（规划中）

| # | 功能 | 影响 | 状态 |
|---|------|------|------|
| 12 | **蒙特卡洛模拟** | 模拟收益分布 | TODO |
| 13 | **组合回测** | 多标的组合 | TODO |
| 14 | **参数优化算法** | 遗传算法/贝叶斯 | TODO |

---

## 已完成功能详情

### P0-1: API重试机制 ✅
```python
@tushare_retry_on_error(max_retries=3, base_delay=1.0)
# 429限流自动等待60秒，指数退避重试
```

### P0-2: 数据缓存 ✅
```python
TushareCache(max_size=100, ttl_seconds=3600)
# 实时:1分钟, 日线:1小时, 周/月:24小时
```

### P0-3: 指标计算缓存 ✅
```python
IndicatorCalculator(cache_size=100)
# LRU清理，避免重复计算
```

### P1-4: 背离检测 ✅
```python
DivergenceDetector(lookback=20)
# 顶背离/底背离/隐藏背离
# get_divergence_signal() 综合信号
```

### P1-5: 自适应权重 ✅
```python
AdaptiveWeightEngine()
# TREND_UP/TREND_DOWN/VOLATILE/CONSOLIDATION
# get_weights_with_volume(df)
```

### P1-6: 13个新指标 ✅
```
SKDJ DMI VR MI PVI NVI TRIX DMA EXPMA BIAS PSY MFI TEMA
```

### P2-8/9: 通知系统 ✅
```python
DesktopNotifier()
# send_signal_notification()
# 飞书 Webhook 卡片消息
```

### P2-10: 图表可视化 ✅
```python
StockChartGenerator()
# create_candlestick_chart()
# K线 + 均线 + 布林带 + MACD/RSI/KDJ
# save_html()/get_html()
```

### P2-11: 风险指标增强 ✅
```python
EnhancedRiskAnalyzer()
# Omega比率、VaR/CVaR、偏度/峰度
# 连续亏损分析、尾部比率
# get_risk_summary() → 风险等级A/B/C/D
```

---

## Git 提交记录

```
c581d7f P2优化: K线图表可视化 + 风险指标增强
77e6877 P1优化: 自适应信号权重 + 数据增量更新
baad3f0 P0优化: API重试机制、数据缓存、指标缓存
e178e4e P2优化: 桌面通知 + 飞书推送
```

## 新增文件

```
src/core/indicator/divergence_detector.py  # 背离检测
src/core/signal/adaptive_weight.py      # 自适应权重
src/core/data/incremental_update.py      # 增量更新
src/core/notification/notifier.py       # 通知系统
src/core/visualization/chart.py       # Plotly图表
src/core/backtest/risk_metrics.py      # 风险指标
```

## 进度记录

- [x] P0-1: API重试机制 ✅
- [x] P0-2: 数据缓存机制 ✅
- [x] P0-3: 指标计算优化 ✅
- [x] P1-4: 背离检测 ✅
- [x] P1-5: 自适应权重 ✅
- [x] P1-6: 更多技术指标 ✅
- [x] P1-7: 数据增量更新 ✅
- [x] P2-8: 桌面通知 ✅
- [x] P2-9: 飞书推送 ✅
- [x] P2-10: 图表可视化 ✅
- [x] P2-11: 风险指标增强 ✅
- [ ] P3-12: 蒙特卡洛模拟
- [ ] P3-13: 组合回测
- [ ] P3-14: 参数优化算法
