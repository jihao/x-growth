from __future__ import annotations

import json

from fastapi import APIRouter, HTTPException, Query

from quant.screening import explain as screening_explain
from quant.screening import llm as screening_llm
from quant.screening import store as screening_store

from api.serializers import parse_date_param

router = APIRouter(tags=["screening"])


def _row_to_dict(row) -> dict:
    out = {}
    for key, value in row.items():
        if hasattr(value, "item"):
            try:
                value = value.item()
            except Exception:
                value = str(value)
        if isinstance(value, str) and key.endswith("_json"):
            try:
                value = json.loads(value)
            except Exception:
                pass
        out[str(key)] = value
    return out


@router.get("/screening/dates")
def screening_dates():
    try:
        dates = screening_store.list_dates()
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"读取选股日期失败：{exc}") from exc
    return [
        f"{d[:4]}-{d[4:6]}-{d[6:8]}" if len(d) == 8 and d.isdigit() else d for d in dates
    ]


@router.get("/screening/results")
def screening_results(date: str = Query(...)):
    try:
        d = parse_date_param(date)
        df = screening_store.load_results(d)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"读取选股结果失败：{exc}") from exc
    if df is None or df.empty:
        return []
    return [_row_to_dict(row) for _, row in df.iterrows()]


@router.get("/screening/explain")
def screening_explain_api(
    date: str = Query(...),
    ts_code: str = Query(...),
    deep: int = Query(default=0),
):
    try:
        d = parse_date_param(date)
        df = screening_store.load_results(d)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"读取选股结果失败：{exc}") from exc
    if df is None or df.empty:
        raise HTTPException(status_code=404, detail="该日无选股结果")
    hit = df[df["ts_code"] == ts_code]
    if hit.empty:
        raise HTTPException(status_code=404, detail="该股未入选该日榜单")
    row = _row_to_dict(hit.iloc[0])
    explained = screening_explain.explain_row(row)
    if deep:
        if not screening_llm.is_configured():
            raise HTTPException(status_code=400, detail="LLM 未配置")
        try:
            deep_text = screening_llm.explain_with_llm(explained)
        except Exception as exc:
            raise HTTPException(status_code=502, detail=f"LLM 解读失败：{exc}") from exc
        explained = {**explained, "llm": deep_text}
    return explained
