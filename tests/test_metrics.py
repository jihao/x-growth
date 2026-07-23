import numpy as np
import pandas as pd

from quant.backtest import engine, metrics


def test_performance_basic():
    idx = pd.date_range("2020-01-01", periods=4, freq="D")
    df = pd.DataFrame({"close": [100, 110, 121, 133.1]}, index=idx, dtype=float)
    sig = pd.Series([1, 1, 1, 1], index=idx, dtype=float)
    res = engine.run(df, sig, cost=0.0)
    perf = metrics.performance(res)
    assert perf["total_return"] > 0
    assert perf["max_drawdown"] <= 0
    assert "sharpe" in perf and "num_trades" in perf


def test_ann_vol_sharpe_zero_when_single_return():
    idx = pd.date_range("2020-01-01", periods=1, freq="D")
    res = engine.BacktestResult(
        equity=pd.Series([1.0], index=idx),
        position=pd.Series([0.0], index=idx),
        strat_ret=pd.Series([0.0], index=idx),
        benchmark=pd.Series([1.0], index=idx),
        trades=[],
    )
    perf = metrics.performance(res)
    assert perf["ann_vol"] == 0.0
    assert perf["sharpe"] == 0.0
    assert not np.isnan(perf["ann_vol"])


def test_max_drawdown():
    idx = pd.date_range("2020-01-01", periods=3, freq="D")
    # 净值 1 -> 1.2 -> 0.9，最大回撤 = 0.9/1.2 - 1 = -0.25
    res = engine.BacktestResult(
        equity=pd.Series([1.0, 1.2, 0.9], index=idx),
        position=pd.Series([1, 1, 1], index=idx),
        strat_ret=pd.Series([0.0, 0.2, -0.25], index=idx),
        benchmark=pd.Series([1.0, 1.0, 1.0], index=idx),
        trades=[],
    )
    perf = metrics.performance(res)
    assert abs(perf["max_drawdown"] + 0.25) < 1e-9
