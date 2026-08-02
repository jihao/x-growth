"""选股因子打分器：纯计算，输入日线 DataFrame，输出 0~1 标准化分数与明细。

分数语义统一为「越大越值得关注」，中性（无信号/数据不足）一律 0.5。
结构类因子复用 quant.structure 的浪型/背离/趋势线分析。
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from quant.backtest import strategies
from quant.structure.divergence import analyze_divergence
from quant.structure.trendlines import evaluate_breakout, find_trendlines
from quant.structure.waves import analyze_wave_speed

NEUTRAL = 0.5

# 背离事件「级别 × 状态 × 新鲜度」的折算系数
_LEVEL_W = {"strong": 1.0, "medium": 0.7, "weak": 0.4}
_STATUS_W = {"confirmed": 1.0, "pending": 0.5}
# 结构组内部子权重
STRUCTURE_SUB_WEIGHTS = {"divergence": 0.4, "trendline": 0.35, "wave": 0.25}
# 浪型结论映射：(direction, verdict) -> 分数
_WAVE_SCORE = {
    ("up", "extend"): 1.0,
    ("up", "similar"): 0.7,
    ("up", "end"): 0.4,
    ("down", "end"): 0.6,
    ("down", "similar"): 0.3,
    ("down", "extend"): 0.0,
}


def _clip01(x: float) -> float:
    return float(min(max(x, 0.0), 1.0))


def strategy_score(df: pd.DataFrame, weights: dict | None = None) -> tuple[float, dict]:
    """各策略最新目标仓位（持仓=1）按权重加权和。weights 缺省等权。"""
    names = list(strategies.REGISTRY)
    if not names or df.empty:
        return NEUTRAL, {}
    if weights is None:
        weights = {n: 1.0 / len(names) for n in names}
    total_w = sum(weights.get(n, 0.0) for n in names) or 1.0
    detail, score = {}, 0.0
    for name in names:
        strat = strategies.get(name)
        sig = strat.generate(df)
        holding = int(sig.iloc[-1] >= 0.5) if len(sig) else 0
        w = float(weights.get(name, 0.0)) / total_w
        score += w * holding
        detail[name] = {"signal": holding, "weight": round(w, 4)}
    return _clip01(score), detail


def divergence_score(df: pd.DataFrame, recent_bars: int = 60) -> tuple[float, dict]:
    """近期 DIF 背离：底背离加分、顶背离减分，级别越高、越近影响越大。"""
    if df.empty:
        return NEUTRAL, {}
    res = analyze_divergence(df)
    n = len(df.index)
    best = {"bottom": 0.0, "top": 0.0}
    chosen: dict[str, dict] = {}
    for ev in res.events:
        try:
            bars_since = n - 1 - int(df.index.get_loc(ev.p2_date))
        except KeyError:
            continue
        if bars_since < 0 or bars_since > recent_bars:
            continue
        recency_w = 1.0 - 0.5 * (bars_since / recent_bars)
        mag = _LEVEL_W.get(ev.level, 0.7) * _STATUS_W.get(ev.status, 0.5) * recency_w
        side = ev.side if ev.side in best else None
        if side and mag > best[side]:
            best[side] = mag
            chosen[side] = {
                "status": ev.status,
                "level": ev.level,
                "p2_date": str(ev.p2_date)[:10],
                "bars_since": bars_since,
                "magnitude": round(mag, 4),
            }
    score = NEUTRAL + 0.5 * (best["bottom"] - best["top"])
    return _clip01(score), chosen


def wave_score(df: pd.DataFrame) -> tuple[float, dict]:
    """浪型速度：三浪加速(up/extend)最高，下跌加速(down/extend)最低。"""
    if df.empty:
        return NEUTRAL, {}
    res = analyze_wave_speed(df)
    cur = res.current
    if cur is None:
        return NEUTRAL, {"verdict": None}
    score = _WAVE_SCORE.get((cur.direction, cur.verdict), NEUTRAL)
    detail = {
        "direction": cur.direction,
        "verdict": cur.verdict,
        "ratio": round(float(cur.ratio), 4),
    }
    return score, detail


def trendline_score(df: pd.DataFrame) -> tuple[float, dict]:
    """趋势线：向上突破下降压力线加分，跌破上升支撑线减分。"""
    if df.empty:
        return NEUTRAL, {}
    res = find_trendlines(df)
    close_today = float(df["close"].iloc[-1])
    res = evaluate_breakout(res, close_today, len(df) - 1)
    score = NEUTRAL
    detail: dict[str, dict] = {}
    if res.best_down is not None:
        broken = res.best_down.status == "broken"
        score += 0.5 if broken else -0.1
        detail["down_line"] = {
            "status": res.best_down.status,
            "touch_count": res.best_down.touch_count,
            "distance_pct": round(float(res.best_down.distance_pct or 0.0), 4),
        }
    if res.best_up is not None:
        broken = res.best_up.status == "broken"
        score += -0.4 if broken else 0.2
        detail["up_line"] = {
            "status": res.best_up.status,
            "touch_count": res.best_up.touch_count,
            "distance_pct": round(float(res.best_up.distance_pct or 0.0), 4),
        }
    return _clip01(score), detail


def heat_score(amount_today: float, amount_avg20: float, panel_amounts: pd.Series) -> tuple[float, dict]:
    """市场热度：成交额在候选池的分位（0.6）+ 量比（0.4，3 倍封顶）。"""
    if panel_amounts is None or len(panel_amounts) == 0:
        return NEUTRAL, {}
    rank_pct = float((panel_amounts < amount_today).sum() / len(panel_amounts))
    vol_ratio = float(amount_today / amount_avg20) if amount_avg20 > 0 else 1.0
    ratio_norm = min(vol_ratio / 3.0, 1.0)
    score = 0.6 * rank_pct + 0.4 * ratio_norm
    detail = {"rank_pct": round(rank_pct, 4), "vol_ratio": round(vol_ratio, 4)}
    return _clip01(score), detail


def momentum_score(ret20: float, panel_rets: pd.Series | None = None) -> tuple[float, dict]:
    """20 日动量：有候选池收益序列时按分位，否则按 ±20% 线性映射。"""
    if panel_rets is not None and len(panel_rets) > 0:
        pct = float((panel_rets < ret20).sum() / len(panel_rets))
        return _clip01(pct), {"ret20": round(ret20, 4), "pct": round(pct, 4)}
    score = min(max(ret20 / 0.2, -1.0), 1.0) * 0.5 + 0.5
    return _clip01(score), {"ret20": round(ret20, 4)}


def structure_score(df: pd.DataFrame) -> tuple[float, dict]:
    """结构组：背离/趋势线/浪型按固定子权重合成。"""
    s_div, d_div = divergence_score(df)
    s_tl, d_tl = trendline_score(df)
    s_wave, d_wave = wave_score(df)
    w = STRUCTURE_SUB_WEIGHTS
    score = w["divergence"] * s_div + w["trendline"] * s_tl + w["wave"] * s_wave
    detail = {
        "divergence": {"score": round(s_div, 4), **d_div},
        "trendline": {"score": round(s_tl, 4), **d_tl},
        "wave": {"score": round(s_wave, 4), **d_wave},
    }
    return _clip01(score), detail


def ret20(df: pd.DataFrame, window: int = 20) -> float:
    """20 日收盘收益率，数据不足返回 NaN。"""
    close = df["close"].astype(float)
    if len(close) < window + 1:
        return float("nan")
    return float(close.iloc[-1] / close.iloc[-window - 1] - 1.0)


def amount_avg(df: pd.DataFrame, window: int = 20) -> float:
    """近 window 日平均成交额，数据不足按实际天数。"""
    amt = df["amount"].astype(float).tail(window)
    if amt.empty:
        return float("nan")
    return float(amt.mean())
