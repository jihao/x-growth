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


def _make_pivot_df(n, specs):
    """合成 OHLC：单调基线 + 窗口内 V/^ 形 pivot，供 detect_swings(window=2) 稳定识别。"""
    low = 14.0 + np.arange(n) * 0.001
    high = low + 0.3
    for idx, p, k in specs:
        p = float(p)
        if k == "L":
            for d in (-2, -1, 0, 1, 2):
                j = idx + d
                if 0 <= j < n:
                    low[j] = p + abs(d) * 0.4
                    high[j] = low[j] + 0.15
        else:
            for d in (-2, -1, 0, 1, 2):
                j = idx + d
                if 0 <= j < n:
                    high[j] = p - abs(d) * 0.4
                    low[j] = high[j] - 0.15
    close = (high + low) / 2
    return pd.DataFrame(
        {"open": close, "high": high, "low": low, "close": close,
         "volume": 1, "amount": 1},
        index=pd.date_range("2020-01-01", periods=n, freq="D"),
    )


def test_verdict_from_ratio():
    assert waves.verdict_from_ratio(1.2, 1.05, 0.95) == "extend"
    assert waves.verdict_from_ratio(0.8, 1.05, 0.95) == "end"
    assert waves.verdict_from_ratio(1.0, 1.05, 0.95) == "similar"


def test_up_triple_extend_when_wave3_faster():
    # L-H-L-H：浪1 慢、浪3 快（更短 bars 更大涨幅）
    df = _make_pivot_df(
        33,
        [(5, 10.0, "L"), (15, 12.0, "H"), (25, 11.0, "L"), (30, 16.0, "H")],
    )
    res = waves.analyze_wave_speed(df, offset=0, window=2, min_pct=0.0)
    assert res.current is not None
    assert res.current.direction == "up"
    assert res.current.verdict == "extend"
    assert res.current.ratio >= 1.05


def test_up_triple_end_when_wave3_slower():
    # 浪3 涨幅小、耗时长 → 更慢
    df = _make_pivot_df(
        48,
        [(5, 10.0, "L"), (12, 16.0, "H"), (18, 14.0, "L"), (40, 15.0, "H")],
    )
    res = waves.analyze_wave_speed(df, offset=0, window=2, min_pct=0.0)
    assert res.current is not None
    assert res.current.verdict == "end"


def test_offset_one_picks_earlier_triple():
    # 两段上涨三浪：靠后一段与靠前一段 end 日期不同
    early = [(5, 10, "L"), (12, 14, "H"), (18, 12, "L"), (25, 16, "H")]
    late = [(45, 11, "L"), (52, 15, "H"), (58, 13, "L"), (65, 18, "H")]
    df = _make_pivot_df(72, early + late)
    r0 = waves.analyze_wave_speed(df, offset=0, window=2, min_pct=0.0)
    r1 = waves.analyze_wave_speed(df, offset=1, window=2, min_pct=0.0)
    assert r0.current is not None and r1.current is not None
    assert r0.previous_available is True
    assert r0.current.pivots[-1][0] > r1.current.pivots[-1][0]


def test_insufficient_pivots_returns_empty():
    df = _df_ohlc(np.linspace(10, 11, 15))
    res = waves.analyze_wave_speed(df, offset=0, window=5, min_pct=0.01)
    assert res.current is None
