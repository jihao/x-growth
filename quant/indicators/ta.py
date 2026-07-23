"""技术指标库：纯 pandas/numpy 实现，输入输出长度对齐。"""
from __future__ import annotations

import numpy as np
import pandas as pd


def ma(s: pd.Series, n: int) -> pd.Series:
    return s.rolling(n).mean()


def ema(s: pd.Series, n: int) -> pd.Series:
    return s.ewm(span=n, adjust=False).mean()


def macd(close, fast=12, slow=26, signal=9):
    dif = ema(close, fast) - ema(close, slow)
    dea = ema(dif, signal)
    hist = dif - dea
    return dif, dea, hist


def boll(close, n=20, k=2.0):
    mid = close.rolling(n).mean()
    std = close.rolling(n).std(ddof=0)
    return mid + k * std, mid, mid - k * std


def donchian_channel(high, low, upper_n=20, lower_n=10):
    """唐奇安通道：上轨=近 upper_n 日最高，下轨=近 lower_n 日最低（未位移）。"""
    return high.rolling(upper_n).max(), low.rolling(lower_n).min()


def rsi(close, n=14):
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / n, adjust=False, min_periods=n).mean()
    avg_loss = loss.ewm(alpha=1 / n, adjust=False, min_periods=n).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    out = 100 - 100 / (1 + rs)
    out = out.where(avg_loss != 0, 100.0)
    return out


def kdj(high, low, close, n=9, k=3, d=3):
    low_n = low.rolling(n).min()
    high_n = high.rolling(n).max()
    rsv = (close - low_n) / (high_n - low_n).replace(0, np.nan) * 100
    k_line = rsv.ewm(alpha=1 / k, adjust=False).mean()
    d_line = k_line.ewm(alpha=1 / d, adjust=False).mean()
    j_line = 3 * k_line - 2 * d_line
    return k_line, d_line, j_line


def roc(close, n=12):
    return (close / close.shift(n) - 1) * 100


def obv(close, volume):
    direction = np.sign(close.diff()).fillna(0)
    return (direction * volume).cumsum()


def _typical_price(high, low, close):
    return (high + low + close) / 3


def mfi(high, low, close, volume, n=14):
    tp = _typical_price(high, low, close)
    mf = tp * volume
    pos = mf.where(tp > tp.shift(1), 0.0)
    neg = mf.where(tp < tp.shift(1), 0.0)
    pos_sum = pos.rolling(n).sum()
    neg_raw = neg.rolling(n).sum()
    mfr = pos_sum / neg_raw.replace(0, np.nan)
    out = 100 - 100 / (1 + mfr)
    out = out.where(~((neg_raw == 0) & (pos_sum > 0)), 100.0)
    return out


def atr(high, low, close, n=14):
    prev_close = close.shift(1)
    tr = pd.concat(
        [(high - low), (high - prev_close).abs(), (low - prev_close).abs()], axis=1
    ).max(axis=1)
    return tr.ewm(alpha=1 / n, adjust=False, min_periods=n).mean()


def swing_points(close, window=5):
    highs = close.rolling(window * 2 + 1, center=True).max()
    lows = close.rolling(window * 2 + 1, center=True).min()
    not_flat = highs > lows
    return pd.DataFrame(
        {"is_high": (close == highs) & not_flat, "is_low": (close == lows) & not_flat},
        index=close.index,
    )


def ma_bull_alignment(close, periods=(5, 10, 20, 60)):
    mas = [ma(close, p) for p in periods]
    aligned = pd.Series(True, index=close.index)
    for faster, slower in zip(mas[:-1], mas[1:]):
        aligned &= faster > slower
    return aligned.where(mas[-1].notna(), False)
