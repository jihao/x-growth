# 结构分析 · 背离级别设计

日期：2026-07-27  
状态：已确认设计；实现计划见 `docs/superpowers/plans/2026-07-27-divergence-level.md`  
范围：在已有 DIF 背离上增加价格速度级别（强/中/弱）与同侧择优；复用现有 events；本地 Streamlit

## 背景

DIF 顶/底背离（钝化 + 确认）已落地。课件「结构和趋势」进一步强调：同样出现背离，**价格速度越慢结构越强**；同向多个背离时应优先更慢、更靠近当前的那个；时间跨度可辅助判断级别。本设计在现有事件上标注级别与优先，不改钝化/确认规则。

## 目标

1. 为每条 `DivergenceEvent` 计算 P1→P2 的 `speed`、`span_bars`，给出 `level ∈ {strong, medium, weak}`。
2. 同侧（顶/底分别）标出至多一条 `preferred=True`。
3. 明细表展示速度/跨度/级别/优先；中栏 caption 提示优先事件（不强行在图上加文字标签）。
4. 逻辑落在现有 `quant/structure/divergence.py`（扩展），与 Streamlit 解耦。

## 非目标

- 不改 DIF 对齐、钝化、确认公式与 overlay 过滤规则。
- 不做周线/分时级别；不做全市场选股、结构回测。
- 不做课件中「第一浪固定、第三浪越缓」的完整浪型耦合（可后续与浪型速度联动）。
- 不做图上「强/优先」文字标签（避免拥挤）。
- 不把跨度作为主分档维度（仅择优平局打破）。

## 技术选型

- 扩展 `DivergenceEvent` / `DivergenceResult`
- 在 `analyze_divergence` 末尾调用 `annotate_levels`
- pytest 合成事件列表离线测（可构造 `DivergenceEvent` 直接测 annotate，不必重跑 MACD）

## 目录结构

```
quant/structure/
  models.py         # DivergenceEvent / Result 增字段
  divergence.py     # 增 annotate_levels 及相关纯函数
app/main.py         # 明细列 + caption；参数说明
tests/
  test_divergence_level.py   # 级别与择优
  test_divergence.py         # 回归：旧用例仍通过（新字段有默认）
```

## 算法

### 速度与跨度

对每条事件（需 `df` 下标）：

```
bars = max(index(p2_date) - index(p1_date), 1)
speed = abs(p2_price - p1_price) / bars
span_bars = bars
```

语义：顶段上涨越缓、底段下跌越缓 → `speed` 越小 → 级别越强（与浪型速度同一量纲）。

### 分档 `level`

按**同侧**事件集合的 `speed` 分位数（默认 `q_slow=0.33`，`q_fast=0.66`）：

| 条件 | level | 中文 |
|---|---|---|
| `speed ≤ P_{q_slow}` | `strong` | 强 |
| `P_{q_slow} < speed ≤ P_{q_fast}` | `medium` | 中 |
| `speed > P_{q_fast}` | `weak` | 弱 |

边界：

- 该侧 0 条：跳过
- 该侧 1 条：`medium`，且 `preferred=True`
- 该侧 2 条：较慢 → `strong`，较快 → `weak`（不经分位数）

跨度**不**用于上调档位；仅参与择优平局（见下）。

### 同侧择优 `preferred`

对 `top` / `bottom` 各自独立：

1. `speed` 更小者优先  
2. 相对速度差 `|s1-s2|/max(s1,s2,eps) < near_pct`（默认 `0.05`）时，取 **p2_date 更晚**  
3. 仍平则取 `span_bars` 更大  

每侧至多一个 `preferred=True`；其余为 `False`。

### `DivergenceResult.preferred_event`

- 两侧皆有 preferred：取 `p2_date` 更晚者  
- 仅一侧有：取该侧  
- 皆无：`None`

### 与 pending / confirmed

级别与择优对两种 `status` **同样计算**（描述结构强弱，不依赖确认）。

### 输出字段（增量）

`DivergenceEvent` 新增（均有默认，兼容旧构造）：

- `speed: float = 0.0`
- `span_bars: int = 0`
- `level: str = "medium"`  # strong|medium|weak
- `preferred: bool = False`

`DivergenceResult` 新增：

- `preferred_event: DivergenceEvent | None = None`

`analyze_divergence(...)` 增可选参数 `q_slow=0.33`, `q_fast=0.66`, `near_pct=0.05`（UI 可不全部暴露；至少说明文案 + 必要时暴露分位）。

## 界面

- 背离参数 expander：补充「缓=强；同侧标优先」说明  
- 明细列：速度、跨度、级别（中文）、优先（是/否）  
- 中栏 caption：若有 `preferred_event`，例如  
  `优先关注：底背离·强（钝化）` / `优先关注：顶背离·中（确认）`  
- 图上 overlay 规则不变

## 数据流

```
detect_events → events
  → annotate_levels(df, events, q_slow, q_fast, near_pct)
  → filter_overlay_events（不变）
  → DivergenceResult(events, overlay_events, preferred_event)
  → 明细 + caption
```

## 错误处理

- 事件为空：结果空，无 caption  
- `p1_date`/`p2_date` 不在 index：该事件 `speed=0`、`span_bars=0`、`level=medium`，并记入 info（实现时跳过或保守处理，不抛未捕获异常）

## 测试

1. 同侧两条不同速度 → 慢=strong+preferred，快=weak  
2. 单条 → medium + preferred  
3. 速度接近（<5%）→ preferred 取 p2 更晚  
4. 顶/底两侧各有 preferred → `preferred_event` 取更晚 p2  
5. 既有 `test_divergence.py` 全绿（新字段默认值或 annotate 后填充）

## 验收标准

1. 明细可读；caption 与课件「优先慢速、近端」一致  
2. 不破坏原有背离检出与叠加  
3. 全量 pytest 通过

## 后续子项目（本 spec 不包含）

1. 与浪型速度模块联动（「第一浪固定、第三浪越缓」）  
2. 周线背离级别  
3. 全市场按级别选股  
4. 图上级别标注
