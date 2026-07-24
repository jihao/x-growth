import pandas as pd

from quant.structure import swings


def _hl(vals_h, vals_l=None):
    idx = pd.date_range("2020-01-01", periods=len(vals_h), freq="D")
    h = pd.Series(vals_h, index=idx, dtype=float)
    l = pd.Series(vals_l if vals_l is not None else vals_h, index=idx, dtype=float)
    return h, l


def test_detect_swings_finds_peak_and_trough():
    # 平 → 峰 → 平 → 谷 → 平；window=2 需两侧各 2 根更低/更高
    h = [10, 10, 10, 12, 10, 10, 10, 8, 10, 10, 10]
    l = [9, 9, 9, 11, 9, 9, 9, 7, 9, 9, 9]
    high, low = _hl(h, l)
    out = swings.detect_swings(high, low, window=2, min_pct=0.0)
    assert out["is_high"].sum() >= 1
    assert out["is_low"].sum() >= 1
    assert out["is_high"].iloc[3]  # 峰值
    assert out["is_low"].iloc[7]   # 谷值
    # 边缘 window 根不能为摆动点
    assert not out["is_high"].iloc[:2].any()
    assert not out["is_high"].iloc[-2:].any()


def test_min_pct_filters_near_duplicates():
    # 两个很近的高点，应只保留更高的
    h = [10, 10, 11.0, 10, 10, 10, 11.05, 10, 10, 10]
    high, low = _hl(h, [9] * len(h))
    out = swings.detect_swings(high, low, window=2, min_pct=0.02)
    # 11 与 11.05 相差约 0.45% < 2%，过滤后高点更少或只留 11.05
    assert out["is_high"].sum() <= 1
