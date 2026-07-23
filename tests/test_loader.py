import pandas as pd

from quant.data import loader


def test_normalize_daily_sorts_and_types():
    raw = pd.DataFrame(
        {
            "trade_date": ["20100105", "20100104"],
            "open": ["2.0", "1.0"],
            "high": ["2.5", "1.5"],
            "low": ["1.5", "0.5"],
            "close": ["2.2", "1.2"],
            "volume": [200, 100],
            "amount": ["2000.0", "1000.0"],
        }
    )
    out = loader._normalize_daily(raw)
    assert list(out.columns) == loader._DAILY_COLS
    assert str(out.index.dtype).startswith("datetime64")
    assert out.index.name == "trade_date"
    assert out.index.is_monotonic_increasing
    assert out["close"].dtype == float
    assert out.iloc[0]["close"] == 1.2
    assert out.iloc[1]["close"] == 2.2
    assert out.index[0] == pd.Timestamp("2010-01-04")
    assert out.index[1] == pd.Timestamp("2010-01-05")


def test_normalize_daily_empty():
    out = loader._normalize_daily(pd.DataFrame())
    assert out.empty
    assert list(out.columns) == loader._DAILY_COLS
    assert isinstance(out.index, pd.DatetimeIndex)
    assert out.index.name == "trade_date"
