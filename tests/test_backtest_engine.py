import numpy as np
import pandas as pd

from quant.backtest import engine


def _df(prices):
    idx = pd.date_range("2020-01-01", periods=len(prices), freq="D")
    return pd.DataFrame({"close": prices}, index=idx, dtype=float)


def test_no_lookahead_shift():
    # 价格 100->110->121（每日+10%）。信号在 t=0 给出买入，应在 t=1 才吃到收益。
    df = _df([100, 110, 121])
    sig = pd.Series([1, 1, 0], index=df.index, dtype=float)
    res = engine.run(df, sig, cost=0.0)
    # t=0 无持仓（position 由 shift 得来），t=1 持仓吃到 +10%
    assert res.position.iloc[0] == 0
    assert res.position.iloc[1] == 1
    assert abs(res.strat_ret.iloc[1] - 0.10) < 1e-9
    assert abs(res.equity.iloc[1] - 1.10) < 1e-9


def test_cost_applied_on_change():
    df = _df([100, 100, 100])
    sig = pd.Series([1, 1, 1], index=df.index, dtype=float)
    res = engine.run(df, sig, cost=0.001)
    # t=1 建仓（position 0->1）扣一次手续费
    assert res.strat_ret.iloc[1] < 0
    assert abs(res.strat_ret.iloc[1] + 0.001) < 1e-9


def test_benchmark_buyhold():
    df = _df([100, 110, 121])
    sig = pd.Series([0, 0, 0], index=df.index, dtype=float)
    res = engine.run(df, sig, cost=0.0)
    assert abs(res.benchmark.iloc[-1] - 1.21) < 1e-9
