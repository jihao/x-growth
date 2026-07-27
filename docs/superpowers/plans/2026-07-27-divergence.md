# DIF 背离 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在行情 Tab 增加日线 DIF 顶/底背离检测（钝化 pending + 确认 confirmed），K 线叠加与全量明细表。

**Architecture:** 扩展 `models.py`；新增 `divergence.py`（摆动对齐 DIF → 相邻配对 → 确认 → overlay 过滤）；`plots.overlay_divergence`；`app/main.py` 开关与参数。复用 `waves.build_pivots` 与 `ta.macd`。测试通过可注入的 `dif` 序列绕过 MACD 推导，保证合成断言稳定。

**Tech Stack:** Python 3.13、pandas、plotly、streamlit、pytest（现有 `.venv`）。

## Global Constraints

- 仅日线 DIF；不做 RSI/周线/选股/背离级别/多重背离状态机。
- 顶：`P2>P1` 且 `D2<D1`；底：`P2<P1` 且 `D2>D1`。
- 确认：`max(p2_date,d2_date)` 之后，顶 `move=(D2-dif_t)/max(|D2|,eps)`，底对称；`move>=confirm_pct`（默认 0.05）。
- 明细=全部事件；图上=全部 pending + 最近 1 条 confirmed。
- MACD 固定 12/26/9，UI 不暴露。
- 单测离线：`.venv/bin/python -m pytest`；每 Task 提交一次。
- 不在 `main` 上直接开发：执行时先建 `feat/divergence` 分支。
- Spec：`docs/superpowers/specs/2026-07-27-divergence-design.md`。

## File Structure

| 文件 | 职责 |
|---|---|
| `quant/structure/models.py` | 增 `DivergenceEvent`、`DivergenceResult` |
| `quant/structure/divergence.py` | 对齐、配对、确认、过滤、入口 `analyze_divergence` |
| `quant/charts/plots.py` | 增 `overlay_divergence` |
| `app/main.py` | Tab1 开关 / 参数 / caption / 明细 |
| `tests/test_divergence_models.py` | 模型字段 |
| `tests/test_divergence.py` | 算法（可注入 dif） |
| `tests/test_charts.py` | overlay 烟测 |
| `tests/test_app_import.py` | UI 关键字烟测 |

---

### Task 1: 扩展 models（DivergenceEvent / DivergenceResult）

**Files:**
- Modify: `quant/structure/models.py`
- Create: `tests/test_divergence_models.py`

**Interfaces:**
- Produces:
  - `@dataclass DivergenceEvent`: `side: str` (`"top"|"bottom"`), `status: str` (`"pending"|"confirmed"`), `p1_date`, `p1_price: float`, `d1: float`, `d1_date`, `p2_date`, `p2_price: float`, `d2: float`, `d2_date`, `confirm_date=None`, `confirm_dif: float | None = None`
  - `@dataclass DivergenceResult`: `events: list[DivergenceEvent]`（默认空列表）, `overlay_events: list[DivergenceEvent]`（默认空列表）

- [ ] **Step 1: 写失败测试**

```python
# tests/test_divergence_models.py
from quant.structure.models import DivergenceEvent, DivergenceResult


def test_divergence_event_pending_fields():
    ev = DivergenceEvent(
        side="top",
        status="pending",
        p1_date="a",
        p1_price=10.0,
        d1=1.0,
        d1_date="a",
        p2_date="b",
        p2_price=11.0,
        d2=0.8,
        d2_date="b",
    )
    assert ev.side == "top" and ev.status == "pending"
    assert ev.confirm_date is None and ev.confirm_dif is None


def test_divergence_result_defaults():
    r = DivergenceResult()
    assert r.events == [] and r.overlay_events == []
```

- [ ] **Step 2: 运行确认失败**

Run: `.venv/bin/python -m pytest tests/test_divergence_models.py -v`  
Expected: FAIL（类不存在）

- [ ] **Step 3: 在 `models.py` 末尾追加**

