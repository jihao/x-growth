"""DIF 顶/底背离：钝化（pending）与确认（confirmed）。"""
from __future__ import annotations

from dataclasses import replace

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
