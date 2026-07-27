"""DIF 顶/底背离：钝化（pending）与确认（confirmed）。"""
from __future__ import annotations

from dataclasses import replace

import numpy as np
import pandas as pd

from quant.indicators import ta
from quant.structure.models import DivergenceEvent, DivergenceResult
from quant.structure.waves import build_pivots

EPS = 1e-8

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
            return replace(
                ev,
                status="confirmed",
                confirm_date=t,
                confirm_dif=float(v),
            )
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