```python
@dataclass
class DivergenceEvent:
    side: str  # "top" | "bottom"
    status: str  # "pending" | "confirmed"
    p1_date: Any
    p1_price: float
    d1: float
    d1_date: Any
    p2_date: Any
    p2_price: float
    d2: float
    d2_date: Any
    confirm_date: Any | None = None
    confirm_dif: float | None = None


@dataclass
class DivergenceResult:
    events: list[DivergenceEvent] = field(default_factory=list)
    overlay_events: list[DivergenceEvent] = field(default_factory=list)
```

- [ ] **Step 4: 运行确认通过**

Run: `.venv/bin/python -m pytest tests/test_divergence_models.py -v`  
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add quant/structure/models.py tests/test_divergence_models.py
git commit -m "feat(structure): DivergenceEvent / DivergenceResult"
```

---

### Task 2: `divergence.py` 核心算法

**Files:**
- Create: `quant/structure/divergence.py`
- Create: `tests/test_divergence.py`

**Interfaces:**
- Consumes: `waves.build_pivots`, `ta.macd`, models
- Produces:
  - `EPS = 1e-8`
  - `align_dif_at_pivot(dif: pd.Series, pivot_date, kind: str, align_bars: int) -> tuple[Any, float] | None`  
    `kind` 为 `"H"`→窗内 DIF max；`"L"`→min；返回 `(dif_date, dif_value)`；无有效值则 `None`
  - `confirm_move(side: str, d2: float, dif_t: float) -> float`  
    top: `(d2 - dif_t) / max(abs(d2), EPS)`；bottom: `(dif_t - d2) / max(abs(d2), EPS)`
  - `apply_confirm(ev: DivergenceEvent, dif: pd.Series, confirm_pct: float) -> DivergenceEvent`  
    从 `max(p2_date, d2_date)` **之后**扫描；首次 `confirm_move >= confirm_pct` 则返回新事件 `status=confirmed`（不修改入参）
  - `filter_overlay_events(events: list[DivergenceEvent]) -> list[DivergenceEvent]`  
    全部 pending + confirmed 中按 `(confirm_date or p2_date)` 最新 1 条
  - `detect_events(df, dif, pivots, align_bars=3, confirm_pct=0.05) -> list[DivergenceEvent]`  
    对齐 → 同类相邻配对 → pending → apply_confirm；按 `p2_date` 升序
  - `analyze_divergence(df, window=5, min_pct=0.01, align_bars=3, confirm_pct=0.05, dif: pd.Series | None = None) -> DivergenceResult`  
    `dif is None` 时用 `ta.macd(df["close"])[0]`；pivots 用 `build_pivots`；填 `events` 与 `overlay_events`

- [ ] **Step 1: 写失败测试**

```python
# tests/test_divergence.py
import numpy as np
import pandas as pd

from quant.structure.models import DivergenceEvent
from quant.structure import divergence as div


def _idx(n):
    return pd.date_range("2020-01-01", periods=n, freq="D")


def test_confirm_move_top_and_bottom():
    assert abs(div.confirm_move("top", 1.0, 0.9) - 0.1) < 1e-9
    assert abs(div.confirm_move("bottom", -1.0, -0.9) - 0.1) < 1e-9


def test_align_dif_at_pivot_high_takes_max():
    idx = _idx(10)
    dif = pd.Series([0.1, 0.2, 0.5, 0.3, 0.1, 0.0, -0.1, 0.0, 0.1, 0.2], index=idx)
    got = div.align_dif_at_pivot(dif, idx[4], "H", align_bars=2)
    assert got is not None
    assert got[0] == idx[2] and abs(got[1] - 0.5) < 1e-9


