# 背离级别 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在已有 DIF 背离事件上标注价格速度级别（强/中/弱）与同侧优先事件，并在行情 Tab 明细与 caption 展示。

**Architecture:** 扩展 `DivergenceEvent`/`DivergenceResult` 字段；在 `divergence.py` 增加 `annotate_levels`（算 speed/span → 分档 → 择优），由 `analyze_divergence` 末尾调用；`app/main.py` 增加明细列与优先 caption。不改钝化/确认与 overlay 过滤。

**Tech Stack:** Python 3.13、pandas、numpy、streamlit、pytest（现有 `.venv`）。

## Global Constraints

- 不改 DIF 对齐、钝化、确认公式与 `filter_overlay_events`。
- `speed = abs(P2-P1)/bars`，`bars = max(index差, 1)`；越慢级别越强。
- 同侧分位数默认 `q_slow=0.33`、`q_fast=0.66`；1 条→medium；2 条→慢 strong / 快 weak。
- 择优：更慢优先；相对差 `< near_pct`(0.05) 时取 p2 更晚；再平取 `span_bars` 更大。
- 跨度不用于上调档位，仅择优平局。
- 单测离线；`.venv/bin/python -m pytest`；每 Task 提交一次。
- 执行时建 `feat/divergence-level` 分支（勿直接在脏主分支堆功能；若工作区有未提交的 UI 改动，先 stash 或一并纳入约定）。
- Spec：`docs/superpowers/specs/2026-07-27-divergence-level-design.md`。

## File Structure

| 文件 | 职责 |
|---|---|
| `quant/structure/models.py` | Event/Result 增字段 |
| `quant/structure/divergence.py` | `annotate_levels` + 接入 `analyze_divergence` |
| `app/main.py` | 说明、明细列、优先 caption |
| `tests/test_divergence_models.py` | 新字段默认 |
| `tests/test_divergence_level.py` | 级别/择优 |
| `tests/test_divergence.py` | 回归（应仍绿） |
| `tests/test_app_import.py` | UI 关键字烟测 |

---

### Task 1: 扩展 models 字段

**Files:**
- Modify: `quant/structure/models.py`
- Modify: `tests/test_divergence_models.py`

**Interfaces:**
- Produces:
  - `DivergenceEvent` 增：`speed: float = 0.0`, `span_bars: int = 0`, `level: str = "medium"`, `preferred: bool = False`
  - `DivergenceResult` 增：`preferred_event: DivergenceEvent | None = None`

- [ ] **Step 1: 扩展失败测试**

在 `tests/test_divergence_models.py` 追加：

```python
def test_divergence_event_level_defaults():
    ev = DivergenceEvent(
        side="bottom",
        status="pending",
        p1_date="a",
        p1_price=10.0,
        d1=-1.0,
        d1_date="a",
        p2_date="b",
        p2_price=9.0,
        d2=-0.8,
        d2_date="b",
    )
    assert ev.speed == 0.0 and ev.span_bars == 0
    assert ev.level == "medium" and ev.preferred is False


def test_divergence_result_preferred_default():
    r = DivergenceResult()
    assert r.preferred_event is None
```

- [ ] **Step 2: 运行确认失败**

Run: `.venv/bin/python -m pytest tests/test_divergence_models.py -v`  
Expected: FAIL（缺属性）

- [ ] **Step 3: 修改 `models.py`**

在 `DivergenceEvent` 末尾字段后追加默认字段：

```python
    confirm_date: Any | None = None
    confirm_dif: float | None = None
    speed: float = 0.0
    span_bars: int = 0
    level: str = "medium"  # strong | medium | weak
    preferred: bool = False
```

在 `DivergenceResult`：

```python
@dataclass
class DivergenceResult:
    events: list[DivergenceEvent] = field(default_factory=list)
    overlay_events: list[DivergenceEvent] = field(default_factory=list)
    preferred_event: DivergenceEvent | None = None
```

- [ ] **Step 4: 运行确认通过**

Run: `.venv/bin/python -m pytest tests/test_divergence_models.py tests/test_divergence.py -q`  
Expected: PASS（旧构造仍可用）

- [ ] **Step 5: 提交**

```bash
git add quant/structure/models.py tests/test_divergence_models.py
git commit -m "feat(structure): DivergenceEvent level/preferred fields"
```

---

### Task 2: `annotate_levels` 并接入 `analyze_divergence`

**Files:**
- Modify: `quant/structure/divergence.py`
- Create: `tests/test_divergence_level.py`

