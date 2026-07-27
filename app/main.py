"""量化分析系统 Streamlit 界面。运行: .venv/bin/streamlit run app/main.py"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd
import streamlit as st

from quant.data import loader
from quant.concentration import cache
from quant.backtest import engine, metrics, strategies
from quant.charts import plots

st.set_page_config(page_title="量化分析系统", layout="wide")


@st.cache_data(ttl=600)
def _stocks():
    return loader.list_stocks()


@st.cache_data(ttl=600)
def _daily(ts_code, start, end):
    return loader.load_daily(ts_code, start, end)


def _safe_daily(ts_code, start, end):
    try:
        return _daily(ts_code, start, end)
    except Exception as exc:  # DB 失败友好提示
        st.error(f"读取日线数据失败：{exc}")
        st.stop()


st.title("量化交易分析系统")

with st.sidebar:
    st.header("参数")
    try:
        stocks = _stocks()
        options = (stocks["ts_code"] + "  " + stocks["name"].fillna("")).tolist()
    except Exception as exc:  # 连库失败友好提示
        st.error(f"无法连接 MySQL，请检查 database/mysql/mysql.env：{exc}")
        st.stop()
    if stocks.empty or not options:
        st.error("股票列表为空，请检查数据库。")
        st.stop()
    picked = st.selectbox("股票", options)
    ts_code = picked.split("  ")[0]
    _default_start = pd.Timestamp.today() - pd.DateOffset(months=6)
    start = st.date_input("开始", _default_start).strftime("%Y%m%d")
    end = st.date_input("结束", pd.Timestamp.today()).strftime("%Y%m%d")

tab1, tab2, tab3 = st.tabs(["行情分析", "资金集中度", "策略回测"])

with tab1:
    df = _safe_daily(ts_code, start, end)
    if df.empty:
        st.warning("该区间无数据。")
    else:
        overlays = st.multiselect("叠加", ["ma5", "ma10", "ma20", "ma60", "boll"],
                                  default=["ma5", "ma20", "boll"])
        sub = st.multiselect("副图", ["macd", "rsi"], default=["macd", "rsi"])
        period = st.selectbox("周期", ["日线", "周线（即将支持）"])
        if period.startswith("周线"):
            st.caption("周线趋势线即将支持；以下仍按日线计算。")

        auto_tl = st.checkbox("自动趋势线", value=True)
        with st.expander("趋势线参数", expanded=False):
            st.markdown(
                """
**起点 / 终点怎么定？**

1. 先用 `window` 在日线 `high`/`low` 上找波段高低点（左右各确认若干根 K 线）。
2. **上升趋势线**：在波段**低点**里任取两点连线，且斜率必须为正；  
   **下降趋势线**：在波段**高点**里任取两点连线，且斜率必须为负。
3. 明细表里的 **起点 / 终点** = 这条线用来定直线的那两个波段点（按时间早晚排序），图上线段也画在这两点之间。
4. **触点** = 落在该直线容差 `tol` 内的其它波段点（含起终点），触点越多得分越高；`min_bars` 限制两点至少隔多少根 K 线；`top_k` 为上升/下降各保留几条。
                """.strip()
            )
            tl_window = st.number_input("window", min_value=2, max_value=20, value=5, step=1)
            tl_tol = st.number_input("tol", min_value=0.001, max_value=0.1, value=0.015, format="%.3f")
            tl_top_k = st.number_input("top_k", min_value=1, max_value=10, value=3, step=1)
            tl_min_bars = st.number_input("min_bars", min_value=3, max_value=60, value=10, step=1)

        fig = plots.kline_chart(df, tuple(overlays), tuple(sub))
        detail_rows = []
        if auto_tl:
            from quant.structure.trendlines import find_trendlines, evaluate_breakout

            res = find_trendlines(
                df,
                window=int(tl_window),
                tol=float(tl_tol),
                top_k=int(tl_top_k),
                min_bars=int(tl_min_bars),
            )
            if res.best_up is None and res.best_down is None:
                st.info("区间内有效波段点不足，无法拟合趋势线。")
            else:
                x_today = len(df) - 1
                res = evaluate_breakout(
                    res, float(df["close"].iloc[-1]), x_today, tol=float(tl_tol)
                )
                fig = plots.overlay_trendlines(fig, df, res)
                msgs = []
                if res.best_up and res.best_up.status == "broken":
                    msgs.append("上升趋势线已破位")
                if res.best_down and res.best_down.status == "broken":
                    msgs.append("下降趋势线已升破")
                if msgs:
                    st.warning("；".join(msgs))
                for tl in res.up + res.down:
                    detail_rows.append({
                        "方向": "上升" if tl.side == "up" else "下降",
                        "触点数": tl.touch_count,
                        "得分": round(tl.score, 2),
                        "起点": str(tl.start_date)[:10],
                        "终点": str(tl.end_date)[:10],
                        "状态": tl.status or "",
                        "触点日": ", ".join(str(d)[:10] for d in tl.touch_dates),
                    })
        auto_wave = st.checkbox("浪型速度", value=True)
        with st.expander("浪型参数", expanded=False):
            st.markdown(
                """
**浪型速度怎么算？**

