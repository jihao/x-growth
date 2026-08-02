"""选股跟踪复盘：入选后 30 个交易日的再入选 / 建议变化 / 价格验证。

口径约定：
- 信号于 T 日收盘后产生，统一以 T+1 开盘价作为入场基准（最接近真实可成交价）；
- T+n 收益 = 第 n 个后续交易日收盘价 / T+1 开盘价 - 1（行情为前复权，口径一致）；
- 行情库最新日之前的窗口为「复盘进行中」，按可用天数计算并标注；
- 操作建议只在入选日存在（未入选日记为 None），由当日落库因子用 explain 规则引擎重算。
"""
from __future__ import annotations

import json

import numpy as np
import pandas as pd

from quant import config
from quant.data import loader
from quant.market import regime as _regime
from quant.screening import explain as _explain
from quant.screening import store as _store

HORIZON = 30
SNAPSHOT_DAYS = (5, 10, 20, 30)

_POSITIVE_ACTIONS = {"买入参考", "轻仓试探"}
_NEGATIVE_ACTIONS = {"减仓/回避"}

# 验证结论色调：good 兑现 / ok 基本符合 / neutral 中性 / bad 打脸 / pending 进行中
VERDICT_TONES = ("good", "ok", "neutral", "bad", "pending")

_RANK_BUCKETS = ((1, 10, "Top10"), (11, 30, "11-30"), (31, 10**9, "31-50"))


def _fmt(d) -> str:
    return config.fmt_date(d)


def _window_calendar(trade_date: str, horizon: int = HORIZON) -> list[str]:
    """T 之后最多 horizon 个交易日（行情库未覆盖的未来日期自然截断）。"""
    t = _fmt(trade_date)
    cal = loader.trading_dates(t, "99991231")
    if t not in cal:
        raise RuntimeError(f"{t} 在行情库中不存在（不是交易日或数据缺失）")
    i = cal.index(t)
    return cal[i + 1: i + 1 + horizon]


def _pct_limit(ts_code: str) -> float:
    if ts_code.endswith(".BJ"):
        return 0.298
    return 0.198 if ts_code.startswith(("30", "68")) else 0.098


def _action_of(row: pd.Series) -> str:
    rep = _explain.explain_row({
        "total_score": row["total_score"],
        "score_strategy": row["score_strategy"],
        "score_structure": row["score_structure"],
        "score_volume": row["score_volume"],
        "weights": json.loads(row["weights_json"] or "{}"),
        "factors": json.loads(row["factors_json"] or "{}"),
        "regime": _regime.market_regime(str(row["trade_date"])),
    })
    return rep["action"]


def _verdict(action0, days_traded, ret_check, n_check,
             max_gain, max_dd, blocked) -> tuple[str, str]:
    """规则化验证结论，返回 (文案, 色调)。"""
    if days_traded < 5:
        return f"复盘进行中（行情仅 {days_traded} 个交易日，不足验证）", "pending"
    suffix = f"（T+{n_check} 收益 {ret_check:+.1%}）"
    blk = "；注意 T+1 一字板，实际难以成交" if blocked else ""
    if action0 in _POSITIVE_ACTIONS:
        if ret_check >= 0.05:
            return f"建议兑现{suffix}{blk}", "good"
        if ret_check >= 0:
            return f"方向符合但涨幅有限{suffix}{blk}", "ok"
        if max_gain >= 0.08:
            return f"盘中曾冲高 {max_gain:+.1%} 但未守住{suffix}{blk}", "neutral"
        return f"建议未兑现{suffix}{blk}", "bad"
    if action0 in _NEGATIVE_ACTIONS:
        if ret_check <= -0.03 or max_dd <= -0.08:
            return f"正确回避{suffix}，期间最大浮亏 {max_dd:+.1%}", "good"
        if ret_check >= 0.05:
            return f"回避误判，期间上涨{suffix}", "bad"
        return f"区间震荡，回避意义有限{suffix}", "neutral"
    # 观望类中性建议，不做对错判定，只描述
    if ret_check >= 0.08:
        return f"观望期间明显上涨{suffix}，可复盘是否错失", "neutral"
    if ret_check <= -0.08:
        return f"观望正确，期间明显走弱{suffix}", "ok"
    return f"观望期间区间震荡{suffix}", "neutral"


def _longest_streak(flags: list[bool]) -> int:
    best = cur = 0
    for f in flags:
        cur = cur + 1 if f else 0
        best = max(best, cur)
    return best


