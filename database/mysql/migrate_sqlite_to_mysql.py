#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""将 astocks_qfq.db 的 stocks / daily_qfq 全量迁入 MySQL。"""

from __future__ import annotations

import argparse
import sqlite3
import sys
import time
from pathlib import Path

import mysql_config

HERE = Path(__file__).resolve().parent
DEFAULT_SQLITE = HERE / "astocks_qfq.db"
SCHEMA_PATH = HERE / "schema_mysql.sql"

STOCKS_INSERT = "INSERT INTO stocks (ts_code, name) VALUES (%s, %s)"
DAILY_INSERT = (
    "INSERT INTO daily_qfq "
    "(ts_code, trade_date, `open`, high, low, close_qfq, volume, amount) "
    "VALUES (%s, %s, %s, %s, %s, %s, %s, %s)"
)


def _split_sql(sql: str) -> list[str]:
    stmts: list[str] = []
    buf: list[str] = []
    for line in sql.splitlines():
        if line.strip().startswith("--"):
            continue
        buf.append(line)
        if ";" in line:
            chunk = "\n".join(buf).strip()
            buf = []
            for part in chunk.split(";"):
                part = part.strip()
                if part:
                    stmts.append(part)
    return stmts


def apply_schema() -> None:
    sql = SCHEMA_PATH.read_text(encoding="utf-8")
    conn = mysql_config.connect_mysql(database=None)
    try:
        with conn.cursor() as cur:
            for stmt in _split_sql(sql):
                cur.execute(stmt)
        conn.commit()
    finally:
        conn.close()


def table_counts(conn) -> dict:
    with conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM stocks")
        stocks = cur.fetchone()[0]
        cur.execute(
            "SELECT COUNT(*), COUNT(DISTINCT ts_code), "
            "MIN(trade_date), MAX(trade_date), "
            "COALESCE(SUM(close_qfq),0) FROM daily_qfq"
        )
        rows, codes, dmin, dmax, sclose = cur.fetchone()
    return {
        "stocks": stocks,
        "rows": rows,
        "codes": codes,
        "min_date": dmin,
        "max_date": dmax,
        "sum_close": float(sclose or 0),
    }


def sqlite_stats(sqlite_path: Path) -> dict:
    conn = sqlite3.connect(f"file:{sqlite_path}?mode=ro", uri=True)
    try:
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM stocks")
        stocks = cur.fetchone()[0]
        cur.execute(
            "SELECT COUNT(*), COUNT(DISTINCT ts_code), "
            "MIN(trade_date), MAX(trade_date), "
            "COALESCE(SUM(close_qfq),0) FROM daily_qfq"
        )
        rows, codes, dmin, dmax, sclose = cur.fetchone()
        return {
            "stocks": stocks,
            "rows": rows,
            "codes": codes,
            "min_date": dmin,
            "max_date": dmax,
            "sum_close": float(sclose or 0),
        }
    finally:
        conn.close()


def migrate(sqlite_path: Path, force: bool, batch_size: int) -> int:
    if not sqlite_path.is_file():
        print(f"SQLite 不存在: {sqlite_path}", file=sys.stderr)
        return 2

    mysql_config.load_dotenv()
    settings = mysql_config.mysql_settings()
    print(f"SQLite: {sqlite_path}")
    print(
        f"MySQL: {settings['user']}@{settings['host']}:{settings['port']}/{settings['database']}"
    )

    apply_schema()
    dst = mysql_config.connect_mysql()
    src = sqlite3.connect(f"file:{sqlite_path}?mode=ro", uri=True)
    try:
        with dst.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM daily_qfq")
            existing = cur.fetchone()[0]
        if existing and not force:
            print(
                f"目标 daily_qfq 已有 {existing} 行。使用 --force 清空后重导。",
                file=sys.stderr,
            )
            return 3
        if force:
            with dst.cursor() as cur:
                cur.execute("TRUNCATE TABLE daily_qfq")
                cur.execute("TRUNCATE TABLE stocks")
            dst.commit()
            print("已 TRUNCATE stocks / daily_qfq")

        t0 = time.time()
        rows = src.execute(
            "SELECT ts_code, COALESCE(name,'') FROM stocks"
        ).fetchall()
        with dst.cursor() as cur:
            for i in range(0, len(rows), batch_size):
                cur.executemany(STOCKS_INSERT, rows[i : i + batch_size])
        dst.commit()
        print(f"stocks 导入: {len(rows)}")

        years = [
            r[0]
            for r in src.execute(
                "SELECT DISTINCT substr(trade_date,1,4) FROM daily_qfq ORDER BY 1"
            )
        ]
        total = 0
        for year in years:
            batch = src.execute(
                "SELECT ts_code, trade_date, open, high, low, close_qfq, volume, amount "
                "FROM daily_qfq WHERE substr(trade_date,1,4)=?",
                (year,),
            )
            year_n = 0
            with dst.cursor() as cur:
                while True:
                    chunk = batch.fetchmany(batch_size)
                    if not chunk:
                        break
                    buf = [tuple(r) for r in chunk]
                    cur.executemany(DAILY_INSERT, buf)
                    year_n += len(buf)
                    total += len(buf)
                dst.commit()
            print(f"  {year}: {year_n} 行")
        print(f"daily_qfq 导入合计: {total} 耗时 {time.time() - t0:.1f}s")

        left = sqlite_stats(sqlite_path)
        right = table_counts(dst)
        print("校验 SQLite vs MySQL:")
        ok = True
        for key in ("stocks", "rows", "codes", "min_date", "max_date"):
            match = left[key] == right[key]
            ok = ok and match
            print(f"  {key}: {left[key]} vs {right[key]} {'OK' if match else 'FAIL'}")
        close_ok = abs(left["sum_close"] - right["sum_close"]) < 1.0
        ok = ok and close_ok
        print(
            f"  sum_close: {left['sum_close']:.4f} vs {right['sum_close']:.4f} "
            f"{'OK' if close_ok else 'FAIL'}"
        )
        return 0 if ok else 4
    finally:
        src.close()
        dst.close()


def main() -> None:
    p = argparse.ArgumentParser(description="Migrate stocks/daily_qfq SQLite → MySQL")
    p.add_argument("--sqlite", default=str(DEFAULT_SQLITE))
    p.add_argument("--force", action="store_true")
    p.add_argument("--batch-size", type=int, default=2000)
    args = p.parse_args()
    raise SystemExit(migrate(Path(args.sqlite), args.force, args.batch_size))


if __name__ == "__main__":
    main()
