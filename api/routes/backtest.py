from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from quant.backtest import engine, metrics
from quant.backtest.strategies import REGISTRY, get
from quant.data import loader

from api.serializers import bars_from_daily, parse_date_param

router = APIRouter(tags=["backtest"])


class BacktestRequest(BaseModel):
    strategy: str = Field(..., description="REGISTRY key, e.g. ma_cross")
    start: str | None = None
    end: str | None = None


@router.get("/strategies")
def list_strategies():
    return [
        {"name": s.name, "label": s.label, "default_params": s.default_params}
        for s in REGISTRY.values()
    ]


@router.post("/stocks/{ts_code}/backtest")
def run_backtest(ts_code: str, body: BacktestRequest):
    try:
        strategy = get(body.strategy)
    except KeyError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    try:
        s = parse_date_param(body.start)
        e = parse_date_param(body.end)
        df = loader.load_daily(ts_code, s, e)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"读取日线失败：{exc}") from exc
    if df is None or df.empty:
        raise HTTPException(status_code=400, detail="该区间无日线数据")
    signal = strategy.generate(df)
    result = engine.run(df, signal)
    perf = metrics.performance(result)

    def series_points(series):
        out = []
        for ts, value in series.items():
            date = ts.strftime("%Y-%m-%d") if hasattr(ts, "strftime") else str(ts)[:10]
            out.append({"date": date, "value": float(value)})
        return out

    trades = []
    for t in result.trades:
        trades.append(
            {
                "entry": str(t["entry"])[:10],
                "exit": str(t["exit"])[:10],
                "entry_px": float(t["entry_px"]),
                "exit_px": float(t["exit_px"]),
                "ret": float(t["ret"]),
            }
        )
    return {
        "ts_code": ts_code,
        "strategy": body.strategy,
        "metrics": {k: (None if v == float("inf") else float(v)) for k, v in perf.items()},
        "equity": series_points(result.equity),
        "benchmark": series_points(result.benchmark),
        "trades": trades,
        "bars": bars_from_daily(df),
    }
