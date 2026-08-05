from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from quant.concentration import cache as conc_cache
from quant.market import regime as market_regime

from api.serializers import parse_date_param

router = APIRouter(tags=["market"])


def _jsonable(obj):
    if isinstance(obj, dict):
        return {k: _jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_jsonable(v) for v in obj]
    if hasattr(obj, "item"):
        try:
            return obj.item()
        except Exception:
            pass
    if isinstance(obj, float):
        return float(obj)
    if isinstance(obj, (int, str, bool)) or obj is None:
        return obj
    return str(obj)


@router.get("/market/regime")
def get_regime(date: str | None = Query(default=None)):
    try:
        d = parse_date_param(date)
        if d is None:
            raise HTTPException(status_code=400, detail="需要 date 参数")
        return _jsonable(market_regime.market_regime(d))
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"读取市场环境失败：{exc}") from exc


@router.get("/market/concentration")
def get_concentration(
    start: str | None = Query(default=None),
    end: str | None = Query(default=None),
):
    try:
        s = parse_date_param(start)
        e = parse_date_param(end)
        df = conc_cache.read_series(s, e)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"读取集中度失败：{exc}") from exc
    if df is None or df.empty:
        return []
    rows = []
    for ts, row in df.iterrows():
        date = ts.strftime("%Y-%m-%d") if hasattr(ts, "strftime") else str(ts)[:10]
        item = {"date": date}
        for col, val in row.items():
            item[str(col)] = float(val) if val is not None else None
        rows.append(item)
    return rows