def test_pending_top_then_confirm():
    # 手工 pivots + dif：两高点价升 DIF 降，之后 DIF 回落确认
    idx = _idx(20)
    close = np.linspace(10, 12, 20)
    df = pd.DataFrame(
        {"open": close, "high": close + 0.2, "low": close - 0.2, "close": close,
         "volume": 1.0, "amount": 1.0},
        index=idx,
    )
    dif = pd.Series(0.0, index=idx, dtype=float)
    # pivot1 @5: D1=1.0; pivot2 @12: D2=0.8; then drop to 0.7 (<5% of 0.8 → need more)
    # move = (0.8 - dif_t)/0.8 >= 0.05 → dif_t <= 0.76
    dif.iloc[5] = 1.0
    dif.iloc[12] = 0.8
    dif.iloc[14] = 0.70  # move = 0.125 >= 0.05
    pivots = [
        (idx[5], 10.5, "H"),
        (idx[8], 10.0, "L"),
        (idx[12], 11.5, "H"),
    ]
    events = div.detect_events(df, dif, pivots, align_bars=0, confirm_pct=0.05)
    tops = [e for e in events if e.side == "top"]
    assert len(tops) == 1
    assert tops[0].status == "confirmed"
    assert tops[0].confirm_date == idx[14]


def test_pending_bottom_symmetric():
    idx = _idx(20)
    close = np.linspace(12, 10, 20)
    df = pd.DataFrame(
        {"open": close, "high": close + 0.2, "low": close - 0.2, "close": close,
         "volume": 1.0, "amount": 1.0},
        index=idx,
    )
    dif = pd.Series(0.0, index=idx, dtype=float)
    dif.iloc[5] = -1.0
    dif.iloc[12] = -0.8
    dif.iloc[14] = -0.70  # bottom lift from -0.8
    pivots = [
        (idx[5], 11.5, "L"),
        (idx[8], 12.0, "H"),
        (idx[12], 10.5, "L"),
    ]
    events = div.detect_events(df, dif, pivots, align_bars=0, confirm_pct=0.05)
    bots = [e for e in events if e.side == "bottom"]
    assert len(bots) == 1
    assert bots[0].status == "confirmed"


def test_no_top_when_dif_also_higher():
    idx = _idx(15)
    close = np.ones(15) * 10.0
    df = pd.DataFrame(
        {"open": close, "high": close + 0.2, "low": close - 0.2, "close": close,
         "volume": 1.0, "amount": 1.0},
        index=idx,
    )
    dif = pd.Series(0.0, index=idx, dtype=float)
    dif.iloc[3] = 0.5
    dif.iloc[10] = 0.7  # DIF 同步抬高
    pivots = [(idx[3], 10.0, "H"), (idx[6], 9.5, "L"), (idx[10], 11.0, "H")]
    events = div.detect_events(df, dif, pivots, align_bars=0)
    assert all(e.side != "top" for e in events)


def test_empty_pivots_ok():
    idx = _idx(10)
    df = pd.DataFrame(
        {"open": 1.0, "high": 1.1, "low": 0.9, "close": 1.0, "volume": 1.0, "amount": 1.0},
        index=idx,
    )
    dif = pd.Series(0.0, index=idx)
    assert div.detect_events(df, dif, []) == []
    r = div.analyze_divergence(df, dif=dif)
    assert r.events == [] and r.overlay_events == []


def test_filter_overlay_keeps_all_pending_and_latest_confirmed():
    idx = _idx(5)
    def ev(side, status, p2, conf=None):
        return DivergenceEvent(
            side=side, status=status,
            p1_date=idx[0], p1_price=1.0, d1=1.0, d1_date=idx[0],
            p2_date=p2, p2_price=2.0, d2=0.5, d2_date=p2,
            confirm_date=conf, confirm_dif=0.4 if conf is not None else None,
        )
    events = [
        ev("top", "pending", idx[1]),
        ev("bottom", "pending", idx[2]),
        ev("top", "confirmed", idx[3], idx[3]),
        ev("bottom", "confirmed", idx[4], idx[4]),
    ]
    ov = div.filter_overlay_events(events)
    assert sum(1 for e in ov if e.status == "pending") == 2
    conf = [e for e in ov if e.status == "confirmed"]
    assert len(conf) == 1 and conf[0].p2_date == idx[4]
```

- [ ] **Step 2: 运行确认失败**

Run: `.venv/bin/python -m pytest tests/test_divergence.py -v`  
Expected: FAIL（模块不存在）

- [ ] **Step 3: 实现 `quant/structure/divergence.py`**

```python
"""DIF 顶/底背离：钝化（pending）与确认（confirmed）。"""
from __future__ import annotations

from copy import copy

import pandas as pd

