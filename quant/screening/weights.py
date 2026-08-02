"""选股权重：策略动态权重（滚动回测夏普归一化）与组间加权合成。"""
from __future__ import annotations

from quant.backtest import engine, metrics, strategies

# 组间默认权重：策略信号 / 结构因子 / 量价热度
DEFAULT_GROUP_WEIGHTS = {"strategy": 0.4, "structure": 0.35, "volume": 0.25}

_MIN_BARS = 60  # 滚动回测至少需要的数据量


def dynamic_strategy_weights(
    df,
    lookback: int = 120,
    cost: float = 0.0003,
) -> tuple[dict[str, float], dict]:
    """对该股近 lookback 根 K 线逐策略回测，按夏普（负值截断）归一化为权重。

    全部策略夏普 <= 0 或数据不足时退化为等权。
    返回 (weights, detail)，detail 含各策略夏普便于落库快照。
    """
    names = list(strategies.REGISTRY)
    equal = {n: 1.0 / len(names) for n in names} if names else {}
    if df is None or len(df) < _MIN_BARS or not names:
        return equal, {"fallback": "insufficient_data"}
    win = df.tail(lookback)
    sharpes: dict[str, float] = {}
    for name in names:
        strat = strategies.get(name)
        sig = strat.generate(win)
        res = engine.run(win, sig, cost=cost)
        sharpes[name] = float(metrics.performance(res)["sharpe"])
    pos = {n: max(s, 0.0) for n, s in sharpes.items()}
    total = sum(pos.values())
    if total <= 0:
        return equal, {"fallback": "all_non_positive", "sharpe": sharpes}
    weights = {n: v / total for n, v in pos.items()}
    detail = {"sharpe": {n: round(s, 4) for n, s in sharpes.items()}}
    return weights, detail


def normalize_group_weights(weights: dict | None) -> dict[str, float]:
    """校验并归一化组间权重，缺省用 DEFAULT_GROUP_WEIGHTS。"""
    base = dict(DEFAULT_GROUP_WEIGHTS)
    if weights:
        for k in base:
            if k in weights and weights[k] is not None:
                base[k] = max(float(weights[k]), 0.0)
    total = sum(base.values())
    if total <= 0:
        return dict(DEFAULT_GROUP_WEIGHTS)
    return {k: v / total for k, v in base.items()}


def combine_scores(
    group_scores: dict[str, float],
    group_weights: dict | None = None,
    ml_boost: float | None = None,
) -> float:
    """组分数加权合成。ml_boost 为 v2 机器学习预留：score *= (1 + ml_boost)。"""
    w = normalize_group_weights(group_weights)
    total = sum(w[g] * float(group_scores.get(g, 0.5)) for g in w)
    if ml_boost is not None:
        total *= 1.0 + float(ml_boost)
    return float(min(max(total, 0.0), 1.0))
