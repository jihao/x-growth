from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from quant.screening import factors
from quant.structure.models import (
    DivergenceEvent,
    DivergenceResult,
    Trendline,
    TrendlineResult,
    WaveSpeedResult,
    WaveTriple,
)


def _df(n: int = 120, trend: float = 0.01) -> pd.DataFrame:
    idx = pd.date_range("2026-01-01", periods=n, freq="B", name="trade_date")
    close = 10 * (1 + trend) ** np.arange(n)
    return pd.DataFrame(
        {
            "open": close,
            "high": close * 1.01,
            "low": close * 0.99,
            "close": close,
            "volume": 1000,
            "amount": close * 1000,
        },
        index=idx,
    )


def _div_event(side, status, level, p2_date) -> DivergenceEvent:
    return DivergenceEvent(
        side=side, status=status,
        p1_date=p2_date, p1_price=10.0, d1=1.0, d1_date=p2_date,
        p2_date=p2_date, p2_price=11.0, d2=0.5, d2_date=p2_date,
        level=level,
    )


def _trendline(side, status) -> Trendline:
    return Trendline(
        side=side, slope=0.1 if side == "up" else -0.1, intercept=1.0,
        touch_dates=["a", "b", "c"], touch_count=3, score=40.0,
        start_date="a", end_date="b", status=status,
        line_price_today=10.0, distance_pct=0.02,
    )


# ---------------- strategy_score ----------------

def test_strategy_score_structure_and_equal_weights():
    df = _df()
    score, detail = factors.strategy_score(df)
    assert 0.0 <= score <= 1.0
    assert set(detail) == {"ma_cross", "macd", "bollinger", "rsi", "donchian"}
    assert all(v["signal"] in (0, 1) for v in detail.values())
    assert sum(v["weight"] for v in detail.values()) == pytest.approx(1.0)


def test_strategy_score_custom_weights_follow_single_strategy():
    df = _df(trend=0.02)  # 单调上行，双均线必定持仓
    only_ma = {"ma_cross": 1.0, "macd": 0.0, "bollinger": 0.0,
               "rsi": 0.0, "donchian": 0.0}
    score, detail = factors.strategy_score(df, only_ma)
    assert score == detail["ma_cross"]["signal"] == 1


def test_strategy_score_empty_df_neutral():
    score, detail = factors.strategy_score(_df(0))
    assert score == factors.NEUTRAL and detail == {}


# ---------------- divergence_score ----------------

def test_divergence_score_empty_and_no_events(monkeypatch):
    assert factors.divergence_score(_df(0))[0] == factors.NEUTRAL
    monkeypatch.setattr(
        factors, "analyze_divergence", lambda df: DivergenceResult()
    )
    assert factors.divergence_score(_df())[0] == factors.NEUTRAL


def test_divergence_score_confirmed_strong_bottom_max(monkeypatch):
    df = _df()
    ev = _div_event("bottom", "confirmed", "strong", df.index[-1])
    monkeypatch.setattr(
        factors, "analyze_divergence",
        lambda d: DivergenceResult(events=[ev]),
    )
    score, detail = factors.divergence_score(df)
    assert score == pytest.approx(1.0)
    assert detail["bottom"]["level"] == "strong"


def test_divergence_score_confirmed_strong_top_min(monkeypatch):
    df = _df()
    ev = _div_event("top", "confirmed", "strong", df.index[-1])
    monkeypatch.setattr(
        factors, "analyze_divergence",
        lambda d: DivergenceResult(events=[ev]),
    )
    assert factors.divergence_score(df)[0] == pytest.approx(0.0)


def test_divergence_score_pending_weak_bottom_partial(monkeypatch):
    df = _df()
    ev = _div_event("bottom", "pending", "weak", df.index[-1])
    monkeypatch.setattr(
        factors, "analyze_divergence",
        lambda d: DivergenceResult(events=[ev]),
    )
    # 0.5 + 0.5 * (0.4 * 0.5 * 1.0) = 0.6
    assert factors.divergence_score(df)[0] == pytest.approx(0.6)


def test_divergence_score_stale_event_ignored(monkeypatch):
    df = _df()
    ev = _div_event("bottom", "confirmed", "strong", df.index[10])
    monkeypatch.setattr(
        factors, "analyze_divergence",
        lambda d: DivergenceResult(events=[ev]),
    )
    assert factors.divergence_score(df, recent_bars=60)[0] == factors.NEUTRAL


# ---------------- wave_score ----------------

def _wave(direction, verdict) -> WaveSpeedResult:
    triple = WaveTriple(
        direction=direction, pivots=[], legs=[], ratio=1.2, verdict=verdict,
    )
    return WaveSpeedResult(current=triple, previous_available=False)