from quant.indicators import ta
from quant.structure.models import DivergenceEvent, DivergenceResult
from quant.structure.waves import build_pivots

EPS = 1e-8


def align_dif_at_pivot(
    dif: pd.Series, pivot_date, kind: str, align_bars: int
) -> tuple | None:
    i = int(dif.index.get_loc(pivot_date))
    lo = max(0, i - align_bars)
    hi = min(len(dif) - 1, i + align_bars)
    window = dif.iloc[lo : hi + 1]
    valid = window.dropna()
    if valid.empty:
        return None
    if kind == "H":
        j = valid.idxmax()
    else:
        j = valid.idxmin()
    return j, float(valid.loc[j])


def confirm_move(side: str, d2: float, dif_t: float) -> float:
    denom = max(abs(d2), EPS)
    if side == "top":
        return (d2 - dif_t) / denom
    return (dif_t - d2) / denom


def apply_confirm(
    ev: DivergenceEvent, dif: pd.Series, confirm_pct: float
) -> DivergenceEvent:
    start = max(ev.p2_date, ev.d2_date)
    # 之后：严格晚于 start
    after = dif.loc[dif.index > start]
    for t, v in after.items():
        if pd.isna(v):
            continue
        if confirm_move(ev.side, ev.d2, float(v)) >= confirm_pct:
            out = copy(ev)
            out.status = "confirmed"
            out.confirm_date = t
            out.confirm_dif = float(v)
            return out
    return ev


def filter_overlay_events(events: list[DivergenceEvent]) -> list[DivergenceEvent]:
    pending = [e for e in events if e.status == "pending"]
    confirmed = [e for e in events if e.status == "confirmed"]
    if not confirmed:
        return list(pending)
    latest = max(
        confirmed,
        key=lambda e: e.confirm_date if e.confirm_date is not None else e.p2_date,
    )
    return list(pending) + [latest]


def detect_events(
    df: pd.DataFrame,
    dif: pd.Series,
    pivots: list[tuple],
    align_bars: int = 3,
    confirm_pct: float = 0.05,
) -> list[DivergenceEvent]:
    aligned: list[tuple] = []  # (date, price, kind, d_date, d_val)
    for d, price, kind in pivots:
        ad = align_dif_at_pivot(dif, d, kind, align_bars)
        if ad is None:
            continue
        aligned.append((d, float(price), kind, ad[0], ad[1]))

    events: list[DivergenceEvent] = []
    highs = [a for a in aligned if a[2] == "H"]
    lows = [a for a in aligned if a[2] == "L"]

    def _pairs(seq, side: str):
        for i in range(len(seq) - 1):
            a, b = seq[i], seq[i + 1]
            p1, d1 = a[1], a[4]
            p2, d2 = b[1], b[4]
            ok = (p2 > p1 and d2 < d1) if side == "top" else (p2 < p1 and d2 > d1)
            if not ok:
                continue
            ev = DivergenceEvent(
                side=side,
                status="pending",
                p1_date=a[0],
                p1_price=p1,
                d1=d1,
                d1_date=a[3],
                p2_date=b[0],
                p2_price=p2,
                d2=d2,
                d2_date=b[3],
            )
            events.append(apply_confirm(ev, dif, confirm_pct))

    _pairs(highs, "top")
    _pairs(lows, "bottom")
    events.sort(key=lambda e: e.p2_date)
    return events


def analyze_divergence(
    df: pd.DataFrame,
    window: int = 5,
    min_pct: float = 0.01,
    align_bars: int = 3,
    confirm_pct: float = 0.05,
    dif: pd.Series | None = None,
) -> DivergenceResult:
    if dif is None:
        dif, _, _ = ta.macd(df["close"])
    pivots = build_pivots(df, window=window, min_pct=min_pct)
    events = detect_events(
        df, dif, pivots, align_bars=align_bars, confirm_pct=confirm_pct
    )
    return DivergenceResult(
        events=events,
        overlay_events=filter_overlay_events(events),
    )
