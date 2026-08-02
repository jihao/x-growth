"""指数日线落库（index_daily 表）与历史回补。

指数为交易所官方发布值（非自算），经 baostock 下载，不复权。

用法：
    python -m quant.market.index_update --from 20100101   # 首次回补全部历史
    python -m quant.market.index_update                    # 仅今日（与日更脚本一致）
日更脚本 update_daily_mysql.py 会复用其 baostock 会话调用 update_indices()。
"""
from __future__ import annotations

import argparse
import socket
import sys
from datetime import date
from pathlib import Path

import baostock as bs

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from quant import config  # noqa: F401,E402  # 注入 database/mysql 到 sys.path
from mysql_config import connect_mysql, load_dotenv  # noqa: E402

socket.setdefaulttimeout(15)

# baostock 指数代码 -> 展示名
# 说明：科创50（sh.000688）在 baostock 上无数据/查询会挂起，暂不纳入；
# 科创板个股已通过「中证1000」等中小盘指数间接覆盖。
INDICES = {
    "sh.000001": "上证指数",
    "sz.399001": "深证成指",
    "sz.399006": "创业板指",
    "sh.000300": "沪深300",
    "sh.000852": "中证1000",
}

_CREATE_SQL = """
CREATE TABLE IF NOT EXISTS index_daily (
  index_code VARCHAR(12) NOT NULL,
  trade_date CHAR(8) NOT NULL,
  `open`  DOUBLE NULL,
  high    DOUBLE NULL,
  low     DOUBLE NULL,
  close   DOUBLE NULL,
  volume  BIGINT NULL,
  amount  DOUBLE NULL,
  PRIMARY KEY (index_code, trade_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
"""

_UPSERT_SQL = (
    "INSERT INTO index_daily "
    "(index_code, trade_date, `open`, high, low, close, volume, amount) "
    "VALUES (%s,%s,%s,%s,%s,%s,%s,%s) "
    "ON DUPLICATE KEY UPDATE "
    "`open`=VALUES(`open`), high=VALUES(high), low=VALUES(low), "
    "close=VALUES(close), volume=VALUES(volume), amount=VALUES(amount)"
)


def ensure_table(conn) -> None:
    with conn.cursor() as cur:
        cur.execute(_CREATE_SQL)
    conn.commit()


def fetch_index(code: str, start: str, end: str) -> list[tuple]:
    """从 baostock 拉取指数日线（需已登录）。日期转 YYYYMMDD。"""
    rs = bs.query_history_k_data_plus(
        code=code,
        fields="date,open,high,low,close,volume,amount",
        start_date=start, end_date=end,
        frequency="d", adjustflag="3",
    )
    rows = []
    while (rs.error_code == "0") and rs.next():
        r = rs.get_row_data()
        if not r[3]:
            continue
        rows.append((
            code, r[0].replace("-", ""),
            float(r[1]) if r[1] else None, float(r[2]) if r[2] else None,
            float(r[3]) if r[3] else None, float(r[4]) if r[4] else None,
            int(float(r[5])) if r[5] else None,
            float(r[6]) if r[6] else None,
        ))
    return rows


def update_indices(conn, start: str, end: str, dry_run: bool = False) -> int:
    """抓取 [start, end]（YYYY-MM-DD）区间全部指数并落库，返回写入行数。"""
    ensure_table(conn)
    total = 0
    with conn.cursor() as cur:
        for code, name in INDICES.items():
            rows = fetch_index(code, start, end)
            if rows and not dry_run:
                cur.executemany(_UPSERT_SQL, rows)
            total += len(rows)
            print(f"  {name}（{code}）: {len(rows)} 行"
                  f"{'（dry-run 未写入）' if dry_run else ''}")
    if not dry_run:
        conn.commit()
    return total


def main() -> int:
    ap = argparse.ArgumentParser(description="指数日线更新/回补")
    ap.add_argument("--from", dest="start", default=None,
                    help="开始日期 YYYYMMDD 或 YYYY-MM-DD，缺省仅今日")
    args = ap.parse_args()
    today = date.today().strftime("%Y-%m-%d")
    start = args.start or today
    if "-" not in start:
        start = f"{start[:4]}-{start[4:6]}-{start[6:]}"

    load_dotenv()
    lg = bs.login()
    if lg.error_code != "0":
        print(f"Baostock 登录失败: {lg.error_msg}")
        return 1
    print(f"指数日线更新：{start} ~ {today}")
    conn = connect_mysql()
    try:
        n = update_indices(conn, start, today)
    finally:
        conn.close()
        bs.logout()
    print(f"完成，共 {n} 行。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
