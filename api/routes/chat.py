from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from quant.screening import llm as screening_llm

router = APIRouter(tags=["chat"])


class ChatBody(BaseModel):
    message: str = Field(..., min_length=1)


@router.post("/chat")
def chat(body: ChatBody):
    if not screening_llm.is_configured():
        raise HTTPException(status_code=400, detail="LLM 未配置")
    try:
        text = screening_llm.chat(
            [{"role": "user", "content": body.message}]
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"对话失败：{exc}") from exc
    return {"reply": text}
