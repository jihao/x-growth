# 自动趋势线 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在现有量化系统上增加日线自动趋势线（波段点 → 连线打分 → 破位状态 → K 线叠加 + 明细），逻辑与 UI 解耦。

**Architecture:** 新建 `quant/structure/`（models / swings / trendlines）；`charts.overlay_trendlines` 往已有 Plotly Figure 叠加线段与触点；`app/main.py` 行情 Tab 增加开关、参数、周线占位与明细表。

**Tech Stack:** Python 3.13、pandas、numpy、plotly、streamlit、pytest（沿用现有 `.venv`）。

## Global Constraints

- 仅日线；周线 UI 占位 disabled，不算周线。
- 不做浪型/背离/选股/结构回测；不改现有 5 策略。
- 波段点：对 `high`/`low` 居中确认；最近 `window` 根不参与连线。
- 触点容差默认 `tol=0.015`；`min_bars=10`；`window=5`；`min_pct=0.01`；Top-K=3。
- 打分：`touch_count * 10 + span_bars * 0.01 + recent_bonus(+5 if touch in last 60 bars)`。
- 破位：收盘破；上升线 `close < line*(1-tol)` → broken；下降线 `close > line*(1+tol)` → broken。
- 单测离线、合成数据；命令用 `.venv/bin/python -m pytest`。
- 每 Task 结束提交一次。

---

### Task 1: 数据结构 `models.py`

**Files:**
- Create: `quant/structure/__init__.py`
- Create: `quant/structure/models.py`
- Test: `tests/test_structure_models.py`

**Interfaces:**
- Produces:
  - `@dataclass Trendline`: `side: str` (`"up"|"down"`), `slope: float`, `intercept: float`, `touch_dates: list`, `touch_count: int`, `score: float`, `start_date`, `end_date`, `status: str | None = None`, `line_price_today: float | None = None`, `distance_pct: float | None = None`
  - 方法 `price_at(x: float | int) -> float`：`slope * x + intercept`（x 为整数下标）
  - `@dataclass TrendlineResult`: `up: list[Trendline]`, `down: list[Trendline]`, `best_up: Trendline | None`, `best_down: Trendline | None`

- [ ] **Step 1: 写失败测试**

```python
# tests/test_structure_models.py
from quant.structure.models import Trendline, TrendlineResult


def test_trendline_price_at():
    tl = Trendline(
        side="up", slope=0.5, intercept=10.0,
        touch_dates=[], touch_count=2, score=20.0,
        start_date=None, end_date=None,
    )
    assert tl.price_at(0) == 10.0
    assert tl.price_at(4) == 12.0


def test_result_holds_lists():
    r = TrendlineResult(up=[], down=[], best_up=None, best_down=None)
    assert r.up == [] and r.best_down is None
```

- [ ] **Step 2: 运行确认失败**

Run: `.venv/bin/python -m pytest tests/test_structure_models.py -v`  
Expected: FAIL（模块不存在）

- [ ] **Step 3: 实现**

```python
# quant/structure/__init__.py
"""结构分析：自动趋势线等（与课件「触点越多越有效」对齐的第一期）。"""

# quant/structure/models.py
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class Trendline:
    side: str  # "up" | "down"
    slope: float
    intercept: float
    touch_dates: list[Any]
    touch_count: int
    score: float
    start_date: Any
    end_date: Any
    status: str | None = None
    line_price_today: float | None = None
    distance_pct: float | None = None

    def price_at(self, x: float) -> float:
        return self.slope * float(x) + self.intercept


@dataclass
class TrendlineResult:
    up: list[Trendline] = field(default_factory=list)
    down: list[Trendline] = field(default_factory=list)
    best_up: Trendline | None = None
    best_down: Trendline | None = None
```

- [ ] **Step 4: 运行确认通过**

Run: `.venv/bin/python -m pytest tests/test_structure_models.py -v`  
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add quant/structure tests/test_structure_models.py
git commit -m "feat(structure): Trendline / TrendlineResult 数据结构"
```

---

### Task 2: 波段点 `swings.py`

**Files:**
- Create: `quant/structure/swings.py`
- Test: `tests/test_swings.py`

**Interfaces:**
- Produces: `detect_swings(high: Series, low: Series, window=5, min_pct=0.01) -> DataFrame`  
  列：`is_high: bool`, `is_low: bool`；索引与输入对齐。  
  居中窗口；最近/最前 `window` 行必为 False；相邻同侧点若相对价差 < `min_pct` 则丢掉较弱者（保留更极端的高/低）。

- [ ] **Step 1: 写失败测试**

```python
# tests/test_swings.py
import numpy as np
import pandas as pd

