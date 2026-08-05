from __future__ import annotations

from unittest.mock import patch

import pandas as pd
from fastapi.testclient import TestClient

from api.main import app

client = TestClient(app)


def test_screening_dates_and_results():
    with patch("api.routes.screening.screening_store.list_dates", return_value=["20260801"]):
        r = client.get("/api/v1/screening/dates")
    assert r.status_code == 200
    assert r.json() == ["2026-08-01"]

    df = pd.DataFrame([{"ts_code": "600519.SH", "total_score": 0.8}])
    with patch("api.routes.screening.screening_store.load_results", return_value=df):
        r = client.get("/api/v1/screening/results", params={"date": "2026-08-01"})
    assert r.status_code == 200
    assert r.json()[0]["ts_code"] == "600519.SH"


def test_explain_llm_not_configured():
    df = pd.DataFrame([{"ts_code": "600519.SH", "total_score": 0.8}])
    with (
        patch("api.routes.screening.screening_store.load_results", return_value=df),
        patch("api.routes.screening.screening_explain.explain_row", return_value={"ok": True}),
        patch("api.routes.screening.screening_llm.is_configured", return_value=False),
    ):
        r = client.get(
            "/api/v1/screening/explain",
            params={"date": "2026-08-01", "ts_code": "600519.SH", "deep": 1},
        )
    assert r.status_code == 400
