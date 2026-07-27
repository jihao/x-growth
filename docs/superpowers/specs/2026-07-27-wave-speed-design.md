# 结构分析 · 浪型速度设计

日期：2026-07-27  
状态：已确认设计，待写实现计划  
范围：结构分析第二期——日线 N 字三浪速度比较；复用现有 swings；本地 Streamlit

## 背景

自动趋势线（第一期）已落地。课件「结构和趋势」以浪型速度为核心判断：比较第三浪与第一浪速度，第三浪更快则倾向仍有第五浪，更慢则倾向止于三浪。本设计实现该能力；背离、选股、结构回测、周线计算仍为后续子项目。

## 目标

1. 基于波段高低点切分上涨/下跌 N 字三浪，计算浪1与浪3速度并给出结论。
2. 默认分析**最近一段**已确认三浪；支持切换**再前一段**。
3. 在行情分析 Tab 的 K 线上标注拐点，展示结论与可解释明细。
4. 逻辑放在 `quant/structure/waves.py`，与 Streamlit 解耦。

## 非目标

- 不做背离结构。
- 不做全市场选股、结构策略回测。
- 不做周线/分时浪型。
- 不做完整艾略特五浪/七浪自动数浪（仅结论「倾向延伸」，不强制标第5浪）。
- 不修改趋势线算法（可并存）。

## 技术选型

- 复用 `quant.structure.swings.detect_swings`
- pandas / numpy；Plotly 叠加；Streamlit Tab1 扩展
- pytest 合成数据离线测

## 目录结构

```
quant/structure/
  models.py       # 增 WaveLeg, WaveTriple, WaveSpeedResult
  swings.py       # 已有
  waves.py        # 新增：拐点序列、切三浪、速度比较
  trendlines.py   # 已有
quant/charts/plots.py  # 增 overlay_waves
app/main.py            # 浪型速度开关、参数、段选择、说明、明细
tests/
  test_waves.py
```

## 算法

### 摆动序列

`detect_swings` → 有序拐点 `[(date, price, kind)]`，`kind ∈ {H,L}`；相邻须异类，连续同类保留更极端者。

### 三浪形态

| 方向 | 拐点 | 浪1 | 浪2 | 浪3 |
|---|---|---|---|---|
| up | L₀→H₁→L₁→H₂ | L₀→H₁ | H₁→L₁ | L₁→H₂ |
| down | H₀→L₁→H₁→L₂ | H₀→L₁ | L₁→H₁ | H₁→L₂ |

- 浪1、浪3 同向且价格变化非零、bars≥1
- 浪3 终点须为已确认摆动点（不在 swings 未确认的边缘 window 内作为「当前未完成浪」的终点——与 detect_swings 边缘规则一致）
- 第一期不做严格回撤比例约束

### 最近 / 再前一段

从右往左收集合法三浪，按浪3结束日排序；`offset=0` 最近，`offset=1` 再前一段；不足则空结果。

### 速度与结论

```
speed = abs(end_price - start_price) / bars
ratio = speed3 / speed1
```

- `bars` = 整数下标差，至少 1
- 默认 `fast_ratio=1.05`，`slow_ratio=0.95`（可调）
  - `ratio >= fast_ratio` → `extend`（倾向仍有第五浪）
  - `ratio <= slow_ratio` → `end`（倾向止于三浪）
  - 否则 → `similar`

### 输出字段

`WaveLeg`: start_date, end_date, start_price, end_price, bars, speed, ret  
`WaveTriple`: direction, pivots, legs[3], ratio, verdict  
`WaveSpeedResult`: current (offset 所选), previous_available: bool

## 界面

- Tab1 开关「浪型速度」（默认开）
- expander「浪型参数」：规则说明 + window/min_pct + fast_ratio/slow_ratio + 段选择（最近一段 / 再前一段）
- K 线叠加拐点标注；caption 结论文案
- 明细表：三浪起止、根数、速度、涨跌幅、比值、结论
- 与「自动趋势线」可同时开启

## 数据流

```
load_daily → detect_swings → pivot sequence
  → find triples → pick(offset) → speed/verdict
  → overlay_waves + 明细
```

## 错误处理

- 拐点或合法三浪不足：info 提示，不画浪、不抛未捕获异常
- 空行情：沿用现有提示

## 测试

- 合成上涨 L-H-L-H：识别 up；加快浪3 → extend；放慢 → end
- 两段合法三浪时 offset=1 取到更早一段
- 不足时返回空不崩溃

## 验收标准

1. 清晰走势个股上能标出合理三浪与结论
2. 结论语义与课件一致（快→延伸，慢→止于三浪）
3. 「再前一段」切换正确或提示不足
4. 全量 pytest 通过

## 后续子项目（本 spec 不包含）

1. 背离结构
2. 全市场选股
3. 结构策略回测
4. 周线浪型
5. 更严的回撤/级别规则
