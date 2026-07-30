from pathlib import Path
from unittest.mock import patch

import pandas as pd
from streamlit.testing.v1 import AppTest


APP_FILE = Path(__file__).resolve().parent.parent / "app" / "main.py"


def test_home_stock_selection_sticks_after_rerun():
    stocks = pd.DataFrame(
        {
            "ts_code": ["000001.SZ", "000002.SZ"],
            "name": ["平安银行", "万科A"],
        }
    )

    with (
        patch("quant.data.loader.list_stocks", return_value=stocks),
        patch("quant.data.loader.load_daily", return_value=pd.DataFrame()),
        patch("quant.concentration.cache.read_series", return_value=pd.DataFrame()),
        patch("quant.favorites.store.ensure_table"),
        patch("quant.favorites.store.is_favorite", return_value=False),
    ):
        app = AppTest.from_file(str(APP_FILE), default_timeout=10).run()
        assert not app.exception

        stock = next(widget for widget in app.selectbox if widget.label == "股票")
        stock.select("000002.SZ  万科A").run()

        stock = next(widget for widget in app.selectbox if widget.label == "股票")
        assert stock.value == "000002.SZ  万科A"
        assert app.session_state["ts_code"] == "000002.SZ"
