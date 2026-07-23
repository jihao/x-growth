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
    start = st.date_input("开始", pd.Timestamp("2022-01-01")).strftime("%Y%m%d")
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
        st.plotly_chart(plots.kline_chart(df, tuple(overlays), tuple(sub)),
                        use_container_width=True)

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
        st.plotly_chart(plots.concentration_chart(sdf, metric), use_container_width=True)
        st.plotly_chart(plots.board_area_chart(sdf), use_container_width=True)
        detail_date = st.date_input("查看某日明细", pd.Timestamp(sdf.index[-1]))
        try:
            cross = loader.load_cross_section(detail_date.strftime("%Y%m%d"))
        except Exception as exc:
            st.error(f"读取截面数据失败：{exc}")
            cross = pd.DataFrame()
        if not cross.empty:
            st.plotly_chart(plots.concentration_detail_chart(cross), use_container_width=True)

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
            st.plotly_chart(plots.backtest_chart(res), use_container_width=True)
