"""自动趋势线：两点连线穷举、触点计数、打分、收盘破位。"""
from __future__ import annotations

from itertools import combinations

import pandas as pd

from quant.structure.models import Trendline, TrendlineResult
from quant.structure.swings import detect_swings


def find_trendlines(
    df: pd.DataFrame,
    window: int = 5,
    min_pct: float = 0.01,
    tol: float = 0.015,
    min_bars: int = 10,
    top_k: int = 3,
) -> TrendlineResult:
    high, low = df["high"].astype(float), df["low"].astype(float)
    sw = detect_swings(high, low, window=window, min_pct=min_pct)
    pos = {d: i for i, d in enumerate(df.index)}
    last_pos = len(df) - 1

    def fit(points: list[tuple], side: str) -> list[Trendline]:
        cands: list[Trendline] = []
        for (i1, p1, d1), (i2, p2, d2) in combinations(points, 2):
            if abs(i2 - i1) < min_bars:
                continue
            slope = (p2 - p1) / (i2 - i1)
            # 上升线必须斜率为正（抬高低点）；下降线必须斜率为负（降低高点）
            if side == "up" and slope <= 0:
                continue
            if side == "down" and slope >= 0:
                continue
            intercept = p1 - slope * i1
            touches, touch_pos = [], []
            for i, p, d in points:
                if abs(p) < 1e-12:
                    continue
                line_p = slope * i + intercept
                if abs(p - line_p) / abs(p) <= tol:
                    touches.append(d)
                    touch_pos.append(i)
            if len(touches) < 2:
                continue
            span = abs(i2 - i1)
            recent = any(last_pos - i <= 60 for i in touch_pos)
            score = len(touches) * 10 + span * 0.01 + (5.0 if recent else 0.0)
            start, end = (d1, d2) if i1 < i2 else (d2, d1)
            cands.append(
                Trendline(
                    side=side,
                    slope=float(slope),
                    intercept=float(intercept),
                    touch_dates=touches,
                    touch_count=len(touches),
                    score=float(score),
                    start_date=start,
                    end_date=end,
                )
            )
        cands.sort(key=lambda t: (t.score, t.touch_count), reverse=True)
        return cands

    low_pts = [(pos[d], float(low.loc[d]), d) for d in df.index[sw["is_low"]]]
    high_pts = [(pos[d], float(high.loc[d]), d) for d in df.index[sw["is_high"]]]
    up = fit(low_pts, "up")[:top_k]
    down = fit(high_pts, "down")[:top_k]
    return TrendlineResult(
        up=up,
        down=down,
        best_up=up[0] if up else None,
        best_down=down[0] if down else None,
    )


def evaluate_breakout(
    result: TrendlineResult,
    close_today: float,
    x_today: int,
    tol: float = 0.015,
) -> TrendlineResult:
    def upd(tl: Trendline | None, side: str) -> Trendline | None:
        if tl is None:
            return None
        line_p = tl.price_at(x_today)
        dist = (close_today - line_p) / line_p if line_p else 0.0
        if side == "up":
            status = "broken" if close_today < line_p * (1 - tol) else "above"
        else:
            status = "broken" if close_today > line_p * (1 + tol) else "below"
        return Trendline(
            side=tl.side,
            slope=tl.slope,
            intercept=tl.intercept,
            touch_dates=list(tl.touch_dates),
            touch_count=tl.touch_count,
            score=tl.score,
            start_date=tl.start_date,
            end_date=tl.end_date,
            status=status,
            line_price_today=float(line_p),
            distance_pct=float(dist),
        )

    best_up = upd(result.best_up, "up")
    best_down = upd(result.best_down, "down")
    up = ([best_up] + list(result.up[1:])) if best_up is not None and result.up else list(result.up)
    down = (
        [best_down] + list(result.down[1:])
        if best_down is not None and result.down
        else list(result.down)
    )
    return TrendlineResult(up=up, down=down, best_up=best_up, best_down=best_down)
