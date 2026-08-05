from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routes import backtest, chat, favorites, market, screening, stocks, structure, tracking

app = FastAPI(title="x-growth API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

for module in (stocks, structure, backtest, favorites, market, screening, tracking, chat):
    app.include_router(module.router, prefix="/api/v1")


@app.get("/health")
def health():
    return {"ok": True}
