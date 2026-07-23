"""布林带均值回归：收盘跌破下轨买入，回到中轨以上离场。"""
import numpy as np
import pandas as pd

from quant.indicators import ta
from quant.backtest.strategies.base import Strategy


def _gen(df, n=20, k=2.0):
    upper, mid, lower = ta.boll(df["close"], n, k)
    close = df["close"]
    pos = np.where(close <= lower, 1.0, np.where(close > mid, 0.0, np.nan))
    return pd.Series(pos, index=df.index).ffill().fillna(0.0)


STRATEGY = Strategy("bollinger", "布林带均值回归", {"n": 20, "k": 2.0}, _gen)
