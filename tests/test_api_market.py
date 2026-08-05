from __future__ import annotations

from unittest.mock import patch

import pandas as pd
from fastapi.testclient import TestClient

from api.main import app

client = TestClient(app)


def test_market_regime():
    with patch(
        "api.routes.market.market_regime.market_regime",
        return_value={"date": "20260801", "score": 0.5, "level": "中性", "summary": "ok"},
    ):
        r = client.get("/api/v1/market/regime", params={"date": "2026-08-01"})
    assert r.status_code == 200
    assert r.json()["level"] == "中性"


def test_concentration_empty():
    empty = pd.DataFrame()
    with patch("api.routes.market.conc_cache.read_series", return_value=empty):
        r = client.get("/api/v1/market/concentration")
    assert r.status_code == 200
    assert r.json() == []