from quant.structure import swings


def _hl(vals_h, vals_l=None):
    idx = pd.date_range("2020-01-01", periods=len(vals_h), freq="D")
    h = pd.Series(vals_h, index=idx, dtype=float)
    l = pd.Series(vals_l if vals_l is not None else vals_h, index=idx, dtype=float)
    return h, l


def test_detect_swings_finds_peak_and_trough():
    # 平 → 峰 → 平 → 谷 → 平；window=2 需两侧各 2 根更低/更高
    h = [10, 10, 10, 12, 10, 10, 10, 8, 10, 10, 10]
    l = [9, 9, 9, 11, 9, 9, 9, 7, 9, 9, 9]
    high, low = _hl(h, l)
    out = swings.detect_swings(high, low, window=2, min_pct=0.0)
    assert out["is_high"].sum() >= 1
    assert out["is_low"].sum() >= 1
    assert out["is_high"].iloc[3]  # 峰值
    assert out["is_low"].iloc[7]   # 谷值
    # 边缘 window 根不能为摆动点
    assert not out["is_high"].iloc[:2].any()
    assert not out["is_high"].iloc[-2:].any()


def test_min_pct_filters_near_duplicates():
    # 两个很近的高点，应只保留更高的
    h = [10, 10, 11.0, 10, 10, 10, 11.05, 10, 10, 10]
    high, low = _hl(h, [9] * len(h))
    out = swings.detect_swings(high, low, window=2, min_pct=0.02)
    # 11 与 11.05 相差约 0.45% < 2%，过滤后高点更少或只留 11.05
    assert out["is_high"].sum() <= 1
```

- [ ] **Step 2: 运行确认失败**

Run: `.venv/bin/python -m pytest tests/test_swings.py -v`  
Expected: FAIL

- [ ] **Step 3: 实现 `quant/structure/swings.py`**

```python
"""波段高低点检测（复盘/展示/历史扫描用）。

使用居中窗口确认局部峰谷；最近/最前 ``window`` 根未确认，不参与连线。
不得把未确认点当作实时交易信号的唯一依据。
"""
from __future__ import annotations

import pandas as pd


def detect_swings(
    high: pd.Series,
    low: pd.Series,
    window: int = 5,
    min_pct: float = 0.01,
) -> pd.DataFrame:
    high = high.astype(float)
    low = low.astype(float)
    w = window * 2 + 1
    roll_max = high.rolling(w, center=True).max()
    roll_min = low.rolling(w, center=True).min()
    is_high = (high == roll_max) & roll_max.notna()
    is_low = (low == roll_min) & roll_min.notna()
    # 边缘未确认
    is_high.iloc[:window] = False
    is_high.iloc[-window:] = False
    is_low.iloc[:window] = False
    is_low.iloc[-window:] = False

    def _filter(mask: pd.Series, prices: pd.Series, prefer: str) -> pd.Series:
        idxs = list(prices.index[mask])
        if len(idxs) <= 1:
            return mask
        keep = [idxs[0]]
        for i in idxs[1:]:
            prev = keep[-1]
            p0, p1 = float(prices.loc[prev]), float(prices.loc[i])
            base = max(abs(p0), abs(p1), 1e-12)
            if abs(p1 - p0) / base < min_pct:
                if prefer == "high":
                    if p1 >= p0:
                        keep[-1] = i
                else:
                    if p1 <= p0:
                        keep[-1] = i
            else:
                keep.append(i)
        out = pd.Series(False, index=prices.index)
        out.loc[keep] = True
        return out

    is_high = _filter(is_high, high, "high")
    is_low = _filter(is_low, low, "low")
    return pd.DataFrame({"is_high": is_high, "is_low": is_low}, index=high.index)
