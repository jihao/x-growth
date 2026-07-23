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
