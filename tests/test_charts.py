import numpy as np
import pandas as pd
import plotly.graph_objects as go

from quant.charts import plots
from quant.backtest import engine


def _df(n=60):
    idx = pd.date_range("2020-01-01", periods=n, freq="D")
    p = pd.Series(np.linspace(10, 20, n), index=idx)
    return pd.DataFrame(
        {"open": p, "high": p * 1.02, "low": p * 0.98, "close": p,
         "volume": 1000.0, "amount": p * 1000.0}
    )


def test_kline_returns_figure():
    fig = plots.kline_chart(_df())
    assert isinstance(fig, go.Figure)
    assert len(fig.data) >= 1


def test_backtest_chart():
    df = _df()
    sig = pd.Series(1.0, index=df.index)
    res = engine.run(df, sig, cost=0.0)
    fig = plots.backtest_chart(res)
    assert isinstance(fig, go.Figure)


def test_concentration_chart():
    idx = pd.date_range("2020-01-01", periods=10, freq="D")
    sdf = pd.DataFrame({"hhi": np.linspace(0.1, 0.2, 10)}, index=idx)
    fig = plots.concentration_chart(sdf, metric="hhi")
    assert isinstance(fig, go.Figure)
