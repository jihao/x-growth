"""中国法定放假日（本地 JSON，运行时不联网）。"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

_DEFAULT_JSON = Path(__file__).resolve().parent / "cn_holidays_2020_2026.json"


@lru_cache(maxsize=1)
def load_holidays(path: str | None = None) -> tuple[str, ...]:
    """返回 YYYY-MM-DD 放假日元组（进程内缓存）。"""
    p = Path(path) if path else _DEFAULT_JSON
    data = json.loads(p.read_text(encoding="utf-8"))
    holidays = data.get("holidays") or []
    return tuple(str(d) for d in holidays)
