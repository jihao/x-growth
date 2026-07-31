#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""MySQL 连接配置：环境变量 + 可选 mysql.env。"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import pymysql

_DEFAULT_ENV = Path(__file__).resolve().parent / "mysql.env"


def load_dotenv(path: str | None = None) -> None:
    """Load KEY=VALUE lines into os.environ if key not already set."""
    env_path = Path(path) if path else _DEFAULT_ENV
    if not env_path.is_file():
        return
    for raw in env_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip("'").strip('"')
        if key and key not in os.environ:
            os.environ[key] = value


def mysql_settings() -> dict[str, Any]:
    host = os.environ.get("MYSQL_HOST", "127.0.0.1")
    port = int(os.environ.get("MYSQL_PORT", "3306"))
    user = os.environ.get("MYSQL_USER")
    if not user:
        raise ValueError("MYSQL_USER is required (env or database/mysql.env)")
    password = os.environ.get("MYSQL_PASSWORD", "")
    database = os.environ.get("MYSQL_DATABASE", "astocks_qfq")
    # 本地默认 5s：连不上尽快失败；远程可在 mysql.env 调大 MYSQL_CONNECT_TIMEOUT
    connect_timeout = int(os.environ.get("MYSQL_CONNECT_TIMEOUT", "5"))
    read_timeout = int(os.environ.get("MYSQL_READ_TIMEOUT", "60"))
    write_timeout = int(os.environ.get("MYSQL_WRITE_TIMEOUT", "60"))
    return {
        "host": host,
        "port": port,
        "user": user,
        "password": password,
        "database": database,
        "connect_timeout": connect_timeout,
        "read_timeout": read_timeout,
        "write_timeout": write_timeout,
    }


def connect_mysql(**overrides: Any) -> pymysql.connections.Connection:
    settings = mysql_settings()
    settings.update(overrides)
    kwargs: dict[str, Any] = dict(
        host=settings["host"],
        port=int(settings["port"]),
        user=settings["user"],
        password=settings["password"],
        charset="utf8mb4",
        autocommit=False,
        cursorclass=pymysql.cursors.Cursor,
        connect_timeout=int(settings["connect_timeout"]),
        read_timeout=int(settings["read_timeout"]),
        write_timeout=int(settings["write_timeout"]),
    )
    db = settings.get("database")
    if db is not None:
        kwargs["database"] = db
    return pymysql.connect(**kwargs)
