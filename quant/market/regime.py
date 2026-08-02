"""市场环境（regime）判定：指数趋势 50% + 市场量能 25% + 市场广度 25%。

- 全部为 point-in-time 计算：任意历史日期只用该日及之前的数据，可安全用于回算；
- 输出五档环境（强势/偏强/中性/偏弱/弱势）与操作建议封顶档位 cap_index，
  供 explain 降档使用（偏弱封 1「轻仓试探」，弱势封 2「观望」）；
- 数据缺失（指数/广度表未初始化）时退化为中性、不封顶，保证 UI 与跑批不中断；
- 结果按日期 lru_cache：跟踪复盘逐日重算建议时不会反复查库。
"""
from __future__ import annotations

from functools import lru_cache

import numpy as np
import pandas as pd

from quant import config
from quant.data import loader
from quant.market.index_update import INDICES

W_TREND, W_VOLUME, W_BREADTH = 0.5, 0.25, 0.25

LEVEL_THRESHOLDS = (
    (0.50, "强势"), (0.15, "偏强"), (-0.15, "中性"),
    (-0.50, "偏弱"), (-1.01, "弱势"),
)
LEVEL_CAP = {"强势": 0, "偏强": 0, "中性": 0, "偏弱": 1, "弱势": 2}
LEVEL_COLORS = {
    "强势": "#43a047", "偏强": "#8bc34a", "中性": "#9aa3b2",
    "偏弱": "#fb8c00", "弱势": "#e53935",
}


@lru_cache(maxsize=None)
def _index_frame(code: str) -> pd.DataFrame:
    """单指数全历史（进程内缓存，逐日切片在 pandas 内完成）。"""
    return loader.load_index_daily(code)


@lru_cache(maxsize=None)
def _breadth_frame() -> pd.DataFrame:
    return loader.load_breadth()


def clear_caches() -> None:
    _index_frame.cache_clear()
    _breadth_frame.cache_clear()
    market_regime.cache_clear()


def _ts(t: str) -> pd.Timestamp:
    return pd.Timestamp(pd.to_datetime(t, format="%Y%m%d"))


def _trend_component(t: str) -> dict:
    """6 指数 × 4 分量（MA20 上 / MA60 上 / 多头排列 / MA20 上行），各 ±1。"""
    end = _ts(t)
    lines, scores = [], []
    for code, name in INDICES.items():
        df = _index_frame(code)
        df = df[df.index <= end]
        if len(df) < 65:
            lines.append(f"{name}：数据不足（{len(df)} 行），未纳入")
            continue
        close = df["close"]
        ma20 = close.rolling(20).mean()
        ma60 = close.rolling(60).mean()
        marks = [
            bool(close.iloc[-1] > ma20.iloc[-1]),
            bool(close.iloc[-1] > ma60.iloc[-1]),
            bool(ma20.iloc[-1] > ma60.iloc[-1]),
            bool(ma20.iloc[-1] > ma20.iloc[-6]),
        ]
        scores.append(sum(1 if m else -1 for m in marks) / 4)
        ico = ["✔" if m else "✘" for m in marks]
        lines.append(
            f"{name}（{close.iloc[-1]:.0f} 点）：MA20 上 {ico[0]}　"
            f"MA60 上 {ico[1]}　多头排列 {ico[2]}　MA20 上行 {ico[3]}"
        )
    score = float(np.mean(scores)) if scores else 0.0
    return {"score": score, "weight": W_TREND, "lines": lines,
            "n_indices": len(scores)}


def _breadth_slice(t: str) -> pd.DataFrame:
    bd = _breadth_frame()
    return bd[bd.index <= _ts(t)].tail(25)


def _volume_component(bd: pd.DataFrame) -> dict:
    if len(bd) < 21:
        return {"score": 0.0, "weight": W_VOLUME,
                "lines": ["广度缓存数据不足，量能按中性计"]}
    amt = bd["total_amount"]
    ma20 = amt.rolling(20).mean().iloc[-1]
    ma5 = amt.rolling(5).mean().iloc[-1]
    today = amt.iloc[-1]
    m1, m2 = bool(today > ma20), bool(ma5 > ma20)
    score = ((1 if m1 else -1) + (1 if m2 else -1)) / 2
    lines = [
        f"两市成交 {today / 1e12:.2f} 万亿 vs 20 日均 {ma20 / 1e12:.2f} 万亿 "
        f"{'✔ 放量' if m1 else '✘ 缩量'}",
        f"量能 5 日均 {'>' if m2 else '<'} 20 日均 "
        f"{'✔ 量能回升' if m2 else '✘ 量能退潮'}",
    ]
    return {"score": score, "weight": W_VOLUME, "lines": lines}


def _breadth_component(bd: pd.DataFrame) -> dict:
    if len(bd) < 6:
        return {"score": 0.0, "weight": W_BREADTH,
                "lines": ["广度缓存数据不足，广度按中性计"]}
    ratio = bd["up_ratio"]
    today_r = ratio.iloc[-1]
    ma5_r = ratio.rolling(5).mean().iloc[-1]
    m1, m2 = bool(today_r > 0.5), bool(ma5_r > 0.5)
    score = ((1 if m1 else -1) + (1 if m2 else -1)) / 2
    lines = [
        f"上涨家数占比 {today_r:.0%} {'✔ 多数上涨' if m1 else '✘ 多数下跌'}",
        f"5 日均上涨占比 {ma5_r:.0%} {'✔ 广度健康' if m2 else '✘ 广度恶化'}",
    ]
    return {"score": score, "weight": W_BREADTH, "lines": lines}


@lru_cache(maxsize=512)
def market_regime(trade_date: str) -> dict:
    """某日市场环境。返回 score/level/cap_index/components/summary。"""
    t = config.fmt_date(trade_date)
    trend = _trend_component(t)
    bd = _breadth_slice(t)
    vol = _volume_component(bd)
    brd = _breadth_component(bd)
    data_missing = trend["n_indices"] == 0 and len(bd) < 21
    score = (trend["score"] * W_TREND + vol["score"] * W_VOLUME
             + brd["score"] * W_BREADTH)
    level = next(lbl for th, lbl in LEVEL_THRESHOLDS if score >= th)
    cap = 0 if data_missing else LEVEL_CAP[level]
    summary = f"{level}（得分 {score:+.2f}）"
    if data_missing:
        summary += "：环境数据缺失（index_daily / market_breadth 未初始化），按不封顶处理"
    return {
        "date": t, "score": round(score, 4), "level": level,
        "cap_index": cap, "data_missing": data_missing,
        "components": {"trend": trend, "volume": vol, "breadth": brd},
        "summary": summary,
    }
