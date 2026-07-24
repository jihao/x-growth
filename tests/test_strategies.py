import numpy as np
import pandas as pd

from quant.backtest import strategies


def _df(prices):
    idx = pd.date_range("2020-01-01", periods=len(prices), freq="D")
    p = pd.Series(prices, index=idx, dtype=float)
    return pd.DataFrame(
        {"open": p, "high": p * 1.01, "low": p * 0.99, "close": p,
         "volume": 1000.0, "amount": p * 1000.0}
    )


def test_registry_has_five():
    assert set(["ma_cross", "macd", "bollinger", "rsi", "donchian"]).issubset(
        set(strategies.REGISTRY)
    )


def test_signals_are_binary_and_aligned():
    df = _df(np.concatenate([np.linspace(10, 20, 60), np.linspace(20, 10, 60)]))
    for name, strat in strategies.REGISTRY.items():
        sig = strat.generate(df, **strat.default_params)
        assert sig.index.equals(df.index), name
        assert set(np.unique(sig.dropna().values)).issubset({0.0, 1.0}), name


def test_ma_cross_goes_long_in_uptrend():
    df = _df(np.linspace(10, 30, 80))
    sig = strategies.get("ma_cross").generate(df, fast=5, slow=20)
    assert sig.iloc[-1] == 1.0


def test_bollinger_touch_lower_inclusive():
    # n=5,k=2: prices [10,10,10,10,9] -> mid=9.8, std=0.4, lower=9.0 == 最后收盘
    df = _df([10.0, 10.0, 10.0, 10.0, 9.0])
    sig = strategies.get("bollinger").generate(df, n=5, k=2.0)
    assert sig.iloc[-1] == 1.0  # close 恰好等于下轨 -> 买入（验证 <=）
