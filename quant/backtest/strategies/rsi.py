"""RSI 超买超卖：RSI 低于超卖阈买入，高于超买阈离场。"""
import numpy as np
import pandas as pd

from quant.indicators import ta
from quant.backtest.strategies.base import Strategy


def _gen(df, n=14, oversold=30, overbought=70):
    r = ta.rsi(df["close"], n)
    pos = np.where(r < oversold, 1.0, np.where(r > overbought, 0.0, np.nan))
    return pd.Series(pos, index=df.index).ffill().fillna(0.0)


STRATEGY = Strategy("rsi", "RSI 超买超卖", {"n": 14, "oversold": 30, "overbought": 70}, _gen)
