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

# 深色 / 浅色行情主题（跟随 Streamlit 右上角主题切换）
_THEMES: dict[str, dict[str, str]] = {
    "dark": dict(
        bg="#0b0e14",
        grid="rgba(255,255,255,0.06)",
        text="#9aa3b2",
        text_bright="#e8eaed",
        up="#ef5350",
        down="#26a69a",
        dif="#FFD54F",
        dea="#42A5F5",
        selector_bg="#161b26",
        selector_active="#2a3142",
        selector_border="#2e3648",
        spike="rgba(255,255,255,0.35)",
        hover_bg="#161b26",
        hover_border="#2e3648",
        legend_bg="rgba(11,14,20,0)",
        slider_bg="#161b26",
        slider_border="#2e3648",
    ),
    "light": dict(
        bg="#ffffff",
        grid="rgba(0,0,0,0.06)",
        text="#5f6368",
        text_bright="#202124",
        up="#ef5350",
        down="#26a69a",
        dif="#F9A825",
        dea="#1565C0",
        selector_bg="#f1f3f4",
        selector_active="#e8eaed",
        selector_border="#dadce0",
        spike="rgba(0,0,0,0.25)",
        hover_bg="#ffffff",
        hover_border="#dadce0",
        legend_bg="rgba(255,255,255,0)",
        slider_bg="#f8f9fa",
        slider_border="#dadce0",
    ),
}
_MA_COLORS: dict[str, dict[int, str]] = {
    "dark": {5: "#FFD54F", 10: "#42A5F5", 20: "#CE93D8", 60: "#26C6DA"},
    "light": {5: "#F57C00", 10: "#1976D2", 20: "#8E24AA", 60: "#00838F"},
}
_RANGE_BUTTONS = [
    dict(count=3, label="3M", step="month", stepmode="backward"),
    dict(count=6, label="6M", step="month", stepmode="backward"),
    dict(count=1, label="1Y", step="year", stepmode="backward"),
    dict(count=3, label="3Y", step="year", stepmode="backward"),
    dict(step="all", label="全部"),
]


def chart_theme(theme_type: str = "dark") -> dict[str, str]:
    """返回 K 线配色；theme_type 为 light 或 dark。"""
    return _THEMES.get(theme_type, _THEMES["dark"])


def _vol_colors(df: pd.DataFrame, theme: dict[str, str]) -> list[str]:
    return [
        theme["up"] if c >= o else theme["down"]
        for o, c in zip(df["open"], df["close"])
    ]


def _hist_colors(hist: pd.Series, theme: dict[str, str]) -> list[str]:
    return [theme["up"] if v >= 0 else theme["down"] for v in hist.fillna(0)]


def _apply_kline_theme(fig: go.Figure, rows: int, theme: dict[str, str]) -> None:
    """统一网格、Y 轴居右、十字光标。"""
    spike = dict(
        showspikes=True,
        spikemode="across",
        spikesnap="cursor",
        spikecolor=theme["spike"],
        spikethickness=1,
        spikedash="dash",
    )
    for i in range(1, rows + 1):
        fig.update_yaxes(
            row=i, col=1,
            side="right",
            gridcolor=theme["grid"],
            zerolinecolor=theme["grid"],
            tickfont=dict(color=theme["text"], size=11),
            title_font=dict(color=theme["text"]),
        )
        fig.update_xaxes(
            row=i, col=1,
            gridcolor=theme["grid"],
            tickfont=dict(color=theme["text"], size=10),
            **spike,
        )
    fig.update_xaxes(showticklabels=True, row=rows, col=1)
    for i in range(1, rows):
        fig.update_xaxes(showticklabels=False, row=i, col=1)