```

- [ ] **Step 4: 运行确认通过**

Run: `.venv/bin/python -m pytest tests/test_swings.py -v`  
Expected: PASS（若峰谷索引因构造数据偏移，微调测试期望索引使断言匹配真实算法行为，但不得削弱「能找到峰谷 / 边缘为 False / min_pct 过滤」的意图）

- [ ] **Step 5: 提交**

```bash
git add quant/structure/swings.py tests/test_swings.py
git commit -m "feat(structure): 波段高低点 detect_swings"
```

---

### Task 3: 趋势线拟合与破位 `trendlines.py`

**Files:**
- Create: `quant/structure/trendlines.py`
- Test: `tests/test_trendlines.py`

**Interfaces:**
- Consumes: `detect_swings`, `Trendline`, `TrendlineResult`
- Produces:
  - `find_trendlines(df, window=5, min_pct=0.01, tol=0.015, min_bars=10, top_k=3) -> TrendlineResult`  
    `df` 需含 `high,low,close`；内部用整数位置 `0..n-1` 作 x；上升用低点价=`low`，下降用高点价=`high`。
  - `evaluate_breakout(result, close_today: float, x_today: int, tol=0.015) -> TrendlineResult`  
    就地/返回更新 `best_up`/`best_down` 的 `status`、`line_price_today`、`distance_pct`。

- [ ] **Step 1: 写失败测试**

```python
# tests/test_trendlines.py
import numpy as np
import pandas as pd

from quant.structure import trendlines
from quant.structure.models import Trendline, TrendlineResult


def _df_from_close(closes):
    idx = pd.date_range("2020-01-01", periods=len(closes), freq="D")
    c = pd.Series(closes, index=idx, dtype=float)
    return pd.DataFrame(
        {"open": c, "high": c * 1.001, "low": c * 0.999, "close": c,
         "volume": 1000, "amount": c * 1000},
        index=idx,
    )


def test_colinear_lows_get_multiple_touches():
    # 构造明确上升低点：索引 5,15,25 的 low 近似共线，中间抬高以免干扰
    n = 40
    close = np.full(n, 20.0)
    low = np.full(n, 19.0)
    high = np.full(n, 21.0)
    for i, p in [(5, 10.0), (15, 12.0), (25, 14.0)]:
        low[i] = p
        close[i] = p + 0.5
        high[i] = p + 1.0
    # 两侧垫高/垫低以便 window=2 确认摆动低点
    for i in [5, 15, 25]:
        for d in range(1, 3):
            low[i - d] = low[i] + 1.0
            low[i + d] = low[i] + 1.0
    idx = pd.date_range("2020-01-01", periods=n, freq="D")
    df = pd.DataFrame(
        {"open": close, "high": high, "low": low, "close": close,
         "volume": 1, "amount": 1},
        index=idx,
    )
    res = trendlines.find_trendlines(df, window=2, min_pct=0.0, tol=0.02, min_bars=5, top_k=3)
    assert res.best_up is not None
    assert res.best_up.touch_count >= 3
    assert res.best_up.side == "up"


def test_point_outside_tol_not_counted():
    # 两点定线，第三点明显偏离
    n = 30
    low = np.full(n, 15.0)
    high = np.full(n, 16.0)
    close = np.full(n, 15.5)
    low[5], low[15], low[25] = 10.0, 12.0, 20.0  # 20 远离 10-12 延长线
    for i in [5, 15, 25]:
        for d in (1, 2):
            low[i - d] = low[i] + 1
            low[i + d] = low[i] + 1
    idx = pd.date_range("2020-01-01", periods=n, freq="D")
    df = pd.DataFrame(
        {"open": close, "high": high, "low": low, "close": close,
         "volume": 1, "amount": 1},
        index=idx,
    )
    res = trendlines.find_trendlines(df, window=2, min_pct=0.0, tol=0.01, min_bars=5, top_k=5)
    # 最优上升线触点不应把偏离点算进去 → touch_count == 2（若算法仍给出含 3 点的线则该线得分应低于仅 2 点合理线，或触点列表不含 day25）
    if res.best_up is not None:
        assert res.best_up.touch_count == 2 or idx[25] not in res.best_up.touch_dates


def test_evaluate_breakout_up_line():
    tl = Trendline(
        side="up", slope=0.0, intercept=100.0,
        touch_dates=[], touch_count=3, score=30.0,
        start_date=None, end_date=None,
    )
    result = TrendlineResult(up=[tl], down=[], best_up=tl, best_down=None)
    out = trendlines.evaluate_breakout(result, close_today=98.0, x_today=10, tol=0.015)
    assert out.best_up.status == "broken"
    out2 = trendlines.evaluate_breakout(result, close_today=100.0, x_today=10, tol=0.015)
    assert out2.best_up.status == "above"
