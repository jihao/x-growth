from __future__ import annotations

from typing import Any

import pandas as pd

from quant.structure.models import DivergenceEvent, Trendline, WaveTriple


def _fmt_date(value: Any) -> str:
    if value is None:
        return ""
    if hasattr(value, "strftime"):
        return value.strftime("%Y-%m-%d")
    s = str(value)
    if len(s) >= 10 and s[4] == "-":
        return s[:10]
    if len(s) == 8 and s.isdigit():
        return f"{s[:4]}-{s[4:6]}-{s[6:8]}"
    return s[:10]


def serialize_trendline(tl: Trendline, df: pd.DataFrame) -> dict[str, Any]:
    pos = {d: i for i, d in enumerate(df.index)}
    i0 = pos.get(tl.start_date)
    i1 = pos.get(tl.end_date)
    start_price = float(tl.price_at(i0)) if i0 is not None else None
    end_price = float(tl.price_at(i1)) if i1 is not None else None
    return {
        "side": tl.side,
        "score": float(tl.score),
        "touch_count": int(tl.touch_count),
        "start_date": _fmt_date(tl.start_date),
        "end_date": _fmt_date(tl.end_date),
        "start_price": start_price,
        "end_price": end_price,
        "status": tl.status,
        "touch_dates": [_fmt_date(d) for d in tl.touch_dates],
    }


def serialize_wave(triple: WaveTriple | None) -> dict[str, Any] | None:
    if triple is None:
        return None
    pivots = []
    for item in triple.pivots:
        if isinstance(item, (list, tuple)) and len(item) >= 3:
            pivots.append(
                {
                    "date": _fmt_date(item[0]),
                    "price": float(item[1]),
                    "kind": str(item[2]),
                }
            )
    return {
        "direction": triple.direction,
        "verdict": triple.verdict,
        "ratio": float(triple.ratio),
        "pivots": pivots,
    }


def serialize_divergence(ev: DivergenceEvent) -> dict[str, Any]:
    return {
        "side": ev.side,
        "status": ev.status,
        "level": ev.level,
        "preferred": bool(ev.preferred),
        "p1_date": _fmt_date(ev.p1_date),
        "p1_price": float(ev.p1_price),
        "p2_date": _fmt_date(ev.p2_date),
        "p2_price": float(ev.p2_price),
    }
