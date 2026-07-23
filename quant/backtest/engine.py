"""向量化回测引擎（close-to-close，T+1 生效，防未来函数）。"""
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


@dataclass
class BacktestResult:
    equity: pd.Series
    position: pd.Series
    strat_ret: pd.Series
    benchmark: pd.Series
    trades: list


def _extract_trades(close: pd.Series, position: pd.Series) -> list:
    prev_close = close.shift(1)
    trades = []
    entry_idx = None
    entry_px = None
    prev = 0.0
    for ts, pos in position.items():
        if prev == 0 and pos == 1:
            entry_idx, entry_px = ts, prev_close.loc[ts]
        elif prev == 1 and pos == 0 and entry_idx is not None:
            exit_px = prev_close.loc[ts]
            trades.append(
                {
                    "entry": entry_idx, "exit": ts,
                    "entry_px": float(entry_px), "exit_px": float(exit_px),
                    "ret": float(exit_px / entry_px - 1),
                }
            )
            entry_idx = None
        prev = pos
    if entry_idx is not None:  # 期末仍持仓，按最后收盘平掉
        exit_px = close.iloc[-1]
        trades.append(
            {
                "entry": entry_idx, "exit": close.index[-1],
                "entry_px": float(entry_px), "exit_px": float(exit_px),
                "ret": float(exit_px / entry_px - 1),
            }
        )
    return trades


def run(df: pd.DataFrame, signal: pd.Series, cost=0.0003, slippage=0.0) -> BacktestResult:
    close = df["close"].astype(float)
    signal = signal.reindex(close.index).fillna(0.0).clip(0, 1).round()
    position = signal.shift(1).fillna(0.0)          # T+1 生效
    ret = close.pct_change().fillna(0.0)
    turnover = position.diff().abs().fillna(position.abs())
    trade_cost = turnover * (cost + slippage)
    strat_ret = position * ret - trade_cost
    equity = (1 + strat_ret).cumprod()
    benchmark = (1 + ret).cumprod()
    trades = _extract_trades(close, position)
    return BacktestResult(
        equity=equity, position=position, strat_ret=strat_ret,
        benchmark=benchmark, trades=trades,
    )
