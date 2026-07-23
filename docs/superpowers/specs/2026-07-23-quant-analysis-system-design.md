# 量化分析系统设计

日期：2026-07-23
状态：已确认设计，待写实现计划
范围：本地单人自用；纯 Python；数据源统一用 MySQL（按 `database/mysql/mysql.env`）

## 背景

仓库已具备 A 股前复权日线数据：SQLite `database/sqlite/astocks_qfq.db`（约 1.8GB，5201 只股票，2010-01-04 → 2026-04-30，约 984 万条），并已镜像到远程 MySQL（`astocks_qfq` 库，表 `stocks` / `daily_qfq`，连接见 `database/mysql/mysql.env`）。字段口径：`ts_code, trade_date(YYYYMMDD), open, high, low, close_qfq, volume, amount`，价格为 baostock 前复权（`adjustflag=2`）。

`docs/课04_*` 的技术分析课件体现了目标分析取向：趋势线（触点越多越有效）、浪型/背离结构、空间·速度·结构、资金/仓位面。

现要在此数据之上构建一个量化交易分析系统：技术指标分析、资金集中度分析、量化策略回测，并产出交互式网页图表（可调时间轴、可画趋势线）。

## 目标

1. 提供技术指标分析与交互式 K 线网页（可缩放时间轴、可手画趋势线）。
2. 提供“资金集中度”分析（市场成交额集中度，A 类），支持每日计算与历史回看。
3. 提供量化策略回测引擎与 5 个内置策略，输出绩效与净值/买卖点图。
4. 保持简洁高效：纯 Python，本地一条命令启动，`quant/` 核心库与界面解耦、可独立测试。

## 非目标

- 不做个股主力资金流 / 龙虎榜 / 股东户数 / 北向资金（B 类），本版不接 akshare。
- 不做行业级集中度（现库无行业分类；板块级用代码前缀可做）。
- 不做实盘交易、下单、自动化调度。
- 不做多人/公网部署、鉴权、读写分离。
- 不做手画趋势线的持久化保存（Plotly 交互画线即可，保存留后续）。
- v1 回测只做单股；多股选股组合回测留 v2。

## 技术选型

- 后端/逻辑：Python + pandas + numpy（指标纯手写实现，不引重型 TA 库）。
- 数据源：MySQL（复用 `database/mysql/mysql_config.py` 的 `connect_mysql()`，读取 `database/mysql/mysql.env`）。
- 图表：Plotly（K 线、指标副图、`drawline` 画趋势线、`rangeslider` 调时间轴、净值曲线）。
- 界面：Streamlit（侧边栏 + 3 个 Tab）。
- 测试：pytest。

## 目录结构

```
x-growth/
├── database/                      # 已有，不动
├── quant/                         # 新增：纯逻辑核心库（不依赖 Streamlit）
│   ├── __init__.py
│   ├── config.py                  # 默认参数、数据源配置
│   ├── data/
│   │   ├── __init__.py
│   │   └── loader.py              # 统一行情读取（MySQL），输出标准字段
│   ├── indicators/
│   │   ├── __init__.py
│   │   └── ta.py                  # 技术指标库
│   ├── concentration/
│   │   ├── __init__.py
│   │   └── market.py              # 资金集中度 A：CR_N/HHI/基尼 + 板块分布
│   ├── backtest/
│   │   ├── __init__.py
│   │   ├── engine.py              # 向量化回测引擎（防未来函数）
│   │   ├── metrics.py             # 绩效指标
│   │   └── strategies/
│   │       ├── __init__.py        # 策略注册表
│   │       ├── base.py            # 策略接口（输入行情→输出仓位/信号）
│   │       ├── ma_cross.py        # 1 双均线交叉
│   │       ├── macd.py            # 2 MACD 金叉死叉
│   │       ├── bollinger.py       # 3 布林带均值回归
│   │       ├── rsi.py             # 4 RSI 超买超卖
│   │       └── donchian.py        # 5 唐奇安通道突破
│   └── charts/
│       ├── __init__.py
│       └── plots.py               # Plotly 图表封装
├── app/
│   └── main.py                    # Streamlit 入口（3 个 Tab）
├── tests/                         # pytest
│   ├── test_indicators.py
│   ├── test_concentration.py
│   ├── test_backtest_engine.py
│   └── test_metrics.py
└── requirements.txt               # 追加 streamlit, plotly（保留 database 段）
```

