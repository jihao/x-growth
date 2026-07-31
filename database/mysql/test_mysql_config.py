import os

import mysql_config


def test_mysql_settings_defaults(monkeypatch):
    for key in list(os.environ):
        if key.startswith("MYSQL_"):
            monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("MYSQL_USER", "u1")
    s = mysql_config.mysql_settings()
    assert s["host"] == "127.0.0.1"
    assert s["port"] == 3306
    assert s["user"] == "u1"
    assert s["password"] == ""
    assert s["database"] == "astocks_qfq"
    assert s["connect_timeout"] == 5
    assert s["read_timeout"] == 60
    assert s["write_timeout"] == 60


def test_mysql_settings_timeout_env(monkeypatch):
    for key in list(os.environ):
        if key.startswith("MYSQL_"):
            monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("MYSQL_USER", "u1")
    monkeypatch.setenv("MYSQL_CONNECT_TIMEOUT", "3")
    monkeypatch.setenv("MYSQL_READ_TIMEOUT", "120")
    monkeypatch.setenv("MYSQL_WRITE_TIMEOUT", "90")
    s = mysql_config.mysql_settings()
    assert s["connect_timeout"] == 3
    assert s["read_timeout"] == 120
    assert s["write_timeout"] == 90


def test_mysql_settings_requires_user(monkeypatch):
    for key in list(os.environ):
        if key.startswith("MYSQL_"):
            monkeypatch.delenv(key, raising=False)
    try:
        mysql_config.mysql_settings()
        assert False, "expected ValueError"
    except ValueError as e:
        assert "MYSQL_USER" in str(e)


def test_load_dotenv_file(tmp_path, monkeypatch):
    for key in list(os.environ):
        if key.startswith("MYSQL_"):
            monkeypatch.delenv(key, raising=False)
    env = tmp_path / "mysql.env"
    env.write_text(
        "MYSQL_USER=fromfile\nMYSQL_HOST=db.local\nMYSQL_PORT=3307\n",
        encoding="utf-8",
    )
    mysql_config.load_dotenv(str(env))
    s = mysql_config.mysql_settings()
    assert s["user"] == "fromfile"
    assert s["host"] == "db.local"
    assert s["port"] == 3307
