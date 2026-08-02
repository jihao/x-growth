from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from quant.screening import pipeline


def _daily(n: int = 120) -> pd.DataFrame:
    idx = pd.date_range("2026-01-01", periods=n, freq="B", name="trade_date")
    close = 10 * 1.005 ** np.arange(n)
    return pd.DataFrame(
        {"open": close, "high": close * 1.01, "low": close * 0.99,
         "close": close, "volume": 1000, "amount": close * 1000},
        index=idx,
    )


def _cross() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "ts_code": ["600519.SH", "600000.SH", "000001.SZ",
                        "600666.SH", "300999.SZ"],
            "name": ["贵州茅台", "浦发银行", "平安银行", "ST 示例", "停牌示例"],
            "close": [1500.0, 10.0, 12.0, 5.0, 20.0],
            "volume": [100000, 200000, 150000, 80000, 0],
            "amount": [1.5e9, 8e8, 6e8, 5e8, 9e8],
        }
    )


@pytest.fixture
def _patched(monkeypatch):
    monkeypatch.setattr(pipeline, "_latest_trade_date", lambda: "20260731")
    monkeypatch.setattr(
        pipeline.loader, "load_cross_section", lambda d: _cross()
    )
    monkeypatch.setattr(
        pipeline.loader, "load_daily",
        lambda ts_code, start=None, end=None: _daily(),
    )
    monkeypatch.setattr(
        pipeline.weights, "dynamic_strategy_weights",
        lambda df: ({"ma_cross": 1.0}, {"sharpe": {"ma_cross": 1.0}}),
    )
    monkeypatch.setattr(
        pipeline.factors, "strategy_score",
        lambda df, w=None: (0.9, {"ma_cross": {"signal": 1}}),
    )
    monkeypatch.setattr(
        pipeline.factors, "structure_score",
        lambda df: (0.8, {"divergence": {"score": 0.8}}),
    )


def test_run_filters_and_ranks(_patched):
    out = pipeline.run(top_n_volume=250, top_k=10)
    assert list(out.columns) == pipeline._RESULT_COLS
    # ST 与停牌被剔除，剩 3 只
    assert set(out["ts_code"]) == {"600519.SH", "600000.SH", "000001.SZ"}
    assert list(out["rank_no"]) == [1, 2, 3]
    assert out["total_score"].is_monotonic_decreasing
    assert all(0.0 <= s <= 1.0 for s in out["total_score"])


def test_run_respects_top_k_and_top_n(_patched):
    out = pipeline.run(top_n_volume=2, top_k=1)
    assert len(out) == 1
    # 过滤后成交额前二为茅台/浦发，top_k=1 取总分第一
    assert out.iloc[0]["rank_no"] == 1


def test_run_progress_callback(_patched):
    seen = []
    pipeline.run(top_n_volume=250, top_k=10,
                 progress_cb=lambda i, n, code: seen.append(code))
    assert len(seen) == 3


def test_run_empty_cross_raises(monkeypatch):
    monkeypatch.setattr(pipeline, "_latest_trade_date", lambda: "20260731")
    monkeypatch.setattr(
        pipeline.loader, "load_cross_section", lambda d: pd.DataFrame()
    )
    with pytest.raises(RuntimeError):
        pipeline.run()


def test_filter_universe_rules():
    out = pipeline._filter_universe(_cross(), top_n_volume=250)
    assert set(out["ts_code"]) == {"600519.SH", "600000.SH", "000001.SZ"}
    top1 = pipeline._filter_universe(_cross(), top_n_volume=1)
    assert list(top1["ts_code"]) == ["600519.SH"]


def test_start_for_400_calendar_days():
    start = pipeline._start_for("20260731")
    delta = pd.Timestamp("2026-07-31") - pd.Timestamp(start)
    assert delta.days == 400
