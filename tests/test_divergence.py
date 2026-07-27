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
    dif.iloc[13] = 0.8  # hold: default 0.0 would spuriously confirm here
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