```

注意：`copy(ev)` 对 dataclass 是浅拷贝，足够改 `status/confirm_*`；若项目偏好可用 `dataclasses.replace`。

- [ ] **Step 4: 运行确认通过**

Run: `.venv/bin/python -m pytest tests/test_divergence.py tests/test_divergence_models.py -v`  
Expected: PASS

若 `align_bars=0` 时 `get_loc`/`iloc` 边界有问题，保持窗为单点即可。

- [ ] **Step 5: 提交**

```bash
git add quant/structure/divergence.py tests/test_divergence.py
git commit -m "feat(structure): DIF 背离检测（钝化与确认）"
```

---

### Task 3: Plotly `overlay_divergence`

**Files:**
- Modify: `quant/charts/plots.py`（在 `overlay_waves` 之后追加）
- Modify: `tests/test_charts.py`（追加测试）

**Interfaces:**
- Produces: `overlay_divergence(fig, df, events: list[DivergenceEvent]) -> Figure`  
  对每个事件画 P1→P2 价格连线：`top` 色 `#ef5350`，`bottom` 色 `#26a69a`；`pending` → `dash="dot"`，`confirmed` → `dash="solid"`；`name` 含侧别与状态；`row=1,col=1`

- [ ] **Step 1: 追加测试**

在 `tests/test_charts.py` 末尾追加：

```python
def test_overlay_divergence_adds_traces():
    from quant.structure.models import DivergenceEvent

    df = _df(40)
    ev = DivergenceEvent(
        side="top",
        status="pending",
        p1_date=df.index[10],
        p1_price=float(df["high"].iloc[10]),
        d1=1.0,
        d1_date=df.index[10],
        p2_date=df.index[25],
        p2_price=float(df["high"].iloc[25]),
        d2=0.8,
        d2_date=df.index[25],
    )
    fig0 = plots.kline_chart(df, overlays=(), sub=())
    n0 = len(fig0.data)
    fig1 = plots.overlay_divergence(fig0, df, [ev])
    assert len(fig1.data) > n0
```

- [ ] **Step 2: 运行确认失败**

Run: `.venv/bin/python -m pytest tests/test_charts.py::test_overlay_divergence_adds_traces -v`  
Expected: FAIL

- [ ] **Step 3: 在 `plots.py` 实现**

```python
def overlay_divergence(fig, df, events):
    """叠加 DIF 背离两触点连线（价位）。"""
    for i, ev in enumerate(events):
        color = "#ef5350" if ev.side == "top" else "#26a69a"
        dash = "dot" if ev.status == "pending" else "solid"
        side_cn = "顶" if ev.side == "top" else "底"
        st_cn = "钝化" if ev.status == "pending" else "确认"
        fig.add_trace(
            go.Scatter(
                x=[ev.p1_date, ev.p2_date],
                y=[ev.p1_price, ev.p2_price],
                mode="lines+markers",
                name=f"{side_cn}背离·{st_cn}",
                line=dict(color=color, width=2, dash=dash),
                marker=dict(size=8, color=color),
                hovertemplate=(
                    f"{side_cn}背离({st_cn})<br>"
                    "%{x|%Y-%m-%d}: %{y:.4f}<extra></extra>"
                ),
                legendgroup=f"div-{ev.side}-{i}",
                showlegend=True,
            ),
            row=1,
            col=1,
        )
    return fig
```

- [ ] **Step 4: 运行确认通过**

Run: `.venv/bin/python -m pytest tests/test_charts.py -q`  
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add quant/charts/plots.py tests/test_charts.py
git commit -m "feat(charts): K线叠加 DIF 背离连线"
```

---

### Task 4: Streamlit 接入

**Files:**
- Modify: `app/main.py`（浪型逻辑之后、`st.plotly_chart` 之前接入背离；明细 expander 与浪型并列）
- Modify: `tests/test_app_import.py`

**Interfaces:**
- Consumes: `analyze_divergence`, `overlay_divergence`

- [ ] **Step 1: 扩展烟测**

在 `tests/test_app_import.py` 追加：

```python
    assert "DIF 背离" in src
    assert "analyze_divergence" in src
