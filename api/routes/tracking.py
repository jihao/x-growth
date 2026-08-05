from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from quant.screening import tracking

from api.serializers import parse_date_param

router = APIRouter(tags=["tracking"])


def _jsonable(obj):
    if isinstance(obj, dict):
        return {k: _jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_jsonable(v) for v in obj]
    if hasattr(obj, "to_dict"):
        return _jsonable(obj.to_dict(orient="records"))
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


@router.get("/tracking/review")
def tracking_review(date: str = Query(...)):
    try:
        d = parse_date_param(date)
        df, stats = tracking.review_date(d, with_stats=True)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"跟踪复盘失败：{exc}") from exc
    rows = []
    if df is not None and not df.empty:
        rows = _jsonable(df.to_dict(orient="records"))
    return {"date": d, "rows": rows, "stats": _jsonable(stats)}


@router.get("/tracking/stock")
def tracking_stock(date: str = Query(...), ts_code: str = Query(...)):
    try:
        d = parse_date_param(date)
        result = tracking.track_pick(d, ts_code)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"个股跟踪失败：{exc}") from exc
    return _jsonable(result)