**Interfaces:**
- Consumes: `DivergenceEvent`, `df` index
- Produces:
  - `LEVEL_CN = {"strong": "强", "medium": "中", "weak": "弱"}`（可供 UI import）
  - `event_speed_span(df, ev) -> tuple[float, int]`
  - `assign_levels_for_side(events: list[DivergenceEvent], q_slow=0.33, q_fast=0.66) -> list[DivergenceEvent]`  
    返回带 `level` 的新列表（`dataclasses.replace`），不改入参对象
  - `pick_preferred(events: list[DivergenceEvent], near_pct=0.05) -> DivergenceEvent | None`  
    同侧列表中选 1 个；空则 None
  - `annotate_levels(df, events, q_slow=0.33, q_fast=0.66, near_pct=0.05) -> tuple[list[DivergenceEvent], DivergenceEvent | None]`  
    填 speed/span/level/preferred；返回 (annotated_events, preferred_event)
  - `analyze_divergence(..., q_slow=0.33, q_fast=0.66, near_pct=0.05)` 在 detect 后调用 annotate，再 filter overlay

- [ ] **Step 1: 写失败测试**

```python
# tests/test_divergence_level.py
import numpy as np
import pandas as pd

from quant.structure.models import DivergenceEvent
from quant.structure import divergence as div


def _idx(n):
    return pd.date_range("2020-01-01", periods=n, freq="D")


def _df(n=30):
    idx = _idx(n)
    c = np.linspace(10, 12, n)
    return pd.DataFrame(
        {"open": c, "high": c + 0.2, "low": c - 0.2, "close": c,
         "volume": 1.0, "amount": 1.0},
        index=idx,
    )


def _ev(side, p1_i, p1_p, p2_i, p2_p, idx, status="pending"):
    return DivergenceEvent(
        side=side, status=status,
        p1_date=idx[p1_i], p1_price=p1_p, d1=1.0, d1_date=idx[p1_i],
        p2_date=idx[p2_i], p2_price=p2_p, d2=0.8, d2_date=idx[p2_i],
    )


def test_two_bottom_slower_is_strong_and_preferred():
    df = _df(40)
    idx = df.index
    # 慢：价差 1 / 20 bars = 0.05；快：价差 2 / 10 bars = 0.2
    slow = _ev("bottom", 5, 12.0, 25, 11.0, idx)
    fast = _ev("bottom", 26, 11.5, 36, 9.5, idx)
    annotated, pref = div.annotate_levels(df, [slow, fast])
    by_p2 = {e.p2_date: e for e in annotated}
    assert by_p2[idx[25]].level == "strong" and by_p2[idx[25]].preferred is True
    assert by_p2[idx[36]].level == "weak" and by_p2[idx[36]].preferred is False
    assert pref is by_p2[idx[25]]


def test_single_event_medium_preferred():
    df = _df(20)
    idx = df.index
    ev = _ev("top", 2, 10.0, 12, 11.0, idx)
    annotated, pref = div.annotate_levels(df, [ev])
    assert len(annotated) == 1
    assert annotated[0].level == "medium" and annotated[0].preferred is True
    assert pref is annotated[0]


def test_near_speed_prefers_later_p2():
    df = _df(40)
    idx = df.index
    # 相同 bars=10、相同 |Δp|=1 → speed 相同 → 取更晚 p2
    a = _ev("top", 2, 10.0, 12, 11.0, idx)
    b = _ev("top", 20, 10.0, 30, 11.0, idx)
    annotated, pref = div.annotate_levels(df, [a, b], near_pct=0.05)
    assert pref is not None and pref.p2_date == idx[30]
    assert sum(1 for e in annotated if e.preferred) == 1


def test_preferred_event_later_across_sides():
    df = _df(40)
    idx = df.index
    top = _ev("top", 2, 10.0, 12, 11.0, idx)
    bot = _ev("bottom", 15, 12.0, 35, 11.0, idx)  # p2 更晚
    annotated, pref = div.annotate_levels(df, [top, bot])
    assert pref is not None and pref.side == "bottom" and pref.p2_date == idx[35]


def test_analyze_divergence_fills_levels():
    df = _df(80)
    # 注入手工 pivots 路径：直接测 annotate 已覆盖；这里确保 analyze 返回 preferred_event 字段存在
    r = div.analyze_divergence(df, dif=pd.Series(0.0, index=df.index))
    assert hasattr(r, "preferred_event")
    assert isinstance(r.events, list)
```

- [ ] **Step 2: 运行确认失败**

Run: `.venv/bin/python -m pytest tests/test_divergence_level.py -v`  
Expected: FAIL（`annotate_levels` 不存在）

