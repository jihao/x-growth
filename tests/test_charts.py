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


def test_kline_cn_colors_and_hover():
    """A 股习惯：红涨绿跌；hover 显示开盘/最高/最低/收盘。"""
    fig = plots.kline_chart(_df())
    candle = next(t for t in fig.data if t.type == "candlestick")
    assert candle.increasing.line.color == "#ef5350"
    assert candle.decreasing.line.color == "#26a69a"
    assert candle.hoverinfo == "text"
    assert candle.text is not None and len(candle.text) > 0
    sample = candle.text[0]
    for label in ("开盘", "最高", "最低", "收盘"):
        assert label in sample
    assert fig.layout.dragmode == "zoom"  # 默认 zoom 才能悬停出 tip
    assert fig.layout.hovermode == "x"


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


def test_kline_has_drawtools_and_timeline():
    fig = plots.kline_chart(_df())
    assert fig.layout.dragmode == "zoom"
    # 画线工具仍在 modebar，需要时点选
    assert "drawline" in (fig.layout.modebar.add or [])
    layout = fig.layout.to_plotly_json()
    any_slider = any(
        isinstance(v, dict) and v.get("rangeslider", {}).get("visible")
        for k, v in layout.items() if k.startswith("xaxis")
    )
    assert any_slider
    assert layout["xaxis"].get("rangeselector") is not None


def test_board_area_chart_returns_figure():
    idx = pd.date_range("2020-01-01", periods=5, freq="D")
    sdf = pd.DataFrame({
        "amt_sh_main": [1.0]*5, "amt_sz_main": [1.0]*5, "amt_sme": [1.0]*5,
        "amt_gem": [1.0]*5, "amt_star": [1.0]*5, "amt_bse": [1.0]*5,
    }, index=idx)
    assert isinstance(plots.board_area_chart(sdf), go.Figure)


def test_concentration_detail_chart_uses_cross_section_amount():
    # cross_df 是每股截面（load_cross_section），列为 ts_code/name/amount
    cross = pd.DataFrame({
        "ts_code": ["600000.SH", "000001.SZ"],
        "name": ["浦发银行", "平安银行"],
        "amount": [200.0, 100.0],
    })
    fig = plots.concentration_detail_chart(cross, top=10)
    assert isinstance(fig, go.Figure)
