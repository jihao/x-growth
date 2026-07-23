from quant.concentration import cache


def test_row_to_params_order():
    row = {
        "total_amount": 100.0,
        "cr5": 1.0, "cr10": 1.0, "cr20": 1.0, "cr50": 1.0, "cr100": 1.0,
        "hhi": 0.3, "gini": 0.5,
        "amt_sh_main": 50.0, "amt_sz_main": 30.0, "amt_sme": 0.0,
        "amt_gem": 15.0, "amt_star": 5.0, "amt_bse": 0.0,
    }
    params = cache.row_to_params("20240102", row)
    expected = (
        "20240102", 100.0, 1.0, 1.0, 1.0, 1.0, 1.0, 0.3, 0.5,
        50.0, 30.0, 0.0, 15.0, 5.0, 0.0,
    )
    assert params == expected
    assert len(params) == 15


def test_create_sql_has_table():
    assert "market_concentration" in cache.CREATE_SQL
    assert "PRIMARY KEY" in cache.CREATE_SQL
