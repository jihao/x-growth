"""选股结果落库（MySQL screening_results 表）。同日重跑先删后插，保证幂等。"""
from __future__ import annotations

import json

import pandas as pd

from quant import config  # noqa: F401  # 注入 database/mysql 到 sys.path
from mysql_config import connect_mysql, load_dotenv

_CREATE_SQL = """
CREATE TABLE IF NOT EXISTS screening_results (
  trade_date      CHAR(8) NOT NULL,
  ts_code         VARCHAR(12) NOT NULL,
  rank_no         INT NOT NULL,
  total_score     DECIMAL(8,4) NULL,
  score_strategy  DECIMAL(8,4) NULL,
  score_structure DECIMAL(8,4) NULL,
  score_volume    DECIMAL(8,4) NULL,
  weights_json    TEXT NULL,
  factors_json    TEXT NULL,
  created_at      DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (trade_date, ts_code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
"""

_INSERT_SQL = (
    "INSERT INTO screening_results "
    "(trade_date, ts_code, rank_no, total_score, score_strategy, "
    " score_structure, score_volume, weights_json, factors_json) "
    "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)"
)

_COLS = [
    "ts_code", "rank_no", "total_score", "score_strategy",
    "score_structure", "score_volume", "weights_json", "factors_json",
]

_ensured = False


def _conn():
    load_dotenv()
    return connect_mysql()


def _ensure_on(conn) -> None:
    """在已有连接上建表；进程内只执行一次 CREATE。"""
    global _ensured
    if _ensured:
        return
    with conn.cursor() as cur:
        cur.execute(_CREATE_SQL)
    conn.commit()
    _ensured = True


def ensure_table() -> None:
    if _ensured:
        return
    conn = _conn()
    try:
        _ensure_on(conn)
    finally:
        conn.close()


def _dump(value) -> str:
    """dict/list -> JSON 字符串；已是字符串则原样保存。"""
    if isinstance(value, str):
        return value
    return json.dumps(value or {}, ensure_ascii=False)


def save_results(trade_date, results: pd.DataFrame) -> int:
    """保存某日选股结果。results 需含 _COLS 列；同日主键冲突时整批重写。"""
    d = config.fmt_date(trade_date)
    conn = _conn()
    try:
        _ensure_on(conn)
        with conn.cursor() as cur:
            cur.execute("DELETE FROM screening_results WHERE trade_date=%s", (d,))
            rows = []
            for _, r in results.iterrows():
                rows.append((
                    d,
                    r["ts_code"],
                    int(r["rank_no"]),
                    float(r["total_score"]),
                    float(r["score_strategy"]),
                    float(r["score_structure"]),
                    float(r["score_volume"]),
                    _dump(r.get("weights_json")),
                    _dump(r.get("factors_json")),
                ))
            if rows:
                cur.executemany(_INSERT_SQL, rows)
        conn.commit()
        return len(rows)
    finally:
        conn.close()


def load_results(trade_date) -> pd.DataFrame:
    """读取某日选股结果（关联股票名称，按排名升序）。"""
    d = config.fmt_date(trade_date)
    conn = _conn()
    try:
        _ensure_on(conn)
        with conn.cursor() as cur:
            cur.execute(
                "SELECT r.trade_date, r.rank_no, r.ts_code, s.name, "
                "r.total_score, r.score_strategy, r.score_structure, "
                "r.score_volume, r.weights_json, r.factors_json "
                "FROM screening_results r "
                "LEFT JOIN stocks s ON s.ts_code=r.ts_code "
                "WHERE r.trade_date=%s ORDER BY r.rank_no",
                (d,),
            )
            rows = cur.fetchall()
            cols = [c[0] for c in cur.description] if cur.description else []
        return pd.DataFrame(list(rows), columns=cols)
    finally:
        conn.close()


def load_stock_results(ts_code, start, end) -> pd.DataFrame:
    """读取某股票在 [start, end] 区间内的全部选股记录（按日期升序）。

    供跟踪复盘使用：查询入选后窗口期内的再入选/分数/因子变化。
    """
    s, e = config.fmt_date(start), config.fmt_date(end)
    conn = _conn()
    try:
        _ensure_on(conn)
        with conn.cursor() as cur:
            cur.execute(
                "SELECT trade_date, rank_no, total_score, score_strategy, "
                "score_structure, score_volume, weights_json, factors_json "
                "FROM screening_results "
                "WHERE ts_code=%s AND trade_date BETWEEN %s AND %s "
                "ORDER BY trade_date",
                (ts_code, s, e),
            )
            rows = cur.fetchall()
            cols = [c[0] for c in cur.description] if cur.description else []
        return pd.DataFrame(list(rows), columns=cols)
    finally:
        conn.close()


def load_results_many(codes: list[str], start, end) -> pd.DataFrame:
    """多股票区间选股记录一次取数（含 ts_code 列），供批量复盘使用。"""
    s, e = config.fmt_date(start), config.fmt_date(end)
    if not codes:
        return pd.DataFrame()
    placeholders = ",".join(["%s"] * len(codes))
    conn = _conn()
    try:
        _ensure_on(conn)
        with conn.cursor() as cur:
            cur.execute(
                f"SELECT ts_code, trade_date, rank_no, total_score, "
                f"score_strategy, score_structure, score_volume, "
                f"weights_json, factors_json FROM screening_results "
                f"WHERE ts_code IN ({placeholders}) "
                f"AND trade_date BETWEEN %s AND %s "
                f"ORDER BY trade_date, rank_no",
                (*codes, s, e),
            )
            rows = cur.fetchall()
            cols = [c[0] for c in cur.description] if cur.description else []
        return pd.DataFrame(list(rows), columns=cols)
    finally:
        conn.close()


def list_dates() -> list[str]:
    """已有选股结果的交易日列表，新的在前。"""
    conn = _conn()
    try:
        _ensure_on(conn)
        with conn.cursor() as cur:
            cur.execute(
                "SELECT DISTINCT trade_date FROM screening_results "
                "ORDER BY trade_date DESC"
            )
            return [r[0] for r in cur.fetchall()]
    finally:
        conn.close()
