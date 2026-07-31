from __future__ import annotations

import re

from quant.calendar.cn_holidays import load_holidays
from quant.charts import plots


def test_load_holidays_years_and_format():
    holidays = load_holidays()
    assert len(holidays) >= 100
    years = {int(d[:4]) for d in holidays}
    assert years >= set(range(2020, 2027))
    for d in holidays:
        assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", d)


def test_load_holidays_has_new_year_samples():
    holidays = set(load_holidays())
    assert "2020-01-01" in holidays
    assert "2024-01-01" in holidays
    assert "2026-01-01" in holidays


def test_kline_rangebreaks_hide_weekend_and_holidays():
    import numpy as np
    import pandas as pd

    idx = pd.date_range("2024-01-01", periods=30, freq="B")
    df = pd.DataFrame(
        {
            "open": np.linspace(10, 12, len(idx)),
            "high": np.linspace(10.5, 12.5, len(idx)),
            "low": np.linspace(9.5, 11.5, len(idx)),
            "close": np.linspace(10.2, 12.2, len(idx)),
            "volume": np.arange(len(idx)) + 100,
            "amount": np.arange(len(idx)) + 1000.0,
        },
        index=idx,
    )
    fig = plots.kline_chart(df, overlays=(), sub=())
    # subplot shared axes: check first xaxis rangebreaks
    breaks = fig.layout.xaxis.rangebreaks
    assert breaks is not None and len(breaks) >= 2
    weekend = next(b for b in breaks if getattr(b, "bounds", None))
    assert list(weekend.bounds) == ["sat", "mon"]
    holiday_break = next(b for b in breaks if getattr(b, "values", None))
    assert "2024-01-01" in list(holiday_break.values)
