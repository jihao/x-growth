# 浪型速度 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在现有结构分析上增加日线 N 字三浪速度比较（切浪 → 比浪1/浪3 → 结论 extend/end/similar），并在行情 Tab 标注与展示。

**Architecture:** 扩展 `quant/structure/models.py`；新增 `waves.py`（拐点序列、切三浪、速度）；`plots.overlay_waves`；`app/main.py` 增加开关与段选择。复用 `detect_swings`。

**Tech Stack:** Python 3.13、pandas、plotly、streamlit、pytest（现有 `.venv`）。

## Global Constraints

- 仅日线；不做背离/选股/五浪完整数浪/周线。
- 速度：`abs(Δprice) / bars`；`ratio = speed3/speed1`。
- 默认 `fast_ratio=1.05`，`slow_ratio=0.95` → extend / end / similar。
- 上涨三浪拐点 L-H-L-H；下跌 H-L-H-L。
- `offset=0` 最近一段，`offset=1` 再前一段。
- 单测离线；`.venv/bin/python -m pytest`；每 Task 提交一次。
- 不在 `main` 上直接开发：先建 `feat/wave-speed` 分支（执行时）。

---

### Task 1: 扩展 models（WaveLeg / WaveTriple / WaveSpeedResult）

**Files:**
- Modify: `quant/structure/models.py`
- Test: `tests/test_wave_models.py`

**Interfaces:**
- Produces:
  - `@dataclass WaveLeg`: `start_date, end_date, start_price, end_price, bars: int, speed: float, ret: float`
  - `@dataclass WaveTriple`: `direction: str` (`"up"|"down"`), `pivots: list` (4 元组或小结构), `legs: list[WaveLeg]` (len=3), `ratio: float`, `verdict: str` (`"extend"|"end"|"similar"`)
  - `@dataclass WaveSpeedResult`: `current: WaveTriple | None`, `previous_available: bool`

- [ ] **Step 1: 写失败测试**

```python
# tests/test_wave_models.py
from quant.structure.models import WaveLeg, WaveTriple, WaveSpeedResult


def test_wave_leg_fields():
    leg = WaveLeg(
        start_date="a", end_date="b", start_price=10.0, end_price=12.0,
        bars=5, speed=0.4, ret=0.2,
    )
    assert leg.bars == 5 and leg.speed == 0.4


def test_wave_speed_result_empty():
    r = WaveSpeedResult(current=None, previous_available=False)
    assert r.current is None and r.previous_available is False
```

- [ ] **Step 2: 运行确认失败**

Run: `.venv/bin/python -m pytest tests/test_wave_models.py -v`  
Expected: FAIL（类不存在）

- [ ] **Step 3: 在 `models.py` 追加**

```python
@dataclass
class WaveLeg:
    start_date: Any
    end_date: Any
    start_price: float
    end_price: float
    bars: int
    speed: float
    ret: float


@dataclass
class WaveTriple:
    direction: str  # "up" | "down"
    pivots: list[Any]  # 4 个 (date, price, kind)
    legs: list[WaveLeg]
    ratio: float
    verdict: str  # "extend" | "end" | "similar"


@dataclass
class WaveSpeedResult:
    current: WaveTriple | None = None
    previous_available: bool = False
```

同步更新文件头注释为「结构分析数据结构」。

- [ ] **Step 4: 运行确认通过**

Run: `.venv/bin/python -m pytest tests/test_wave_models.py -v`  
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add quant/structure/models.py tests/test_wave_models.py
git commit -m "feat(structure): WaveLeg / WaveTriple / WaveSpeedResult"
```

---

### Task 2: `waves.py` 核心算法

**Files:**
- Create: `quant/structure/waves.py`
- Test: `tests/test_waves.py`

**Interfaces:**
- Consumes: `detect_swings`, models
- Produces:
  - `build_pivots(df, window=5, min_pct=0.01) -> list[tuple]`  # (date, price, "H"|"L")，相邻异类
  - `leg_from_pivots(df, a, b) -> WaveLeg`  # a/b 为 pivot；bars 用 index 差
  - `find_wave_triples(df, window=5, min_pct=0.01) -> list[WaveTriple]`  # 全部合法三浪，浪3结束日从新到旧
  - `analyze_wave_speed(df, offset=0, window=5, min_pct=0.01, fast_ratio=1.05, slow_ratio=0.95) -> WaveSpeedResult`
  - `verdict_from_ratio(ratio, fast_ratio, slow_ratio) -> str`

- [ ] **Step 1: 写失败测试**

```python
# tests/test_waves.py
import numpy as np
import pandas as pd

