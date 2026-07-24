from datetime import date

from quant import config


def test_fmt_date_variants():
    assert config.fmt_date("2010-01-01") == "20100101"
    assert config.fmt_date("20100101") == "20100101"
    assert config.fmt_date(date(2010, 1, 1)) == "20100101"


def test_fmt_date_rejects_invalid_calendar():
    try:
        config.fmt_date("20230231")
        assert False, "expected ValueError"
    except ValueError as e:
        assert "20230231" in str(e) or "无法解析" in str(e)
    assert config.fmt_date("20230228") == "20230228"


def test_mysql_dir_on_path():
    assert str(config.MYSQL_DIR) in __import__("sys").path
