from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from quant.favorites import store as fav_store

router = APIRouter(tags=["favorites"])


class FavoriteBody(BaseModel):
    ts_code: str = Field(..., min_length=1)


@router.get("/favorites")
def list_favorites():
    try:
        df = fav_store.list_favorites()
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"读取收藏失败：{exc}") from exc
    if df is None or df.empty:
        return []
    rows = []
    for r in df.itertuples(index=False):
        rows.append(
            {
                "ts_code": str(r.ts_code),
                "name": str(r.name) if r.name is not None else "",
                "created_at": str(r.created_at),
            }
        )
    return rows


@router.post("/favorites")
def add_favorite(body: FavoriteBody):
    try:
        fav_store.add(body.ts_code)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"添加收藏失败：{exc}") from exc
    return {"ok": True}


@router.delete("/favorites/{ts_code}")
def remove_favorite(ts_code: str):
    try:
        fav_store.remove(ts_code)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"取消收藏失败：{exc}") from exc
    return {"ok": True}
