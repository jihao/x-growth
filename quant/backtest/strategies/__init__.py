"""策略注册表。"""
from quant.backtest.strategies.base import Strategy
from quant.backtest.strategies import ma_cross, macd, bollinger, rsi, donchian

REGISTRY = {
    s.name: s
    for s in [
        ma_cross.STRATEGY,
        macd.STRATEGY,
        bollinger.STRATEGY,
        rsi.STRATEGY,
        donchian.STRATEGY,
    ]
}


def get(name: str) -> Strategy:
    if name not in REGISTRY:
        raise KeyError(f"未知策略: {name}. 可选: {list(REGISTRY)}")
    return REGISTRY[name]