def test_wave_score_mapping(monkeypatch):
    df = _df()
    cases = {
        ("up", "extend"): 1.0, ("up", "similar"): 0.7, ("up", "end"): 0.4,
        ("down", "end"): 0.6, ("down", "similar"): 0.3, ("down", "extend"): 0.0,
    }
    for (direction, verdict), expected in cases.items():
        monkeypatch.setattr(
            factors, "analyze_wave_speed",
            lambda d, r=_wave(direction, verdict): r,
        )
        score, detail = factors.wave_score(df)
        assert score == pytest.approx(expected)
        assert detail["verdict"] == verdict


def test_wave_score_none_and_empty(monkeypatch):
    monkeypatch.setattr(
        factors, "analyze_wave_speed",
        lambda d: WaveSpeedResult(current=None),
    )
    assert factors.wave_score(_df())[0] == factors.NEUTRAL
    assert factors.wave_score(_df(0))[0] == factors.NEUTRAL


# ---------------- trendline_score ----------------

def _tl_result(best_up=None, best_down=None) -> TrendlineResult:
    return TrendlineResult(best_up=best_up, best_down=best_down)


@pytest.fixture
def _patch_tl(monkeypatch):
    def apply(result):
        monkeypatch.setattr(factors, "find_trendlines", lambda df: result)
        monkeypatch.setattr(
            factors, "evaluate_breakout",
            lambda res, close, x: res,
        )
    return apply


def test_trendline_score_no_lines(_patch_tl):
    _patch_tl(_tl_result())
    assert factors.trendline_score(_df())[0] == factors.NEUTRAL


def test_trendline_score_down_breakout_bullish(_patch_tl):
    _patch_tl(_tl_result(best_down=_trendline("down", "broken")))
    assert factors.trendline_score(_df())[0] == pytest.approx(1.0)


def test_trendline_score_up_breakdown_bearish(_patch_tl):
    _patch_tl(_tl_result(best_up=_trendline("up", "broken")))
    assert factors.trendline_score(_df())[0] == pytest.approx(0.1)


def test_trendline_score_capped_below_resistance(_patch_tl):
    _patch_tl(_tl_result(
        best_up=_trendline("up", "above"),
        best_down=_trendline("down", "below"),
    ))
    # 0.5 - 0.1 + 0.2 = 0.6
    assert factors.trendline_score(_df())[0] == pytest.approx(0.6)


def test_trendline_score_empty_df():
    assert factors.trendline_score(_df(0))[0] == factors.NEUTRAL


# ---------------- heat_score / momentum_score ----------------

def test_heat_score_rank_and_ratio():
    panel = pd.Series([100.0, 200.0, 300.0, 400.0])
    score, detail = factors.heat_score(400.0, 100.0, panel)
    # rank_pct=0.75, vol_ratio=4 -> norm 1.0 => 0.6*0.75+0.4*1.0=0.85
    assert score == pytest.approx(0.85)
    assert detail["vol_ratio"] == pytest.approx(4.0)


def test_heat_score_empty_panel_and_zero_avg():
    assert factors.heat_score(100.0, 50.0, pd.Series(dtype=float))[0] == factors.NEUTRAL
    score, _ = factors.heat_score(100.0, 0.0, pd.Series([100.0]))
    assert 0.0 <= score <= 1.0


def test_momentum_score_with_panel():
    panel = pd.Series([-0.1, 0.0, 0.1])
    score, _ = factors.momentum_score(0.05, panel)
    assert score == pytest.approx(2 / 3)


def test_momentum_score_without_panel():
    assert factors.momentum_score(0.1)[0] == pytest.approx(0.75)
    assert factors.momentum_score(-0.5)[0] == 0.0
    assert factors.momentum_score(0.5)[0] == 1.0


# ---------------- structure_score 合成 ----------------

def test_structure_score_sub_weights(monkeypatch):
    monkeypatch.setattr(factors, "divergence_score", lambda df: (1.0, {}))
    monkeypatch.setattr(factors, "trendline_score", lambda df: (0.5, {}))
    monkeypatch.setattr(factors, "wave_score", lambda df: (0.0, {}))
    score, detail = factors.structure_score(_df())
    # 0.4*1.0 + 0.35*0.5 + 0.25*0.0 = 0.575
    assert score == pytest.approx(0.575)
    assert detail["divergence"]["score"] == 1.0


# ---------------- 原始量 ----------------

def test_ret20_and_amount_avg():
    df = _df(n=60, trend=0.01)
    expected = df["close"].iloc[-1] / df["close"].iloc[-21] - 1
    assert factors.ret20(df) == pytest.approx(expected)
    assert factors.amount_avg(df, 20) == pytest.approx(
        df["amount"].tail(20).mean()
    )
    assert np.isnan(factors.ret20(_df(10)))
