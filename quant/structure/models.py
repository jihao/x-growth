"""趋势线数据结构。"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class Trendline:
    side: str  # "up" | "down"
    slope: float
    intercept: float
    touch_dates: list[Any]
    touch_count: int
    score: float
    start_date: Any
    end_date: Any
    status: str | None = None
    line_price_today: float | None = None
    distance_pct: float | None = None

    def price_at(self, x: float) -> float:
        return self.slope * float(x) + self.intercept


@dataclass
class TrendlineResult:
    up: list[Trendline] = field(default_factory=list)
    down: list[Trendline] = field(default_factory=list)
    best_up: Trendline | None = None
    best_down: Trendline | None = None
