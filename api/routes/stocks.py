from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from quant.data import loader

from api.schemas.stocks import DailyResponse, StockItem
from api.serializers import bars_from_daily, parse_date_param

router = APIRouter(tags=["stocks"])


@router.get("/stocks", response_model=list[StockItem])
def list_stocks():
    try:
        df = loader.list_stocks()
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"读取股票列表失败：{exc}") from exc
    if df is None or df.empty:
        return []
    return [
        StockItem(ts_code=str(r.ts_code), name=str(r.name))
        for r in df.itertuples(index=False)
    ]


@router.get("/stocks/{ts_code}/daily", response_model=DailyResponse)
def get_daily(
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
    return DailyResponse(ts_code=ts_code, bars=bars_from_daily(df))
