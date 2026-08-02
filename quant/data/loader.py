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
    # volume 可能为 NULL（停牌/缺失），先补 0 再转整型，避免 IntCastingNaNError
    df["volume"] = df["volume"].fillna(0).astype("int64")
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
        # volume 可能为 NULL（停牌/缺失），先补 0 再转整型
        df["volume"] = df["volume"].fillna(0).astype("int64")
    return df


def load_daily_many(codes: list[str], start, end) -> pd.DataFrame:
    """多股票区间行情一次取数（含 ts_code 列），供批量复盘使用。

    返回列：ts_code / trade_date(YYYYMMMDD 字符串) / open / high / low / close / volume / amount。
    """
    if not codes:
        return pd.DataFrame(
            columns=["ts_code", "trade_date"] + _DAILY_COLS)
    s = config.fmt_date(start) if start else "19900101"
    e = config.fmt_date(end) if end else "99991231"
    placeholders = ",".join(["%s"] * len(codes))
    sql = (
        f"SELECT ts_code, trade_date, `open`, high, low, close_qfq AS close, "
        f"volume, amount FROM daily_qfq "
        f"WHERE ts_code IN ({placeholders}) AND trade_date BETWEEN %s AND %s "
        f"ORDER BY ts_code, trade_date"
    )
    conn = _conn()
    try:
        df = _read_df(conn, sql, (*codes, s, e))
    finally:
        conn.close()
    return df


def load_index_daily(code: str, start=None, end=None) -> pd.DataFrame:
    """指数日线（index_daily 表，baostock 代码如 sh.000001），结构与 load_daily 一致。"""
    s = config.fmt_date(start) if start else "19900101"
    e = config.fmt_date(end) if end else "99991231"
    sql = (
        "SELECT trade_date, `open`, high, low, close, volume, amount "
        "FROM index_daily WHERE index_code=%s AND trade_date BETWEEN %s AND %s "
        "ORDER BY trade_date"
    )
    conn = _conn()
    try:
        df = _read_df(conn, sql, (code, s, e))
    finally:
        conn.close()
    return _normalize_daily(df)


def load_breadth(start=None, end=None) -> pd.DataFrame:
    """市场广度缓存（market_breadth 表），trade_date 为索引（DatetimeIndex）。"""
    s = config.fmt_date(start) if start else "19900101"
    e = config.fmt_date(end) if end else "99991231"
    sql = (
        "SELECT trade_date, total_amount, up_count, down_count, flat_count, up_ratio "
        "FROM market_breadth WHERE trade_date BETWEEN %s AND %s ORDER BY trade_date"
    )
    conn = _conn()
    try:
        df = _read_df(conn, sql, (s, e))
    finally:
        conn.close()
    if df.empty:
        return pd.DataFrame(
            columns=["total_amount", "up_count", "down_count",
                     "flat_count", "up_ratio"],
            index=pd.DatetimeIndex([], name="trade_date"),
        )
    df["trade_date"] = pd.to_datetime(df["trade_date"].astype(str), format="%Y%m%d")
    df = df.set_index("trade_date").sort_index()
    for col in ["total_amount", "up_ratio"]:
        df[col] = df[col].astype(float)
    for col in ["up_count", "down_count", "flat_count"]:
        df[col] = df[col].astype("int64")
    return df


def load_cross_section_ohlc(date) -> pd.DataFrame:
    """某日全市场开/收盘价（前复权），用于基准收益计算。"""
    d = config.fmt_date(date)
    sql = (
        "SELECT ts_code, `open`, close_qfq AS close "
        "FROM daily_qfq WHERE trade_date=%s"
    )
    conn = _conn()
    try:
        df = _read_df(conn, sql, (d,))
    finally:
        conn.close()
    if not df.empty:
        df["open"] = df["open"].astype(float)
        df["close"] = df["close"].astype(float)
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
