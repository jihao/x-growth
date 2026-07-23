"""回测绩效指标。"""
from __future__ import annotations

import numpy as np

TRADING_DAYS = 252


def performance(result) -> dict:
    equity = result.equity
    strat_ret = result.strat_ret
    n = len(equity)
    total_return = float(equity.iloc[-1] - 1) if n else 0.0
    ann_return = float(equity.iloc[-1] ** (TRADING_DAYS / n) - 1) if n else 0.0
    vol = float(strat_ret.std())
    ann_vol = vol * np.sqrt(TRADING_DAYS)
    mean = float(strat_ret.mean())
    sharpe = (mean / vol * np.sqrt(TRADING_DAYS)) if vol > 0 else 0.0

    running_max = equity.cummax()
    drawdown = equity / running_max - 1
    max_drawdown = float(drawdown.min()) if n else 0.0

    trades = result.trades
    rets = [t["ret"] for t in trades]
    wins = [r for r in rets if r > 0]
    losses = [r for r in rets if r < 0]
    win_rate = (len(wins) / len(rets)) if rets else 0.0
    gross_win = sum(wins)
    gross_loss = abs(sum(losses))
    profit_factor = (gross_win / gross_loss) if gross_loss > 0 else float("inf") if gross_win > 0 else 0.0

    bench_total = float(result.benchmark.iloc[-1] - 1) if len(result.benchmark) else 0.0

    return {
        "total_return": total_return,
        "ann_return": ann_return,
        "ann_vol": ann_vol,
        "sharpe": sharpe,
        "max_drawdown": max_drawdown,
        "win_rate": win_rate,
        "profit_factor": profit_factor,
        "num_trades": len(trades),
        "bench_total_return": bench_total,
    }