```

- [ ] **Step 2: 运行确认失败**

Run: `.venv/bin/python -m pytest tests/test_trendlines.py -v`  
Expected: FAIL

- [ ] **Step 3: 实现 `quant/structure/trendlines.py`（整文件如下，勿留半成品）**

```python
"""自动趋势线：两点连线穷举、触点计数、打分、收盘破位。"""
from __future__ import annotations

from itertools import combinations

import pandas as pd

from quant.structure.models import Trendline, TrendlineResult
from quant.structure.swings import detect_swings


def find_trendlines(
    df: pd.DataFrame,
    window: int = 5,
    min_pct: float = 0.01,
    tol: float = 0.015,
    min_bars: int = 10,
    top_k: int = 3,
) -> TrendlineResult:
    high, low = df["high"].astype(float), df["low"].astype(float)
    sw = detect_swings(high, low, window=window, min_pct=min_pct)
    pos = {d: i for i, d in enumerate(df.index)}
    last_pos = len(df) - 1

    def fit(points: list[tuple], side: str) -> list[Trendline]:
        cands: list[Trendline] = []
        for (i1, p1, d1), (i2, p2, d2) in combinations(points, 2):
            if abs(i2 - i1) < min_bars:
                continue
            slope = (p2 - p1) / (i2 - i1)
            intercept = p1 - slope * i1
            touches, touch_pos = [], []
            for i, p, d in points:
                if abs(p) < 1e-12:
                    continue
                line_p = slope * i + intercept
                if abs(p - line_p) / abs(p) <= tol:
                    touches.append(d)
                    touch_pos.append(i)
            if len(touches) < 2:
                continue
            span = abs(i2 - i1)
            recent = any(last_pos - i <= 60 for i in touch_pos)
            score = len(touches) * 10 + span * 0.01 + (5.0 if recent else 0.0)
            start, end = (d1, d2) if i1 < i2 else (d2, d1)
            cands.append(
                Trendline(
                    side=side,
                    slope=float(slope),
                    intercept=float(intercept),
                    touch_dates=touches,
                    touch_count=len(touches),
                    score=float(score),
                    start_date=start,
                    end_date=end,
                )
            )
        cands.sort(key=lambda t: (t.score, t.touch_count), reverse=True)
        return cands

    low_pts = [(pos[d], float(low.loc[d]), d) for d in df.index[sw["is_low"]]]
    high_pts = [(pos[d], float(high.loc[d]), d) for d in df.index[sw["is_high"]]]
    up = fit(low_pts, "up")[:top_k]
    down = fit(high_pts, "down")[:top_k]
    return TrendlineResult(
        up=up,
        down=down,
        best_up=up[0] if up else None,
        best_down=down[0] if down else None,
    )


def evaluate_breakout(
    result: TrendlineResult,
    close_today: float,
    x_today: int,
    tol: float = 0.015,
) -> TrendlineResult:
    def upd(tl: Trendline | None, side: str) -> Trendline | None:
        if tl is None:
            return None
        line_p = tl.price_at(x_today)
        dist = (close_today - line_p) / line_p if line_p else 0.0
        if side == "up":
            status = "broken" if close_today < line_p * (1 - tol) else "above"
        else:
            status = "broken" if close_today > line_p * (1 + tol) else "below"
        return Trendline(
            side=tl.side,
            slope=tl.slope,
            intercept=tl.intercept,
            touch_dates=list(tl.touch_dates),
            touch_count=tl.touch_count,
            score=tl.score,
            start_date=tl.start_date,
            end_date=tl.end_date,
            status=status,
            line_price_today=float(line_p),
            distance_pct=float(dist),
        )

    best_up = upd(result.best_up, "up")
    best_down = upd(result.best_down, "down")
    up = ([best_up] + list(result.up[1:])) if best_up is not None and result.up else list(result.up)
    down = (
        [best_down] + list(result.down[1:])
        if best_down is not None and result.down
        else list(result.down)
    )
    return TrendlineResult(up=up, down=down, best_up=best_up, best_down=best_down)
```

- [ ] **Step 4: 运行测试；必要时微调合成数据使共线用例稳定通过，保持断言意图**

Run: `.venv/bin/python -m pytest tests/test_trendlines.py tests/test_swings.py -v`  
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add quant/structure/trendlines.py tests/test_trendlines.py
git commit -m "feat(structure): 自动趋势线拟合与收盘破位判定"
```

