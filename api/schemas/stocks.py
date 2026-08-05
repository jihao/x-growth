from pydantic import BaseModel, Field


class StockItem(BaseModel):
    ts_code: str
    name: str


class Bar(BaseModel):
    date: str
    open: float
    high: float
    low: float
    close: float
    volume: int
    amount: float


class DailyResponse(BaseModel):
    ts_code: str
    bars: list[Bar] = Field(default_factory=list)