from quant.structure import waves


def _df_ohlc(close):
    idx = pd.date_range("2020-01-01", periods=len(close), freq="D")
    c = np.asarray(close, dtype=float)
    return pd.DataFrame(
        {"open": c, "high": c + 0.1, "low": c - 0.1, "close": c,
         "volume": 1, "amount": 1},
        index=idx,
    )


def test_verdict_from_ratio():
    assert waves.verdict_from_ratio(1.2, 1.05, 0.95) == "extend"
    assert waves.verdict_from_ratio(0.8, 1.05, 0.95) == "end"
    assert waves.verdict_from_ratio(1.0, 1.05, 0.95) == "similar"


def test_up_triple_extend_when_wave3_faster():
    # 构造 L-H-L-H：浪1 慢、浪3 快（更短 bars 更大涨幅）
    n = 50
    close = np.full(n, 15.0)
    # pivots roughly at 5(L=10), 15(H=12), 25(L=11), 30(H=16) → wave3 steeper
    low = close.copy() - 0.2
    high = close.copy() + 0.2
    specs = [(5, 10.0, "L"), (15, 12.0, "H"), (25, 11.0, "L"), (30, 16.0, "H")]
    for i, p, k in specs:
        if k == "L":
            low[i] = p
            close[i] = p + 0.3
            high[i] = p + 0.6
            for d in (1, 2):
                low[i - d] = p + 1.0
                low[i + d] = p + 1.0
        else:
            high[i] = p
            close[i] = p - 0.3
            low[i] = p - 0.6
            for d in (1, 2):
                high[i - d] = p - 1.0
                high[i + d] = p - 1.0
    df = pd.DataFrame(
        {"open": close, "high": high, "low": low, "close": close,
         "volume": 1, "amount": 1},
        index=pd.date_range("2020-01-01", periods=n, freq="D"),
    )
    res = waves.analyze_wave_speed(df, offset=0, window=2, min_pct=0.0)
    assert res.current is not None
    assert res.current.direction == "up"
    assert res.current.verdict == "extend"
    assert res.current.ratio >= 1.05


def test_up_triple_end_when_wave3_slower():
    n = 50
    close = np.full(n, 15.0)
    low = close.copy() - 0.2
    high = close.copy() + 0.2
    # 浪3 涨幅小、耗时长 → 更慢
    specs = [(5, 10.0, "L"), (12, 16.0, "H"), (18, 14.0, "L"), (40, 15.0, "H")]
    for i, p, k in specs:
        if k == "L":
            low[i] = p
            close[i] = p + 0.3
            high[i] = p + 0.6
            for d in (1, 2):
                low[i - d] = p + 1.0
                low[i + d] = p + 1.0
        else:
            high[i] = p
            close[i] = p - 0.3
            low[i] = p - 0.6
            for d in (1, 2):
                high[i - d] = p - 1.0
                high[i + d] = p - 1.0
    df = pd.DataFrame(
        {"open": close, "high": high, "low": low, "close": close,
         "volume": 1, "amount": 1},
        index=pd.date_range("2020-01-01", periods=n, freq="D"),
    )
    res = waves.analyze_wave_speed(df, offset=0, window=2, min_pct=0.0)
    assert res.current is not None
    assert res.current.verdict == "end"


def test_offset_one_picks_earlier_triple():
    # 两段上涨三浪：靠后一段与靠前一段 end 日期不同
    n = 80
    close = np.full(n, 20.0)
    low = close - 0.2
    high = close + 0.2
    # 早期: 5,12,18,25 ; 晚期: 45,52,58,65
    early = [(5, 10, "L"), (12, 14, "H"), (18, 12, "L"), (25, 16, "H")]
    late = [(45, 11, "L"), (52, 15, "H"), (58, 13, "L"), (65, 18, "H")]
    for i, p, k in early + late:
        p = float(p)
        if k == "L":
            low[i] = p
            close[i] = p + 0.3
            high[i] = p + 0.6
            for d in (1, 2):
                low[i - d] = p + 1.0
                low[i + d] = p + 1.0
        else:
            high[i] = p
            close[i] = p - 0.3
            low[i] = p - 0.6
            for d in (1, 2):
                high[i - d] = p - 1.0
                high[i + d] = p - 1.0
    df = pd.DataFrame(
        {"open": close, "high": high, "low": low, "close": close,
         "volume": 1, "amount": 1},
        index=pd.date_range("2020-01-01", periods=n, freq="D"),
    )
    r0 = waves.analyze_wave_speed(df, offset=0, window=2, min_pct=0.0)
    r1 = waves.analyze_wave_speed(df, offset=1, window=2, min_pct=0.0)
    assert r0.current is not None and r1.current is not None
    assert r0.previous_available is True
    assert r0.current.pivots[-1][0] > r1.current.pivots[-1][0]


