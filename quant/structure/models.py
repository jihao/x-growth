"""结构分析数据结构。"""
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


@dataclass
class WaveLeg:
    start_date: Any
    end_date: Any
    start_price: float
    end_price: float
    bars: int
    speed: float
    ret: float


@dataclass
class WaveTriple:
    direction: str  # "up" | "down"
    pivots: list[Any]  # 4 个 (date, price, kind)
    legs: list[WaveLeg]
    ratio: float
    verdict: str  # "extend" | "end" | "similar"


@dataclass
class WaveSpeedResult:
    current: WaveTriple | None = None
    previous_available: bool = False


@dataclass
class DivergenceEvent:
    side: str  # "top" | "bottom"
    status: str  # "pending" | "confirmed"
    p1_date: Any
    p1_price: float
    d1: float
    d1_date: Any
    p2_date: Any
    p2_price: float
    d2: float
    d2_date: Any
    confirm_date: Any | None = None
    confirm_dif: float | None = None
    speed: float = 0.0
    span_bars: int = 0
    level: str = "medium"  # strong | medium | weak
    preferred: bool = False


@dataclass
class DivergenceResult:
    events: list[DivergenceEvent] = field(default_factory=list)
    overlay_events: list[DivergenceEvent] = field(default_factory=list)
    preferred_event: DivergenceEvent | None = None
