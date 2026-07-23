import numpy as np
import pandas as pd

from quant.concentration import market as m


def test_classify_board():
    assert m.classify_board("600000.SH") == "sh_main"
    assert m.classify_board("000001.SZ") == "sz_main"
    assert m.classify_board("002415.SZ") == "sme"
    assert m.classify_board("300750.SZ") == "gem"
    assert m.classify_board("688981.SH") == "star"
    assert m.classify_board("830799.BJ") == "bse"


def test_cr_n():
    amt = pd.Series([50, 30, 15, 5], dtype=float)  # total 100
    assert m.cr_n(amt, 1) == 0.5
    assert m.cr_n(amt, 2) == 0.8
    assert m.cr_n(amt, 10) == 1.0  # n 超过数量取全部


def test_hhi_equal_vs_concentrated():
    equal = pd.Series([25, 25, 25, 25], dtype=float)
    conc = pd.Series([97, 1, 1, 1], dtype=float)
    assert abs(m.hhi(equal) - 0.25) < 1e-9
    assert m.hhi(conc) > m.hhi(equal)


def test_gini_bounds():
    equal = pd.Series([10, 10, 10, 10], dtype=float)
    assert abs(m.gini(equal)) < 1e-9
    skew = pd.Series([0, 0, 0, 100], dtype=float)
    assert m.gini(skew) > 0.7


def test_concentration_row():
    df = pd.DataFrame(
        {
            "ts_code": ["600000.SH", "000001.SZ", "300750.SZ", "688981.SH"],
            "amount": [50.0, 30.0, 15.0, 5.0],
        }
    )
    row = m.concentration_row(df)
    assert row["total_amount"] == 100.0
    assert row["cr5"] == 1.0
    assert abs(row["amt_sh_main"] - 50.0) < 1e-9
    assert abs(row["amt_gem"] - 15.0) < 1e-9