def test_insufficient_pivots_returns_empty():
    df = _df_ohlc(np.linspace(10, 11, 15))
    res = waves.analyze_wave_speed(df, offset=0, window=5, min_pct=0.01)
    assert res.current is None
```

- [ ] **Step 2: 运行确认失败**

Run: `.venv/bin/python -m pytest tests/test_waves.py -v`  
Expected: FAIL

- [ ] **Step 3: 实现 `quant/structure/waves.py`**

```python
"""N 字三浪切分与速度比较（课件：第三浪 vs 第一浪）。"""
from __future__ import annotations

import pandas as pd

from quant.structure.models import WaveLeg, WaveTriple, WaveSpeedResult
from quant.structure.swings import detect_swings


def verdict_from_ratio(ratio: float, fast_ratio: float = 1.05, slow_ratio: float = 0.95) -> str:
    if ratio >= fast_ratio:
        return "extend"
    if ratio <= slow_ratio:
        return "end"
    return "similar"


def build_pivots(df: pd.DataFrame, window: int = 5, min_pct: float = 0.01) -> list[tuple]:
    sw = detect_swings(df["high"], df["low"], window=window, min_pct=min_pct)
    raw: list[tuple] = []
    for d in df.index:
        if sw.loc[d, "is_high"]:
            raw.append((d, float(df.loc[d, "high"]), "H"))
        if sw.loc[d, "is_low"]:
            raw.append((d, float(df.loc[d, "low"]), "L"))
    raw.sort(key=lambda x: x[0])
    if not raw:
        return []
    out = [raw[0]]
    for d, p, k in raw[1:]:
        pd0, pp, pk = out[-1]
        if k == pk:
            if (k == "H" and p >= pp) or (k == "L" and p <= pp):
                out[-1] = (d, p, k)
        else:
            out.append((d, p, k))
    return out


def _pos(df: pd.DataFrame, d) -> int:
    return int(df.index.get_loc(d))


def leg_from_pivots(df: pd.DataFrame, a: tuple, b: tuple) -> WaveLeg:
    d0, p0, _ = a
    d1, p1, _ = b
    bars = max(_pos(df, d1) - _pos(df, d0), 1)
    ret = (p1 / p0 - 1.0) if p0 else 0.0
    speed = abs(p1 - p0) / bars
    return WaveLeg(d0, d1, float(p0), float(p1), bars, float(speed), float(ret))


def _triple_from_four(df, pivots4, direction, fast_ratio, slow_ratio) -> WaveTriple | None:
    legs = [
        leg_from_pivots(df, pivots4[0], pivots4[1]),
        leg_from_pivots(df, pivots4[1], pivots4[2]),
        leg_from_pivots(df, pivots4[2], pivots4[3]),
    ]
    if legs[0].speed <= 0 or legs[2].speed <= 0:
        return None
    # 同向：上涨浪1/3 价格上升；下跌下降
    if direction == "up":
        if not (legs[0].end_price > legs[0].start_price and legs[2].end_price > legs[2].start_price):
            return None
    else:
        if not (legs[0].end_price < legs[0].start_price and legs[2].end_price < legs[2].start_price):
            return None
    ratio = legs[2].speed / legs[0].speed
    return WaveTriple(
        direction=direction,
        pivots=list(pivots4),
        legs=legs,
        ratio=float(ratio),
        verdict=verdict_from_ratio(ratio, fast_ratio, slow_ratio),
    )


