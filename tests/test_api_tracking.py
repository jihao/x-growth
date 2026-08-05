from __future__ import annotations

from unittest.mock import patch

import pandas as pd
from fastapi.testclient import TestClient

from api.main import app

client = TestClient(app)


def test_tracking_review():
    df = pd.DataFrame([{"ts_code": "600519.SH", "ret_20": 0.1}])
    with patch(
        "api.routes.tracking.tracking.review_date",
        return_value=(df, {"n": 1}),
    ):
        r = client.get("/api/v1/tracking/review", params={"date": "2026-08-01"})
    assert r.status_code == 200
    body = r.json()
    assert body["stats"]["n"] == 1
    assert body["rows"][0]["ts_code"] == "600519.SH"


def test_tracking_stock():
    with patch(
        "api.routes.tracking.tracking.track_pick",
        return_value={"ts_code": "600519.SH", "ret_20": 0.05},
    ):
        r = client.get(
            "/api/v1/tracking/stock",
            params={"date": "2026-08-01", "ts_code": "600519.SH"},
        )
    assert r.status_code == 200
    assert r.json()["ret_20"] == 0.05
