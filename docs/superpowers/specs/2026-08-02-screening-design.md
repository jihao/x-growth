# 多策略加权选股设计

日期：2026-08-02  
状态：已实现（v1 动态加权 + 跑批落库）  
范围：全市场每日扫描选股；多策略动态加权 + 结构因子 + 量价热度合成评分；结果落 MySQL；Streamlit 第四 Tab 展示；预留 v2 机器学习接口

## 背景

系统已有 5 个经典策略的单股回测（`quant/backtest/`）与浪型/背离/趋势线结构分析（`quant/structure/`），但选股仍靠人工逐只查看。需要一个每日跑批的选股功能：以市场热点（成交额 top250）为股票池，融合多策略信号（按近期回测绩效动态加权）、结构因子与量价因子，输出值得关注的股票榜。

## 目标

1. 每日一次跑批：全市场截面 → 成交额 top250 缩圈 → 逐股评分 → top50 落库。
2. 评分 = 策略组 / 结构组 / 量价组三层加权合成，权重可配置。
3. 策略组内部权重动态化：对该股近 120 日逐策略滚动回测，按夏普归一化。
4. 结构因子直接复用 `quant/structure/`：DIF 背离、浪型速度、趋势线突破。
5. Streamlit 新增「选股榜」Tab 只读展示，可跳回行情分析。
6. 架构预留 v2 监督学习（ML）接口，v1 不引入 ML 依赖。

## 非目标

- 实时盘中选股（数据为日频，收盘后跑批）
- 自动化调度（沿用项目惯例，手动执行，串在日更之后）
- v1 不训练 ML 模型、不改 `requirements.txt`
- 多股组合回测（仍属回测 v2 范畴）

## 总体流程

```
load_cross_section(最新交易日)
  -> 过滤：剔除 ST / 停牌(volume=0) / 无成交 -> 成交额 top250
  -> 逐股 load_daily(近 400 自然日)
       策略组：dynamic_strategy_weights(近120日回测夏普归一化) × 各策略最新持仓信号
       结构组：0.4*背离 + 0.35*趋势线 + 0.25*浪型
       量价组：0.5*热度(成交额分位+量比) + 0.5*动量(20日收益分位)
  -> combine_scores(组间权重 0.4/0.35/0.25) -> 排序 top50 -> screening_results 表
Streamlit Tab4 只读展示
```

## 目录结构

```
quant/screening/
  __init__.py
  factors.py    # 六个打分器 + structure_score 合成 + ret20/amount_avg 原始量
  weights.py    # dynamic_strategy_weights / normalize_group_weights / combine_scores
  pipeline.py   # run() 扫描管线（截面过滤 -> 逐股评分 -> 排序）
  store.py      # ensure_table / save_results / load_results / list_dates
  cli.py        # python -m quant.screening.cli 跑批入口
  explain.py    # 规则化中文解读与交易建议（不依赖 LLM）
  llm.py        # LLM 深度解读（OpenAI 兼容接口，可选）
app/main.py     # Tab4「选股榜」（含解读报告与 AI 深度解读）
llm.env.example # LLM 配置模板；llm.env 已加入 .gitignore
tests/
  test_screening_factors.py / _weights.py / _pipeline.py / _store.py
  test_screening_explain.py / _llm.py
```

## 因子定义（输出均归一化到 0~1，中性 0.5）

### 策略组 `strategy_score(df, weights)`

- 各策略 `generate(df)` 最新目标仓位（持仓=1），按动态权重加权和
- 动态权重 `dynamic_strategy_weights(df, lookback=120)`：近 120 根 K 线逐策略 `engine.run` + `metrics.performance`，夏普负值截断为 0 后归一化；全部非正或数据不足（<60 根）退化为等权

### 结构组（子权重 背离 0.4 / 趋势线 0.35 / 浪型 0.25）

- **背离** `divergence_score(df, recent_bars=60)`：只计 p2 在 60 个交易日以内的事件；`magnitude = 级别系数(强1/中0.7/弱0.4) × 状态系数(确认1/钝化0.5) × 新鲜度(1 - 0.5*距今年限比)`；`score = 0.5 + 0.5*(最强底背离 - 最强顶背离)`
- **趋势线** `trendline_score(df)`：基准 0.5；向上突破下降压力线 +0.5，仍受压 -0.1；跌破上升支撑线 -0.4，支撑有效 +0.2
- **浪型** `wave_score(df)`：`(up,extend)=1.0 / (up,similar)=0.7 / (up,end)=0.4 / (down,end)=0.6 / (down,similar)=0.3 / (down,extend)=0.0`；无浪型 0.5

### 量价组（0.5 / 0.5）

- **热度** `heat_score`：`0.6 × 成交额在候选池分位 + 0.4 × 量比(当日amount/20日均，3倍封顶)`
- **动量** `momentum_score`：20 日收益率在候选池内的分位

### 合成 `combine_scores(group_scores, group_weights, ml_boost=None)`

- 默认组间权重 `{strategy: 0.4, structure: 0.35, volume: 0.25}`，CLI 可覆盖
- **v2 ML 钩子**：`ml_boost` 非空时 `total *= (1 + ml_boost)`；`factors_json` 即特征向量，v2 可直接用于训练

## 数据模型

表 `screening_results`（应用首次调用 store 时 `CREATE TABLE IF NOT EXISTS`）：