- [ ] **Step 3: 在 `divergence.py` 实现并接入**

在文件中 `EPS` 附近增加，并在 `analyze_divergence` 末尾调用：

```python
import numpy as np
from dataclasses import replace

LEVEL_CN = {"strong": "强", "medium": "中", "weak": "弱"}


def event_speed_span(df: pd.DataFrame, ev: DivergenceEvent) -> tuple[float, int]:
    try:
        i1 = int(df.index.get_loc(ev.p1_date))
        i2 = int(df.index.get_loc(ev.p2_date))
    except KeyError:
        return 0.0, 0
    bars = max(i2 - i1, 1)
    speed = abs(float(ev.p2_price) - float(ev.p1_price)) / bars
    return float(speed), int(bars)


def assign_levels_for_side(
    events: list[DivergenceEvent],
    q_slow: float = 0.33,
    q_fast: float = 0.66,
) -> list[DivergenceEvent]:
    if not events:
        return []
    if len(events) == 1:
        return [replace(events[0], level="medium")]
    if len(events) == 2:
        a, b = events[0], events[1]
        if a.speed <= b.speed:
            return [replace(a, level="strong"), replace(b, level="weak")]
        return [replace(a, level="weak"), replace(b, level="strong")]
    speeds = np.array([e.speed for e in events], dtype=float)
    p_slow = float(np.quantile(speeds, q_slow))
    p_fast = float(np.quantile(speeds, q_fast))
    out = []
    for e in events:
        if e.speed <= p_slow:
            lv = "strong"
        elif e.speed <= p_fast:
            lv = "medium"
        else:
            lv = "weak"
        out.append(replace(e, level=lv))
    return out


def _better_preferred(a: DivergenceEvent, b: DivergenceEvent, near_pct: float) -> DivergenceEvent:
    denom = max(a.speed, b.speed, EPS)
    rel = abs(a.speed - b.speed) / denom
    if rel < near_pct:
        if a.p2_date != b.p2_date:
            return a if a.p2_date > b.p2_date else b
        return a if a.span_bars >= b.span_bars else b
    return a if a.speed <= b.speed else b


def pick_preferred(
    events: list[DivergenceEvent], near_pct: float = 0.05
) -> DivergenceEvent | None:
    if not events:
        return None
    best = events[0]
    for e in events[1:]:
        best = _better_preferred(best, e, near_pct)
    return best


def annotate_levels(
    df: pd.DataFrame,
    events: list[DivergenceEvent],
    q_slow: float = 0.33,
    q_fast: float = 0.66,
    near_pct: float = 0.05,
) -> tuple[list[DivergenceEvent], DivergenceEvent | None]:
    if not events:
        return [], None
    filled: list[DivergenceEvent] = []
    for ev in events:
        speed, span = event_speed_span(df, ev)
        filled.append(replace(ev, speed=speed, span_bars=span))

    annotated: list[DivergenceEvent] = []
    prefs: list[DivergenceEvent] = []
    for side in ("top", "bottom"):
        side_evs = [e for e in filled if e.side == side]
        leveled = assign_levels_for_side(side_evs, q_slow=q_slow, q_fast=q_fast)
        pref = pick_preferred(leveled, near_pct=near_pct)
        for e in leveled:
            is_pref = (
                pref is not None
                and e.side == pref.side
                and e.p2_date == pref.p2_date
                and e.p1_date == pref.p1_date
            )
            annotated.append(replace(e, preferred=is_pref))
        if pref is not None:
            marked = next(x for x in annotated if x.preferred and x.side == side)
            prefs.append(marked)

    annotated.sort(key=lambda e: e.p2_date)
    if not prefs:
        return annotated, None
    preferred_event = max(prefs, key=lambda e: e.p2_date)
    return annotated, preferred_event
```

用 `side+p1+p2` 匹配 preferred，避免 `replace` 后对象身份比较失败。

更新 `analyze_divergence`：

```python
def analyze_divergence(
    df: pd.DataFrame,
    window: int = 5,
    min_pct: float = 0.01,
    align_bars: int = 3,
    confirm_pct: float = 0.05,
    dif: pd.Series | None = None,
    q_slow: float = 0.33,
    q_fast: float = 0.66,
    near_pct: float = 0.05,
) -> DivergenceResult:
    if dif is None:
        dif, _, _ = ta.macd(df["close"])
    pivots = build_pivots(df, window=window, min_pct=min_pct)
    events = detect_events(
        df, dif, pivots, align_bars=align_bars, confirm_pct=confirm_pct
    )
    events, preferred = annotate_levels(
        df, events, q_slow=q_slow, q_fast=q_fast, near_pct=near_pct
    )
    return DivergenceResult(
        events=events,
        overlay_events=filter_overlay_events(events),
        preferred_event=preferred,
    )
```