设计原则：`quant/` 为纯逻辑库，可单独 import 与测试；`app/` 只负责界面拼装与调用。未来更换前端（Dash/JS）后端零改动。

## 模块设计

### 1. 数据访问层 `quant/data/loader.py`

复用 `database/mysql/mysql_config.py::connect_mysql()`。对外提供：

- `load_daily(ts_code, start=None, end=None) -> DataFrame`：标准列 `open, high, low, close, volume, amount`（`close` 由 `close_qfq` 映射），索引为 `trade_date`（datetime），按日期升序。
- `load_cross_section(date) -> DataFrame`：某交易日全市场截面（`ts_code, name, close, volume, amount`），用于集中度。
- `list_stocks() -> DataFrame`：`ts_code, name`，供界面搜索。
- `trading_dates(start, end) -> list`：区间内实际交易日。

约定：升序读取、区间过滤下推到 SQL；不一次性载入全库。日期在库内为 `YYYYMMDD` 字符串，读出后转 datetime。

### 2. 技术指标库 `quant/indicators/ta.py`

纯 pandas/numpy 实现，输入价格/量序列，输出同长度序列：

- 趋势：`ma`、`ema`、`macd`（DIF/DEA/HIST）、`boll`（上轨/中轨/下轨）
- 动量：`rsi`、`kdj`（K/D/J）、`roc`
- 量能：`obv`、`mfi`、`vol_ma`
- 波动：`atr`
- 结构辅助：`swing_points`（波段高低点）、`auto_trendline`（基于波段点拟合趋势线，触点越多权重越高）、`ma_bull_alignment`（均线多头排列布尔序列）

### 3. 资金集中度 A `quant/concentration/market.py`

基于每日全市场 `amount`（成交额）截面分布：

- `CR_N`：成交额前 N 名占全市场比例，N ∈ {5,10,20,50,100}
- `HHI`：Σ(share_i²)，share_i = amount_i / total_amount
- `gini`：成交额分布基尼系数
- 板块分布：用 `ts_code` 前缀分类占比
  - 沪主板 `60*`、深主板 `000*`/`001*`、中小板 `002*`、创业板 `300*`/`301*`、科创板 `688*`、北交所 `8*`/`4*`/`92*`
- 输出：
  - `concentration_series(start, end)`：逐日集中度时间序列（回看历史）
  - `concentration_detail(date)`：某日成交额排行明细 + 板块占比

**预计算与缓存（MySQL）**：新建表 `market_concentration`，全历史逐日预计算一次并写入；界面读该表实现秒开；提供 `rebuild`（全量重算）与增量更新（追加最新交易日）两种入口。

`market_concentration` 建议字段：

```
trade_date CHAR(8) PRIMARY KEY,
total_amount DECIMAL(24,2),
cr5 DECIMAL(8,6), cr10 DECIMAL(8,6), cr20 DECIMAL(8,6), cr50 DECIMAL(8,6), cr100 DECIMAL(8,6),
hhi DECIMAL(12,10), gini DECIMAL(8,6),
amt_sh_main DECIMAL(24,2), amt_sz_main DECIMAL(24,2), amt_sme DECIMAL(24,2),
amt_gem DECIMAL(24,2), amt_star DECIMAL(24,2), amt_bse DECIMAL(24,2)
```

### 4. 回测引擎 `quant/backtest/`