| 列 | 类型 | 说明 |
|----|------|------|
| `trade_date` | CHAR(8) | 交易日，与 `ts_code` 联合主键 |
| `ts_code` | VARCHAR(12) | 股票代码 |
| `rank_no` | INT | 当日排名（1 起） |
| `total_score` | DECIMAL(8,4) | 总分 |
| `score_strategy` / `score_structure` / `score_volume` | DECIMAL(8,4) | 三组分数 |
| `weights_json` | TEXT | 动态策略权重与夏普快照 |
| `factors_json` | TEXT | 各因子明细（v2 直接当特征） |
| `created_at` | DATETIME | 默认 `CURRENT_TIMESTAMP` |

`save_results` 同日先 `DELETE` 再批量 `INSERT`，幂等可重跑。

## 跑批用法

```bash
.venv/bin/python -m quant.screening.cli                      # 最新交易日，默认参数并落库
.venv/bin/python -m quant.screening.cli --date 20260731 --top-n-volume 250 --top-k 50
.venv/bin/python -m quant.screening.cli --w-strategy 0.5 --w-structure 0.3 --w-volume 0.2
.venv/bin/python -m quant.screening.cli --dry-run            # 只打印不落库
.venv/bin/python -m quant.screening.cli --from 20260701 --to 20260731    # 区间逐日回算
.venv/bin/python -m quant.screening.cli --from 20260701 --skip-existing  # 跳过已算过的日期
```

建议串在日更之后：`python update_daily_mysql.py && .venv/bin/python -m quant.screening.cli`。  
实测（2026-07-31，5203 只 -> 250 候选）：约 34 秒。

## UI（Tab4 选股榜）

- 交易日下拉（`list_dates` 倒序）→ 表格：排名/代码/名称/总分/策略/结构/量价
- 单行选中后展示**解读报告**（规则引擎生成，无外部依赖）：
  - 操作建议横幅：买入参考（success）/ 轻仓试探（info）/ 观望（warning）/ 减仓/回避（error）
  - 支撑因素与风险因素清单
  - 三个可展开小节：策略组（各策略持仓状态、权重、近 120 日夏普）、结构组（背离/趋势线/浪型的人话描述）、量价组（成交额分位、量比、20 日动量）
  - 原始 JSON（因子明细 / 动态权重）折叠展示
- 「AI 深度解读」按钮：配置 `llm.env` 后可用，调 LLM 生成解读与建议；结果按（日期，代码）缓存在 session_state
- 「在行情分析中查看」写入 `session_state.ts_code` 并 rerun，切到 Tab1 看结构分析
- 无结果时提示先运行 CLI

## 解读与交易建议（explain.py）

### 动作档位

`ACTIONS = ["买入参考", "轻仓试探", "观望", "减仓/回避"]`，由总分定基础档：

| 总分 | 基础档 |
|------|--------|
| ≥ 0.75 | 买入参考 |
| 0.60~0.75 | 轻仓试探 |
| 0.45~0.60 | 观望 |
| < 0.45 | 减仓/回避 |

每个**硬伤**（已确认顶背离 / 跌破上升趋势线 / 下跌三浪加速）在此基础上降一档，最低到减仓/回避。每档附带仓位思路（分批建仓 3~5 成 / 试探 ≤2 成 / 收紧止损 / 逢高减仓），并区分「未持有 / 已持有」两种情形。

### 支撑与风险因素（reasons）

- 支撑：已确认/钝化底背离、向上突破下降压力线、上涨三浪加速、全部策略持仓中
- 风险：已确认/钝化顶背离、跌破上升趋势线、下跌三浪加速、无任何策略持仓

## LLM 深度解读（llm.py，可选）

- **配置**：仓库根目录 `llm.env`（模板见 `llm.env.example`，文件已 gitignore）：`LLM_BASE_URL`（默认 `https://api.deepseek.com`）/ `LLM_API_KEY`（必填）/ `LLM_MODEL`（默认 `deepseek-chat`）/ `LLM_TIMEOUT`（默认 30s）。任何 OpenAI 兼容接口（DeepSeek/Kimi/Qwen 等）均可
- **未配置**：`is_configured()` 为 False，UI 隐藏按钮并提示配置方式；规则解读不受影响
- **提示词**：system 约束输出结构（评分解读 / 交易建议 / 风险提示，≤250 字，强制免责结尾）；user 携带股票、四档分数、规则引擎结论与完整因子 JSON
- **调用**：`requests.post` 到 `{base}/v1/chat/completions`，`temperature=0.3`，失败在 UI `st.error` 展示

## 错误处理

- 单股计算异常：记 warning 跳过，不阻断整批
- 截面为空 / 候选全部失败：抛 `RuntimeError`，CLI 非零退出
- UI 读库失败：`st.error` 友好提示

## 测试

- `test_screening_factors.py`：各打分器边界（空数据/中性/顶底背离/突破/子权重合成）
- `test_screening_weights.py`：夏普归一化、负值截断、全负等权退化、`ml_boost` 钩子
- `test_screening_pipeline.py`：mock loader 端到端（ST/停牌过滤、top_n/top_k、排序、回调）
- `test_screening_store.py`：建表、删后插幂等、读回排序（fake 连接，对齐 favorites 测法）

## v2 规划（本次未实现）

- `quant/screening/ml/`：以 `factors_json` 为特征、未来 N 日收益>阈值为标签，LightGBM 预测分数经 `combine_scores(..., ml_boost=...)` 注入
- `requirements.txt` 届时再加 lightgbm / scikit-learn
