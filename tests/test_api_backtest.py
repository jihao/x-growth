from __future__ import annotations

from unittest.mock import MagicMock, patch

import pandas as pd
from fastapi.testclient import TestClient

from api.main import app
from quant.backtest.engine import BacktestResult

client = TestClient(app)


def test_list_strategies():
    r = client.get("/api/v1/strategies")
    assert r.status_code == 200
    names = {item["name"] for item in r.json()}
    assert "ma_cross" in names


def test_backtest_unknown_strategy():
    r = client.post("/api/v1/stocks/600519.SH/backtest", json={"strategy": "nope"})
    assert r.status_code == 400


def test_backtest_ok():
    idx = pd.to_datetime(["2026-01-02", "2026-01-03", "2026-01-06"])
    df = pd.DataFrame(
        {
            "open": [100.0, 101.0, 102.0],
            "high": [102.0, 103.0, 104.0],
            "low": [99.0, 100.0, 101.0],
            "close": [101.0, 102.0, 103.0],
            "volume": [1000, 1100, 1200],
            "amount": [1e8, 1.1e8, 1.2e8],
        },
        index=idx,
    )
    equity = pd.Series([1.0, 1.01, 1.02], index=idx)
    result = BacktestResult(
        equity=equity,
        position=pd.Series([0.0, 1.0, 1.0], index=idx),
        strat_ret=pd.Series([0.0, 0.01, 0.01], index=idx),
        benchmark=equity.copy(),
        trades=[],
    )
    strat = MagicMock()
    strat.generate.return_value = pd.Series([0.0, 1.0, 1.0], index=idx)
    with (
        patch("api.routes.backtest.get", return_value=strat),
        patch("api.routes.backtest.loader.load_daily", return_value=df),
        patch("api.routes.backtest.engine.run", return_value=result),
        patch(
            "api.routes.backtest.metrics.performance",
            return_value={
                "total_return": 0.02,
                "ann_return": 0.1,
                "ann_vol": 0.2,
                "sharpe": 1.0,
                "max_drawdown": -0.01,
                "win_rate": 0.5,
                "profit_factor": 1.2,
                "num_trades": 0,
                "bench_total_return": 0.02,
            },
        ),
    ):
        r = client.post(
            "/api/v1/stocks/600519.SH/backtest",
            json={"strategy": "ma_cross", "start": "2026-01-01", "end": "2026-01-31"},
        )
    assert r.status_code == 200
    body = r.json()
    assert body["metrics"]["total_return"] == 0.02
    assert len(body["equity"]) == 3
