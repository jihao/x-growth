from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from quant.screening import weights


def _df(n: int = 150) -> pd.DataFrame:
    idx = pd.date_range("2026-01-01", periods=n, freq="B", name="trade_date")
    close = 10 * 1.001 ** np.arange(n)
    return pd.DataFrame(
        {"open": close, "high": close, "low": close, "close": close,
         "volume": 1000, "amount": close * 1000},
        index=idx,
    )


def _patch_sharpes(monkeypatch, sharpes: list[float]):
    """按 REGISTRY 顺序依次返回给定夏普。"""
    monkeypatch.setattr(weights.engine, "run", lambda df, sig, cost=0.0003: object())
    it = iter(sharpes)
    monkeypatch.setattr(
        weights.metrics, "performance",
        lambda res: {"sharpe": next(it)},
    )


def test_dynamic_weights_insufficient_data_equal():
    w, detail = weights.dynamic_strategy_weights(_df(30))
    assert len(w) == 5
    assert all(v == pytest.approx(1 / 5) for v in w.values())
    assert detail["fallback"] == "insufficient_data"


def test_dynamic_weights_sharpe_normalized(monkeypatch):
    _patch_sharpes(monkeypatch, [1.0, 2.0, -1.0, 0.0, 3.0])
    w, detail = weights.dynamic_strategy_weights(_df())
    assert w["ma_cross"] == pytest.approx(1 / 6)
    assert w["macd"] == pytest.approx(2 / 6)
    assert w["bollinger"] == pytest.approx(0.0)   # 负夏普截断为 0
    assert w["rsi"] == pytest.approx(0.0)
    assert w["donchian"] == pytest.approx(3 / 6)
    assert sum(w.values()) == pytest.approx(1.0)
    assert detail["sharpe"]["macd"] == pytest.approx(2.0)


def test_dynamic_weights_all_non_positive_fallback(monkeypatch):
    _patch_sharpes(monkeypatch, [-1.0, -2.0, 0.0, -0.5, -3.0])
    w, detail = weights.dynamic_strategy_weights(_df())
    assert all(v == pytest.approx(1 / 5) for v in w.values())
    assert detail["fallback"] == "all_non_positive"


def test_normalize_group_weights_default_and_override():
    assert weights.normalize_group_weights(None) == weights.DEFAULT_GROUP_WEIGHTS
    w = weights.normalize_group_weights({"strategy": 0.8})
    assert sum(w.values()) == pytest.approx(1.0)
    assert w["strategy"] == pytest.approx(0.8 / (0.8 + 0.35 + 0.25))
    assert weights.normalize_group_weights(
        {"strategy": 0, "structure": 0, "volume": 0}
    ) == weights.DEFAULT_GROUP_WEIGHTS


def test_combine_scores_weighted_sum():
    total = weights.combine_scores(
        {"strategy": 1.0, "structure": 0.0, "volume": 0.5}
    )
    # 0.4*1 + 0.35*0 + 0.25*0.5
    assert total == pytest.approx(0.525)


def test_combine_scores_missing_group_defaults_neutral():
    total = weights.combine_scores({"strategy": 1.0})
    assert total == pytest.approx(0.4 * 1.0 + 0.35 * 0.5 + 0.25 * 0.5)


def test_combine_scores_ml_boost_hook():
    base = weights.combine_scores(
        {"strategy": 1.0, "structure": 0.0, "volume": 0.5}
    )
    boosted = weights.combine_scores(
        {"strategy": 1.0, "structure": 0.0, "volume": 0.5}, ml_boost=0.1
    )
    assert boosted == pytest.approx(base * 1.1)