def _track_compute(t: str, ts_code: str, win: list[str],
                   px: pd.DataFrame, scr: pd.DataFrame) -> dict:
    """纯计算部分：给定窗口日历、行情与选股记录，输出 daily + summary。"""
    scr_by_date = {}
    if scr is not None and not scr.empty:
        for _, r in scr.iterrows():
            scr_by_date[str(r["trade_date"])] = r
    row_t = scr_by_date.get(t)
    action0 = _action_of(row_t) if row_t is not None else "未知"
    rank0 = int(row_t["rank_no"]) if row_t is not None else None
    score0 = float(row_t["total_score"]) if row_t is not None else np.nan

    # 预备：量比（前 20 日均量）与涨跌幅（用于事件检测，含 T 日前缓冲段）
    if not px.empty:
        vol_ma = px["volume"].rolling(20, min_periods=5).mean().shift(1)
        pct = px["close"].pct_change()
    else:
        vol_ma = pd.Series(dtype=float)
        pct = pd.Series(dtype=float)

    limit = _pct_limit(ts_code)
    low_t = float(px.loc[pd.Timestamp(pd.to_datetime(t, format="%Y%m%d")), "low"]) \
        if (not px.empty and pd.Timestamp(pd.to_datetime(t, format="%Y%m%d")) in px.index) \
        else np.nan

    daily_rows, events = [], []
    entry_price = entry_date = None
    entry_blocked = False
    broke_low = False
    close_ff = None
    in_list_flags: list[bool] = []
    ranks: list[int] = []
    actions_seq: list[tuple[str, str]] = []  # (date, action) 入选日序列

    for n, d in enumerate(win, 1):
        ts = pd.Timestamp(pd.to_datetime(d, format="%Y%m%d"))
        traded = not px.empty and ts in px.index
        if traded:
            r = px.loc[ts]
            close_ff = float(r["close"])
            if entry_price is None:
                entry_price = float(r["open"])
                entry_date = d
                if (float(r["open"]) == float(r["high"])
                        == float(r["low"]) == float(r["close"])
                        and float(pct.get(ts, 0) or 0) >= 0.045):
                    entry_blocked = True
                    events.append({"date": d, "kind": "blocked",
                                   "text": "T+1 一字板，买入困难"})
            vr = float(r["volume"] / vol_ma.get(ts, np.nan)) \
                if pd.notna(vol_ma.get(ts, np.nan)) and vol_ma.get(ts, 0) else np.nan
            chg = float(pct.get(ts, np.nan))
            if pd.notna(vr) and vr >= 2.0:
                events.append({"date": d, "kind": "vol_spike",
                               "text": f"放量（量比 {vr:.1f}）"})
            if pd.notna(chg) and chg >= limit:
                events.append({"date": d, "kind": "limit_up", "text": "涨停"})
            elif pd.notna(chg) and chg <= -limit:
                events.append({"date": d, "kind": "limit_down", "text": "跌停"})
            if (not broke_low and pd.notna(low_t)
                    and float(r["close"]) < low_t):
                broke_low = True
                events.append({"date": d, "kind": "break_low",
                               "text": f"收盘跌破入选日低点（{low_t:.2f}）"})
        else:
            r = None

        srow = scr_by_date.get(d)
        in_list = srow is not None
        in_list_flags.append(in_list)
        act = _action_of(srow) if in_list else None
        if in_list:
            ranks.append(int(srow["rank_no"]))
            actions_seq.append((d, act))
        cum_ret = (close_ff / entry_price - 1) if entry_price and close_ff else np.nan
        daily_rows.append({
            "date": d, "day_n": n, "traded": traded,
            "close": float(r["close"]) if traded else np.nan,
            "cum_ret": cum_ret,
            "in_list": in_list,
            "rank_no": int(srow["rank_no"]) if in_list else None,
            "total_score": float(srow["total_score"]) if in_list else np.nan,
            "action": act,
        })

    daily = pd.DataFrame(daily_rows, columns=[
        "date", "day_n", "traded", "close", "cum_ret",
        "in_list", "rank_no", "total_score", "action",
    ])
    days_traded = int(daily["traded"].sum()) if not daily.empty else 0
    window_days = len(win)

    rets = {}
    closes = daily["cum_ret"].tolist() if not daily.empty else []
    for n_snap in SNAPSHOT_DAYS:
        rets[n_snap] = closes[n_snap - 1] if len(closes) >= n_snap else np.nan
    ret_latest = closes[-1] if closes else np.nan

    if entry_price and days_traded:
        traded_px = daily[daily["traded"]]
        # 最大浮盈/浮亏用日内极值，更贴近真实持仓体验
        px_win = px.loc[[pd.Timestamp(pd.to_datetime(d, format="%Y%m%d"))
                         for d in traded_px["date"]]]
        max_gain = float(px_win["high"].max() / entry_price - 1)
        max_gain_day = str(px_win["high"].idxmax().strftime("%Y%m%d"))
        max_dd = float(px_win["low"].min() / entry_price - 1)
        max_dd_day = str(px_win["low"].idxmin().strftime("%Y%m%d"))
    else:
        max_gain = max_dd = np.nan
        max_gain_day = max_dd_day = None

    exit_day = next((n for n, f in enumerate(in_list_flags, 1) if not f), None)
    flips = []
    for (d_prev, a_prev), (d_cur, a_cur) in zip(actions_seq, actions_seq[1:]):
        if a_cur != a_prev:
            flips.append(f"{a_prev}→{a_cur}（{d_cur[4:6]}-{d_cur[6:]}）")

    reg = _regime.market_regime(t)
    n_check = min(20, window_days) if window_days else 0
    ret_check = closes[n_check - 1] if n_check and len(closes) >= n_check else np.nan
    if pd.isna(ret_check):
        ret_check, n_check = ret_latest if pd.notna(ret_latest) else 0.0, len(closes)
    verdict, tone = _verdict(action0, days_traded, ret_check, n_check,
                             max_gain if pd.notna(max_gain) else 0.0,
                             max_dd if pd.notna(max_dd) else 0.0,
                             entry_blocked)

    summary = {
        "trade_date": t, "ts_code": ts_code,
        "rank0": rank0, "score0": score0, "action0": action0,
        "entry_date": entry_date, "entry_price": entry_price,
        "entry_blocked": entry_blocked,
        "window_days": window_days, "days_traded": days_traded,
        "complete": window_days >= HORIZON,
        "ret_5": rets[5], "ret_10": rets[10],
        "ret_20": rets[20], "ret_30": rets[30],
        "ret_latest": ret_latest,
        "max_gain": max_gain, "max_gain_day": max_gain_day,
        "max_dd": max_dd, "max_dd_day": max_dd_day,
        "in_list_days": int(sum(in_list_flags)),
        "longest_streak": _longest_streak(in_list_flags),
        "best_rank": min(ranks) if ranks else None,
        "last_rank": ranks[-1] if ranks else None,
        "exit_day": exit_day,
        "action_last": actions_seq[-1][1] if actions_seq else None,
        "flips": flips, "n_flips": len(flips),
        "events": events,
        "verdict": verdict, "verdict_tone": tone,
        "regime_level": reg["level"], "regime_score": reg["score"],
    }
    return {"daily": daily, "summary": summary}


