# StockQuant Pro - 优化计划

## 优化优先级排序

### 🔴 P0 - 关键问题（已完成 ✅）

| # | 问题 | 影响 | 状态 |
|---|------|------|------|
| 1 | **API重试机制缺失** | EastMoney有重试，但TuShare没有，网络不稳定时容易失败 | ✅ `tushare_retry_on_error` 装饰器 + 429限流处理 |
| 2 | **数据缓存机制不完善** | 每次请求都调API，浪费资源且容易触发限流 | ✅ `TushareCache` LRU内存缓存 |
| 3 | **指标计算重复** | signal_generator.py 每次分析都重复计算指标 | ✅ `IndicatorCalculator` 内置缓存 |

### 🟠 P1 - 重要功能（已完成 ✅）

| # | 功能 | 影响 | 状态 |
|---|------|------|------|
| 4 | **背离检测** | MACD/RSI/KDJ顶底背离是重要反转信号 | ✅ `divergence_detector.py` 顶底背离检测 |
| 5 | **自适应权重** | 信号权重可根据市场状态动态调整 | ✅ `adaptive_weight.py` 市场状态自适应 |
| 6 | **更多技术指标** | SKDJ, DMI, VR, MI, PVI/NVI | ✅ 13个新指标 (SKDJ/DMI/VR/MI/PVI/NVI/TRIX/DMA/EXPMA/BIAS/PSY/MFI/TEMA) |
| 7 | **数据增量更新** | 只获取新数据，减少API调用 | ✅ `incremental_update.py` 增量更新管理器 |

### 🟡 P2 - 增强功能（进行中 🔄）

| # | 功能 | 影响 | 状态 |
|---|------|------|------|
| 8 | **桌面通知** | 集成 plyer 发送信号通知 | ✅ `notifier.py` 已实现 |
| 9 | **飞书推送** | 信号推送至飞书群 | ✅ Webhook卡片消息已实现 |
| 10 | **图表可视化** | K线+指标绑定展示 | TODO |
| 11 | **风险指标增强** | 添加索提诺比率、Omega比率 | TODO |

### 🟢 P3 - 长期优化（规划中）

| # | 功能 | 影响 | 状态 |
|---|------|------|------|
| 12 | **蒙特卡洛模拟** | 模拟收益分布 | TODO |
| 13 | **组合回测** | 多标的组合 | TODO |
| 14 | **参数优化算法** | 遗传算法、贝叶斯优化 | TODO |

---

## 已完成功能详情

### P0-1: API重试机制 ✅
```python
@tushare_retry_on_error(max_retries=3, base_delay=1.0)
def get_kline(self, code: str, days: int = 250, ktype: str = 'D'):
    # 429限流自动等待60秒
    # 网络错误指数退避重试
    # 3次重试后仍失败抛出异常
```

### P0-2: 数据缓存 ✅
```python
TushareCache(max_size=100, ttl_seconds=3600)
# 实时行情: 1分钟 TTL
# 日线数据: 1小时 TTL
# 周线/月线: 24小时 TTL
```

### P0-3: 指标计算缓存 ✅
```python
IndicatorCalculator(cache_size=100)
# 自动缓存计算结果
# LRU清理机制
# 避免重复计算
```

### P1-4: 背离检测 ✅
```python
DivergenceDetector(lookback=20)
# 顶背离检测 (价格创新高,指标没新高)
# 底背离检测 (价格创新低,指标没新低)
# get_divergence_signal() 综合背离信号
```

### P1-5: 自适应权重 ✅
```python
AdaptiveWeightEngine()
# MarketRegime: TREND_UP/TREND_DOWN/VOLATILE/CONSOLIDATION
# get_weights_with_volume(df) 获取自适应权重
# 趋势市场: MACD/MA权重增加
# 震荡市场: RSI/KDJ权重增加
```

### P1-6: 更多技术指标 ✅
```
SKDJ  - 慢速随机指标
DMI   - 趋向指标  
VR    - 成交量变异率
MI    - 质量指标
PVI   - 正量指标
NVI   - 负量指标
TRIX  - 三重指数平滑平均线
DMA   - 差分平均线
EXPMA - 指数加权移动平均
BIAS  - 乖离率
PSY   - 心理线
MFI   - 资金流量指标
TEMA  - 三重指数移动平均
```

### P2-8/9: 通知系统 ✅
```python
DesktopNotifier()
# send_signal_notification() 发送信号通知
# notify_error() 发送错误通知
# 支持飞书 Webhook 卡片消息
```

---

## Git 提交记录

```
77e6877 P1优化: 自适应信号权重 + 数据增量更新
baad3f0 P0优化: API重试机制、数据缓存、指标缓存
e178e4e P2优化: 桌面通知 + 飞书推送
```

---

## 进度记录

- [x] 创建优化计划
- [x] P0-1: API重试机制 ✅
- [x] P0-2: 数据缓存机制 ✅
- [x] P0-3: 指标计算优化 ✅
- [x] P1-4: 背离检测 ✅
- [x] P1-5: 自适应权重 ✅
- [x] P1-6: 更多技术指标 ✅
- [x] P1-7: 数据增量更新 ✅
- [x] P2-8: 桌面通知 ✅
- [x] P2-9: 飞书推送 ✅
- [ ] P2-10: 图表可视化
- [ ] P2-11: 风险指标增强
