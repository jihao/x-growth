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


def test_trade_prices_match_equity():
    df = _df([100, 110, 121, 110])
    sig = pd.Series([1, 1, 0, 0], index=df.index, dtype=float)
    res = engine.run(df, sig, cost=0.0)
    assert len(res.trades) == 1
    t = res.trades[0]
    assert t["entry_px"] == 100.0
    assert t["exit_px"] == 121.0
    assert abs(t["ret"] - 0.21) < 1e-9
    assert abs((res.equity.iloc[-1] - 1) - t["ret"]) < 1e-9


def test_open_position_closed_at_end():
    df = _df([100, 110, 121])
    sig = pd.Series([1, 1, 1], index=df.index, dtype=float)
    res = engine.run(df, sig, cost=0.0)
    assert len(res.trades) == 1
    t = res.trades[0]
    assert t["entry_px"] == 100.0
    assert t["exit_px"] == 121.0
    assert abs(t["ret"] - 0.21) < 1e-9


def test_run_requires_close_column():
    idx = pd.date_range("2020-01-01", periods=2, freq="D")
    df = pd.DataFrame({"open": [100.0, 101.0]}, index=idx)
    sig = pd.Series([1, 0], index=idx, dtype=float)
    try:
        engine.run(df, sig)
        assert False, "expected ValueError"
    except ValueError as e:
        assert "close" in str(e)


def test_slippage_adds_cost():
    df = _df([100, 100, 100])
    sig = pd.Series([1, 1, 1], index=df.index, dtype=float)
    res = engine.run(df, sig, cost=0.0, slippage=0.002)
    assert abs(res.strat_ret.iloc[1] + 0.002) < 1e-9
