"""N 字三浪切分与速度比较（课件：第三浪 vs 第一浪）。"""
from __future__ import annotations

import pandas as pd

from quant.structure.models import WaveLeg, WaveTriple, WaveSpeedResult
from quant.structure.swings import detect_swings


def verdict_from_ratio(ratio: float, fast_ratio: float = 1.05, slow_ratio: float = 0.95) -> str:
    if ratio >= fast_ratio:
        return "extend"
    if ratio <= slow_ratio:
        return "end"
    return "similar"


def build_pivots(df: pd.DataFrame, window: int = 5, min_pct: float = 0.01) -> list[tuple]:
    sw = detect_swings(df["high"], df["low"], window=window, min_pct=min_pct)
    raw: list[tuple] = []
    for d in df.index:
        if sw.loc[d, "is_high"]:
            raw.append((d, float(df.loc[d, "high"]), "H"))
        if sw.loc[d, "is_low"]:
            raw.append((d, float(df.loc[d, "low"]), "L"))
    raw.sort(key=lambda x: x[0])
    if not raw:
        return []
    out = [raw[0]]
    for d, p, k in raw[1:]:
        pd0, pp, pk = out[-1]
        if k == pk:
            if (k == "H" and p >= pp) or (k == "L" and p <= pp):
                out[-1] = (d, p, k)
        else:
            out.append((d, p, k))
    return out


def _pos(df: pd.DataFrame, d) -> int:
    return int(df.index.get_loc(d))


def leg_from_pivots(df: pd.DataFrame, a: tuple, b: tuple) -> WaveLeg:
    d0, p0, _ = a
    d1, p1, _ = b
    bars = max(_pos(df, d1) - _pos(df, d0), 1)
    ret = (p1 / p0 - 1.0) if p0 else 0.0
    speed = abs(p1 - p0) / bars
    return WaveLeg(d0, d1, float(p0), float(p1), bars, float(speed), float(ret))


def _triple_from_four(df, pivots4, direction, fast_ratio, slow_ratio) -> WaveTriple | None:
    legs = [
        leg_from_pivots(df, pivots4[0], pivots4[1]),
        leg_from_pivots(df, pivots4[1], pivots4[2]),
        leg_from_pivots(df, pivots4[2], pivots4[3]),
    ]
    if legs[0].speed <= 0 or legs[2].speed <= 0:
        return None
    # 同向：上涨浪1/3 价格上升；下跌下降
    if direction == "up":
        if not (legs[0].end_price > legs[0].start_price and legs[2].end_price > legs[2].start_price):
            return None
    else:
        if not (legs[0].end_price < legs[0].start_price and legs[2].end_price < legs[2].start_price):
            return None
    ratio = legs[2].speed / legs[0].speed
    return WaveTriple(
        direction=direction,
        pivots=list(pivots4),
        legs=legs,
        ratio=float(ratio),
        verdict=verdict_from_ratio(ratio, fast_ratio, slow_ratio),
    )


def find_wave_triples(
    df: pd.DataFrame,
    window: int = 5,
    min_pct: float = 0.01,
    fast_ratio: float = 1.05,
    slow_ratio: float = 0.95,
) -> list[WaveTriple]:
    pivots = build_pivots(df, window=window, min_pct=min_pct)
    triples: list[WaveTriple] = []
    for i in range(len(pivots) - 3):
        four = pivots[i : i + 4]
        kinds = [k for _, _, k in four]
        if kinds == ["L", "H", "L", "H"]:
            t = _triple_from_four(df, four, "up", fast_ratio, slow_ratio)
        elif kinds == ["H", "L", "H", "L"]:
            t = _triple_from_four(df, four, "down", fast_ratio, slow_ratio)
        else:
            continue
        if t is not None:
            triples.append(t)
    triples.sort(key=lambda t: t.pivots[-1][0], reverse=True)
    return triples


def analyze_wave_speed(
    df: pd.DataFrame,
    offset: int = 0,
    window: int = 5,
    min_pct: float = 0.01,
    fast_ratio: float = 1.05,
    slow_ratio: float = 0.95,
) -> WaveSpeedResult:
    triples = find_wave_triples(
        df, window=window, min_pct=min_pct,
        fast_ratio=fast_ratio, slow_ratio=slow_ratio,
    )
    if offset < 0 or offset >= len(triples):
        return WaveSpeedResult(current=None, previous_available=len(triples) > 1)
    return WaveSpeedResult(
        current=triples[offset],
        previous_available=len(triples) > 1,
    )
