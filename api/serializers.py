"""DataFrame / 日期 → API JSON。"""
from __future__ import annotations

from typing import Any

import pandas as pd

from quant import config


def parse_date_param(value: str | None) -> str | None:
    if value is None or value == "":
        return None
    return config.fmt_date(value)


def bars_from_daily(df: pd.DataFrame) -> list[dict[str, Any]]:
    if df is None or df.empty:
        return []
    out: list[dict[str, Any]] = []
    for ts, row in df.iterrows():
        date = ts.strftime("%Y-%m-%d") if hasattr(ts, "strftime") else str(ts)[:10]
        out.append(
            {
                "date": date,
                "open": float(row["open"]),
                "high": float(row["high"]),
                "low": float(row["low"]),
                "close": float(row["close"]),
                "volume": int(row["volume"]),
                "amount": float(row["amount"]),
            }
        )
    return out
