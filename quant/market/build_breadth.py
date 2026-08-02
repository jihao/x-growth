"""市场广度缓存（market_breadth 表）：每日全市场成交额、涨/跌家数与上涨占比。

数据源自 daily_qfq 聚合（MySQL 5.7 无窗口函数，用 pandas 逐股算涨跌），
表按日 upsert，幂等。日更脚本调用 refresh_recent()；历史用 --rebuild 分年回补。

用法：
    python -m quant.market.build_breadth            # 最近 10 个交易日（日更维护）
    python -m quant.market.build_breadth --rebuild  # 全历史回补（分年，约几分钟）
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from quant import config  # noqa: F401,E402  # 注入 database/mysql 到 sys.path
from mysql_config import connect_mysql, load_dotenv  # noqa: E402

_CREATE_SQL = """
CREATE TABLE IF NOT EXISTS market_breadth (
  trade_date   CHAR(8) NOT NULL PRIMARY KEY,
  total_amount DOUBLE NULL,
  up_count     INT NULL,
  down_count   INT NULL,
  flat_count   INT NULL,
  up_ratio     DOUBLE NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
"""

_UPSERT_SQL = (
    "INSERT INTO market_breadth "
    "(trade_date, total_amount, up_count, down_count, flat_count, up_ratio) "
    "VALUES (%s,%s,%s,%s,%s,%s) "
    "ON DUPLICATE KEY UPDATE "
    "total_amount=VALUES(total_amount), up_count=VALUES(up_count), "
    "down_count=VALUES(down_count), flat_count=VALUES(flat_count), "
    "up_ratio=VALUES(up_ratio)"
)


def _conn():
    load_dotenv()
    return connect_mysql()


def ensure_table(conn) -> None:
    with conn.cursor() as cur:
        cur.execute(_CREATE_SQL)
    conn.commit()


def compute_breadth(df: pd.DataFrame) -> pd.DataFrame:
    """纯计算：逐股日涨跌 -> 每日广度统计。

    df 需含 trade_date(str) / ts_code / close / amount 四列，且覆盖
    目标日期前一个交易日（否则首日逐股涨跌缺失，该日涨/跌家数偏少）。
    返回以 trade_date 排序的 DataFrame：
    total_amount / up_count / down_count / flat_count / up_ratio。
    """
    if df.empty:
        return pd.DataFrame(columns=[
            "trade_date", "total_amount", "up_count",
            "down_count", "flat_count", "up_ratio",
        ])
    d = df.sort_values(["ts_code", "trade_date"]).copy()
    prev_close = d.groupby("ts_code")["close"].shift(1)
    chg = d["close"] - prev_close
    d["_up"] = (chg > 0).astype(int)
    d["_dn"] = (chg < 0).astype(int)
    d["_flat"] = (chg == 0).astype(int)
    g = d.groupby("trade_date").agg(
        total_amount=("amount", "sum"),
        up_count=("_up", "sum"),
        down_count=("_dn", "sum"),
        flat_count=("_flat", "sum"),
    ).reset_index()
    denom = (g["up_count"] + g["down_count"]).replace(0, np.nan)
    g["up_ratio"] = g["up_count"] / denom
    return g.sort_values("trade_date").reset_index(drop=True)


def _load_daily_chunk(conn, start: str, end: str) -> pd.DataFrame:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT trade_date, ts_code, close_qfq AS close, amount "
            "FROM daily_qfq WHERE trade_date BETWEEN %s AND %s",
            (start, end),
        )
        rows = cur.fetchall()
    df = pd.DataFrame(list(rows), columns=["trade_date", "ts_code", "close", "amount"])
    if not df.empty:
        df["close"] = df["close"].astype(float)
        df["amount"] = df["amount"].astype(float)
    return df


def _upsert(conn, stats: pd.DataFrame) -> int:
    rows = [
        (r.trade_date, float(r.total_amount), int(r.up_count), int(r.down_count),
         int(r.flat_count),
         float(r.up_ratio) if pd.notna(r.up_ratio) else None)
        for r in stats.itertuples()
    ]
    with conn.cursor() as cur:
        cur.executemany(_UPSERT_SQL, rows)
    conn.commit()
    return len(rows)


def refresh_recent(conn, days: int = 10, dry_run: bool = False) -> int:
    """重算最近 days 个交易日（含缓冲），幂等。日更脚本调用。"""
    ensure_table(conn)
    with conn.cursor() as cur:
        cur.execute(
            "SELECT DISTINCT trade_date FROM daily_qfq "
            "ORDER BY trade_date DESC LIMIT %s", (days + 25,)
        )
        dates = sorted(r[0] for r in cur.fetchall())
    if not dates:
        return 0
    df = _load_daily_chunk(conn, dates[0], dates[-1])
    stats = compute_breadth(df)
    keep = stats[stats["trade_date"].isin(dates[-days:])]
    if dry_run:
        print(f"  广度最近 {len(keep)} 天（dry-run 未写入）")
        return len(keep)
    n = _upsert(conn, keep)
    print(f"  广度最近 {n} 天已刷新")
    return n


def rebuild(conn, from_year: int = 2010, dry_run: bool = False) -> int:
    """分年回补全历史。每年向前多取 15 天保证跨年首日涨跌可算。"""
    ensure_table(conn)
    with conn.cursor() as cur:
        cur.execute("SELECT MAX(trade_date) FROM daily_qfq")
        max_date = cur.fetchone()[0]
    end_year = int(str(max_date)[:4])
    total = 0
    for year in range(from_year, end_year + 1):
        t0 = time.time()
        start = (pd.Timestamp(f"{year}-01-01") - pd.Timedelta(days=15)
                 ).strftime("%Y%m%d")
        end = f"{year}1231"
        df = _load_daily_chunk(conn, start, end)
        stats = compute_breadth(df)
        stats = stats[stats["trade_date"] >= f"{year}0101"]
        if not dry_run and not stats.empty:
            _upsert(conn, stats)
        total += len(stats)
        print(f"  {year}: {len(stats)} 个交易日（{time.time() - t0:.1f}s）")
    return total


def main() -> int:
    ap = argparse.ArgumentParser(description="市场广度缓存构建")
    ap.add_argument("--rebuild", action="store_true", help="全历史分年回补")
    ap.add_argument("--recent", type=int, default=10, help="默认模式：最近 N 天")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    conn = _conn()
    try:
        if args.rebuild:
            n = rebuild(conn, dry_run=args.dry_run)
        else:
            n = refresh_recent(conn, days=args.recent, dry_run=args.dry_run)
    finally:
        conn.close()
    print(f"完成，共 {n} 天。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
