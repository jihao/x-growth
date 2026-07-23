"""Plotly 图表封装：K线/回测/集中度。"""
from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from quant.indicators import ta

_BOARD_LABELS = {
    "amt_sh_main": "沪主板", "amt_sz_main": "深主板", "amt_sme": "中小板",
    "amt_gem": "创业板", "amt_star": "科创板", "amt_bse": "北交所",
}


def kline_chart(df, overlays=("ma5", "ma20", "boll"), sub=("macd", "rsi"), drawable=True):
    rows = 1 + 1 + len(sub)  # 主图 + 量 + 各副图
    heights = [0.5, 0.15] + [0.35 / max(len(sub), 1)] * len(sub)
    fig = make_subplots(
        rows=rows, cols=1, shared_xaxes=True, vertical_spacing=0.02,
        row_heights=heights,
    )
    fig.add_trace(
        go.Candlestick(
            x=df.index, open=df["open"], high=df["high"], low=df["low"],
            close=df["close"], name="K线",
        ),
        row=1, col=1,
    )
    for ov in overlays:
        if ov.startswith("ma"):
            n = int(ov[2:])
            fig.add_trace(go.Scatter(x=df.index, y=ta.ma(df["close"], n),
                                     name=f"MA{n}", line=dict(width=1)), row=1, col=1)
        elif ov == "boll":
            up, mid, low = ta.boll(df["close"])
            for y, nm in [(up, "BOLL上"), (mid, "BOLL中"), (low, "BOLL下")]:
                fig.add_trace(go.Scatter(x=df.index, y=y, name=nm,
                                         line=dict(width=1, dash="dot")), row=1, col=1)
    fig.add_trace(go.Bar(x=df.index, y=df["volume"], name="成交量"), row=2, col=1)

    r = 3
    for name in sub:
        if name == "macd":
            dif, dea, hist = ta.macd(df["close"])
            fig.add_trace(go.Scatter(x=df.index, y=dif, name="DIF"), row=r, col=1)
            fig.add_trace(go.Scatter(x=df.index, y=dea, name="DEA"), row=r, col=1)
            fig.add_trace(go.Bar(x=df.index, y=hist, name="MACD"), row=r, col=1)
        elif name == "rsi":
            fig.add_trace(go.Scatter(x=df.index, y=ta.rsi(df["close"]), name="RSI"),
                          row=r, col=1)
        r += 1

    fig.update_layout(
        height=800, xaxis_rangeslider_visible=False,
        dragmode="drawline" if drawable else "zoom",
        newshape=dict(line_color="orange"),
        modebar_add=["drawline", "drawopenpath", "eraseshape"] if drawable else [],
        legend=dict(orientation="h"),
        margin=dict(l=40, r=20, t=30, b=20),
    )
    fig.update_xaxes(rangeslider_visible=False)
    return fig


def backtest_chart(result):
    fig = make_subplots(
        rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.05,
        row_heights=[0.7, 0.3],
    )
    eq = result.equity
    fig.add_trace(go.Scatter(x=eq.index, y=eq, name="策略净值"), row=1, col=1)
    fig.add_trace(go.Scatter(x=result.benchmark.index, y=result.benchmark,
                             name="买入持有", line=dict(dash="dot")), row=1, col=1)
    for t in result.trades:
        fig.add_trace(go.Scatter(x=[t["entry"]], y=[eq.loc[t["entry"]]], mode="markers",
                                 marker=dict(symbol="triangle-up", color="red", size=10),
                                 showlegend=False), row=1, col=1)
        fig.add_trace(go.Scatter(x=[t["exit"]], y=[eq.loc[t["exit"]]], mode="markers",
                                 marker=dict(symbol="triangle-down", color="green", size=10),
                                 showlegend=False), row=1, col=1)
    dd = eq / eq.cummax() - 1
    fig.add_trace(go.Scatter(x=dd.index, y=dd, name="回撤", fill="tozeroy",
                             line=dict(color="rgba(200,0,0,0.5)")), row=2, col=1)
    fig.update_layout(height=600, legend=dict(orientation="h"),
                      margin=dict(l=40, r=20, t=30, b=20))
    return fig


def concentration_chart(series_df, metric="hhi"):
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=series_df.index, y=series_df[metric], name=metric))
    fig.update_layout(height=400, title=f"市场资金集中度：{metric}",
                      margin=dict(l=40, r=20, t=40, b=20))
    return fig


def board_area_chart(series_df):
    fig = go.Figure()
    cols = [c for c in _BOARD_LABELS if c in series_df.columns]
    total = series_df[cols].sum(axis=1).replace(0, pd.NA)
    for c in cols:
        share = series_df[c] / total
        fig.add_trace(go.Scatter(x=series_df.index, y=share, name=_BOARD_LABELS[c],
                                 stackgroup="one"))
    fig.update_layout(height=400, title="各板块成交额占比",
                      yaxis_tickformat=".0%", margin=dict(l=40, r=20, t=40, b=20))
    return fig


def concentration_detail_chart(cross_df, top=20):
    d = cross_df.sort_values("amount", ascending=False).head(top)
    label = d["name"].fillna(d["ts_code"]) if "name" in d else d["ts_code"]
    fig = go.Figure(go.Bar(x=d["amount"], y=label, orientation="h"))
    fig.update_layout(height=500, title=f"成交额前 {top} 名",
                      yaxis=dict(autorange="reversed"), margin=dict(l=120, r=20, t=40, b=20))
    return fig
