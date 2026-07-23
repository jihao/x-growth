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
