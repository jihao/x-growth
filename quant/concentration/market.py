"""市场资金集中度（A 类）：基于每日全市场成交额分布。纯计算，DB 分离。"""
from __future__ import annotations

import numpy as np
import pandas as pd

from quant.config import CR_LEVELS

_BOARD_KEYS = ["sh_main", "sz_main", "sme", "gem", "star", "bse", "other"]


def classify_board(ts_code: str) -> str:
    code = ts_code.split(".")[0]
    if code.startswith(("600", "601", "603", "605")):
        return "sh_main"
    if code.startswith("688") or code.startswith("689"):
        return "star"
    if code.startswith(("000", "001", "003")):
        return "sz_main"
    if code.startswith("002"):
        return "sme"
    if code.startswith(("300", "301")):
        return "gem"
    if code.startswith(("8", "4", "92")):
        return "bse"
    return "other"


def cr_n(amounts: pd.Series, n: int) -> float:
    a = amounts.dropna().astype(float)
    total = a.sum()
    if total <= 0:
        return 0.0
    top = a.sort_values(ascending=False).head(n).sum()
    return float(top / total)


def hhi(amounts: pd.Series) -> float:
    a = amounts.dropna().astype(float)
    total = a.sum()
    if total <= 0:
        return 0.0
    shares = a / total
    return float((shares ** 2).sum())


def gini(amounts: pd.Series) -> float:
    a = np.sort(amounts.dropna().astype(float).values)
    n = a.size
    if n == 0 or a.sum() == 0:
        return 0.0
    index = np.arange(1, n + 1)
    return float((2 * (index * a).sum()) / (n * a.sum()) - (n + 1) / n)


def board_amounts(df: pd.DataFrame) -> dict:
    boards = df["ts_code"].map(classify_board)
    grouped = df.assign(board=boards).groupby("board")["amount"].sum()
    return {k: float(grouped.get(k, 0.0)) for k in _BOARD_KEYS}


def concentration_row(df: pd.DataFrame) -> dict:
    amt = df["amount"].astype(float)
    row = {"total_amount": float(amt.sum())}
    for n in CR_LEVELS:
        row[f"cr{n}"] = cr_n(amt, n)
    row["hhi"] = hhi(amt)
    row["gini"] = gini(amt)
    boards = board_amounts(df)
    row["amt_sh_main"] = boards["sh_main"]
    row["amt_sz_main"] = boards["sz_main"]
    row["amt_sme"] = boards["sme"]
    row["amt_gem"] = boards["gem"]
    row["amt_star"] = boards["star"]
    row["amt_bse"] = boards["bse"]
    return row
