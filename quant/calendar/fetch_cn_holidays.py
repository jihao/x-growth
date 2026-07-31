#!/usr/bin/env python3
"""从 timor.tech 拉取中国法定放假日并写入 JSON（可重复运行）。

用法（仓库根目录）:
  .venv/bin/python -m quant.calendar.fetch_cn_holidays
  .venv/bin/python -m quant.calendar.fetch_cn_holidays --start 2020 --end 2026
"""
from __future__ import annotations

import argparse
import json
import time
import urllib.request
from pathlib import Path

OUT = Path(__file__).resolve().parent / "cn_holidays_2020_2026.json"
SOURCE = "https://timor.tech/api/holiday/"


def fetch_year(year: int) -> dict:
    url = f"{SOURCE}year/{year}/"
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (compatible; x-growth/1.0)",
            "Accept": "application/json",
            "Referer": SOURCE,
        },
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def collect_holidays(start: int, end: int) -> list[str]:
    holidays: set[str] = set()
    for year in range(start, end + 1):
        last_err = None
        for attempt in range(1, 5):
            try:
                data = fetch_year(year)
                if data.get("code") != 0:
                    raise RuntimeError(f"code={data.get('code')}")
                for mmdd, info in (data.get("holiday") or {}).items():
                    if isinstance(info, dict) and info.get("holiday") is True:
                        holidays.add(info.get("date") or f"{year}-{mmdd}")
                print(f"{year}: ok")
                last_err = None
                break
            except Exception as exc:
                last_err = exc
                time.sleep(2 * attempt)
        if last_err is not None:
            raise RuntimeError(f"{year}: {last_err}") from last_err
        time.sleep(1.5)
    return sorted(holidays)


def main() -> int:
    p = argparse.ArgumentParser(description="拉取中国法定放假日到 JSON")
    p.add_argument("--start", type=int, default=2020)
    p.add_argument("--end", type=int, default=2026)
    p.add_argument("--out", type=Path, default=OUT)
    args = p.parse_args()
    holidays = collect_holidays(args.start, args.end)
    payload = {
        "source": SOURCE,
        "years": list(range(args.start, args.end + 1)),
        "holidays": holidays,
    }
    args.out.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"wrote {args.out} ({len(holidays)} days)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
