"""全局股票收藏（MySQL favorites 表）。"""
from __future__ import annotations

import pandas as pd

from quant import config  # noqa: F401  # 注入 database/mysql 到 sys.path
from mysql_config import connect_mysql, load_dotenv

_CREATE_SQL = """
CREATE TABLE IF NOT EXISTS favorites (
  ts_code VARCHAR(16) NOT NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (ts_code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
"""


def _conn():
    load_dotenv()
    return connect_mysql()


def ensure_table() -> None:
    conn = _conn()
    try:
        with conn.cursor() as cur:
            cur.execute(_CREATE_SQL)
        conn.commit()
    finally:
        conn.close()


def add(ts_code: str) -> None:
    ensure_table()
    conn = _conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT IGNORE INTO favorites (ts_code) VALUES (%s)",
                (ts_code,),
            )
        conn.commit()
    finally:
        conn.close()


def remove(ts_code: str) -> None:
    ensure_table()
    conn = _conn()
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM favorites WHERE ts_code=%s", (ts_code,))
        conn.commit()
    finally:
        conn.close()


def is_favorite(ts_code: str) -> bool:
    ensure_table()
    conn = _conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT 1 FROM favorites WHERE ts_code=%s LIMIT 1",
                (ts_code,),
            )
            return cur.fetchone() is not None
    finally:
        conn.close()


def list_favorites() -> pd.DataFrame:
    ensure_table()
    conn = _conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT f.ts_code, s.name, f.created_at "
                "FROM favorites f "
                "LEFT JOIN stocks s ON s.ts_code=f.ts_code "
                "ORDER BY f.created_at DESC"
            )
            rows = cur.fetchall()
            cols = [c[0] for c in cur.description] if cur.description else [
                "ts_code", "name", "created_at"
            ]
        return pd.DataFrame(list(rows), columns=cols)
    finally:
        conn.close()
