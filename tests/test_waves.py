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
    specs = [(5, 10.0, "L"), (15, 12.0, "H"), (25, 11.0, "L"), (30, 16.0, "H")]
    df = _make_pivot_df(33, specs)
    res = waves.analyze_wave_speed(df, offset=0, window=2, min_pct=0.0)
    assert res.current is not None
    assert res.current.direction == "up"
    assert res.current.verdict == "extend"
    assert res.current.ratio >= 1.05
    assert res.current.pivots[-1][0] == df.index[specs[-1][0]]


def test_up_triple_end_when_wave3_slower():
    # 浪3 涨幅小、耗时长 → 更慢；min_pct 滤除基线噪声，保证 offset=0 为 intended 上涨三浪
    specs = [(5, 10.0, "L"), (12, 16.0, "H"), (18, 14.0, "L"), (40, 15.0, "H")]
    df = _make_pivot_df(48, specs)
    res = waves.analyze_wave_speed(df, offset=0, window=2, min_pct=0.01)
    assert res.current is not None
    assert res.current.direction == "up"
    assert res.current.verdict == "end"
    assert res.current.ratio <= 0.95
    assert res.current.pivots[-1][0] == df.index[specs[-1][0]]


def test_offset_one_picks_earlier_triple():
    # 连续 L-H-L-H-L-H：靠前段 end@75、靠后段 end@93；仅 2 个 up triple，offset=1 为靠前段
    specs = [
        (27, 14, "L"), (43, 15, "H"), (58, 18, "L"), (75, 19, "H"),
        (81, 14, "L"), (93, 20, "H"),
    ]
    early_h_idx, late_h_idx = 75, 93
    df = _make_pivot_df(96, specs)
    kw = dict(window=2, min_pct=0.01)
    triples = waves.find_wave_triples(df, **kw)
    assert len(triples) == 2
    assert triples[0].direction == "up"
    assert triples[0].pivots[-1][0] == df.index[late_h_idx]
    assert triples[1].direction == "up"
    assert triples[1].pivots[-1][0] == df.index[early_h_idx]
    r0 = waves.analyze_wave_speed(df, offset=0, **kw)
    r1 = waves.analyze_wave_speed(df, offset=1, **kw)
    assert r0.current is not None and r1.current is not None
    assert r0.previous_available is True
    assert r0.current.direction == "up"
    assert r1.current.direction == "up"
    assert r0.current.pivots[-1][0] == df.index[late_h_idx]
    assert r1.current.pivots[-1][0] == df.index[early_h_idx]
    assert r0.current.pivots[-1][0] > r1.current.pivots[-1][0]


def test_down_triple_extend_when_wave3_faster():
    # H-L-H-L：浪1 慢跌、浪3 快跌 → extend
    specs = [(5, 16.0, "H"), (15, 14.0, "L"), (25, 15.0, "H"), (30, 10.0, "L")]
    df = _make_pivot_df(33, specs)
    res = waves.analyze_wave_speed(df, offset=0, window=2, min_pct=0.0)
    assert res.current is not None
    assert res.current.direction == "down"
    assert res.current.verdict == "extend"
    assert res.current.ratio >= 1.05
    assert res.current.legs[0].end_price < res.current.legs[0].start_price
    assert res.current.legs[2].end_price < res.current.legs[2].start_price
    assert res.current.pivots[-1][0] == df.index[specs[-1][0]]


def test_down_triple_end_when_wave3_slower():
    # 浪3 跌幅小、耗时长 → 更慢；min_pct 滤除基线噪声
    specs = [(5, 16.0, "H"), (12, 10.0, "L"), (18, 14.0, "H"), (40, 13.0, "L")]
    df = _make_pivot_df(48, specs)
    res = waves.analyze_wave_speed(df, offset=0, window=2, min_pct=0.01)
    assert res.current is not None
    assert res.current.direction == "down"
    assert res.current.verdict == "end"
    assert res.current.ratio <= 0.95
    assert res.current.legs[0].end_price < res.current.legs[0].start_price
    assert res.current.legs[2].end_price < res.current.legs[2].start_price
    assert res.current.pivots[-1][0] == df.index[specs[-1][0]]


def test_insufficient_pivots_returns_empty():
    df = _df_ohlc(np.linspace(10, 11, 15))
    res = waves.analyze_wave_speed(df, offset=0, window=5, min_pct=0.01)
    assert res.current is None
