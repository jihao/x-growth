#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
增量更新 MySQL astocks_qfq 到最新交易日
=====================================

功能对齐 update_daily.py：
1. 同步股票列表（自动新增新股、移除退市股）
2. 下载最新K线数据（只下载缺失的日期）

使用方法：
    python update_daily_mysql.py
    python update_daily_mysql.py --dry-run

连接配置见 mysql_config.py / mysql.env（MYSQL_* 环境变量）。
依赖：
    pip install baostock pymysql
"""

from __future__ import annotations

import argparse
import re
import socket
import sys
import time
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import baostock as bs

import mysql_config

socket.setdefaulttimeout(15)

INSERT_STOCK = "INSERT IGNORE INTO stocks (ts_code, name) VALUES (%s, %s)"
DELETE_STOCK = "DELETE FROM stocks WHERE ts_code=%s"
DELETE_DAILY = "DELETE FROM daily_qfq WHERE ts_code=%s"
LATEST_SQL = (
    "SELECT trade_date FROM daily_qfq WHERE ts_code=%s "
    "ORDER BY trade_date DESC LIMIT 1"
)
UPSERT_DAILY = (
    "INSERT INTO daily_qfq "
    "(ts_code, trade_date, `open`, high, low, close_qfq, volume, amount) "
    "VALUES (%s,%s,%s,%s,%s,%s,%s,%s) "
    "ON DUPLICATE KEY UPDATE "
    "`open`=VALUES(`open`), high=VALUES(high), low=VALUES(low), "
    "close_qfq=VALUES(close_qfq), volume=VALUES(volume), amount=VALUES(amount)"
)


def normal_date(td):
    """统一日期格式 YYYY-MM-DD <-> YYYYMMDD"""
    if "-" in td:
        p = td.split("-")
        return (
            f"{p[0]}-{p[1].zfill(2)}-{p[2].zfill(2)}",
            f"{p[0]}{p[1].zfill(2)}{p[2].zfill(2)}",
        )
    return f"{td[:4]}-{td[4:6].zfill(2)}-{td[6:8].zfill(2)}", td


def main():
    parser = argparse.ArgumentParser(description="增量更新 MySQL astocks_qfq")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="只查询并统计，不写入 MySQL",
    )
    args = parser.parse_args()
    dry_run = args.dry_run

    mysql_config.load_dotenv()
    try:
        settings = mysql_config.mysql_settings()
    except ValueError as e:
        print(f"错误: {e}")
        return

    today = date.today()
    TODAY = today.strftime("%Y-%m-%d")
    UPDATE_DATE = today.strftime("%Y%m%d")

    print("=" * 60)
    print("增量更新 MySQL astocks_qfq")
    print("=" * 60)
    print(
        f"MySQL: {settings['user']}@{settings['host']}:{settings['port']}/{settings['database']}"
    )
    print(f"更新日期: {UPDATE_DATE} ({TODAY})")
    if dry_run:
        print("模式: --dry-run（不写入）")
    print()

    try:
        conn = mysql_config.connect_mysql()
    except Exception as e:
        print(f"错误: 无法连接 MySQL: {e}")
        return

    lg = bs.login()
    if lg.error_code != "0":
        print(f"Baostock 登录失败: {lg.error_msg}")
        conn.close()
        return
    print("Baostock 登录成功")

    rs = bs.query_stock_basic()
    bs_stocks = []
    while (rs.error_code == "0") and rs.next():
        bs_stocks.append(rs.get_row_data())

    bs_a_codes = set()
    bs_name_map = {}
    for s in bs_stocks:
        code = s[0]
        name = s[1]
        if re.match(r"(sh\.60|sz\.00|sz\.30|sh\.68)\d+", code):
            ex, num = code.split(".")
            ts_code = f"{num}.{ex.upper()}"
            bs_a_codes.add(ts_code)
            bs_name_map[ts_code] = name

    print(f"baostock A股股票数: {len(bs_a_codes)}")

    c = conn.cursor()
    c.execute("SELECT ts_code FROM stocks")
    our_codes = set(r[0] for r in c.fetchall())

    new_stocks = bs_a_codes - our_codes
    removed_stocks = our_codes - bs_a_codes

    print(f"本地股票数: {len(our_codes)}")
    print(f"新增股票: {len(new_stocks)}")
    print(f"移除股票: {len(removed_stocks)}")

    if removed_stocks:
        if not dry_run:
            for code in removed_stocks:
                c.execute(DELETE_STOCK, (code,))
                c.execute(DELETE_DAILY, (code,))
            conn.commit()
        print(
            f"  {'将移除' if dry_run else '已移除'}: "
            f"{list(removed_stocks)[:5]}{'...' if len(removed_stocks) > 5 else ''}"
        )

    if new_stocks:
        if not dry_run:
            for code in new_stocks:
                c.execute(INSERT_STOCK, (code, bs_name_map.get(code, "")))
            conn.commit()
        print(
            f"  {'将添加' if dry_run else '已添加'}: "
            f"{list(new_stocks)[:5]}{'...' if len(new_stocks) > 5 else ''}"
        )

    if dry_run:
        stocks = sorted((our_codes | new_stocks) - removed_stocks)
    else:
        c.execute("SELECT ts_code FROM stocks ORDER BY ts_code")
        stocks = [r[0] for r in c.fetchall()]

    print(f"\n最终股票总数: {len(stocks)}")
    print()

    updated = 0
    skipped = 0
    failed = 0
    errors = []
    t0 = time.time()

    for i, ts_code in enumerate(stocks):
        code, mkt = ts_code.split(".")
        bs_code = mkt.lower() + "." + code

        c.execute(LATEST_SQL, (ts_code,))
        row = c.fetchone()
        if row:
            _, latest_db = normal_date(str(row[0]))
            if latest_db >= UPDATE_DATE:
                skipped += 1
                continue

        rs = bs.query_history_k_data_plus(
            code=bs_code,
            fields="date,open,high,low,close,volume,amount",
            start_date=TODAY,
            end_date=TODAY,
            frequency="d",
            adjustflag="2",
        )
        data = []
        if rs:
            while rs.next():
                data.append(rs.get_row_data())

        if data and data[0][4]:
            td = data[0][0].replace("-", "")
            params = (
                ts_code,
                td,
                float(data[0][1]) if data[0][1] else None,
                float(data[0][2]) if data[0][2] else None,
                float(data[0][3]) if data[0][3] else None,
                float(data[0][4]) if data[0][4] else None,
                int(float(data[0][5])) if data[0][5] else None,
                float(data[0][6]) if data[0][6] else None,
            )
            try:
                if not dry_run:
                    c.execute(UPSERT_DAILY, params)
                updated += 1
            except Exception as e:
                failed += 1
                errors.append(f"{ts_code}: {e}")
        else:
            skipped += 1

        if (i + 1) % 200 == 0:
            print(
                f"  进度: {i + 1}/{len(stocks)} | 更新:{updated} 跳过:{skipped} 失败:{failed}"
            )

        time.sleep(0.05)

    if not dry_run:
        conn.commit()
    c.close()

    # 指数日线与市场广度：复用本次 baostock 会话与 MySQL 连接，
    # 失败不影响股票日更结果
    try:
        from quant.market import build_breadth, index_update
        print("\n指数日线更新:")
        index_update.update_indices(conn, TODAY, TODAY, dry_run=dry_run)
        print("市场广度刷新:")
        build_breadth.refresh_recent(conn, days=10, dry_run=dry_run)
    except Exception as e:
        print(f"指数/广度更新失败（不影响股票日更）: {e}")

    conn.close()
    bs.logout()

    elapsed = time.time() - t0
    print()
    print("=" * 60)
    print("增量更新完成" + (" (dry-run)" if dry_run else ""))
    print("=" * 60)
    print(f"耗时: {elapsed:.1f}s")
    print(f"更新: {updated} 只")
    print(f"跳过: {skipped} 只 (已最新或非交易日)")
    print(f"失败: {failed} 只")
    if errors[:5]:
        for e in errors[:5]:
            print(f"  错误: {e}")


if __name__ == "__main__":
    main()
