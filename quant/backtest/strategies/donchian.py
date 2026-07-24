"""唐奇安通道突破（海龟式）：突破 N 日最高买入，跌破 M 日最低离场。"""
import numpy as np
import pandas as pd

from quant.indicators import ta
from quant.backtest.strategies.base import Strategy


def _gen(df, entry=20, exit=10):
    upper_raw, lower_raw = ta.donchian_channel(df["high"], df["low"], entry, exit)
    upper = upper_raw.shift(1)
    lower = lower_raw.shift(1)
    close = df["close"]
    pos = np.where(close > upper, 1.0, np.where(close < lower, 0.0, np.nan))
    return pd.Series(pos, index=df.index).ffill().fillna(0.0)


STRATEGY = Strategy("donchian", "唐奇安通道突破", {"entry": 20, "exit": 10}, _gen)
