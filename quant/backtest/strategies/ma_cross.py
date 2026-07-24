"""双均线交叉：快线上穿慢线持有，下穿空仓。"""
from quant.indicators import ta
from quant.backtest.strategies.base import Strategy


def _gen(df, fast=5, slow=20):
    f = ta.ma(df["close"], fast)
    s = ta.ma(df["close"], slow)
    return (f > s).astype(float)


STRATEGY = Strategy("ma_cross", "双均线交叉", {"fast": 5, "slow": 20}, _gen)
