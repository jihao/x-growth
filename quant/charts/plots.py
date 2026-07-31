"""Plotly 图表封装：K线/回测/集中度。"""
from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from quant.calendar.cn_holidays import load_holidays
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
            increasing=dict(line=dict(color="#ef5350"), fillcolor="#ef5350"),
            decreasing=dict(line=dict(color="#26a69a"), fillcolor="#26a69a"),
            # Candlestick 在部分 plotly 版本不支持 hovertemplate，用 text + hoverinfo
            text=[
                (
                    f"{idx.strftime('%Y-%m-%d')}<br>"
                    f"开盘: {o:.4f}<br>"
                    f"最高: {h:.4f}<br>"
                    f"最低: {lo:.4f}<br>"
                    f"收盘: {c:.4f}"
                )
                for idx, o, h, lo, c in zip(
                    df.index, df["open"], df["high"], df["low"], df["close"]
                )
            ],
            hoverinfo="text",
        ),
        row=1, col=1,
    )
    # 均线/布林带不抢 K 线 hover
    for ov in overlays:
        if ov.startswith("ma"):
            n = int(ov[2:])
            fig.add_trace(go.Scatter(
                x=df.index, y=ta.ma(df["close"], n),
                name=f"MA{n}", line=dict(width=1), hoverinfo="skip",
            ), row=1, col=1)
        elif ov == "boll":
            up, mid, low = ta.boll(df["close"])
            for y, nm in [(up, "BOLL上"), (mid, "BOLL中"), (low, "BOLL下")]:
                fig.add_trace(go.Scatter(
                    x=df.index, y=y, name=nm,
                    line=dict(width=1, dash="dot"), hoverinfo="skip",
                ), row=1, col=1)
    fig.add_trace(go.Bar(x=df.index, y=df["volume"], name="成交量",
                         hovertemplate="%{x|%Y-%m-%d}<br>成交量: %{y}<extra></extra>"),
                  row=2, col=1)

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
        height=800,
        # 默认 zoom，悬停才能出 tip；画线从右上角 modebar 点选
        dragmode="zoom",
        hovermode="x",
        newshape=dict(line_color="orange"),
        modebar_add=["drawline", "drawopenpath", "eraseshape"] if drawable else [],
        # 横向图例放到整图下方，避免叠在主图/副图上
        legend=dict(
            orientation="h",
            yanchor="top",
            y=-0.12,
            xanchor="left",
            x=0,
            bgcolor="rgba(255,255,255,0.8)",
        ),
        margin=dict(l=40, r=20, t=30, b=100),
    )
    # 上方子图关 rangeslider，仅最底部启用作为时间轴拖拽条；主图加区间选择按钮
    fig.update_xaxes(rangeslider_visible=False)
    fig.update_xaxes(rangeslider_visible=True, rangeslider_thickness=0.05, row=rows, col=1)
    fig.update_xaxes(
        rangeselector=dict(
            buttons=[
                dict(count=1, label="1M", step="month", stepmode="backward"),
                dict(count=3, label="3M", step="month", stepmode="backward"),
                dict(count=6, label="6M", step="month", stepmode="backward"),
                dict(count=1, label="YTD", step="year", stepmode="todate"),
                dict(count=1, label="1Y", step="year", stepmode="backward"),
                dict(step="all", label="ALL"),
            ]
        ),
        row=1, col=1,
    )
    # 隐藏周六/周日 + 法定放假日，避免 K 线自然日空白
    fig.update_xaxes(
        rangebreaks=[
            dict(bounds=["sat", "mon"]),  # 周六、周日
            dict(values=list(load_holidays())),
        ]
    )
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


def overlay_trendlines(fig, df, result):
    """在已有 K 线 Figure 上叠加自动趋势线与触点。"""
    pos = {d: i for i, d in enumerate(df.index)}

    def add_line(tl, color, name):
        if tl.start_date not in pos or tl.end_date not in pos:
            return
        i0, i1 = pos[tl.start_date], pos[tl.end_date]
        x0, x1 = df.index[i0], df.index[i1]
        y0, y1 = tl.price_at(i0), tl.price_at(i1)
        fig.add_trace(
            go.Scatter(
                x=[x0, x1], y=[y0, y1], mode="lines",
                name=name, line=dict(color=color, width=2),
                hoverinfo="skip",
            ),
            row=1, col=1,
        )
        touch_x = [d for d in tl.touch_dates if d in pos]
        touch_y = [tl.price_at(pos[d]) for d in touch_x]
        if touch_x:
            fig.add_trace(
                go.Scatter(
                    x=touch_x, y=touch_y, mode="markers",
                    name=f"{name}触点",
                    marker=dict(color=color, size=8, symbol="circle-open"),
                    hovertemplate="%{x|%Y-%m-%d}<br>触点: %{y:.4f}<extra></extra>",
                ),
                row=1, col=1,
            )

    for i, tl in enumerate(result.up):
        add_line(tl, "#e57373", f"上升趋势{i + 1}")
    for i, tl in enumerate(result.down):
        add_line(tl, "#4db6ac", f"下降趋势{i + 1}")
    return fig


def overlay_waves(fig, df, triple):
    """叠加 N 字三浪拐点与连线。"""
    color = "#e57373" if triple.direction == "up" else "#4db6ac"
    xs = [p[0] for p in triple.pivots]
    ys = [p[1] for p in triple.pivots]
    labels = ["浪1起", "浪1终", "浪2终", "浪3终"]
    fig.add_trace(
        go.Scatter(
            x=xs, y=ys, mode="lines+markers+text",
            name="浪型",
            line=dict(color=color, width=2, dash="dash"),
            marker=dict(size=9, color=color),
            text=labels, textposition="top center",
            hovertemplate="%{x|%Y-%m-%d}<br>%{text}: %{y:.4f}<extra></extra>",
        ),
        row=1, col=1,
    )
    return fig


def overlay_divergence(fig, df, events):
    """叠加 DIF 背离两触点连线（价位）。"""
    for i, ev in enumerate(events):
        color = "#ef5350" if ev.side == "top" else "#26a69a"
        dash = "dot" if ev.status == "pending" else "solid"
        side_cn = "顶" if ev.side == "top" else "底"
        st_cn = "钝化" if ev.status == "pending" else "确认"
        fig.add_trace(
            go.Scatter(
                x=[ev.p1_date, ev.p2_date],
                y=[ev.p1_price, ev.p2_price],
                mode="lines+markers",
                name=f"{side_cn}背离·{st_cn}",
                line=dict(color=color, width=2, dash=dash),
                marker=dict(size=8, color=color),
                hovertemplate=(
                    f"{side_cn}背离({st_cn})<br>"
                    "%{x|%Y-%m-%d}: %{y:.4f}<extra></extra>"
                ),
                legendgroup=f"div-{ev.side}-{i}",
                showlegend=True,
            ),
            row=1,
            col=1,
        )
    return fig