- [ ] **Step 4: 运行确认通过**

Run: `.venv/bin/python -m pytest tests/test_divergence_level.py tests/test_divergence.py -q`  
Expected: PASS

若 `test_two_bottom_*` 因日期排序断言失败，核对 preferred 匹配键（side+p1+p2）。

- [ ] **Step 5: 提交**

```bash
git add quant/structure/divergence.py tests/test_divergence_level.py
git commit -m "feat(structure): annotate DIF divergence speed levels"
```

---

### Task 3: Streamlit 明细列 + 优先 caption

**Files:**
- Modify: `app/main.py`（背离说明、`div_rows`、中栏 infos）
- Modify: `tests/test_app_import.py`

**Interfaces:**
- Consumes: `dres.preferred_event`, `LEVEL_CN`（或本地映射）, event.`speed/span_bars/level/preferred`

- [ ] **Step 1: 烟测追加**

```python
    assert "优先关注" in src or "级别" in src
    assert "annotate_levels" in src or "preferred_event" in src or "LEVEL_CN" in src
```

更稳妥（UI 文案必现）：

```python
    assert "优先关注" in src
    assert "缓" in src  # 参数说明含「缓=强」
```

- [ ] **Step 2: 运行确认失败**

Run: `.venv/bin/python -m pytest tests/test_app_import.py -v`  
Expected: FAIL

- [ ] **Step 3: 改 `app/main.py`**

1. 背离参数 markdown 末尾追加两行说明：

```
5. **级别**：P1→P2 价格速度越慢（缓涨/缓跌）→ 强；同侧多个背离优先更慢、更靠近当前的一个。
```

2. 在 `if auto_div` 成功分支，用 `preferred_event` 生成 caption（可替代或补充原「最新一条」info）：

```python
                from quant.structure.divergence import LEVEL_CN

                pe = dres.preferred_event
                if pe is not None:
                    side_cn = "顶" if pe.side == "top" else "底"
                    st_cn = "确认" if pe.status == "confirmed" else "钝化"
                    lv = LEVEL_CN.get(pe.level, pe.level)
                    mid_infos.append(f"优先关注：{side_cn}背离·{lv}（{st_cn}）")
                else:
                    last = dres.events[-1]
                    side_cn = "顶" if last.side == "top" else "底"
                    if last.status == "confirmed":
                        mid_infos.append(f"{side_cn}背离已确认")
                    else:
                        mid_infos.append(f"{side_cn}背离钝化中")
```

（若仍想保留「最近一条」提示，可两条都 append；推荐优先 caption 为主，避免刷屏——按上面只保留优先或回退最近。）

3. `div_rows.append` 增加列：

```python
                    div_rows.append({
                        "类型": "顶" if ev.side == "top" else "底",
                        "状态": "确认" if ev.status == "confirmed" else "钝化",
                        "级别": {"strong": "强", "medium": "中", "weak": "弱"}.get(
                            ev.level, ev.level
                        ),
                        "优先": "是" if ev.preferred else "否",
                        "速度": round(ev.speed, 4),
                        "跨度": ev.span_bars,
                        "P1": str(ev.p1_date)[:10],
                        "P1价": round(ev.p1_price, 4),
                        "D1": round(ev.d1, 4),
                        "P2": str(ev.p2_date)[:10],
                        "P2价": round(ev.p2_price, 4),
                        "D2": round(ev.d2, 4),
                        "确认日": (
                            str(ev.confirm_date)[:10]
                            if ev.confirm_date is not None else ""
                        ),
                    })
```

- [ ] **Step 4: 全量测试**

Run: `.venv/bin/python -m pytest -q`  
Expected: 全 PASS

- [ ] **Step 5: 提交**

```bash
git add app/main.py tests/test_app_import.py
git commit -m "feat(app): show divergence level and preferred caption"
```

---

## Self-Review

**Spec coverage:** speed/span/level/preferred、同侧分档边界、择优规则、preferred_event、明细+caption、不改 confirm/overlay → Task 1–3 ✅  

**Placeholder scan:** 无 TBD  

**Type consistency:** `level` 英文枚举 + UI `LEVEL_CN`；`annotate_levels -> (list, preferred|None)`；`analyze_divergence` 增 `q_slow/q_fast/near_pct` 与 spec 一致