```

- [ ] **Step 2: 运行确认失败**

Run: `.venv/bin/python -m pytest tests/test_app_import.py -v`  
Expected: FAIL

- [ ] **Step 3: 在 Tab1 接入**

放在浪型块结束、`st.plotly_chart(fig)` **之前**：

```python
        auto_div = st.checkbox("DIF 背离", value=True)
        with st.expander("背离参数", expanded=False):
            st.markdown(
                """
**DIF 背离怎么看？**

1. **顶背离**：价格高点抬升，但 MACD 的 DIF 高点下降。
2. **底背离**：价格低点下移，但 DIF 低点抬升。
3. 价格创新高/新低而 DIF 不同步 → **钝化（pending）**；之后 DIF 自极值反向离开达 `confirm_pct` → **确认（confirmed）**。
4. 图上画全部钝化 + 最近 1 条已确认；明细表列出全部事件。
                """.strip()
            )
            d_window = st.number_input(
                "div_window", min_value=2, max_value=20, value=5, step=1
            )
            d_min_pct = st.number_input(
                "div_min_pct", min_value=0.0, max_value=0.1, value=0.01,
                format="%.3f", step=0.005,
            )
            d_align = st.number_input(
                "align_bars", min_value=0, max_value=10, value=3, step=1
            )
            d_confirm = st.number_input(
                "confirm_pct", min_value=0.01, max_value=0.5, value=0.05,
                format="%.2f", step=0.01,
            )

        div_rows = []
        if auto_div:
            from quant.structure.divergence import analyze_divergence

            dres = analyze_divergence(
                df,
                window=int(d_window),
                min_pct=float(d_min_pct),
                align_bars=int(d_align),
                confirm_pct=float(d_confirm),
            )
            if not dres.events:
                st.info("区间内未识别到 DIF 背离（钝化/确认）。")
            else:
                fig = plots.overlay_divergence(fig, df, dres.overlay_events)
                # caption：优先最近一条（按 p2_date）
                last = dres.events[-1]
                side_cn = "顶" if last.side == "top" else "底"
                if last.status == "confirmed":
                    st.info(f"{side_cn}背离已确认")
                else:
                    st.info(f"{side_cn}背离钝化中")
                for ev in dres.events:
                    div_rows.append({
                        "类型": "顶" if ev.side == "top" else "底",
                        "状态": "确认" if ev.status == "confirmed" else "钝化",
                        "P1": str(ev.p1_date)[:10],
                        "P1价": round(ev.p1_price, 4),
                        "D1": round(ev.d1, 4),
                        "P2": str(ev.p2_date)[:10],
                        "P2价": round(ev.p2_price, 4),
                        "D2": round(ev.d2, 4),
                        "确认日": str(ev.confirm_date)[:10] if ev.confirm_date is not None else "",
                    })
```

在浪型明细之后增加：

```python
        if div_rows:
            with st.expander("背离明细", expanded=True):
                st.dataframe(pd.DataFrame(div_rows), width="stretch")
```

约束：`st.plotly_chart(fig)` 仍只调用一次，且在趋势线 / 浪型 / 背离全部叠加之后。

- [ ] **Step 4: 全量测试**

Run: `.venv/bin/python -m pytest -q`  
Expected: 全 PASS

- [ ] **Step 5: 提交**

```bash
git add app/main.py tests/test_app_import.py
git commit -m "feat(app): 行情 Tab 接入 DIF 背离分析"
```

---

## Self-Review

**Spec coverage:**
- 顶/底 pending + confirmed 公式 → Task 2 ✅
- align_bars / confirm_pct / MACD 默认 → Task 2+4 ✅
- 明细全量、图上 pending+最新 confirmed → Task 2 `filter_overlay_events` + Task 3/4 ✅
- UI 开关/说明/参数/caption/明细 → Task 4 ✅
- 非目标未纳入 ✅
- 合成测试清单 1–6 → Task 2 测试覆盖 ✅

**Placeholder scan:** 无 TBD / “similar to Task N” / 空实现步骤

**Type consistency:** `DivergenceEvent.side/status`、`analyze_divergence(...)->DivergenceResult`、`overlay_divergence(fig, df, events)` 在 Task 1–4 命名一致；可注入 `dif` 仅用于测试，生产路径 `dif=None` 走 `ta.macd`
