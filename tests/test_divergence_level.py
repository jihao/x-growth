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


def test_missing_dates_medium_not_preferred():
    df = _df(20)
    idx = df.index
    valid = _ev("bottom", 2, 12.0, 12, 11.0, idx)
    missing = DivergenceEvent(
        side="bottom",
        status="pending",
        p1_date=pd.Timestamp("2019-01-01"),
        p1_price=12.0,
        d1=1.0,
        d1_date=pd.Timestamp("2019-01-01"),
        p2_date=pd.Timestamp("2019-06-01"),
        p2_price=11.0,
        d2=0.8,
        d2_date=pd.Timestamp("2019-06-01"),
    )
    annotated, pref = div.annotate_levels(df, [missing, valid])
    by_p1 = {e.p1_date: e for e in annotated}
    assert by_p1[missing.p1_date].level == "medium"
    assert by_p1[missing.p1_date].preferred is False
    assert by_p1[missing.p1_date].speed == 0.0
    assert by_p1[missing.p1_date].span_bars == 0
    assert pref is not None and pref.p1_date == valid.p1_date


def test_analyze_divergence_fills_levels():
    df = _df(80)
    # 注入手工 pivots 路径：直接测 annotate 已覆盖；这里确保 analyze 返回 preferred_event 字段存在
    r = div.analyze_divergence(df, dif=pd.Series(0.0, index=df.index))
    assert hasattr(r, "preferred_event")
    assert isinstance(r.events, list)