def quote_header_html(
    df: pd.DataFrame,
    ts_code: str,
    name: str = "",
    theme_type: str = "dark",
) -> str:
    """生成与 K 线主题一致的行情头部 HTML。"""
    if df.empty:
        return ""
    theme = chart_theme(theme_type)
    last = df.iloc[-1]
    prev_close = float(df["close"].iloc[-2]) if len(df) > 1 else float(last["close"])
    close = float(last["close"])
    chg = close - prev_close
    pct = chg / prev_close * 100 if prev_close else 0.0
    color = theme["up"] if chg >= 0 else theme["down"]
    sign = "+" if chg >= 0 else ""
    title = f"{name} " if name else ""
    date_str = df.index[-1].strftime("%Y/%m/%d")
    amount = last.get("amount")
    amount_str = (
        f"{amount / 1e8:.2f}亿" if pd.notna(amount) and amount >= 1e8
        else (f"{amount / 1e4:.0f}万" if pd.notna(amount) else "—")
    )
    return f"""
<div style="
  background:{theme['bg']};
  border:1px solid {theme['selector_border']};
  border-radius:8px;
  padding:14px 18px;
  margin-bottom:6px;
  font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
">
  <div style="display:flex;align-items:flex-start;justify-content:space-between;flex-wrap:wrap;gap:12px;">
    <div>
      <div style="color:{theme['text_bright']};font-size:18px;font-weight:600;">
        {title}<span style="color:{theme['text']};font-size:13px;font-weight:400;margin-left:8px;">{ts_code}</span>
      </div>
      <div style="margin-top:6px;">
        <span style="color:{color};font-size:28px;font-weight:700;">{close:.2f}</span>
        <span style="color:{color};font-size:15px;margin-left:12px;">{sign}{chg:.2f}</span>
        <span style="color:{color};font-size:15px;margin-left:6px;">{sign}{pct:.2f}%</span>
      </div>
      <div style="color:{theme['text']};font-size:12px;margin-top:4px;">截至 {date_str} 收盘</div>
    </div>
    <div style="display:flex;gap:24px;color:{theme['text']};font-size:12px;align-self:center;">
      <div>今开<br><span style="color:{theme['text_bright']};font-size:14px;">{float(last['open']):.2f}</span></div>
      <div>最高<br><span style="color:{theme['up']};font-size:14px;">{float(last['high']):.2f}</span></div>
      <div>最低<br><span style="color:{theme['down']};font-size:14px;">{float(last['low']):.2f}</span></div>
      <div>成交额<br><span style="color:{theme['text_bright']};font-size:14px;">{amount_str}</span></div>
    </div>
  </div>
</div>
"""


