"""市场广度缓存测试：逐股涨跌聚合的纯计算逻辑。"""
from __future__ import annotations

import pandas as pd
import pytest

from quant.market import build_breadth


def _daily() -> pd.DataFrame:
    """3 只股票 3 天：A 连涨、B 先跌后涨、C 平后跌。"""
    rows = []
    data = {
        "A": [10.0, 11.0, 12.0],
        "B": [20.0, 19.0, 21.0],
        "C": [30.0, 30.0, 29.0],
    }
    for code, closes in data.items():
        for i, c in enumerate(closes, 1):
            rows.append({"trade_date": f"2026070{i}", "ts_code": code,
                         "close": c, "amount": i * 100.0})
    return pd.DataFrame(rows)


def test_compute_breadth_counts_and_ratio():
    g = build_breadth.compute_breadth(_daily()).set_index("trade_date")
    # 首日无前收：涨/跌/平均为 0，ratio 为 NaN
    d1 = g.loc["20260701"]
    assert d1["up_count"] == 0 and d1["down_count"] == 0
    assert pd.isna(d1["up_ratio"])
    # 第二日：A 涨、B 跌、C 平
    d2 = g.loc["20260702"]
    assert (d2["up_count"], d2["down_count"], d2["flat_count"]) == (1, 1, 1)
    assert d2["up_ratio"] == pytest.approx(0.5)
    # 第三日：A 涨、B 涨、C 跌
    d3 = g.loc["20260703"]
    assert (d3["up_count"], d3["down_count"], d3["flat_count"]) == (2, 1, 0)
    assert d3["up_ratio"] == pytest.approx(2 / 3)
    assert d3["total_amount"] == pytest.approx(900.0)


def test_compute_breadth_empty():
    out = build_breadth.compute_breadth(pd.DataFrame())
    assert out.empty
    assert "up_ratio" in out.columns
