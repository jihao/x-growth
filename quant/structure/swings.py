"""波段高低点检测（复盘/展示/历史扫描用）。

使用居中窗口确认局部峰谷；最近/最前 ``window`` 根未确认，不参与连线。
不得把未确认点当作实时交易信号的唯一依据。
"""
from __future__ import annotations

import pandas as pd


def detect_swings(
    high: pd.Series,
    low: pd.Series,
    window: int = 5,
    min_pct: float = 0.01,
) -> pd.DataFrame:
    high = high.astype(float)
    low = low.astype(float)
    w = window * 2 + 1
    roll_max = high.rolling(w, center=True).max()
    roll_min = low.rolling(w, center=True).min()
    is_high = (high == roll_max) & roll_max.notna()
    is_low = (low == roll_min) & roll_min.notna()
    # 边缘未确认
    is_high.iloc[:window] = False
    is_high.iloc[-window:] = False
    is_low.iloc[:window] = False
    is_low.iloc[-window:] = False

    def _filter(mask: pd.Series, prices: pd.Series, prefer: str) -> pd.Series:
        idxs = list(prices.index[mask])
        if len(idxs) <= 1:
            return mask
        keep = [idxs[0]]
        for i in idxs[1:]:
            prev = keep[-1]
            p0, p1 = float(prices.loc[prev]), float(prices.loc[i])
            base = max(abs(p0), abs(p1), 1e-12)
            if abs(p1 - p0) / base < min_pct:
                if prefer == "high":
                    if p1 >= p0:
                        keep[-1] = i
                else:
                    if p1 <= p0:
                        keep[-1] = i
            else:
                keep.append(i)
        out = pd.Series(False, index=prices.index)
        out.loc[keep] = True
        return out

    is_high = _filter(is_high, high, "high")
    is_low = _filter(is_low, low, "low")
    return pd.DataFrame({"is_high": is_high, "is_low": is_low}, index=high.index)
