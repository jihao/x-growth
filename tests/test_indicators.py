import numpy as np
import pandas as pd

from quant.indicators import ta


def _series(vals):
    idx = pd.date_range("2020-01-01", periods=len(vals), freq="D")
    return pd.Series(vals, index=idx, dtype=float)


def test_ma():
    s = _series([1, 2, 3, 4, 5])
    assert ta.ma(s, 3).iloc[-1] == 4.0  # (3+4+5)/3


def test_ema_first_equals_value():
    s = _series([1, 2, 3])
    assert ta.ema(s, 2).iloc[0] == 1.0


def test_macd_shapes():
    s = _series(np.linspace(1, 10, 40))
    dif, dea, hist = ta.macd(s)
    assert len(dif) == len(dea) == len(hist) == 40
    assert np.allclose((dif - dea).dropna(), hist.dropna())


def test_boll_constant_zero_width():
    s = _series([5] * 25)
    up, mid, low = ta.boll(s, n=20, k=2.0)
    assert up.iloc[-1] == mid.iloc[-1] == low.iloc[-1] == 5.0


def test_rsi_bounds_and_uptrend():
    s = _series(np.arange(1, 40, dtype=float))
    r = ta.rsi(s, 14).dropna()
    assert (r >= 0).all() and (r <= 100).all()
    assert r.iloc[-1] > 70


def test_roc():
    s = _series([10, 11, 12, 13])
    assert round(ta.roc(s, 1).iloc[-1], 4) == round((13 / 12 - 1) * 100, 4)


def test_obv_direction():
    close = _series([10, 11, 10, 12])
    vol = pd.Series([100, 200, 150, 300], index=close.index, dtype=float)
    o = ta.obv(close, vol)
    assert o.iloc[1] == 200      # 上涨 +vol
    assert o.iloc[2] == 200 - 150  # 下跌 -vol
    assert o.iloc[3] == 50 + 300


def test_atr_positive():
    n = 20
    idx = pd.date_range("2020-01-01", periods=n, freq="D")
    high = pd.Series(np.arange(2, 2 + n), index=idx, dtype=float)
    low = pd.Series(np.arange(1, 1 + n), index=idx, dtype=float)
    close = (high + low) / 2
    a = ta.atr(high, low, close, 14).dropna()
    assert (a > 0).all()


def test_mfi_all_positive_returns_100():
    n = 20
    idx = pd.date_range("2020-01-01", periods=n, freq="D")
    close = pd.Series(np.arange(10.0, 10.0 + n), index=idx)
    high = close + 1.0
    low = close - 1.0
    volume = pd.Series(np.full(n, 1000.0), index=idx)
    m = ta.mfi(high, low, close, volume, n=14)
    assert abs(m.dropna().iloc[-1] - 100.0) < 1e-9
    warmed = m.iloc[13:]
    assert warmed.notna().all()
    assert np.allclose(warmed, 100.0)


def test_swing_points_flat_not_both():
    s = _series([5.0] * 20)
    res = ta.swing_points(s, window=2)
    assert not (res["is_high"] & res["is_low"]).any()


def test_swing_points_detects_peak():
    vals = [1.0, 2.0, 3.0, 4.0, 5.0, 4.0, 3.0, 2.0, 3.0, 4.0, 3.0, 2.0]
    s = _series(vals)
    res = ta.swing_points(s, window=1)
    peak_idx = s.index[4]
    trough_idx = s.index[7]
    assert res.loc[peak_idx, "is_high"]
    assert not res.loc[peak_idx, "is_low"]
    assert res.loc[trough_idx, "is_low"]
    assert not res.loc[trough_idx, "is_high"]


def test_donchian_channel():
    idx = pd.date_range("2020-01-01", periods=6, freq="D")
    high = pd.Series([2, 3, 4, 3, 2, 5], index=idx, dtype=float)
    low = pd.Series([1, 1, 2, 1, 0, 1], index=idx, dtype=float)
    up, lo = ta.donchian_channel(high, low, upper_n=3, lower_n=3)
    assert up.iloc[2] == 4.0   # max(2,3,4)
    assert lo.iloc[2] == 1.0   # min(1,1,2)
    assert up.iloc[5] == 5.0   # max(3,2,5)
