"""集中度缓存表读写。字段顺序集中定义，供预计算与界面复用。"""
from __future__ import annotations

import pandas as pd

from quant import config  # noqa: F401
from mysql_config import connect_mysql, load_dotenv

TABLE = config.CONCENTRATION_TABLE

_FIELDS = [
    "total_amount",
    "cr5", "cr10", "cr20", "cr50", "cr100",
    "hhi", "gini",
    "amt_sh_main", "amt_sz_main", "amt_sme", "amt_gem", "amt_star", "amt_bse",
]

CREATE_SQL = f"""
CREATE TABLE IF NOT EXISTS {TABLE} (
  trade_date CHAR(8) NOT NULL PRIMARY KEY,
  total_amount DECIMAL(24,2),
  cr5 DECIMAL(8,6), cr10 DECIMAL(8,6), cr20 DECIMAL(8,6),
  cr50 DECIMAL(8,6), cr100 DECIMAL(8,6),
  hhi DECIMAL(12,10), gini DECIMAL(8,6),
  amt_sh_main DECIMAL(24,2), amt_sz_main DECIMAL(24,2), amt_sme DECIMAL(24,2),
  amt_gem DECIMAL(24,2), amt_star DECIMAL(24,2), amt_bse DECIMAL(24,2)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
"""


def upsert_sql() -> str:
    cols = ["trade_date"] + _FIELDS
    placeholders = ", ".join(["%s"] * len(cols))
    updates = ", ".join(f"{c}=VALUES({c})" for c in _FIELDS)
    return (
        f"INSERT INTO {TABLE} ({', '.join(cols)}) VALUES ({placeholders}) "
        f"ON DUPLICATE KEY UPDATE {updates}"
    )


def row_to_params(trade_date: str, row: dict) -> tuple:
    return tuple([trade_date] + [row[f] for f in _FIELDS])


def _conn():
    load_dotenv()
    return connect_mysql()


def ensure_table() -> None:
    conn = _conn()
    try:
        with conn.cursor() as cur:
            cur.execute(CREATE_SQL)
        conn.commit()
    finally:
        conn.close()


def read_series(start=None, end=None) -> pd.DataFrame:
    s = config.fmt_date(start) if start else "19900101"
    e = config.fmt_date(end) if end else "99991231"
    conn = _conn()
    try:
        df = pd.read_sql(
            f"SELECT * FROM {TABLE} WHERE trade_date BETWEEN %s AND %s ORDER BY trade_date",
            conn, params=(s, e),
        )
    finally:
        conn.close()
    if not df.empty:
        df["trade_date"] = pd.to_datetime(df["trade_date"].astype(str), format="%Y%m%d")
        df = df.set_index("trade_date")
    return df


def max_cached_date() -> str | None:
    conn = _conn()
    try:
        with conn.cursor() as cur:
            cur.execute(f"SELECT MAX(trade_date) FROM {TABLE}")
            val = cur.fetchone()[0]
    finally:
        conn.close()
    return val
