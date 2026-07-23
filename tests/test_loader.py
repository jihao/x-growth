import pandas as pd

from quant.data import loader


def test_normalize_daily_sorts_and_types():
    raw = pd.DataFrame(
        {
            "trade_date": ["20100104", "20100105"],
            "open": ["1.0", "2.0"],
            "high": ["1.5", "2.5"],
            "low": ["0.5", "1.5"],
            "close": ["1.2", "2.2"],
            "volume": [100, 200],
            "amount": ["1000.0", "2000.0"],
        }
    )
    out = loader._normalize_daily(raw)
    assert list(out.columns) == ["open", "high", "low", "close", "volume", "amount"]
    assert str(out.index.dtype).startswith("datetime64")
    assert out.index.is_monotonic_increasing
    assert out["close"].dtype == float
    assert out.iloc[0]["close"] == 1.2


def test_normalize_daily_empty():
    assert loader._normalize_daily(pd.DataFrame()).empty
