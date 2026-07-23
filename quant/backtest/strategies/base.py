"""策略接口：输入标准行情 DataFrame，输出目标仓位序列 {0,1}。"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import pandas as pd


@dataclass
class Strategy:
    name: str
    label: str
    default_params: dict
    _fn: Callable[..., pd.Series]

    def generate(self, df: pd.DataFrame, **params) -> pd.Series:
        merged = {**self.default_params, **params}
        sig = self._fn(df, **merged)
        return sig.reindex(df.index).fillna(0.0).clip(0, 1)