def _window_start(t: str) -> str:
    """行情缓冲起点：T 前 100 个自然日（覆盖约 45+ 交易日，够均量/涨跌幅计算）。"""
    return (pd.Timestamp(pd.to_datetime(t, format="%Y%m%d"))
            - pd.Timedelta(days=100)).strftime("%Y%m%d")


def track_pick(trade_date, ts_code) -> dict:
    """单次入选的 30 日跟踪。返回 {"daily": DataFrame, "summary": dict}。"""
    t = _fmt(trade_date)
    win = _window_calendar(t)
    last = win[-1] if win else t
    px = loader.load_daily(ts_code, _window_start(t), last)
    scr = _store.load_stock_results(ts_code, t, last)
    return _track_compute(t, ts_code, win, px, scr)


def _benchmark_returns(win: list[str]) -> dict[int, float]:
    """全市场基准：T+1 开盘买入，各快照日收盘收益的中位数。"""
    if not win:
        return {}
    base = loader.load_cross_section_ohlc(win[0]).set_index("ts_code")["open"]
    out = {}
    for n_snap in SNAPSHOT_DAYS:
        if len(win) < n_snap:
            out[n_snap] = np.nan
            continue
        close = loader.load_cross_section_ohlc(
            win[n_snap - 1]).set_index("ts_code")["close"]
        ret = (close / base - 1).replace([np.inf, -np.inf], np.nan).dropna()
        out[n_snap] = float(ret.median()) if len(ret) else np.nan
    return out


def _spearman(a: pd.Series, b: pd.Series) -> float:
    """秩次相关（spearman），不依赖 scipy；样本不足返回 nan。"""
    valid = pd.concat([a, b], axis=1).dropna()
    if len(valid) < 10:
        return np.nan
    ra, rb = valid.iloc[:, 0].rank(), valid.iloc[:, 1].rank()
    if ra.std() == 0 or rb.std() == 0:
        return np.nan
    return float(ra.corr(rb))


