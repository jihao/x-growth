from __future__ import annotations

from unittest.mock import patch

import pandas as pd
from fastapi.testclient import TestClient

from api.main import app

client = TestClient(app)


def test_favorites_list_add_delete():
    df = pd.DataFrame(
        [{"ts_code": "600519.SH", "name": "贵州茅台", "created_at": "2026-08-01"}]
    )
    with patch("api.routes.favorites.fav_store.list_favorites", return_value=df):
        r = client.get("/api/v1/favorites")
    assert r.status_code == 200
    assert r.json()[0]["ts_code"] == "600519.SH"

    with patch("api.routes.favorites.fav_store.add") as add:
        r = client.post("/api/v1/favorites", json={"ts_code": "600519.SH"})
    assert r.status_code == 200
    add.assert_called_once_with("600519.SH")

    with patch("api.routes.favorites.fav_store.remove") as remove:
        r = client.delete("/api/v1/favorites/600519.SH")
    assert r.status_code == 200
    remove.assert_called_once_with("600519.SH")
