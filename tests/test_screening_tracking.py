"""跟踪复盘模块测试：mock 行情/选股数据，验证口径与统计逻辑。"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from quant.screening import tracking

_T = "20260701"


def _cal(n_total: int = 40) -> list[str]:
    """2026-06-30 起共 n_total 个工作日（字符串日历）。"""
    days = pd.bdate_range("2026-06-30", periods=n_total)
    return [d.strftime("%Y%m%d") for d in days]


def _px(n_fwd: int = 35, start_close: float = 10.0, trend: float = 0.01,
        missing: set[str] | None = None) -> pd.DataFrame:
    """T 前约 22 天缓冲 + 窗口行情；trend>0 每日上涨。"""
    days = pd.bdate_range("2026-06-01", periods=24 + n_fwd)
    close = start_close * (1 + trend) ** np.arange(len(days))
    df = pd.DataFrame({
        "open": close * 0.995, "high": close * 1.02, "low": close * 0.98,
        "close": close, "volume": 1000, "amount": close * 1000,
    }, index=pd.DatetimeIndex(days, name="trade_date"))
    if missing:
        df = df.drop(index=[pd.Timestamp(m) for m in missing])
    return df


def _scr_rows(specs: dict[str, tuple[int, float]]) -> pd.DataFrame:
    """{date: (rank, score)} -> load_stock_results 返回结构。"""
    return pd.DataFrame([
        {"trade_date": d, "rank_no": r, "total_score": s,
         "score_strategy": s, "score_structure": s, "score_volume": s,
         "weights_json": "{}", "factors_json": "{}"}
        for d, (r, s) in specs.items()
    ])


_FAKE_REGIME = {"date": _T, "score": 0.0, "level": "中性", "cap_index": 0,
                "data_missing": False, "components": {}, "summary": "中性（+0.00）"}


def _patch_market(monkeypatch, px=None, scr=None, action="买入参考"):
    cal = _cal()
    monkeypatch.setattr(tracking.loader, "trading_dates",
                        lambda s, e: [d for d in cal if s <= d <= e])
    monkeypatch.setattr(tracking.loader, "load_daily",
                        lambda code, start=None, end=None: px if px is not None else _px())
    monkeypatch.setattr(tracking._regime, "market_regime",
                        lambda d: _FAKE_REGIME)
    if scr is None:
        scr = _scr_rows({d: (3, 0.85) for d in cal if d >= _T})
    monkeypatch.setattr(tracking._store, "load_stock_results",
                        lambda code, s, e: scr)
    monkeypatch.setattr(tracking._explain, "explain_row",
                        lambda row: {"action": action})
    return cal


def test_entry_is_t1_open(monkeypatch):
    cal = _patch_market(monkeypatch)
    s = tracking.track_pick(_T, "600000.SH")["summary"]
    t1 = pd.Timestamp(cal[cal.index(_T) + 1])
    assert s["entry_date"] == t1.strftime("%Y%m%d")
    assert s["entry_price"] == pytest.approx(float(_px().loc[t1, "open"]))
    assert s["action0"] == "买入参考"
    assert s["rank0"] == 3


def test_returns_and_complete_window(monkeypatch):
    _patch_market(monkeypatch)
    s = tracking.track_pick(_T, "600000.SH")["summary"]
    assert s["complete"] is True and s["window_days"] == 30
    for k in ["ret_5", "ret_10", "ret_20", "ret_30", "ret_latest"]:
        assert s[k] > 0
    assert s["ret_30"] == pytest.approx(s["ret_latest"])
    # 单调上涨：最大浮盈（末日高点）> 至今收益 > 0 > 最大浮亏（首日低点）
    assert s["max_gain"] > s["ret_latest"] > 0 > s["max_dd"]
    assert s["verdict_tone"] == "good"


def test_relist_full_window(monkeypatch):
    _patch_market(monkeypatch)
    s = tracking.track_pick(_T, "600000.SH")["summary"]
    assert s["in_list_days"] == 30
    assert s["longest_streak"] == 30
    assert s["exit_day"] is None
    assert s["best_rank"] == 3 and s["last_rank"] == 3
    assert s["n_flips"] == 0


def test_exit_and_action_flips(monkeypatch):
    cal = _cal()
    i1, i2 = cal.index(_T) + 1, cal.index(_T) + 2
    scr = _scr_rows({_T: (1, 0.9), cal[i1]: (2, 0.8), cal[i2]: (5, 0.7)})
    _patch_market(monkeypatch, px=_px(trend=-0.01), scr=scr)
    seq = {0.9: "买入参考", 0.8: "观望", 0.7: "减仓/回避"}
    monkeypatch.setattr(
        tracking._explain, "explain_row",
        lambda row: {"action": seq[round(float(row["total_score"]), 1)]})
    s = tracking.track_pick(_T, "600000.SH")["summary"]
    assert s["in_list_days"] == 2  # 第 3 个交易日起落榜
    assert s["exit_day"] == 3
    assert s["n_flips"] == 1
    assert "观望→减仓/回避" in s["flips"][0]
    # 买入参考 + 持续下跌 + 无大幅冲高 -> 建议未兑现
    assert s["verdict_tone"] == "bad"


def test_suspension_days_are_skipped(monkeypatch):
    cal = _cal()
    t1, t2 = cal[cal.index(_T) + 1], cal[cal.index(_T) + 2]
    _patch_market(monkeypatch, px=_px(missing={t1, t2}))
    s = tracking.track_pick(_T, "600000.SH")["summary"]
    # T+1/T+2 停牌：入场顺延到 T+3，交易日计数 28
    assert s["entry_date"] == cal[cal.index(_T) + 3]
    assert s["days_traded"] == 28
    assert s["window_days"] == 30


def test_incomplete_window_pending(monkeypatch):
    cal = _cal(n_total=6)  # T 后仅 4 个交易日
    monkeypatch.setattr(tracking.loader, "trading_dates",
                        lambda s, e: [d for d in cal if s <= d <= e])
    monkeypatch.setattr(tracking.loader, "load_daily",
                        lambda code, start=None, end=None: _px())
    monkeypatch.setattr(tracking._regime, "market_regime",
                        lambda d: _FAKE_REGIME)
    monkeypatch.setattr(tracking._store, "load_stock_results",
                        lambda code, s, e: _scr_rows({_T: (1, 0.9)}))
    monkeypatch.setattr(tracking._explain, "explain_row",
                        lambda row: {"action": "买入参考"})
    s = tracking.track_pick(_T, "600000.SH")["summary"]
    assert s["complete"] is False
    assert s["window_days"] == 4
    assert pd.isna(s["ret_5"])
    assert s["verdict_tone"] == "pending"


def test_empty_window_latest_date(monkeypatch):
    """T 为行情库最新日：窗口为空，daily 也要带齐列（UI 判空依赖）。"""
    cal = [d.strftime("%Y%m%d") for d in pd.bdate_range(end="2026-07-01", periods=5)]
    monkeypatch.setattr(tracking.loader, "trading_dates",
                        lambda s, e: [d for d in cal if s <= d <= e])
    monkeypatch.setattr(tracking.loader, "load_daily",
                        lambda code, start=None, end=None: _px())
    monkeypatch.setattr(tracking._regime, "market_regime",
                        lambda d: _FAKE_REGIME)
    monkeypatch.setattr(tracking._store, "load_stock_results",
                        lambda code, s, e: _scr_rows({_T: (1, 0.9)}))
    monkeypatch.setattr(tracking._explain, "explain_row",
                        lambda row: {"action": "买入参考"})
    out = tracking.track_pick(_T, "600000.SH")
    s = out["summary"]
    assert out["daily"].empty
    assert "traded" in out["daily"].columns
    assert s["window_days"] == 0 and s["entry_price"] is None
    assert s["verdict_tone"] == "pending"


def test_negative_action_verdict(monkeypatch):
    _patch_market(monkeypatch, px=_px(trend=-0.01), action="减仓/回避")
    s = tracking.track_pick(_T, "600000.SH")["summary"]
    assert s["verdict_tone"] == "good"  # 正确回避


def test_vol_spike_event(monkeypatch):
    px = _px()
    spike_day = pd.Timestamp(_cal()[_cal().index(_T) + 3])
    px.loc[spike_day, "volume"] = 5000  # 5 倍于均量
    _patch_market(monkeypatch, px=px)
    s = tracking.track_pick(_T, "600000.SH")["summary"]
    kinds = [e["kind"] for e in s["events"]]
    assert "vol_spike" in kinds


def _picks() -> pd.DataFrame:
    return pd.DataFrame({
        "trade_date": [_T, _T], "rank_no": [1, 2],
        "ts_code": ["600000.SH", "000001.SZ"], "name": ["浦发", "平安"],
        "total_score": [0.9, 0.8], "score_strategy": [0.9, 0.8],
        "score_structure": [0.9, 0.8], "score_volume": [0.9, 0.8],
        "weights_json": ["{}", "{}"], "factors_json": ["{}", "{}"],
    })


def _patch_batch(monkeypatch):
    """整体复盘的批量取数通道：两只股票共用同一份假行情/选股记录。"""
    cal = _patch_market(monkeypatch)

    def _daily_many(codes, start=None, end=None):
        frames = []
        for c in codes:
            df = _px().reset_index()
            df["trade_date"] = df["trade_date"].dt.strftime("%Y%m%d")
            df.insert(0, "ts_code", c)
            frames.append(df)
        return pd.concat(frames, ignore_index=True)

    scr_many = _scr_rows({d: (3, 0.85) for d in cal if d >= _T})
    scr_many.insert(0, "ts_code", "600000.SH")
    scr_many2 = scr_many.copy()
    scr_many2["ts_code"] = "000001.SZ"
    scr_many = pd.concat([scr_many, scr_many2], ignore_index=True)

    monkeypatch.setattr(tracking.loader, "load_daily_many", _daily_many)
    monkeypatch.setattr(tracking._store, "load_results_many",
                        lambda codes, s, e: scr_many)
    monkeypatch.setattr(tracking._store, "load_results", lambda d: _picks())
    monkeypatch.setattr(
        tracking.loader, "load_cross_section_ohlc",
        lambda d: pd.DataFrame({"ts_code": ["600000.SH", "000001.SZ"],
                                "open": [1.0, 1.0], "close": [1.0, 1.0]}))


def test_review_date_aggregates(monkeypatch):
    _patch_batch(monkeypatch)
    df, stats = tracking.review_date(_T)
    assert len(df) == 2
    assert set(df["name"]) == {"浦发", "平安"}
    by_action = stats["by_action"]
    assert by_action.iloc[0]["只数"] == 2
    assert by_action.iloc[0]["胜率T+20"] == 1.0  # 均上涨
    assert stats["by_bucket"].iloc[0]["_bucket"] == "Top10"
    assert stats["n_exits_day1"] == 0


def test_spearman_insufficient_samples():
    assert pd.isna(tracking._spearman(pd.Series([1, 2, 3]),
                                      pd.Series([1, 2, 3])))
    n = 12
    a = pd.Series(np.arange(n, dtype=float))
    assert tracking._spearman(a, a) == pytest.approx(1.0)


def test_multi_stats_across_dates(monkeypatch):
    _patch_batch(monkeypatch)
    out = tracking.multi_stats([_T, "20260702"])
    by_action = out["by_action"]
    assert len(by_action) == 1  # 同一建议类型合并
    assert by_action.iloc[0]["样本数"] == 4
    assert by_action.iloc[0]["覆盖日期数"] == 2
    assert by_action.iloc[0]["建议兑现率"] == 1.0
    by_regime = out["by_regime"]
    assert len(by_regime) == 1  # fake regime 统一为中性
    assert by_regime.iloc[0]["环境"] == "中性"
    assert by_regime.iloc[0]["样本数"] == 4
