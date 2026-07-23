"""集中度预计算 CLI：全量 rebuild 或从已缓存最大日期增量。

用法:
  .venv/bin/python -m quant.concentration.build_cache --rebuild
  .venv/bin/python -m quant.concentration.build_cache            # 增量
  .venv/bin/python -m quant.concentration.build_cache --start 2024-01-01 --end 2024-12-31
"""
from __future__ import annotations

import argparse
import sys

from quant.concentration import cache, market
from quant.data import loader


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--rebuild", action="store_true", help="全量重算")
    parser.add_argument("--start", default=None)
    parser.add_argument("--end", default=None)
    args = parser.parse_args(argv)

    cache.ensure_table()

    if args.start:
        start = args.start
    elif args.rebuild:
        start = "20100101"
    else:
        last = cache.max_cached_date()
        start = last or "20100101"
    end = args.end or "20991231"

    dates = loader.trading_dates(start, end)
    if not args.rebuild and cache.max_cached_date() in dates:
        dates = dates[dates.index(cache.max_cached_date()) + 1:]

    print(f"待计算交易日 {len(dates)} 个：{start}..{end}")
    conn = cache._conn()
    sql = cache.upsert_sql()
    try:
        for i, d in enumerate(dates, 1):
            cs = loader.load_cross_section(d)
            if cs.empty:
                continue
            row = market.concentration_row(cs)
            with conn.cursor() as cur:
                cur.execute(sql, cache.row_to_params(d, row))
            if i % 50 == 0:
                conn.commit()
                print(f"  {i}/{len(dates)} {d}")
        conn.commit()
    finally:
        conn.close()
    print("完成。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