1. 用波段高低点串成拐点，切出 N 字三浪（上涨 L-H-L-H / 下跌 H-L-H-L）。
2. 单浪速度 = |价格变化| / 根数；比较**第三浪 vs 第一浪**。
3. 第三浪更快 → 倾向仍有第五浪；更慢 → 倾向止于三浪。
4. 「再前一段」查看时间上更早的一段已确认三浪。
                """.strip()
            )
            w_window = st.number_input("wave_window", min_value=2, max_value=20, value=5, step=1)
            w_min_pct = st.number_input("min_pct", min_value=0.0, max_value=0.1, value=0.01, format="%.3f", step=0.005)
            w_fast = st.number_input("fast_ratio", min_value=1.0, max_value=2.0, value=1.05, format="%.2f")
            w_slow = st.number_input("slow_ratio", min_value=0.5, max_value=1.0, value=0.95, format="%.2f")
            wave_seg = st.selectbox("浪型段", ["最近一段", "再前一段"])

        wave_rows = []
        if auto_wave:
            from quant.structure.waves import analyze_wave_speed

            wave_offset = 0 if wave_seg == "最近一段" else 1
            wres = analyze_wave_speed(
                df,
                offset=wave_offset,
                window=int(w_window),
                min_pct=float(w_min_pct),
                fast_ratio=float(w_fast),
                slow_ratio=float(w_slow),
            )
            if wres.current is None:
                if wave_offset == 1:
                    st.info("没有更早的一段已确认三浪。")
                else:
                    st.info("区间内有效三浪不足，无法做浪型速度分析。")
            else:
                t = wres.current
                fig = plots.overlay_waves(fig, df, t)
                verdict_cn = {
                    "extend": "倾向仍有第五浪",
                    "end": "倾向止于三浪",
                    "similar": "速度接近，需结合更大周期",
                }[t.verdict]
                dir_cn = "上涨" if t.direction == "up" else "下跌"
                st.info(
                    f"{dir_cn}三浪 · 第三浪/第一浪速度比={t.ratio:.2f} → {verdict_cn}"
                )
                for i, leg in enumerate(t.legs, 1):
                    wave_rows.append({
                        "浪": i,
                        "起点": str(leg.start_date)[:10],
                        "终点": str(leg.end_date)[:10],
                        "根数": leg.bars,
                        "速度": round(leg.speed, 4),
                        "涨跌幅": f"{leg.ret:.2%}",
                    })
                wave_rows.append({
                    "浪": "结论",
                    "起点": "", "终点": "", "根数": "",
                    "速度": round(t.ratio, 4),
                    "涨跌幅": verdict_cn,
                })
        st.plotly_chart(fig, width="stretch")
        if detail_rows:
            with st.expander("趋势线明细", expanded=True):
                st.dataframe(pd.DataFrame(detail_rows), width="stretch")
        if wave_rows:
            with st.expander("浪型明细", expanded=True):
                st.dataframe(pd.DataFrame(wave_rows), width="stretch")

with tab2:
    st.subheader("市场资金集中度（历史）")
    try:
        sdf = cache.read_series(start, end)
    except Exception as exc:
        st.error(f"读取集中度缓存失败：{exc}")
        sdf = pd.DataFrame()
    if sdf.empty:
        st.info("集中度缓存为空，请先运行：.venv/bin/python -m quant.concentration.build_cache --rebuild")
    else:
        metric = st.selectbox("指标", ["hhi", "gini", "cr5", "cr10", "cr20", "cr50", "cr100"])
        st.plotly_chart(plots.concentration_chart(sdf, metric), width="stretch")
        st.plotly_chart(plots.board_area_chart(sdf), width="stretch")
        detail_date = st.date_input("查看某日明细", pd.Timestamp(sdf.index[-1]))
        try:
            cross = loader.load_cross_section(detail_date.strftime("%Y%m%d"))
        except Exception as exc:
            st.error(f"读取截面数据失败：{exc}")
            cross = pd.DataFrame()
        if not cross.empty:
            st.plotly_chart(plots.concentration_detail_chart(cross), width="stretch")

with tab3:
    st.subheader("策略回测")
    strat_name = st.selectbox("策略", list(strategies.REGISTRY),
                              format_func=lambda k: strategies.get(k).label)
    strat = strategies.get(strat_name)
    params = {}
    cols = st.columns(max(len(strat.default_params), 1))
    for (k, v), c in zip(strat.default_params.items(), cols):
        if isinstance(v, bool):
            params[k] = c.checkbox(k, value=v)
        elif isinstance(v, int):
            params[k] = int(c.number_input(k, value=int(v), step=1))
        else:
            params[k] = float(c.number_input(k, value=float(v)))
    cost = st.number_input("单边手续费率", value=0.0003, format="%.4f")
    if st.button("运行回测"):
        df = _safe_daily(ts_code, start, end)
        if df.empty:
            st.warning("该区间无数据。")
        else:
            sig = strat.generate(df, **params)
            res = engine.run(df, sig, cost=cost)
            perf = metrics.performance(res)
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("总收益", f"{perf['total_return']:.2%}")
            c2.metric("年化", f"{perf['ann_return']:.2%}")
            c3.metric("夏普", f"{perf['sharpe']:.2f}")
            c4.metric("最大回撤", f"{perf['max_drawdown']:.2%}")
            c5, c6, c7, c8 = st.columns(4)
            c5.metric("胜率", f"{perf['win_rate']:.2%}")
            c6.metric("盈亏比", f"{perf['profit_factor']:.2f}")
            c7.metric("交易次数", perf["num_trades"])
            c8.metric("基准收益", f"{perf['bench_total_return']:.2%}")
            st.plotly_chart(plots.backtest_chart(res), width="stretch")