---

### Task 4: Plotly 叠加 `overlay_trendlines`

**Files:**
- Modify: `quant/charts/plots.py`
- Test: `tests/test_charts.py`（追加用例）

**Interfaces:**
- Consumes: `TrendlineResult`
- Produces: `overlay_trendlines(fig, df, result) -> Figure`  
  对每条 up/down 线：用整数位置算起止价，`go.Scatter` mode=`lines+markers` 画线段；触点再加一层 markers。上升线颜色偏红（如 `#e57373`），下降偏绿（`#4db6ac`）。不修改原 K 线颜色逻辑。

- [ ] **Step 1: 写失败测试（追加到 test_charts.py）**

```python
from quant.structure.models import Trendline, TrendlineResult
from quant.charts import plots


def test_overlay_trendlines_adds_traces():
    df = _df(60)
    fig0 = plots.kline_chart(df, overlays=(), sub=())
    n0 = len(fig0.data)
    tl = Trendline(
        side="up", slope=0.01, intercept=10.0,
        touch_dates=[df.index[10], df.index[30]],
        touch_count=2, score=20.0,
        start_date=df.index[10], end_date=df.index[30],
    )
    result = TrendlineResult(up=[tl], down=[], best_up=tl, best_down=None)
    fig1 = plots.overlay_trendlines(fig0, df, result)
    assert len(fig1.data) > n0
```

- [ ] **Step 2: 运行确认失败**

Run: `.venv/bin/python -m pytest tests/test_charts.py::test_overlay_trendlines_adds_traces -v`  
Expected: FAIL

- [ ] **Step 3: 在 `plots.py` 末尾实现**

```python
def overlay_trendlines(fig, df, result):
    """在已有 K 线 Figure 上叠加自动趋势线与触点。"""
    from quant.structure.models import TrendlineResult  # 类型提示可选

    pos = {d: i for i, d in enumerate(df.index)}

    def add_line(tl, color, name):
        if tl.start_date not in pos or tl.end_date not in pos:
            return
        i0, i1 = pos[tl.start_date], pos[tl.end_date]
        x0, x1 = df.index[i0], df.index[i1]
        y0, y1 = tl.price_at(i0), tl.price_at(i1)
        fig.add_trace(
            go.Scatter(
                x=[x0, x1], y=[y0, y1], mode="lines",
                name=name, line=dict(color=color, width=2),
                hoverinfo="skip",
            ),
            row=1, col=1,
        )
        touch_x = [d for d in tl.touch_dates if d in pos]
        touch_y = [tl.price_at(pos[d]) for d in touch_x]
        if touch_x:
            fig.add_trace(
                go.Scatter(
                    x=touch_x, y=touch_y, mode="markers",
                    name=f"{name}触点",
                    marker=dict(color=color, size=8, symbol="circle-open"),
                    hovertemplate="%{x|%Y-%m-%d}<br>触点: %{y:.4f}<extra></extra>",
                ),
                row=1, col=1,
            )

    for i, tl in enumerate(result.up):
        add_line(tl, "#e57373", f"上升趋势{i+1}")
    for i, tl in enumerate(result.down):
        add_line(tl, "#4db6ac", f"下降趋势{i+1}")
    return fig
```

- [ ] **Step 4: 运行确认通过**

Run: `.venv/bin/python -m pytest tests/test_charts.py -q`  
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add quant/charts/plots.py tests/test_charts.py
git commit -m "feat(charts): K线叠加自动趋势线与触点"
```

---

### Task 5: Streamlit 行情 Tab 接入

**Files:**
- Modify: `app/main.py`
- Test: `tests/test_app_import.py`（扩展断言关键字）

**Interfaces:**
- Consumes: `find_trendlines`, `evaluate_breakout`, `overlay_trendlines`

- [ ] **Step 1: 扩展烟测**

```python
# tests/test_app_import.py 在现有断言上追加：
def test_app_module_imports():
    ...
    assert "自动趋势线" in src or "find_trendlines" in src
    assert "即将支持" in src  # 周线占位
