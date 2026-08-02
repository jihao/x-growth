"""量化分析系统 Streamlit 界面。运行: .venv/bin/streamlit run app/main.py"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd
import streamlit as st

from quant.data import loader
from quant.concentration import cache
from quant.backtest import engine, metrics, strategies
from quant.charts import plots
from quant.favorites import store as fav_store
from quant.screening import store as screening_store
from quant.screening import explain as screening_explain
from quant.screening import llm as screening_llm
from app.ui_theme import install_theme_watcher, ui_theme

st.set_page_config(page_title="量化分析系统", layout="wide")
UI_THEME = ui_theme()


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
    st.header("导航")
    nav = st.radio(
        "页面",
        ["首页", "收藏"],
        key="nav",
        label_visibility="collapsed",
    )

    st.header("参数")
    try:
        stocks = _stocks()
        options = (stocks["ts_code"] + "  " + stocks["name"].fillna("")).tolist()
        code_to_label = {
            label.split("  ")[0]: label for label in options
        }
    except Exception as exc:  # 连库失败友好提示
        st.error(f"无法连接 MySQL，请检查 database/mysql/mysql.env：{exc}")
        st.stop()
    if stocks.empty or not options:
        st.error("股票列表为空，请检查数据库。")
        st.stop()

    if "ts_code" not in st.session_state:
        st.session_state.ts_code = options[0].split("  ")[0]

    _default_start = pd.Timestamp.today() - pd.DateOffset(months=6)
    start = st.date_input(
        "开始", _default_start, key="date_start"
    ).strftime("%Y%m%d")
    end = st.date_input(
        "结束", pd.Timestamp.today(), key="date_end"
    ).strftime("%Y%m%d")

    if nav == "首页":
        if "home_stock" not in st.session_state:
            st.session_state.home_stock = code_to_label.get(
                st.session_state.ts_code, options[0]
            )
        picked = st.selectbox("股票", options, key="home_stock")
        ts_code = picked.split("  ")[0]
        st.session_state.ts_code = ts_code

        try:
            # is_favorite 内部同连接 ensure_table，避免打开页多建一条连接
            starred = fav_store.is_favorite(ts_code)
        except Exception as exc:
            st.error(f"读取收藏失败：{exc}")
            starred = False
        star_label = "★ 取消收藏" if starred else "☆ 收藏"
        if st.button(star_label, key="toggle_fav_home"):
            try:
                if starred:
                    fav_store.remove(ts_code)
                else:
                    fav_store.add(ts_code)
                st.rerun()
            except Exception as exc:
                st.error(f"更新收藏失败：{exc}")
    else:
        try:
            fav_df = fav_store.list_favorites()
        except Exception as exc:
            st.error(f"读取收藏列表失败：{exc}")
            fav_df = pd.DataFrame(columns=["ts_code", "name", "created_at"])

        if fav_df.empty:
            st.info("暂无收藏")
            ts_code = st.session_state.ts_code
        else:
            for _, row in fav_df.iterrows():
                code = row["ts_code"]
                name = row["name"] if pd.notna(row["name"]) and row["name"] else ""
                label = f"{code}  {name}".rstrip()
                c1, c2 = st.columns([4, 1])
                with c1:
                    if st.button(
                        label,
                        key=f"fav_pick_{code}",
                        use_container_width=True,
                    ):
                        st.session_state.ts_code = code
                        if code in code_to_label:
                            st.session_state.home_stock = code_to_label[code]
                        st.rerun()
                with c2:
                    if st.button("✕", key=f"fav_del_{code}", help="取消收藏"):
                        try:
                            fav_store.remove(code)
                            st.rerun()
                        except Exception as exc:
                            st.error(f"取消收藏失败：{exc}")
            ts_code = st.session_state.ts_code
            st.caption(f"当前：{code_to_label.get(ts_code, ts_code)}")

tab1, tab2, tab3, tab4 = st.tabs(["行情分析", "资金集中度", "策略回测", "选股榜"])

with tab1:
    df = _safe_daily(ts_code, start, end)
    if df.empty:
        st.warning("该区间无数据。")
    else:
        # 三列：左=图设置（可收到最左），中=K线，右=结构分析（可收到最右）
        if "tab1_left_open" not in st.session_state:
            st.session_state.tab1_left_open = True
        if "tab1_right_open" not in st.session_state:
            st.session_state.tab1_right_open = True
        left_w = 1.35 if st.session_state.tab1_left_open else 0.18
        right_w = 1.55 if st.session_state.tab1_right_open else 0.18
        col_left, col_mid, col_right = st.columns(
            [left_w, 5.0, right_w], gap="small"
        )

        with col_left:
            if st.session_state.tab1_left_open:
                if st.button("◀ 收起", key="tab1_collapse_left", help="收起到最左"):
                    st.session_state.tab1_left_open = False
                    st.rerun()
                st.markdown("**图设置**")
                overlays = st.multiselect(
                    "叠加", ["ma5", "ma10", "ma20", "ma60"],
                    default=["ma5", "ma10", "ma20", "ma60"], key="tab1_overlays",
                )
                period = st.selectbox(
                    "周期", ["日线", "周线（即将支持）"], key="tab1_period",
                )
                if period.startswith("周线"):
                    st.caption("周线趋势线即将支持；以下仍按日线计算。")
            else:
                if st.button("▶", key="tab1_expand_left", help="展开左栏"):
                    st.session_state.tab1_left_open = True
                    st.rerun()
                overlays = st.session_state.get(
                    "tab1_overlays", ["ma5", "ma10", "ma20", "ma60"]
                )
                period = st.session_state.get("tab1_period", "日线")

        with col_right:
            if st.session_state.tab1_right_open:
                if st.button("收起 ▶", key="tab1_collapse_right", help="收起到最右"):
                    st.session_state.tab1_right_open = False
                    st.rerun()
                st.markdown("**结构分析**")
                auto_tl = st.checkbox("自动趋势线", value=True, key="tab1_auto_tl")
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
                    st.number_input(
                        "window", min_value=2, max_value=20, value=5, step=1,
                        key="tab1_tl_window",
                    )
                    st.number_input(
                        "tol", min_value=0.001, max_value=0.1, value=0.015,
                        format="%.3f", key="tab1_tl_tol",
                    )
                    st.number_input(
                        "top_k", min_value=1, max_value=10, value=3, step=1,
                        key="tab1_tl_top_k",
                    )
                    st.number_input(
                        "min_bars", min_value=3, max_value=60, value=10, step=1,
                        key="tab1_tl_min_bars",
                    )

                auto_wave = st.checkbox("浪型速度", value=True, key="tab1_auto_wave")
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
                    st.number_input(
                        "wave_window", min_value=2, max_value=20, value=5, step=1,
                        key="tab1_w_window",
                    )
                    st.number_input(
                        "min_pct", min_value=0.0, max_value=0.1, value=0.01,
                        format="%.3f", step=0.005, key="tab1_w_min_pct",
                    )
                    st.number_input(
                        "fast_ratio", min_value=1.0, max_value=2.0, value=1.05,
                        format="%.2f", key="tab1_w_fast",
                    )
                    st.number_input(
                        "slow_ratio", min_value=0.5, max_value=1.0, value=0.95,
                        format="%.2f", key="tab1_w_slow",
                    )
                    st.selectbox(
                        "浪型段", ["最近一段", "再前一段"], key="tab1_wave_seg",
                    )

                auto_div = st.checkbox("DIF 背离", value=True, key="tab1_auto_div")
                with st.expander("背离参数", expanded=False):
                    st.markdown(
                        """