def _group_stats(df: pd.DataFrame, by: str, bench: dict) -> pd.DataFrame:
    """按维度聚合：只数 / T+20 胜率 / 各快照平均收益 / 平均最大浮盈浮亏。"""
    rows = []
    for key, g in df.groupby(by):
        r20 = g["ret_20"].dropna()
        rlast = g["ret_latest"].dropna()
        row = {by: key, "只数": len(g),
               "胜率T+20": float((r20 > 0).mean()) if len(r20) else np.nan,
               "平均T+5": g["ret_5"].mean(), "平均T+10": g["ret_10"].mean(),
               "平均T+20": g["ret_20"].mean(), "平均T+30": g["ret_30"].mean(),
               "平均至今": rlast.mean() if len(rlast) else np.nan,
               "平均最大浮盈": g["max_gain"].mean(),
               "平均最大浮亏": g["max_dd"].mean()}
        b20 = bench.get(20)
        row["超额T+20"] = (row["平均T+20"] - b20) \
            if pd.notna(row["平均T+20"]) and pd.notna(b20) else np.nan
        rows.append(row)
    return pd.DataFrame(rows)


def review_date(trade_date, with_stats: bool = True) -> tuple[pd.DataFrame, dict]:
    """某日上榜 50 只的整体复盘。返回 (逐股汇总 DataFrame, 统计 dict)。

    行情与选股记录各一次批量取数（避免 100+ 次单股查询），再逐股纯计算。
    """
    t = _fmt(trade_date)
    picks = _store.load_results(t)
    if picks.empty:
        return pd.DataFrame(), {}
    win = _window_calendar(t)
    last = win[-1] if win else t
    codes = picks["ts_code"].tolist()
    px_all = loader.load_daily_many(codes, _window_start(t), last)
    scr_all = _store.load_results_many(codes, t, last)

    rows = []
    for _, p in picks.iterrows():
        code = p["ts_code"]
        px_raw = px_all[px_all["ts_code"] == code].drop(columns=["ts_code"]) \
            if not px_all.empty else px_all
        px = loader._normalize_daily(px_raw)
        scr = scr_all[scr_all["ts_code"] == code].drop(columns=["ts_code"]) \
            if not scr_all.empty else scr_all
        s = _track_compute(t, code, win, px, scr)["summary"]
        s["name"] = p["name"] if pd.notna(p.get("name")) else ""
        rows.append(s)
    df = pd.DataFrame(rows)
    if not with_stats:
        return df, {}
    bench = _benchmark_returns(win)
    df["_bucket"] = df["rank0"].apply(
        lambda r: next((lbl for lo, hi, lbl in _RANK_BUCKETS
                        if r is not None and lo <= r <= hi), "其他"))
    stats = {
        "benchmark": bench,
        "by_action": _group_stats(df, "action0", bench),
        "by_bucket": _group_stats(df, "_bucket", bench),
        "score_corr": _spearman(df["score0"], df["ret_latest"]),
        "n_exits_day1": int((df["exit_day"] == 1).sum()),
        "n_flips": int((df["n_flips"] > 0).sum()),
    }
    return df, stats


def multi_stats(dates: list[str]) -> dict:
    """跨日期汇总（不计算基准，较快）。

    返回 {"by_action": df, "by_regime": df}：
    - by_action：各建议类型的整体胜率/兑现率；
    - by_regime：按入选日市场环境分组的胜率——直接验证 regime 过滤的价值。
    """
    frames = []
    for t in dates:
        df, _ = review_date(t, with_stats=False)
        if not df.empty:
            frames.append(df)
    if not frames:
        return {"by_action": pd.DataFrame(), "by_regime": pd.DataFrame()}
    all_df = pd.concat(frames, ignore_index=True)

    def _agg(g):
        r20 = g["ret_20"].dropna()
        return {
            "样本数": len(g),
            "覆盖日期数": g["trade_date"].nunique(),
            "胜率T+20": float((r20 > 0).mean()) if len(r20) else np.nan,
            "平均T+20": g["ret_20"].mean(),
            "平均至今": g["ret_latest"].mean(),
            "平均最大浮盈": g["max_gain"].mean(),
            "平均最大浮亏": g["max_dd"].mean(),
            "建议兑现率": float((g["verdict_tone"] == "good").mean()),
        }

    by_action = pd.DataFrame(
        [{"建议": k, **_agg(g)} for k, g in all_df.groupby("action0")])
    level_order = {lvl: i for i, lvl in enumerate(
        ["强势", "偏强", "中性", "偏弱", "弱势"])}
    by_regime = pd.DataFrame(
        [{"环境": k, **_agg(g)} for k, g in all_df.groupby("regime_level")])
    if not by_regime.empty:
        by_regime = by_regime.sort_values(
            "环境", key=lambda s: s.map(level_order)).reset_index(drop=True)
    return {"by_action": by_action, "by_regime": by_regime}
