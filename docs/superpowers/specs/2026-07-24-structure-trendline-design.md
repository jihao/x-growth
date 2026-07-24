# 结构分析 · 自动趋势线设计

日期：2026-07-24  
状态：已确认设计，待写实现计划  
范围：第一期「结构分析引擎」子集——日线自动趋势线；本地 Streamlit；数据仍用 MySQL 日线

## 背景

量化分析系统 v1（行情 / 资金集中度 / 单股回测）已落地。`docs/课04_*` 课件强调趋势线「触点越多越有效」、浪型速度、背离等结构方法，但 v1 未实现这些算法（仅有手画趋势线工具）。

本设计是结构分析大项的第一期，只做**自动趋势线**。浪型速度、背离、全市场选股、结构策略回测列为后续子项目。

## 目标

1. 对单股日线自动识别波段高低点，拟合上升/下降趋势线，按触点数打分，输出 Top-K。
2. 相对当前最优线给出位置状态：`above` / `below` / `broken`（收盘破）。
3. 在行情分析 Tab 的 K 线上叠加趋势线与触点，并展示可解释明细表。
4. 界面预留「周线」入口（disabled / coming soon），第一期不算周线。
5. 逻辑放在 `quant/structure/`，与 Streamlit 解耦，便于后续选股扫描复用。

## 非目标

- 不做浪型速度、背离结构。
- 不做全市场选股扫描。
- 不做结构类回测策略。
- 不做周线真实计算（仅 UI 占位）。
- 不持久化手画或自动趋势线到数据库。
- 不修改现有 5 个回测策略。

## 技术选型

- 纯 pandas / numpy（与现有 `quant/` 一致）。
- 图表：Plotly，在现有 `kline_chart` 上叠加线段与标记。
- 界面：Streamlit「行情分析」Tab 扩展。
- 测试：pytest，合成 K 线离线测。

## 目录结构

```
quant/structure/
  __init__.py
  models.py          # Trendline, TrendlineResult 等数据结构
  swings.py          # detect_swings(high, low, window, min_pct)
  trendlines.py      # find_trendlines / evaluate_breakout
quant/charts/plots.py   # 增 overlay_trendlines(fig, result) 或 kline 可选参数
app/main.py             # Tab1：自动趋势线开关、参数、明细、周线占位
tests/
  test_swings.py
  test_trendlines.py
```

说明：现有 `quant.indicators.ta.swing_points` 基于 `close` + `center=True`，文档已标明仅供事后可视化、不得用于交易信号。结构引擎在 `swings.py` 独立实现，对 `high`/`low` 取峰谷，并写明「复盘/展示/历史扫描；最近 window 根未确认点不参与连线」。

## 算法

### 波段点

- 输入：`high`、`low` 序列，参数 `window`（默认 5）、`min_pct`（默认 0.01）。
- 居中窗口确认局部高/低点；相邻点价差过小则过滤。
- 最近 `window` 根因未确认，不作为连线端点。

### 连线与触点

- 上升趋势线：波段低点两两连线；下降趋势线：波段高点两两连线。
- 触点判定：点到直线相对偏离 `|price - line| / price ≤ tol`（默认 `tol=0.015`）。
- 约束：两点间隔 ≥ `min_bars`（默认 10）。
- 分析窗口：侧栏所选日线区间（不再另截）。

### 打分

```
score = touch_count * 10 + span_bars * 0.01 + recent_bonus
```

- `recent_bonus`：最近 60 根内有触点则 +5。
- 上升、下降各保留 Top-K（默认 K=3）；同分先比触点数再比跨度。

### 破位（收盘破）

- 对上升最优线：`close < line_price * (1 - tol)` → `broken`，否则 `above`。
- 对下降最优线：`close > line_price * (1 + tol)` → `broken`，否则 `below`。
- 输出附带 `line_price_today`、`distance_pct`。

### 可解释字段（每条线）

`side`（up/down）、`slope`、`intercept`、`touch_dates`、`touch_count`、`score`、`start_date`、`end_date`、`status`。

## 界面

- Tab1「行情分析」：
  - 开关「自动趋势线」（默认开）
  - 可折叠高级参数：`window`、`tol`、`top_k`、`min_bars`
  - 周期选择：日线（可用）/ 周线（disabled，文案「即将支持」）
  - K 线叠加 Top-K 上升/下降线与触点标记
  - 破位时 caption/标题提示
  - expander「趋势线明细」表格

## 数据流

```
load_daily → detect_swings → find_trendlines → evaluate_breakout
  → overlay on kline_chart → 明细表
```

## 错误处理

- 波段点不足（无法连线）：界面提示「区间内有效波段点不足」，不画线、不抛未捕获异常。
- 空行情：沿用现有「该区间无数据」提示。

## 测试

- `test_swings.py`：合成峰谷，断言高低点位置与 `min_pct` 过滤。
- `test_trendlines.py`：三点共线触点数与得分；超容差不计入；收盘跌破上升线 → `broken`。

## 验收标准

1. 走势清晰个股上能画出合理上升/下降线及触点。
2. 触点更多的线排序更靠前（符合课件原则）。
3. 变更日期区间后重算稳定、不崩溃。
4. 全量 pytest 通过，新增结构测试全绿。

## 后续子项目（本 spec 不包含）

1. 浪型速度（三浪 vs 一浪斜率）
2. 背离结构
3. 全市场选股扫描（复用本引擎）
4. 结构策略回测
5. 周线聚合与真实周线趋势线