def find_wave_triples(
    df: pd.DataFrame,
    window: int = 5,
    min_pct: float = 0.01,
    fast_ratio: float = 1.05,
    slow_ratio: float = 0.95,
) -> list[WaveTriple]:
    pivots = build_pivots(df, window=window, min_pct=min_pct)
    triples: list[WaveTriple] = []
    for i in range(len(pivots) - 3):
        four = pivots[i : i + 4]
        kinds = [k for _, _, k in four]
        if kinds == ["L", "H", "L", "H"]:
            t = _triple_from_four(df, four, "up", fast_ratio, slow_ratio)
        elif kinds == ["H", "L", "H", "L"]:
            t = _triple_from_four(df, four, "down", fast_ratio, slow_ratio)
        else:
            continue
        if t is not None:
            triples.append(t)
    triples.sort(key=lambda t: t.pivots[-1][0], reverse=True)
    return triples


def analyze_wave_speed(
    df: pd.DataFrame,
    offset: int = 0,
    window: int = 5,
    min_pct: float = 0.01,
    fast_ratio: float = 1.05,
    slow_ratio: float = 0.95,
) -> WaveSpeedResult:
    triples = find_wave_triples(
        df, window=window, min_pct=min_pct,
        fast_ratio=fast_ratio, slow_ratio=slow_ratio,
    )
    if offset < 0 or offset >= len(triples):
        return WaveSpeedResult(current=None, previous_available=len(triples) > 1)
    return WaveSpeedResult(
        current=triples[offset],
        previous_available=len(triples) > 1,
    )
```

- [ ] **Step 4: 运行测试；合成数据若偶发找不到摆动点，可微调 pivot 邻域垫高/垫低，保持断言意图**

Run: `.venv/bin/python -m pytest tests/test_waves.py -v`  
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add quant/structure/waves.py tests/test_waves.py
git commit -m "feat(structure): N字三浪切分与速度比较"
```

---

### Task 3: Plotly `overlay_waves`

**Files:**
- Modify: `quant/charts/plots.py`
- Test: `tests/test_charts.py`（追加）

**Interfaces:**
- Produces: `overlay_waves(fig, df, triple: WaveTriple) -> Figure`  
  在 4 个拐点画 markers + text 标注 `1起/1终/2终/3终` 或 `W1/W2/W3`；用折线连接四点；上涨色偏红系、下跌偏绿系。

- [ ] **Step 1: 追加测试**

```python
def test_overlay_waves_adds_traces():
    from quant.structure.models import WaveLeg, WaveTriple

    df = _df(40)
    piv = [(df.index[5], 10.0, "L"), (df.index[15], 12.0, "H"),
           (df.index[25], 11.0, "L"), (df.index[35], 14.0, "H")]
    legs = [
        WaveLeg(piv[0][0], piv[1][0], 10, 12, 10, 0.2, 0.2),
        WaveLeg(piv[1][0], piv[2][0], 12, 11, 10, 0.1, -1/12),
        WaveLeg(piv[2][0], piv[3][0], 11, 14, 10, 0.3, 3/11),
    ]
    triple = WaveTriple("up", piv, legs, 1.5, "extend")
    fig0 = plots.kline_chart(df, overlays=(), sub=())
    n0 = len(fig0.data)
    fig1 = plots.overlay_waves(fig0, df, triple)
    assert len(fig1.data) > n0
```

- [ ] **Step 2: 运行确认失败**

Run: `.venv/bin/python -m pytest tests/test_charts.py::test_overlay_waves_adds_traces -v`  
Expected: FAIL

- [ ] **Step 3: 在 `plots.py` 实现**

```python
def overlay_waves(fig, df, triple):
    """叠加 N 字三浪拐点与连线。"""
    color = "#e57373" if triple.direction == "up" else "#4db6ac"
    xs = [p[0] for p in triple.pivots]
    ys = [p[1] for p in triple.pivots]
    labels = ["浪1起", "浪1终", "浪2终", "浪3终"]
    fig.add_trace(
        go.Scatter(
            x=xs, y=ys, mode="lines+markers+text",
            name="浪型",
            line=dict(color=color, width=2, dash="dash"),
            marker=dict(size=9, color=color),
            text=labels, textposition="top center",
            hovertemplate="%{x|%Y-%m-%d}<br>%{text}: %{y:.4f}<extra></extra>",
        ),
        row=1, col=1,
    )
    return fig
```

- [ ] **Step 4: 运行确认通过**

