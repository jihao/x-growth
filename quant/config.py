"""全局配置与路径。导入本模块会把 database/mysql 加入 sys.path，便于复用 mysql_config。"""
from __future__ import annotations

import sys
from datetime import datetime, date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MYSQL_DIR = ROOT / "database" / "mysql"

if str(MYSQL_DIR) not in sys.path:
    sys.path.insert(0, str(MYSQL_DIR))

DEFAULT_START = "20100101"
CR_LEVELS = (5, 10, 20, 50, 100)
CONCENTRATION_TABLE = "market_concentration"


def fmt_date(value) -> str:
    """把日期统一成 YYYYMMDD 字符串。接受 datetime/date/'YYYY-MM-DD'/'YYYYMMDD'。"""
    if isinstance(value, (datetime, date)):
        return value.strftime("%Y%m%d")
    s = str(value).strip().replace("-", "").replace("/", "")
    if len(s) != 8 or not s.isdigit():
        raise ValueError(f"无法解析日期: {value!r}")
    try:
        datetime.strptime(s, "%Y%m%d")
    except ValueError:
        raise ValueError(f"无法解析日期: {value!r}") from None
    return s