**DIF 背离怎么看？**

1. **顶背离**：价格高点抬升，但 MACD 的 DIF 高点下降。
2. **底背离**：价格低点下移，但 DIF 低点抬升。
3. 价格创新高/新低而 DIF 不同步 → **钝化（pending）**；之后 DIF 自极值反向离开达 `confirm_pct` → **确认（confirmed）**。
4. 图上画全部钝化 + 最近 1 条已确认；明细表列出全部事件。
5. **级别**：P1→P2 价格速度越慢（缓涨/缓跌）→ 强；同侧多个背离优先更慢、更靠近当前的一个。
                        """.strip()
                    )
                    st.number_input(
                        "div_window", min_value=2, max_value=20, value=5, step=1,
                        key="tab1_d_window",
                    )
                    st.number_input(
                        "div_min_pct", min_value=0.0, max_value=0.1, value=0.01,
                        format="%.3f", step=0.005, key="tab1_d_min_pct",
                    )
                    st.number_input(
                        "align_bars", min_value=0, max_value=10, value=3, step=1,
                        key="tab1_d_align",
                    )
                    st.number_input(
                        "confirm_pct", min_value=0.01, max_value=0.5, value=0.05,
                        format="%.2f", step=0.01, key="tab1_d_confirm",
                    )
            else:
                if st.button("◀", key="tab1_expand_right", help="展开右栏"):
                    st.session_state.tab1_right_open = True
                    st.rerun()
                auto_tl = st.session_state.get("tab1_auto_tl", True)
                auto_wave = st.session_state.get("tab1_auto_wave", True)
                auto_div = st.session_state.get("tab1_auto_div", True)

        # 控件可能在右栏收起时未渲染，统一从 session_state 取值
        tl_window = int(st.session_state.get("tab1_tl_window", 5))
        tl_tol = float(st.session_state.get("tab1_tl_tol", 0.015))
        tl_top_k = int(st.session_state.get("tab1_tl_top_k", 3))
        tl_min_bars = int(st.session_state.get("tab1_tl_min_bars", 10))
        w_window = int(st.session_state.get("tab1_w_window", 5))
        w_min_pct = float(st.session_state.get("tab1_w_min_pct", 0.01))
        w_fast = float(st.session_state.get("tab1_w_fast", 1.05))
        w_slow = float(st.session_state.get("tab1_w_slow", 0.95))
        wave_seg = st.session_state.get("tab1_wave_seg", "最近一段")
        d_window = int(st.session_state.get("tab1_d_window", 5))
        d_min_pct = float(st.session_state.get("tab1_d_min_pct", 0.01))
        d_align = int(st.session_state.get("tab1_d_align", 3))
        d_confirm = float(st.session_state.get("tab1_d_confirm", 0.05))

        if "tab1_indicator" not in st.session_state:
            st.session_state.tab1_indicator = "MACD"
        _ind_label = st.session_state.tab1_indicator
        if _ind_label not in ("MACD", "KDJ", "RSI", "BOLL"):
            _ind_label = "MACD"
            st.session_state.tab1_indicator = _ind_label
        indicator = _ind_label.lower()

        fig = plots.kline_chart(
            df, tuple(overlays), indicator=indicator, theme_type=UI_THEME,
        )
        detail_rows = []
        wave_rows = []
        div_rows = []
        mid_infos: list[str] = []
        mid_warnings: list[str] = []

        if auto_tl:
            from quant.structure.trendlines import find_trendlines, evaluate_breakout

            res = find_trendlines(
                df,
                window=tl_window,
                tol=tl_tol,
                top_k=tl_top_k,
                min_bars=tl_min_bars,
            )
            if res.best_up is None and res.best_down is None:
                mid_infos.append("区间内有效波段点不足，无法拟合趋势线。")
            else:
                x_today = len(df) - 1
                res = evaluate_breakout(
                    res, float(df["close"].iloc[-1]), x_today, tol=tl_tol
                )
                fig = plots.overlay_trendlines(fig, df, res)
                msgs = []
                if res.best_up and res.best_up.status == "broken":
                    msgs.append("上升趋势线已破位")
                if res.best_down and res.best_down.status == "broken":
                    msgs.append("下降趋势线已升破")
                if msgs:
                    mid_warnings.append("；".join(msgs))
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

        if auto_wave:
            from quant.structure.waves import analyze_wave_speed

            wave_offset = 0 if wave_seg == "最近一段" else 1
            wres = analyze_wave_speed(
                df,
                offset=wave_offset,
                window=w_window,
                min_pct=w_min_pct,
                fast_ratio=w_fast,
                slow_ratio=w_slow,
            )
            if wres.current is None:
                if wave_offset == 1:
                    mid_infos.append("没有更早的一段已确认三浪。")
                else:
                    mid_infos.append("区间内有效三浪不足，无法做浪型速度分析。")
            else:
                t = wres.current
                fig = plots.overlay_waves(fig, df, t)
                verdict_cn = {
                    "extend": "倾向仍有第五浪",
                    "end": "倾向止于三浪",
                    "similar": "速度接近，需结合更大周期",
                }[t.verdict]
                dir_cn = "上涨" if t.direction == "up" else "下跌"
                mid_infos.append(
                    f"{dir_cn}三浪 · 第三浪/第一浪速度比={t.ratio:.2f} → {verdict_cn}"
                )
                for i, leg in enumerate(t.legs, 1):
                    wave_rows.append({
                        "浪": str(i),  # str：避免与「结论」混类型导致 Arrow 序列化失败
                        "起点": str(leg.start_date)[:10],
                        "终点": str(leg.end_date)[:10],
                        "根数": leg.bars,
                        "速度": round(leg.speed, 4),
                        "涨跌幅": f"{leg.ret:.2%}",
                    })
                wave_rows.append({
                    "浪": "结论",
                    "起点": "", "终点": "", "根数": None,
                    "速度": round(t.ratio, 4),
                    "涨跌幅": verdict_cn,
                })

        if auto_div:
            from quant.structure.divergence import LEVEL_CN, analyze_divergence

            dres = analyze_divergence(
                df,
                window=d_window,
                min_pct=d_min_pct,
                align_bars=d_align,
                confirm_pct=d_confirm,
            )
            if not dres.events:
                mid_infos.append("区间内未识别到 DIF 背离（钝化/确认）。")
            else:
                fig = plots.overlay_divergence(fig, df, dres.overlay_events)
                pe = dres.preferred_event
                if pe is not None:
                    side_cn = "顶" if pe.side == "top" else "底"
                    st_cn = "确认" if pe.status == "confirmed" else "钝化"
                    lv = LEVEL_CN.get(pe.level, pe.level)
                    mid_infos.append(f"优先关注：{side_cn}背离·{lv}（{st_cn}）")
                else:
                    last = dres.events[-1]
                    side_cn = "顶" if last.side == "top" else "底"
                    if last.status == "confirmed":
                        mid_infos.append(f"{side_cn}背离已确认")
                    else:
                        mid_infos.append(f"{side_cn}背离钝化中")
                for ev in dres.events:
                    div_rows.append({
                        "类型": "顶" if ev.side == "top" else "底",
                        "状态": "确认" if ev.status == "confirmed" else "钝化",
                        "级别": LEVEL_CN.get(ev.level, ev.level),
                        "优先": "是" if ev.preferred else "否",
                        "速度": round(ev.speed, 4),
                        "跨度": ev.span_bars,
                        "P1": str(ev.p1_date)[:10],
                        "P1价": round(ev.p1_price, 4),
                        "D1": round(ev.d1, 4),
                        "P2": str(ev.p2_date)[:10],
                        "P2价": round(ev.p2_price, 4),
                        "D2": round(ev.d2, 4),
                        "确认日": (
                            str(ev.confirm_date)[:10]
                            if ev.confirm_date is not None else ""
                        ),
                    })

        with col_mid:
            stock_name = ""
            if not stocks.empty and "name" in stocks.columns:
                match = stocks.loc[stocks["ts_code"] == ts_code, "name"]
                if not match.empty and pd.notna(match.iloc[0]):
                    stock_name = str(match.iloc[0])
            st.markdown(
                plots.quote_header_html(df, ts_code, stock_name, theme_type=UI_THEME),
                unsafe_allow_html=True,
            )
            st.plotly_chart(
                fig, width="stretch", key=f"kline_{UI_THEME}_{indicator}",
            )
            st.pills(
                "技术指标",
                ["MACD", "KDJ", "RSI", "BOLL"],
                key="tab1_indicator",
                label_visibility="collapsed",
            )
            for w in mid_warnings:
                st.warning(w)
            for info in mid_infos:
                st.info(info)

        if detail_rows:
            with st.expander("趋势线明细", expanded=True):
                st.dataframe(pd.DataFrame(detail_rows), width="stretch")
        if wave_rows:
            with st.expander("浪型明细", expanded=True):
                st.dataframe(pd.DataFrame(wave_rows), width="stretch")
        if div_rows:
            with st.expander("背离明细", expanded=True):
                st.dataframe(pd.DataFrame(div_rows), width="stretch")

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

with tab4:
    st.subheader("选股榜（多策略加权）")
    try:
        screen_dates = screening_store.list_dates()
    except Exception as exc:
        st.error(f"读取选股结果失败：{exc}")
        screen_dates = []
    if not screen_dates:
        st.info("暂无选股结果，请先运行：.venv/bin/python -m quant.screening.cli")
    else:
        picked_date = st.selectbox("交易日", screen_dates, key="tab4_date")
        try:
            res_df = screening_store.load_results(picked_date)
        except Exception as exc:
            st.error(f"读取选股结果失败：{exc}")
            res_df = pd.DataFrame()
        if res_df.empty:
            st.info("该日无数据。")
        else:
            show = res_df.copy()
            for c in ["total_score", "score_strategy",
                      "score_structure", "score_volume"]:
                show[c] = show[c].astype(float)
            show = show.rename(columns={
                "rank_no": "排名", "ts_code": "代码", "name": "名称",
                "total_score": "总分", "score_strategy": "策略",
                "score_structure": "结构", "score_volume": "量价",
            })
            cols_show = ["排名", "代码", "名称", "总分", "策略", "结构", "量价"]
            sel = st.dataframe(
                show[cols_show].style.format({
                    "总分": "{:.4f}", "策略": "{:.4f}",
                    "结构": "{:.4f}", "量价": "{:.4f}",
                }),
                width="stretch",
                hide_index=True,
                on_select="rerun",
                selection_mode="single-row",
                key="tab4_table",
            )
            picked_rows = sel.selection.rows if sel is not None else []
            if picked_rows:
                row = res_df.iloc[picked_rows[0]]
                code = row["ts_code"]
                name = row["name"] if pd.notna(row["name"]) else ""
                weights_obj = json.loads(row["weights_json"] or "{}")
                factors_obj = json.loads(row["factors_json"] or "{}")
                report = screening_explain.explain_row({
                    "total_score": row["total_score"],
                    "score_strategy": row["score_strategy"],
                    "score_structure": row["score_structure"],
                    "score_volume": row["score_volume"],
                    "weights": weights_obj,
                    "factors": factors_obj,
                })

                st.markdown(f"### {row['rank_no']}. {code}  {name}")
                action_box = [st.success, st.info, st.warning, st.error][
                    report["action_index"]
                ]
                action_box(
                    f"操作建议：**{report['action']}** —— {report['position_advice']}"
                )
                for reason in report["reasons"]:
                    st.markdown(f"- {reason}")
                for sec in report["sections"]:
                    with st.expander(sec["title"], expanded=False):
                        for line in sec["lines"]:
                            st.markdown(line)
                with st.expander("原始数据（因子明细 / 动态权重）", expanded=False):
                    dcol1, dcol2 = st.columns(2)
                    with dcol1:
                        st.json(factors_obj)
                    with dcol2:
                        st.json(weights_obj)

                if screening_llm.is_configured():
                    cache_key = f"tab4_llm_{picked_date}_{code}"
                    if st.button("AI 深度解读", key="tab4_llm_btn"):
                        with st.spinner("LLM 解读中…"):
                            try:
                                st.session_state[cache_key] = (
                                    screening_llm.explain_with_llm({
                                        "stock": f"{code} {name}",
                                        "scores": {
                                            "总分": round(float(row["total_score"]), 4),
                                            "策略": round(float(row["score_strategy"]), 4),
                                            "结构": round(float(row["score_structure"]), 4),
                                            "量价": round(float(row["score_volume"]), 4),
                                        },
                                        "rule_action": report["action"],
                                        "rule_reasons": report["reasons"],
                                        "factors": factors_obj,
                                    })
                                )
                            except Exception as exc:
                                st.error(f"LLM 调用失败：{exc}")
                    if st.session_state.get(cache_key):
                        st.markdown("**AI 深度解读**")
                        st.markdown(st.session_state[cache_key])
                else:
                    st.caption(
                        "在仓库根目录配置 llm.env（参考 llm.env.example）后，"
                        "可启用 AI 深度解读。"
                    )
                st.caption(report["disclaimer"])

                if st.button("在行情分析中查看", key="tab4_goto"):
                    st.session_state.ts_code = code
                    if code in code_to_label:
                        st.session_state.home_stock = code_to_label[code]
                    st.rerun()

install_theme_watcher()
