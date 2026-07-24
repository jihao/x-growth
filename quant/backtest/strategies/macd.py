"""MACD：DIF 上穿 DEA 持有，下穿空仓。"""
from quant.indicators import ta
from quant.backtest.strategies.base import Strategy


def _gen(df, fast=12, slow=26, signal=9):
    dif, dea, _ = ta.macd(df["close"], fast, slow, signal)
    return (dif > dea).astype(float)


STRATEGY = Strategy("macd", "MACD 金叉死叉", {"fast": 12, "slow": 26, "signal": 9}, _gen)