- `engine.py`：向量化回测。**严格防未来函数**——T 日收盘用截至 T 的数据生成信号，T+1 成交（成交价可配 `open`/`close`）。支持手续费率与滑点。输入：行情 DataFrame + 策略产出的目标仓位/信号序列；输出：逐日持仓、净值、交易记录。
- `metrics.py`：累计收益、年化收益、年化波动、夏普、最大回撤、胜率、盈亏比、交易次数、与“买入持有”基准对比。
- `strategies/`：统一接口（`base.py`），每个策略输入标准行情、输出信号/目标仓位（0/1 多头或 -1/0/1）：
  1. `ma_cross`：快慢均线金叉买 / 死叉卖（趋势跟踪）
  2. `macd`：DIF 上穿 DEA 买 / 下穿卖
  3. `bollinger`：触下轨买 / 触上轨（或回中轨）卖（均值回归）
  4. `rsi`：RSI < 超卖阈买 / > 超买阈卖（均值回归）
  5. `donchian`：突破 N 日最高买 / 跌破 N 日最低卖（海龟式趋势突破）

  全部策略参数化，界面可调。

### 5. 图表 `quant/charts/plots.py`（Plotly）

- `kline_chart`：K 线主图 + 成交量副图 + 指标副图（MACD/RSI 可选）；开启 `dragmode='drawline'`、modebar 增加画线/擦除工具；`rangeslider` + 区间选择按钮调时间轴；叠加 MA/BOLL。
- `backtest_chart`：净值曲线 vs 买入持有基准、买卖点标注、回撤阴影。
- `concentration_chart`：CR/HHI/基尼历史曲线 + 板块占比堆叠面积图 + 某日明细排行条形图。

### 6. Streamlit 界面 `app/main.py`

- 侧边栏：股票搜索（代码/名称）、时间范围、指标勾选、（数据源信息只读）。
- Tab1 行情分析：K 线 + 所选指标 + 手画趋势线。
- Tab2 资金集中度：历史集中度曲线（可选 CR_N/HHI/基尼）+ 选定日明细 + 板块分布。
- Tab3 策略回测：选策略 + 参数 + 股票 + 区间 + 成交价/费用 → 运行 → 绩效表 + 净值图 + 买卖点。

## 数据流

1. 界面收集参数 → 调 `quant.data.loader` 取行情/截面。
2. Tab1：行情 → `indicators.ta` 算指标 → `charts.plots.kline_chart` 渲染。
3. Tab2：读 `market_concentration` 缓存表（`concentration.market`）→ `charts.plots.concentration_chart`。
4. Tab3：行情 → `strategies.*` 出信号 → `backtest.engine` 回测 → `backtest.metrics` 绩效 → `charts.plots.backtest_chart`。

## 错误处理

- MySQL 连接失败：界面给出明确提示（检查 `mysql.env` / 网络），不崩溃。
- 股票代码不存在 / 区间无数据：返回空并在界面提示，不抛未捕获异常。
- 集中度缓存表不存在或过期：提示先运行 `rebuild`；缺失最新交易日时提示增量更新。
- 回测输入过短（不足以形成指标窗口）：跳过并提示所需最小样本。

## 测试

- `test_indicators.py`：MA/EMA/RSI/MACD/BOLL/ATR 用小样本对拍已知值。
- `test_concentration.py`：构造小截面手算 CR_N/HHI/基尼与板块分类验证。
- `test_backtest_engine.py`：已知价格序列 + 简单信号，校验成交对齐（T+1）、**无未来函数**、手续费计算、净值正确。
- `test_metrics.py`：已知净值序列校验年化/夏普/最大回撤。

## 依赖

`requirements.txt` 追加：`streamlit`、`plotly`（`pandas`、`numpy`、`pymysql` 已有）。

## 里程碑（供实现计划参考）

1. 数据访问层 + 指标库 + 单测。
2. 集中度算法 + `market_concentration` 缓存表 + 预计算脚本 + 单测。
3. 回测引擎 + 5 策略 + 绩效 + 单测。
4. Plotly 图表封装。
5. Streamlit 三 Tab 界面串联。
