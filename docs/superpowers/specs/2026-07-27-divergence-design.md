# 结构分析 · DIF 背离设计

日期：2026-07-27  
状态：已确认设计，待写实现计划  
范围：结构分析第三期——日线 DIF 顶/底背离（钝化 + 确认）；复用 swings 与 `ta.macd`；本地 Streamlit

## 背景

自动趋势线、浪型速度已落地。课件「结构和趋势」定义背离：价格高点继续上移而 DIF 高点下降（顶）；价格低点创新低而 DIF 低点上移（底）。价格创新高/新低但 DIF 拒绝同步时称**钝化**；指标极值转向后才**确认**背离。本设计实现该能力；全市场选股、结构回测、周线、背离级别（速度强弱）仍为后续子项目。

## 目标

1. 基于价格摆动点对齐 DIF 极值，识别顶/底背离的 **pending（钝化）** 与 **confirmed（确认）**。
2. 明细表展示全部事件；K 线叠加 **全部 pending + 最近 1 条 confirmed**（避免图上过挤）。
3. 逻辑放在 `quant/structure/divergence.py`，与 Streamlit 解耦；可与趋势线、浪型速度并存。
4. 语义贴合课件：顶=价高抬升 + DIF 高点下降；底对称；确认=第二触点后 DIF 相对峰值/谷值反向移动达阈值。

## 非目标

- 不做 RSI / 其他指标背离。
- 不做周线/分时背离；不做全市场选股、结构策略回测。
- 不做课件中的「背离级别」（用价格速度判断强弱）、双重/多重背离完整状态机。
- 不修改 swings / 趋势线 / 浪型算法。
- 不改 MACD 默认参数（UI 不暴露 12/26/9；内部固定调用现有 `ta.macd`）。

## 技术选型

- 复用 `quant.structure.swings.detect_swings`、`quant.indicators.ta.macd`
- pandas / numpy；Plotly 叠加；Streamlit Tab1 扩展
- pytest 合成数据离线测

## 目录结构

```
quant/structure/
  models.py         # 增 DivergenceEvent, DivergenceResult
  swings.py         # 已有
  divergence.py     # 新增：对齐 DIF、检测钝化/确认
  waves.py / trendlines.py  # 已有，不改算法
quant/charts/plots.py  # 增 overlay_divergence
app/main.py            # DIF 背离开关、参数、说明、明细
tests/
  test_divergence.py
```

## 算法

### 输入与摆动

1. `df` 日线 OHLCV（至少含 `close`，摆动用 high/low 规则与现有 `detect_swings` 一致）。
2. `dif, _, _ = ta.macd(df["close"])`（fast=12, slow=26, signal=9）。
3. `swings = detect_swings(df, window=..., min_pct=...)` → 有序拐点 `(date, price, kind)`，`kind ∈ {H,L}`。

### DIF 极值对齐

对每个价格摆动点，在 `[i - align_bars, i + align_bars]`（裁剪到有效下标）内找同侧 DIF 极值（顶用局部 max，底用局部 min），取该窗内最极端的一根作为对齐 DIF 值与日期。

- 默认 `align_bars=3`
- 若裁剪后窗口内无有效 DIF（全 NaN）：丢弃该摆动点（不参与配对）

### 钝化（pending）配对

在同类摆动点序列上，取相邻两点 `(P1, D1)` → `(P2, D2)`：

| 类型 | 价格条件 | DIF 条件 | status |
|---|---|---|---|
| top | `P2 > P1` | `D2 < D1` | `pending` |
| bottom | `P2 < P1` | `D2 > D1` | `pending` |

- 同一行情可出现多段相邻对（多次背离/钝化）；全部保留进事件列表。
- 若价格同向创新高/新低但 DIF 同步创新高/新低：不构成背离，不产出事件。

### 确认（confirmed）

第二触点对齐完成后，考察 **`max(p2_date, d2_date)` 之后** 的 DIF 序列（不含对齐日本身）。默认 `confirm_pct=0.05`，`eps` 取很小正数（如 `1e-8`）。统一相对位移公式（正负 DIF 同一套）：

```
# 顶：自 D2 回落
move = (D2 - dif_t) / max(abs(D2), eps)
# 底：自 D2 抬升
move = (dif_t - D2) / max(abs(D2), eps)
# 首次 move >= confirm_pct → confirmed
```

确认日取首次满足条件的交易日，并记录当日 `confirm_dif`；未满足则保持 `pending`。

### 图上过滤

- 明细：全部 `DivergenceEvent`
- 叠加：`status==pending` 的全部 + `status==confirmed` 中按确认日（无无则按 P2 日）最新的 **1** 条

### 输出字段

`DivergenceEvent`:

- `side`: `"top"` | `"bottom"`
- `status`: `"pending"` | `"confirmed"`
- `p1_date`, `p1_price`, `d1`, `d1_date`
- `p2_date`, `p2_price`, `d2`, `d2_date`
- `confirm_date`: 可选
- `confirm_dif`: 可选

`DivergenceResult`:

- `events: list[DivergenceEvent]`（按 p2_date 升序）
- `overlay_events: list[DivergenceEvent]`（上述过滤后）

## 界面

- Tab1 开关「DIF 背离」（默认开）
- expander「背离参数」：
  - 规则说明（顶/底定义；钝化 vs 确认）
  - 独立 `window` / `min_pct`（默认与浪型控件同值风格，不强制共用状态）
  - `align_bars` / `confirm_pct`
- K 线：`overlay_divergence`——两触点连线；pending 虚线、confirmed 实线；顶/底颜色区分
- caption：如有最新相关事件则短句提示（例：`顶背离已确认` / `底背离钝化中`）
- expander「背离明细」：全事件表
- 与「自动趋势线」「浪型速度」可同时开启

## 数据流

```
load_daily → ta.macd(DIF) → detect_swings
  → align DIF extrema (±align_bars)
  → adjacent pairs → pending
  → post-P2 DIF move → confirmed
  → filter overlay_events
  → overlay_divergence + 明细
```

## 错误处理

- 摆动点或合法对齐不足：info 提示，不画线、不抛未捕获异常
- DIF 前期 NaN：跳过不可对齐点
- 空行情：沿用现有提示

## 测试

合成序列（pytest）：

1. 价高抬升 + DIF 高点下降 → 至少 1 条 `pending` top
2. 随后 DIF 按公式回落超阈值 → 升级为 `confirmed`，含 `confirm_date`
3. 底背离对称用例
4. 价与 DIF 同步创新高 → 无 top 事件
5. 拐点不足 → 空结果不崩溃
6. `overlay_events`：多条 confirmed 时仅保留最新 1 条，pending 全保留

## 验收标准

1. 清晰个股日线上能标出合理顶/底背离线段，图上不挤（仅 pending + 最近 1 confirmed）
2. 明细齐全；语义与课件一致（钝化 / 确认）
3. 与趋势线、浪型开关互不破坏
4. 全量 pytest 通过

## 后续子项目（本 spec 不包含）

1. 背离级别（价格速度 → 强弱）
2. 双重/多重背离与更完整状态机
3. 周线背离
4. 全市场选股 / 结构策略回测
5. RSI 等其他指标背离
