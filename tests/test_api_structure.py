from __future__ import annotations

from unittest.mock import MagicMock, patch

import pandas as pd
from fastapi.testclient import TestClient

from api.main import app
from quant.structure.models import Trendline, TrendlineResult, WaveSpeedResult

client = TestClient(app)


def test_structure_empty_daily():
    empty = pd.DataFrame(
        columns=["open", "high", "low", "close", "volume", "amount"]
    )
    empty.index = pd.DatetimeIndex([], name="trade_date")
    with patch("api.routes.structure.loader.load_daily", return_value=empty):
        r = client.get("/api/v1/stocks/600519.SH/structure")
    assert r.status_code == 200
    body = r.json()
    assert body["trendlines"] == {"up": [], "down": []}
    assert body["wave"] is None
    assert body["divergences"] == []


def test_structure_serializes_trendline_dates():
    idx = pd.to_datetime(["2026-01-02", "2026-01-03", "2026-01-06", "2026-01-07"])
    df = pd.DataFrame(
        {
            "open": [100.0, 101.0, 102.0, 103.0],
            "high": [102.0, 103.0, 104.0, 105.0],
            "low": [99.0, 100.0, 101.0, 102.0],
            "close": [101.0, 102.0, 103.0, 104.0],
            "volume": [1000, 1100, 1200, 1300],
            "amount": [1e8, 1.1e8, 1.2e8, 1.3e8],
        },
        index=idx,
    )
    df.index.name = "trade_date"
    tl = Trendline(
        side="up",
        slope=1.0,
        intercept=100.0,
        touch_dates=[idx[0], idx[2]],
        touch_count=2,
        score=1.5,
        start_date=idx[0],
        end_date=idx[2],
        status="ok",
    )
    tres = TrendlineResult(up=[tl], down=[], best_up=tl, best_down=None)
    with (
        patch("api.routes.structure.loader.load_daily", return_value=df),
        patch("api.routes.structure.find_trendlines", return_value=tres),
        patch("api.routes.structure.evaluate_breakout", return_value=tres),
        patch(
            "api.routes.structure.analyze_wave_speed",
            return_value=WaveSpeedResult(current=None),
        ),
        patch(
            "api.routes.structure.analyze_divergence",
            return_value=MagicMock(overlay_events=[]),
        ),
    ):
        r = client.get("/api/v1/stocks/600519.SH/structure")
    assert r.status_code == 200
    body = r.json()
    assert body["trendlines"]["up"][0]["start_date"] == "2026-01-02"
    assert body["trendlines"]["up"][0]["end_date"] == "2026-01-06"
    assert body["trendlines"]["up"][0]["start_price"] is not None
