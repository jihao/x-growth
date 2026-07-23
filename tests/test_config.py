from datetime import date

from quant import config


def test_fmt_date_variants():
    assert config.fmt_date("2010-01-01") == "20100101"
    assert config.fmt_date("20100101") == "20100101"
    assert config.fmt_date(date(2010, 1, 1)) == "20100101"


def test_mysql_dir_on_path():
    assert str(config.MYSQL_DIR) in __import__("sys").path