Run: `.venv/bin/python -m pytest tests/test_charts.py -q`  
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add quant/charts/plots.py tests/test_charts.py
git commit -m "feat(charts): K线叠加浪型拐点"
```

---

### Task 4: Streamlit 接入

**Files:**
- Modify: `app/main.py`
- Modify: `tests/test_app_import.py`

**Interfaces:**
- Consumes: `analyze_wave_speed`, `overlay_waves`

- [ ] **Step 1: 扩展烟测**

```python
assert "浪型速度" in src
assert "analyze_wave_speed" in src
```

- [ ] **Step 2: 运行确认失败**

Run: `.venv/bin/python -m pytest tests/test_app_import.py -v`  
Expected: FAIL

- [ ] **Step 3: 在 Tab1 中（趋势线逻辑之后、`st.plotly_chart` 之前）接入**

在已有 `fig = plots.kline_chart(...)` 与趋势线叠加之后增加：

```python
        auto_wave = st.checkbox("浪型速度", value=True)
        with st.expander("浪型参数", expanded=False):
            st.markdown(
                """
**浪型速度怎么算？**

1. 用波段高低点串成拐点，切出 N 字三浪（上涨 L-H-L-H / 下跌 H-L-H-L）。
2. 单浪速度 = |价格变化| / 根数；比较**第三浪 vs 第一浪**。
3. 第三浪更快 → 倾向仍有第五浪；更慢 → 倾向止于三浪。
4. 「再前一段」查看时间上更早的一段已确认三浪。
                """.strip()
            )
            w_window = st.number_input("wave_window", min_value=2, max_value=20, value=5, step=1)
            w_fast = st.number_input("fast_ratio", min_value=1.0, max_value=2.0, value=1.05, format="%.2f")
            w_slow = st.number_input("slow_ratio", min_value=0.5, max_value=1.0, value=0.95, format="%.2f")
            wave_seg = st.selectbox("浪型段", ["最近一段", "再前一段"])

        wave_rows = []
        if auto_wave:
            from quant.structure.waves import analyze_wave_speed

            wres = analyze_wave_speed(
                df,
                offset=0 if wave_seg == "最近一段" else 1,
                window=int(w_window),
                fast_ratio=float(w_fast),
                slow_ratio=float(w_slow),
            )
            if wres.current is None:
                st.info("区间内有效三浪不足，无法做浪型速度分析。")
            else:
                t = wres.current
                fig = plots.overlay_waves(fig, df, t)
                verdict_cn = {
                    "extend": "倾向仍有第五浪",
                    "end": "倾向止于三浪",
                    "similar": "速度接近，需结合更大周期",
                }[t.verdict]
                dir_cn = "上涨" if t.direction == "up" else "下跌"
                st.info(
                    f"{dir_cn}三浪 · 第三浪/第一浪速度比={t.ratio:.2f} → {verdict_cn}"
                )
                for i, leg in enumerate(t.legs, 1):
                    wave_rows.append({
                        "浪": i,
                        "起点": str(leg.start_date)[:10],
                        "终点": str(leg.end_date)[:10],
                        "根数": leg.bars,
                        "速度": round(leg.speed, 4),
                        "涨跌幅": f"{leg.ret:.2%}",
                    })
                wave_rows.append({
                    "浪": "结论",
                    "起点": "", "终点": "", "根数": "",
                    "速度": round(t.ratio, 4),
                    "涨跌幅": verdict_cn,
                })
```

在趋势线明细之后（或并列）增加：

```python
        if wave_rows:
            with st.expander("浪型明细", expanded=True):
                st.dataframe(pd.DataFrame(wave_rows), width="stretch")
```

注意：`st.plotly_chart(fig)` 须在浪型/趋势线都叠加完成之后只调用一次。

- [ ] **Step 4: 全量测试**

Run: `.venv/bin/python -m pytest -q`  
Expected: 全 PASS

- [ ] **Step 5: 提交**

```bash
git add app/main.py tests/test_app_import.py
git commit -m "feat(app): 行情 Tab 接入浪型速度分析"
```

---

## Self-Review

**Spec coverage:** 切浪/速度/结论/最近与再前一段/K线标注/明细/参数说明 → Task 1–4 ✅；非目标未纳入 ✅  

**Placeholder scan:** 无 TBD  

**Type consistency:** `WaveTriple.pivots` 为 4×`(date,price,kind)`；`overlay_waves` / `analyze_wave_speed` / UI 一致使用 `verdict` ∈ {extend,end,similar}
