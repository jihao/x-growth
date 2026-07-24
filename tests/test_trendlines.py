import numpy as np
import pandas as pd

from quant.structure import trendlines
from quant.structure.models import Trendline, TrendlineResult


def test_colinear_lows_get_multiple_touches():
    # 构造明确上升低点：索引 5,15,25 的 low 近似共线
    n = 40
    close = np.full(n, 20.0)
    low = np.full(n, 19.0)
    high = np.full(n, 21.0)
    for i, p in [(5, 10.0), (15, 12.0), (25, 14.0)]:
        low[i] = p
        close[i] = p + 0.5
        high[i] = p + 1.0
    for i in [5, 15, 25]:
        for d in range(1, 3):
            low[i - d] = low[i] + 1.0
            low[i + d] = low[i] + 1.0
    idx = pd.date_range("2020-01-01", periods=n, freq="D")
    df = pd.DataFrame(
        {"open": close, "high": high, "low": low, "close": close,
         "volume": 1, "amount": 1},
        index=idx,
    )
    res = trendlines.find_trendlines(
        df, window=2, min_pct=0.0, tol=0.02, min_bars=5, top_k=3
    )
    assert res.best_up is not None
    assert res.best_up.touch_count >= 3
    assert res.best_up.side == "up"
    assert res.best_up.slope > 0


def test_declining_lows_are_not_up_trendlines():
    """下跌中的更低低点连线斜率向下，不能标成上升趋势线。"""
    n = 40
    close = np.linspace(20, 10, n)
    low = close - 0.5
    high = close + 0.5
    # 明确递减的低点
    for i, p in [(5, 18.0), (15, 14.0), (25, 10.0)]:
        low[i] = p
        for d in range(1, 3):
            low[i - d] = p + 1.0
            low[i + d] = p + 1.0
    idx = pd.date_range("2020-01-01", periods=n, freq="D")
    df = pd.DataFrame(
        {"open": close, "high": high, "low": low, "close": close,
         "volume": 1, "amount": 1},
        index=idx,
    )
    res = trendlines.find_trendlines(
        df, window=2, min_pct=0.0, tol=0.02, min_bars=5, top_k=5
    )
    assert res.best_up is None
    assert all(tl.slope > 0 for tl in res.up)


def test_point_outside_tol_not_counted():
    n = 30
    low = np.full(n, 15.0)
    high = np.full(n, 16.0)
    close = np.full(n, 15.5)
    low[5], low[15], low[25] = 10.0, 12.0, 20.0
    for i in [5, 15, 25]:
        for d in (1, 2):
            low[i - d] = low[i] + 1
            low[i + d] = low[i] + 1
    idx = pd.date_range("2020-01-01", periods=n, freq="D")
    df = pd.DataFrame(
        {"open": close, "high": high, "low": low, "close": close,
         "volume": 1, "amount": 1},
        index=idx,
    )
    res = trendlines.find_trendlines(
        df, window=2, min_pct=0.0, tol=0.01, min_bars=5, top_k=5
    )
    if res.best_up is not None:
        assert res.best_up.touch_count == 2 or idx[25] not in res.best_up.touch_dates


def test_evaluate_breakout_up_line():
    tl = Trendline(
        side="up", slope=0.0, intercept=100.0,
        touch_dates=[], touch_count=3, score=30.0,
        start_date=None, end_date=None,
    )
    result = TrendlineResult(up=[tl], down=[], best_up=tl, best_down=None)
    out = trendlines.evaluate_breakout(result, close_today=98.0, x_today=10, tol=0.015)
    assert out.best_up.status == "broken"
    out2 = trendlines.evaluate_breakout(result, close_today=100.0, x_today=10, tol=0.015)
    assert out2.best_up.status == "above"