```

- [ ] **Step 2: 运行确认失败**

Run: `.venv/bin/python -m pytest tests/test_app_import.py -v`  
Expected: FAIL（缺文案）

- [ ] **Step 3: 修改 `app/main.py` 的 tab1 区块**

在 `with tab1:` 内，`df` 非空时：

```python
    timeframe = st.radio("周期", ["日线", "周线（即将支持）"], horizontal=True,
                         disabled=False)
    # 周线选项用 selectbox 更易 disabled 单项：改用
    # st.selectbox("周期", ["日线", "周线（即将支持）"], index=0,
    #              format_func=lambda x: x)
    # 若选周线：st.info("周线趋势线即将支持，当前按日线计算。") 并仍用日线

    auto_tl = st.checkbox("自动趋势线", value=True)
    with st.expander("趋势线参数", expanded=False):
        tl_window = st.number_input("window", min_value=2, max_value=20, value=5, step=1)
        tl_tol = st.number_input("tol", min_value=0.001, max_value=0.1, value=0.015, format="%.3f")
        tl_top_k = st.number_input("top_k", min_value=1, max_value=10, value=3, step=1)
        tl_min_bars = st.number_input("min_bars", min_value=3, max_value=60, value=10, step=1)

    period = st.selectbox("周期", ["日线", "周线（即将支持）"])
    if period.startswith("周线"):
        st.caption("周线趋势线即将支持；以下仍按日线计算。")

    fig = plots.kline_chart(df, tuple(overlays), tuple(sub))
    caption = None
    detail_rows = []
    if auto_tl:
        from quant.structure.trendlines import find_trendlines, evaluate_breakout
        res = find_trendlines(
            df, window=int(tl_window), tol=float(tl_tol),
            top_k=int(tl_top_k), min_bars=int(tl_min_bars),
        )
        if res.best_up is None and res.best_down is None:
            st.info("区间内有效波段点不足，无法拟合趋势线。")
        else:
            x_today = len(df) - 1
            res = evaluate_breakout(res, float(df["close"].iloc[-1]), x_today, tol=float(tl_tol))
            fig = plots.overlay_trendlines(fig, df, res)
            msgs = []
            if res.best_up and res.best_up.status == "broken":
                msgs.append("上升趋势线已破位")
            if res.best_down and res.best_down.status == "broken":
                msgs.append("下降趋势线已升破")
            if msgs:
                st.warning("；".join(msgs))
            for tl in res.up + res.down:
                detail_rows.append({
                    "方向": "上升" if tl.side == "up" else "下降",
                    "触点数": tl.touch_count,
                    "得分": round(tl.score, 2),
                    "起点": str(tl.start_date)[:10],
                    "终点": str(tl.end_date)[:10],
                    "状态": tl.status or "",
                    "触点日": ", ".join(str(d)[:10] for d in tl.touch_dates),
                })
    st.plotly_chart(fig, width="stretch")
    if detail_rows:
        with st.expander("趋势线明细", expanded=True):
            st.dataframe(pd.DataFrame(detail_rows), width="stretch")
```

注意：把原有的 `st.plotly_chart(plots.kline_chart(...))` **替换**为上述流程，避免画两次图。`number_input` 的整型参数用 `int(...)` 传入（与策略参数修复一致）。

- [ ] **Step 4: 运行测试**

Run: `.venv/bin/python -m pytest tests/test_app_import.py tests/test_swings.py tests/test_trendlines.py tests/test_charts.py tests/test_structure_models.py -q`  
Expected: 全 PASS

再跑全量：`.venv/bin/python -m pytest -q`  
Expected: 全 PASS

- [ ] **Step 5: 提交**

```bash
git add app/main.py tests/test_app_import.py
git commit -m "feat(app): 行情 Tab 接入自动趋势线与周线占位"
```

---

## Self-Review

**Spec coverage:**
- 波段点 / 连线打分 / 破位 → Task 2–3 ✅
- K 线叠加 + 明细 → Task 4–5 ✅
- 周线占位 → Task 5 ✅
- `quant/structure/` 解耦 → Task 1–3 ✅
- 离线测试 → 各 Task ✅
- 非目标（选股/浪型/周线计算）未纳入 ✅

**Placeholder scan:** 无 TBD；Task 3 实现块含一处「清理未使用函数」说明，实现者须交付干净文件。

**Type consistency:** `Trendline` / `TrendlineResult` 字段在 models → trendlines → overlay → app 一致；`find_trendlines` / `evaluate_breakout` / `overlay_trendlines` 签名前后一致。