def kline_chart(
    df,
    overlays=("ma5", "ma20", "boll"),
    sub=("macd", "rsi"),
    drawable=True,
    theme_type: str = "dark",
):
    theme = chart_theme(theme_type)
    ma_colors = _MA_COLORS.get(theme_type, _MA_COLORS["dark"])
    rows = 1 + 1 + len(sub)  # 主图 + 量 + 各副图
    heights = [0.52, 0.14] + [0.34 / max(len(sub), 1)] * len(sub)
    fig = make_subplots(
        rows=rows, cols=1, shared_xaxes=True, vertical_spacing=0.015,
        row_heights=heights,
    )
    fig.add_trace(
        go.Candlestick(
            x=df.index, open=df["open"], high=df["high"], low=df["low"],
            close=df["close"], name="K线",
            increasing=dict(line=dict(color=theme["up"], width=1), fillcolor=theme["up"]),
            decreasing=dict(line=dict(color=theme["down"], width=1), fillcolor=theme["down"]),
            text=[
                (
                    f"{idx.strftime('%Y-%m-%d')}<br>"
                    f"开盘: {o:.2f}<br>"
                    f"最高: {h:.2f}<br>"
                    f"最低: {lo:.2f}<br>"
                    f"收盘: {c:.2f}"
                )
                for idx, o, h, lo, c in zip(
                    df.index, df["open"], df["high"], df["low"], df["close"]
                )
            ],
            hoverinfo="text",
        ),
        row=1, col=1,
    )
    for ov in overlays:
        if ov.startswith("ma"):
            n = int(ov[2:])
            color = ma_colors.get(n, theme["text"])
            fig.add_trace(go.Scatter(
                x=df.index, y=ta.ma(df["close"], n),
                name=f"MA{n}",
                line=dict(width=1.2, color=color),
                hovertemplate=f"MA{n}: %{{y:.2f}}<extra></extra>",
            ), row=1, col=1)
        elif ov == "boll":
            up, mid, low = ta.boll(df["close"])
            for y, nm, c in [
                (up, "BOLL上", "#78909C"),
                (mid, "BOLL中", "#90A4AE"),
                (low, "BOLL下", "#78909C"),
            ]:
                fig.add_trace(go.Scatter(
                    x=df.index, y=y, name=nm,
                    line=dict(width=1, dash="dot", color=c),
                    hovertemplate=f"{nm}: %{{y:.2f}}<extra></extra>",
                ), row=1, col=1)
    fig.add_trace(
        go.Bar(
            x=df.index, y=df["volume"], name="成交量",
            marker_color=_vol_colors(df, theme),
            hovertemplate="%{x|%Y-%m-%d}<br>成交量: %{y:,.0f}<extra></extra>",
        ),
        row=2, col=1,
    )

    r = 3
    for name in sub:
        if name == "macd":
            dif, dea, hist = ta.macd(df["close"])
            fig.add_trace(go.Scatter(
                x=df.index, y=dif, name="DIF",
                line=dict(width=1.2, color=theme["dif"]),
                hovertemplate="DIF: %{y:.4f}<extra></extra>",
            ), row=r, col=1)
            fig.add_trace(go.Scatter(
                x=df.index, y=dea, name="DEA",
                line=dict(width=1.2, color=theme["dea"]),
                hovertemplate="DEA: %{y:.4f}<extra></extra>",
            ), row=r, col=1)
            fig.add_trace(go.Bar(
                x=df.index, y=hist, name="MACD",
                marker_color=_hist_colors(hist, theme),
                hovertemplate="MACD: %{y:.4f}<extra></extra>",
            ), row=r, col=1)
        elif name == "rsi":
            rsi_vals = ta.rsi(df["close"])
            fig.add_trace(go.Scatter(
                x=df.index, y=rsi_vals, name="RSI",
                line=dict(width=1.2, color="#AB47BC"),
                hovertemplate="RSI: %{y:.2f}<extra></extra>",
            ), row=r, col=1)
            fig.add_hline(y=70, line=dict(color="rgba(239,83,80,0.4)", width=1, dash="dot"), row=r, col=1)
            fig.add_hline(y=30, line=dict(color="rgba(38,166,154,0.4)", width=1, dash="dot"), row=r, col=1)
        r += 1

    fig.update_layout(
        height=820,
        dragmode="zoom",
        hovermode="x unified",
        paper_bgcolor=theme["bg"],
        plot_bgcolor=theme["bg"],
        font=dict(color=theme["text"], size=11),
        newshape=dict(line_color="#FF9800"),
        modebar_add=["drawline", "drawopenpath", "eraseshape"] if drawable else [],
        # 图例放整图下方，避免与顶部区间按钮 / modebar 重叠
        legend=dict(
            orientation="h",
            yanchor="top",
            y=-0.10,
            xanchor="left",
            x=0,
            bgcolor=theme["legend_bg"],
            font=dict(color=theme["text"], size=10),
        ),
        margin=dict(l=8, r=56, t=48, b=88),
        hoverlabel=dict(
            bgcolor=theme["hover_bg"],
            bordercolor=theme["hover_border"],
            font=dict(color=theme["text_bright"], size=11),
        ),
    )
    _apply_kline_theme(fig, rows, theme)

    fig.update_xaxes(rangeslider_visible=False)
    fig.update_xaxes(
        rangeslider_visible=True,
        rangeslider_thickness=0.04,
        rangeslider=dict(bgcolor=theme["slider_bg"], bordercolor=theme["slider_border"]),
        row=rows, col=1,
    )
    # 区间按钮靠左上，与右上角 modebar 错开
    fig.update_xaxes(
        rangeselector=dict(
            buttons=_RANGE_BUTTONS,
            bgcolor=theme["selector_bg"],
            activecolor=theme["selector_active"],
            bordercolor=theme["selector_border"],
            font=dict(color=theme["text"], size=11),
            x=0, y=1.02, xanchor="left",
        ),
        row=1, col=1,
    )
    fig.update_xaxes(
        rangebreaks=[
            dict(bounds=["sat", "mon"]),
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
