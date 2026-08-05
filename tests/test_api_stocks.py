from __future__ import annotations

from unittest.mock import patch

import pandas as pd
from fastapi.testclient import TestClient

from api.main import app

client = TestClient(app)


def test_list_stocks_ok():
    df = pd.DataFrame([{"ts_code": "600519.SH", "name": "贵州茅台"}])
    with patch("api.routes.stocks.loader.list_stocks", return_value=df):
        r = client.get("/api/v1/stocks")
    assert r.status_code == 200
    assert r.json() == [{"ts_code": "600519.SH", "name": "贵州茅台"}]


def test_daily_bars_ok():
    idx = pd.to_datetime(["2026-01-02", "2026-01-03"])
    df = pd.DataFrame(
        {
            "open": [100.0, 101.0],
            "high": [102.0, 103.0],
            "low": [99.0, 100.0],
            "close": [101.0, 102.0],
            "volume": [1000, 1100],
            "amount": [1e8, 1.1e8],
        },
        index=idx,
    )
    df.index.name = "trade_date"
    with patch("api.routes.stocks.loader.load_daily", return_value=df) as m:
        r = client.get(
            "/api/v1/stocks/600519.SH/daily",
            params={"start": "2026-01-01", "end": "2026-01-31"},
        )
    assert r.status_code == 200
    body = r.json()
    assert body["ts_code"] == "600519.SH"
    assert len(body["bars"]) == 2
    assert body["bars"][0]["date"] == "2026-01-02"
    assert body["bars"][0]["close"] == 101.0
    m.assert_called_once()
    args = m.call_args[0]
    assert args[0] == "600519.SH"
    assert args[1] == "20260101"
    assert args[2] == "20260131"


def test_daily_empty():
    empty = pd.DataFrame(
        columns=["open", "high", "low", "close", "volume", "amount"]
    )
    empty.index = pd.DatetimeIndex([], name="trade_date")
    with patch("api.routes.stocks.loader.load_daily", return_value=empty):
        r = client.get("/api/v1/stocks/600519.SH/daily")
    assert r.status_code == 200
    assert r.json()["bars"] == []
