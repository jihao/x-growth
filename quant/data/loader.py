"""统一行情读取层（MySQL）。DB I/O 与纯计算分离，纯计算可离线测试。"""
from __future__ import annotations

import pandas as pd

from quant import config  # noqa: F401  # 注入 sys.path
from mysql_config import connect_mysql, load_dotenv

_DAILY_COLS = ["open", "high", "low", "close", "volume", "amount"]


def _conn():
    load_dotenv()
    return connect_mysql()


def _read_df(conn, sql: str, params=None) -> pd.DataFrame:
    """用游标执行查询并构造 DataFrame，避免 pandas 对裸 DBAPI 连接的告警。"""
    with conn.cursor() as cur:
        cur.execute(sql, params or ())
        rows = cur.fetchall()
        cols = [c[0] for c in cur.description]
    return pd.DataFrame(list(rows), columns=cols)


def _normalize_daily(df_raw: pd.DataFrame) -> pd.DataFrame:
    if df_raw is None or df_raw.empty:
        return pd.DataFrame(
            columns=_DAILY_COLS, index=pd.DatetimeIndex([], name="trade_date")
        )
    df = df_raw.copy()
    df["trade_date"] = pd.to_datetime(df["trade_date"].astype(str), format="%Y%m%d")
    df = df.set_index("trade_date").sort_index()
    for col in ["open", "high", "low", "close", "amount"]:
        df[col] = df[col].astype(float)
    df["volume"] = df["volume"].astype("int64")
    return df[_DAILY_COLS]


def load_daily(ts_code: str, start=None, end=None) -> pd.DataFrame:
    s = config.fmt_date(start) if start else "19900101"
    e = config.fmt_date(end) if end else "99991231"
    sql = (
        "SELECT trade_date, `open`, high, low, close_qfq AS close, volume, amount "
        "FROM daily_qfq WHERE ts_code=%s AND trade_date BETWEEN %s AND %s "
        "ORDER BY trade_date"
    )
    conn = _conn()
    try:
        df = _read_df(conn, sql, (ts_code, s, e))
    finally:
        conn.close()
    return _normalize_daily(df)


def load_cross_section(date) -> pd.DataFrame:
    d = config.fmt_date(date)
    sql = (
        "SELECT d.ts_code, s.name, d.close_qfq AS close, d.volume, d.amount "
        "FROM daily_qfq d LEFT JOIN stocks s ON s.ts_code=d.ts_code "
        "WHERE d.trade_date=%s"
    )
    conn = _conn()
    try:
        df = _read_df(conn, sql, (d,))
    finally:
        conn.close()
    if not df.empty:
        df["close"] = df["close"].astype(float)
        df["amount"] = df["amount"].astype(float)
        df["volume"] = df["volume"].astype("int64")
    return df


def list_stocks() -> pd.DataFrame:
    conn = _conn()
    try:
        return _read_df(conn, "SELECT ts_code, name FROM stocks ORDER BY ts_code")
    finally:
        conn.close()


def trading_dates(start, end) -> list[str]:
    s, e = config.fmt_date(start), config.fmt_date(end)
    sql = (
        "SELECT DISTINCT trade_date FROM daily_qfq "
        "WHERE trade_date BETWEEN %s AND %s ORDER BY trade_date"
    )
    conn = _conn()
    try:
        df = _read_df(conn, sql, (s, e))
    finally:
        conn.close()
    if df.empty:
        return []
    return df["trade_date"].astype(str).tolist()
