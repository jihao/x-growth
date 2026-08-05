from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from quant.data import loader
from quant.structure.divergence import analyze_divergence
from quant.structure.trendlines import evaluate_breakout, find_trendlines
from quant.structure.waves import analyze_wave_speed

from api.serializers import parse_date_param
from api.serializers_structure import (
    serialize_divergence,
    serialize_trendline,
    serialize_wave,
)

router = APIRouter(tags=["structure"])


@router.get("/stocks/{ts_code}/structure")
def get_structure(
    ts_code: str,
    start: str | None = Query(default=None),
    end: str | None = Query(default=None),
):
    try:
        s = parse_date_param(start)
        e = parse_date_param(end)
        df = loader.load_daily(ts_code, s, e)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"读取日线失败：{exc}") from exc

    if df is None or df.empty:
        return {
            "ts_code": ts_code,
            "trendlines": {"up": [], "down": []},
            "wave": None,
            "divergences": [],
        }

    res = find_trendlines(df, window=5, tol=0.015, top_k=3, min_bars=10)
    x_today = len(df) - 1
    res = evaluate_breakout(res, float(df["close"].iloc[-1]), x_today, tol=0.015)

    wres = analyze_wave_speed(
        df, offset=0, window=5, min_pct=0.01, fast_ratio=1.05, slow_ratio=0.95
    )
    dres = analyze_divergence(
        df, window=5, min_pct=0.01, align_bars=3, confirm_pct=0.05
    )

    return {
        "ts_code": ts_code,
        "trendlines": {
            "up": [serialize_trendline(tl, df) for tl in res.up],
            "down": [serialize_trendline(tl, df) for tl in res.down],
        },
        "wave": serialize_wave(wres.current),
        "divergences": [serialize_divergence(ev) for ev in dres.overlay_events],
    }
