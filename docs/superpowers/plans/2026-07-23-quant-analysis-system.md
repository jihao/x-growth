# 量化分析系统 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在现有 A 股前复权日线（MySQL）之上，构建本地纯 Python 的量化分析系统：技术指标、市场资金集中度、策略回测，配 Streamlit + Plotly 交互网页。

**Architecture:** `quant/` 为纯逻辑库（data / indicators / concentration / backtest / charts），可独立 import 与单测；`app/main.py` 为 Streamlit 界面层，只做拼装调用。数据统一从 MySQL 读取（复用 `database/mysql/mysql_config.py`）。

**Tech Stack:** Python 3.13、pandas、numpy、pymysql、plotly、streamlit、pytest。

## Global Constraints

- 数据源统一 MySQL，连接复用 `database/mysql/mysql_config.py::connect_mysql()`（读取 `database/mysql/mysql.env`）。
- 行情标准字段：`open, high, low, close, volume, amount`，索引 `trade_date`（datetime，升序）；`close` 由库字段 `close_qfq` 映射。
- 库内日期为 `YYYYMMDD` 字符串；对外接口日期入参可带或不带分隔符，内部统一转 `YYYYMMDD`。
- **防未来函数**：信号在 T 日收盘生成，按 **T+1 收盘价成交（close-to-close 模型）**；策略 v1 为**多头**（仓位 ∈ {0,1}）。
- 所有纯逻辑单测必须离线可跑（不连 MySQL）：把 DB I/O 与纯计算分离，单测只测纯计算函数。连库脚本（缓存预计算）作为手动集成步骤，不进 pytest 默认集合。
- 依赖装在 `.venv`：`.venv/bin/python`、`.venv/bin/pytest`。
- 编码 UTF-8；每个 Task 结束提交一次。

---

### Task 1: 项目脚手架与依赖

**Files:**
- Create: `quant/__init__.py`, `quant/config.py`
- Create: `quant/data/__init__.py`, `quant/indicators/__init__.py`, `quant/concentration/__init__.py`, `quant/backtest/__init__.py`, `quant/backtest/strategies/__init__.py`, `quant/charts/__init__.py`
- Create: `tests/__init__.py`, `tests/conftest.py`
- Modify: `requirements.txt`
- Test: `tests/test_config.py`

**Interfaces:**
- Produces: `quant.config.ROOT` (Path), `quant.config.CR_LEVELS` (tuple), `quant.config.CONCENTRATION_TABLE` (str), `quant.config.DEFAULT_START` (str), `quant.config.fmt_date(s)->str`（把 `2010-01-01`/`20100101`/`datetime` 统一成 `YYYYMMDD`）；导入 `quant.config` 后 `database/mysql` 在 `sys.path` 中，可 `import mysql_config`。

- [ ] **Step 1: 追加依赖**

在 `requirements.txt` 末尾追加（保留已有 database 段）：

```
# quant/ 分析系统依赖
pymysql>=1.1.0
plotly>=5.20
streamlit>=1.33
pytest>=8.0
```

- [ ] **Step 2: 安装依赖**

Run: `.venv/bin/pip install -r requirements.txt`
Expected: 安装成功（含 pandas/numpy/pymysql/plotly/streamlit/pytest）。

- [ ] **Step 3: 写 `quant/config.py`**

```python
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
    return s
```

- [ ] **Step 4: 建空包文件**

所有 `__init__.py` 写空内容（占位使目录成为包）。`tests/conftest.py` 写：

```python
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
```

- [ ] **Step 5: 写失败测试 `tests/test_config.py`**

```python
from datetime import date

from quant import config


def test_fmt_date_variants():
    assert config.fmt_date("2010-01-01") == "20100101"
    assert config.fmt_date("20100101") == "20100101"
    assert config.fmt_date(date(2010, 1, 1)) == "20100101"


def test_mysql_dir_on_path():
    assert str(config.MYSQL_DIR) in __import__("sys").path
```

- [ ] **Step 6: 运行测试**

Run: `.venv/bin/pytest tests/test_config.py -v`
Expected: PASS。

- [ ] **Step 7: 提交**

```bash
git add quant tests requirements.txt
git commit -m "feat(quant): 项目脚手架、config 与依赖"
```

---

### Task 2: 数据访问层

**Files:**
- Create: `quant/data/loader.py`
- Test: `tests/test_loader.py`

**Interfaces:**
- Consumes: `quant.config`（`fmt_date`、sys.path 注入）、`mysql_config.connect_mysql`。
- Produces:
  - `load_daily(ts_code, start=None, end=None) -> pd.DataFrame`（列 `open,high,low,close,volume,amount`，index=`trade_date` datetime 升序）
  - `load_cross_section(date) -> pd.DataFrame`（列 `ts_code,name,close,volume,amount`）
  - `list_stocks() -> pd.DataFrame`（列 `ts_code,name`）
  - `trading_dates(start, end) -> list[str]`（`YYYYMMDD`）
  - `_normalize_daily(df_raw) -> pd.DataFrame`（纯函数，供离线测试）

- [ ] **Step 1: 写失败测试 `tests/test_loader.py`**（只测纯函数 `_normalize_daily`）

```python
import pandas as pd

from quant.data import loader


def test_normalize_daily_sorts_and_types():
    raw = pd.DataFrame(
        {
            "trade_date": ["20100104", "20100105"],
            "open": ["1.0", "2.0"],
            "high": ["1.5", "2.5"],
            "low": ["0.5", "1.5"],
            "close": ["1.2", "2.2"],
            "volume": [100, 200],
            "amount": ["1000.0", "2000.0"],
        }
    )
    out = loader._normalize_daily(raw)
    assert list(out.columns) == ["open", "high", "low", "close", "volume", "amount"]
    assert str(out.index.dtype).startswith("datetime64")
    assert out.index.is_monotonic_increasing
    assert out["close"].dtype == float
    assert out.iloc[0]["close"] == 1.2


def test_normalize_daily_empty():
    assert loader._normalize_daily(pd.DataFrame()).empty
```

- [ ] **Step 2: 运行确认失败**

Run: `.venv/bin/pytest tests/test_loader.py -v`
Expected: FAIL（`loader` 无 `_normalize_daily`）。

- [ ] **Step 3: 实现 `quant/data/loader.py`**

```python
"""统一行情读取层（MySQL）。DB I/O 与纯计算分离，纯计算可离线测试。"""
from __future__ import annotations

import pandas as pd

from quant import config  # noqa: F401  # 注入 sys.path
from mysql_config import connect_mysql, load_dotenv

_DAILY_COLS = ["open", "high", "low", "close", "volume", "amount"]


def _conn():
    load_dotenv()
    return connect_mysql()


def _normalize_daily(df_raw: pd.DataFrame) -> pd.DataFrame:
    if df_raw is None or df_raw.empty:
        return pd.DataFrame(columns=_DAILY_COLS)
    df = df_raw.copy()
    df["trade_date"] = pd.to_datetime(df["trade_date"].astype(str), format="%Y%m%d")
    df = df.set_index("trade_date").sort_index()
    for col in ["open", "high", "low", "close", "amount"]:
        df[col] = df[col].astype(float)
    df["volume"] = df["volume"].astype("int64")
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
        df = pd.read_sql(sql, conn, params=(ts_code, s, e))
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
        df = pd.read_sql(sql, conn, params=(d,))
    finally:
        conn.close()
    if not df.empty:
        df["close"] = df["close"].astype(float)
        df["amount"] = df["amount"].astype(float)
        df["volume"] = df["volume"].astype("int64")
    return df


def list_stocks() -> pd.DataFrame:
    conn = _conn()
    try:
        return pd.read_sql("SELECT ts_code, name FROM stocks ORDER BY ts_code", conn)
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
        df = pd.read_sql(sql, conn, params=(s, e))
    finally:
        conn.close()
    return df["trade_date"].astype(str).tolist()
```

- [ ] **Step 4: 运行测试**

Run: `.venv/bin/pytest tests/test_loader.py -v`
Expected: PASS。

- [ ] **Step 5:（可选，手动集成）验证连库**

Run: `.venv/bin/python -c "from quant.data import loader; print(loader.load_daily('000001.SZ','2024-01-01','2024-02-01').tail())"`
Expected: 打印近月日线（需网络可达远程 MySQL；沙盒不可用时跳过）。

- [ ] **Step 6: 提交**

```bash
git add quant/data/loader.py tests/test_loader.py
git commit -m "feat(quant): MySQL 行情读取层"
```

---

### Task 3: 技术指标库

**Files:**
- Create: `quant/indicators/ta.py`
- Test: `tests/test_indicators.py`

**Interfaces:**
- Produces（均输入/输出 pandas，长度对齐原序列）：
  - `ma(s, n)`, `ema(s, n)`
  - `macd(close, fast=12, slow=26, signal=9) -> (dif, dea, hist)`
  - `boll(close, n=20, k=2.0) -> (upper, mid, lower)`
  - `rsi(close, n=14) -> Series`
  - `kdj(high, low, close, n=9, k=3, d=3) -> (k, d, j)`
  - `roc(close, n=12) -> Series`
  - `obv(close, volume) -> Series`
  - `mfi(high, low, close, volume, n=14) -> Series`
  - `atr(high, low, close, n=14) -> Series`
  - `swing_points(close, window=5) -> DataFrame[is_high, is_low]`
  - `ma_bull_alignment(close, periods=(5,10,20,60)) -> Series[bool]`

- [ ] **Step 1: 写失败测试 `tests/test_indicators.py`**

```python
import numpy as np
import pandas as pd

from quant.indicators import ta


def _series(vals):
    idx = pd.date_range("2020-01-01", periods=len(vals), freq="D")
    return pd.Series(vals, index=idx, dtype=float)


def test_ma():
    s = _series([1, 2, 3, 4, 5])
    assert ta.ma(s, 3).iloc[-1] == 4.0  # (3+4+5)/3


def test_ema_first_equals_value():
    s = _series([1, 2, 3])
    assert ta.ema(s, 2).iloc[0] == 1.0


def test_macd_shapes():
    s = _series(np.linspace(1, 10, 40))
    dif, dea, hist = ta.macd(s)
    assert len(dif) == len(dea) == len(hist) == 40
    assert np.allclose((dif - dea).dropna(), hist.dropna())


def test_boll_constant_zero_width():
    s = _series([5] * 25)
    up, mid, low = ta.boll(s, n=20, k=2.0)
    assert up.iloc[-1] == mid.iloc[-1] == low.iloc[-1] == 5.0


def test_rsi_bounds_and_uptrend():
    s = _series(np.arange(1, 40, dtype=float))
    r = ta.rsi(s, 14).dropna()
    assert (r >= 0).all() and (r <= 100).all()
    assert r.iloc[-1] > 70


def test_roc():
    s = _series([10, 11, 12, 13])
    assert round(ta.roc(s, 1).iloc[-1], 4) == round((13 / 12 - 1) * 100, 4)


def test_obv_direction():
    close = _series([10, 11, 10, 12])
    vol = pd.Series([100, 200, 150, 300], index=close.index, dtype=float)
    o = ta.obv(close, vol)
    assert o.iloc[1] == 200      # 上涨 +vol
    assert o.iloc[2] == 200 - 150  # 下跌 -vol
    assert o.iloc[3] == 50 + 300


def test_atr_positive():
    n = 20
    idx = pd.date_range("2020-01-01", periods=n, freq="D")
    high = pd.Series(np.arange(2, 2 + n), index=idx, dtype=float)
    low = pd.Series(np.arange(1, 1 + n), index=idx, dtype=float)
    close = (high + low) / 2
    a = ta.atr(high, low, close, 14).dropna()
    assert (a > 0).all()
```

- [ ] **Step 2: 运行确认失败**

Run: `.venv/bin/pytest tests/test_indicators.py -v`
Expected: FAIL（模块/函数未定义）。

- [ ] **Step 3: 实现 `quant/indicators/ta.py`**

```python
"""技术指标库：纯 pandas/numpy 实现，输入输出长度对齐。"""
from __future__ import annotations

import numpy as np
import pandas as pd


def ma(s: pd.Series, n: int) -> pd.Series:
    return s.rolling(n).mean()


def ema(s: pd.Series, n: int) -> pd.Series:
    return s.ewm(span=n, adjust=False).mean()


def macd(close, fast=12, slow=26, signal=9):
    dif = ema(close, fast) - ema(close, slow)
    dea = ema(dif, signal)
    hist = dif - dea
    return dif, dea, hist


def boll(close, n=20, k=2.0):
    mid = close.rolling(n).mean()
    std = close.rolling(n).std(ddof=0)
    return mid + k * std, mid, mid - k * std


def rsi(close, n=14):
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / n, adjust=False, min_periods=n).mean()
    avg_loss = loss.ewm(alpha=1 / n, adjust=False, min_periods=n).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    out = 100 - 100 / (1 + rs)
    out = out.where(avg_loss != 0, 100.0)
    return out


def kdj(high, low, close, n=9, k=3, d=3):
    low_n = low.rolling(n).min()
    high_n = high.rolling(n).max()
    rsv = (close - low_n) / (high_n - low_n).replace(0, np.nan) * 100
    k_line = rsv.ewm(alpha=1 / k, adjust=False).mean()
    d_line = k_line.ewm(alpha=1 / d, adjust=False).mean()
    j_line = 3 * k_line - 2 * d_line
    return k_line, d_line, j_line


def roc(close, n=12):
    return (close / close.shift(n) - 1) * 100


def obv(close, volume):
    direction = np.sign(close.diff()).fillna(0)
    return (direction * volume).cumsum()


def _typical_price(high, low, close):
    return (high + low + close) / 3


def mfi(high, low, close, volume, n=14):
    tp = _typical_price(high, low, close)
    mf = tp * volume
    pos = mf.where(tp > tp.shift(1), 0.0)
    neg = mf.where(tp < tp.shift(1), 0.0)
    pos_sum = pos.rolling(n).sum()
    neg_sum = neg.rolling(n).sum().replace(0, np.nan)
    mfr = pos_sum / neg_sum
    return 100 - 100 / (1 + mfr)


def atr(high, low, close, n=14):
    prev_close = close.shift(1)
    tr = pd.concat(
        [(high - low), (high - prev_close).abs(), (low - prev_close).abs()], axis=1
    ).max(axis=1)
    return tr.ewm(alpha=1 / n, adjust=False, min_periods=n).mean()


def swing_points(close, window=5):
    highs = close.rolling(window * 2 + 1, center=True).max()
    lows = close.rolling(window * 2 + 1, center=True).min()
    return pd.DataFrame(
        {"is_high": close == highs, "is_low": close == lows}, index=close.index
    )


def ma_bull_alignment(close, periods=(5, 10, 20, 60)):
    mas = [ma(close, p) for p in periods]
    aligned = pd.Series(True, index=close.index)
    for faster, slower in zip(mas[:-1], mas[1:]):
        aligned &= faster > slower
    return aligned.where(mas[-1].notna(), False)
```

- [ ] **Step 4: 运行测试**

Run: `.venv/bin/pytest tests/test_indicators.py -v`
Expected: PASS。

- [ ] **Step 5: 提交**

```bash
git add quant/indicators/ta.py tests/test_indicators.py
git commit -m "feat(quant): 技术指标库"
```

---

### Task 4: 资金集中度算法（纯计算）

**Files:**
- Create: `quant/concentration/market.py`
- Test: `tests/test_concentration.py`

**Interfaces:**
- Consumes: `quant.config.CR_LEVELS`。
- Produces:
  - `classify_board(ts_code) -> str`（返回 `sh_main/sz_main/sme/gem/star/bse/other` 之一）
  - `cr_n(amounts: pd.Series, n: int) -> float`
  - `hhi(amounts: pd.Series) -> float`（0..1）
  - `gini(amounts: pd.Series) -> float`（0..1）
  - `board_amounts(df) -> dict[str, float]`（df 含 `ts_code,amount`）
  - `concentration_row(df) -> dict`（df 含 `ts_code,amount`；返回一行缓存字段：`total_amount, cr5..cr100, hhi, gini, amt_*`）

- [ ] **Step 1: 写失败测试 `tests/test_concentration.py`**

```python
import numpy as np
import pandas as pd

from quant.concentration import market as m


def test_classify_board():
    assert m.classify_board("600000.SH") == "sh_main"
    assert m.classify_board("000001.SZ") == "sz_main"
    assert m.classify_board("002415.SZ") == "sme"
    assert m.classify_board("300750.SZ") == "gem"
    assert m.classify_board("688981.SH") == "star"
    assert m.classify_board("830799.BJ") == "bse"


def test_cr_n():
    amt = pd.Series([50, 30, 15, 5], dtype=float)  # total 100
    assert m.cr_n(amt, 1) == 0.5
    assert m.cr_n(amt, 2) == 0.8
    assert m.cr_n(amt, 10) == 1.0  # n 超过数量取全部


def test_hhi_equal_vs_concentrated():
    equal = pd.Series([25, 25, 25, 25], dtype=float)
    conc = pd.Series([97, 1, 1, 1], dtype=float)
    assert abs(m.hhi(equal) - 0.25) < 1e-9
    assert m.hhi(conc) > m.hhi(equal)


def test_gini_bounds():
    equal = pd.Series([10, 10, 10, 10], dtype=float)
    assert abs(m.gini(equal)) < 1e-9
    skew = pd.Series([0, 0, 0, 100], dtype=float)
    assert m.gini(skew) > 0.7


def test_concentration_row():
    df = pd.DataFrame(
        {
            "ts_code": ["600000.SH", "000001.SZ", "300750.SZ", "688981.SH"],
            "amount": [50.0, 30.0, 15.0, 5.0],
        }
    )
    row = m.concentration_row(df)
    assert row["total_amount"] == 100.0
    assert row["cr5"] == 1.0
    assert abs(row["amt_sh_main"] - 50.0) < 1e-9
    assert abs(row["amt_gem"] - 15.0) < 1e-9
```

- [ ] **Step 2: 运行确认失败**

Run: `.venv/bin/pytest tests/test_concentration.py -v`
Expected: FAIL。

- [ ] **Step 3: 实现 `quant/concentration/market.py`**

```python
"""市场资金集中度（A 类）：基于每日全市场成交额分布。纯计算，DB 分离。"""
from __future__ import annotations

import numpy as np
import pandas as pd

from quant.config import CR_LEVELS

_BOARD_KEYS = ["sh_main", "sz_main", "sme", "gem", "star", "bse", "other"]


def classify_board(ts_code: str) -> str:
    code = ts_code.split(".")[0]
    if code.startswith(("600", "601", "603", "605")):
        return "sh_main"
    if code.startswith("688") or code.startswith("689"):
        return "star"
    if code.startswith(("000", "001", "003")):
        return "sz_main"
    if code.startswith("002"):
        return "sme"
    if code.startswith(("300", "301")):
        return "gem"
    if code.startswith(("8", "4", "92")):
        return "bse"
    return "other"


def cr_n(amounts: pd.Series, n: int) -> float:
    a = amounts.dropna().astype(float)
    total = a.sum()
    if total <= 0:
        return 0.0
    top = a.sort_values(ascending=False).head(n).sum()
    return float(top / total)


def hhi(amounts: pd.Series) -> float:
    a = amounts.dropna().astype(float)
    total = a.sum()
    if total <= 0:
        return 0.0
    shares = a / total
    return float((shares ** 2).sum())


def gini(amounts: pd.Series) -> float:
    a = np.sort(amounts.dropna().astype(float).values)
    n = a.size
    if n == 0 or a.sum() == 0:
        return 0.0
    index = np.arange(1, n + 1)
    return float((2 * (index * a).sum()) / (n * a.sum()) - (n + 1) / n)


def board_amounts(df: pd.DataFrame) -> dict:
    boards = df["ts_code"].map(classify_board)
    grouped = df.assign(board=boards).groupby("board")["amount"].sum()
    return {k: float(grouped.get(k, 0.0)) for k in _BOARD_KEYS}


def concentration_row(df: pd.DataFrame) -> dict:
    amt = df["amount"].astype(float)
    row = {"total_amount": float(amt.sum())}
    for n in CR_LEVELS:
        row[f"cr{n}"] = cr_n(amt, n)
    row["hhi"] = hhi(amt)
    row["gini"] = gini(amt)
    boards = board_amounts(df)
    row["amt_sh_main"] = boards["sh_main"]
    row["amt_sz_main"] = boards["sz_main"]
    row["amt_sme"] = boards["sme"]
    row["amt_gem"] = boards["gem"]
    row["amt_star"] = boards["star"]
    row["amt_bse"] = boards["bse"]
    return row
```

- [ ] **Step 4: 运行测试**

Run: `.venv/bin/pytest tests/test_concentration.py -v`
Expected: PASS。

- [ ] **Step 5: 提交**

```bash
git add quant/concentration/market.py tests/test_concentration.py
git commit -m "feat(quant): 市场资金集中度算法"
```

---

### Task 5: 集中度缓存表与预计算脚本

**Files:**
- Create: `quant/concentration/cache.py`
- Create: `quant/concentration/build_cache.py`
- Test: `tests/test_concentration_cache.py`

**Interfaces:**
- Consumes: `quant.concentration.market.concentration_row`、`quant.data.loader`、`mysql_config.connect_mysql`。
- Produces:
  - `cache.CREATE_SQL: str`（建 `market_concentration` 表）
  - `cache.upsert_sql() -> str`（INSERT ... ON DUPLICATE KEY UPDATE）
  - `cache.row_to_params(trade_date, row) -> tuple`（把 `concentration_row` 输出拼成 SQL 参数，字段顺序固定）
  - `cache.read_series(start, end) -> pd.DataFrame`（读缓存，index=trade_date）
  - `build_cache.main(argv)`（CLI：全量 rebuild / 增量）

- [ ] **Step 1: 写失败测试 `tests/test_concentration_cache.py`**（只测纯拼装 `row_to_params` 与 SQL 常量存在）

```python
from quant.concentration import cache
from quant.concentration import market


def test_row_to_params_order():
    row = {
        "total_amount": 100.0,
        "cr5": 1.0, "cr10": 1.0, "cr20": 1.0, "cr50": 1.0, "cr100": 1.0,
        "hhi": 0.3, "gini": 0.5,
        "amt_sh_main": 50.0, "amt_sz_main": 30.0, "amt_sme": 0.0,
        "amt_gem": 15.0, "amt_star": 5.0, "amt_bse": 0.0,
    }
    params = cache.row_to_params("20240102", row)
    assert params[0] == "20240102"
    assert params[1] == 100.0
    assert len(params) == 16  # trade_date + 15 字段


def test_create_sql_has_table():
    assert "market_concentration" in cache.CREATE_SQL
    assert "PRIMARY KEY" in cache.CREATE_SQL
```

- [ ] **Step 2: 运行确认失败**

Run: `.venv/bin/pytest tests/test_concentration_cache.py -v`
Expected: FAIL。

- [ ] **Step 3: 实现 `quant/concentration/cache.py`**

```python
"""集中度缓存表读写。字段顺序集中定义，供预计算与界面复用。"""
from __future__ import annotations

import pandas as pd

from quant import config  # noqa: F401
from mysql_config import connect_mysql, load_dotenv

TABLE = config.CONCENTRATION_TABLE

_FIELDS = [
    "total_amount",
    "cr5", "cr10", "cr20", "cr50", "cr100",
    "hhi", "gini",
    "amt_sh_main", "amt_sz_main", "amt_sme", "amt_gem", "amt_star", "amt_bse",
]

CREATE_SQL = f"""
CREATE TABLE IF NOT EXISTS {TABLE} (
  trade_date CHAR(8) NOT NULL PRIMARY KEY,
  total_amount DECIMAL(24,2),
  cr5 DECIMAL(8,6), cr10 DECIMAL(8,6), cr20 DECIMAL(8,6),
  cr50 DECIMAL(8,6), cr100 DECIMAL(8,6),
  hhi DECIMAL(12,10), gini DECIMAL(8,6),
  amt_sh_main DECIMAL(24,2), amt_sz_main DECIMAL(24,2), amt_sme DECIMAL(24,2),
  amt_gem DECIMAL(24,2), amt_star DECIMAL(24,2), amt_bse DECIMAL(24,2)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
"""


def upsert_sql() -> str:
    cols = ["trade_date"] + _FIELDS
    placeholders = ", ".join(["%s"] * len(cols))
    updates = ", ".join(f"{c}=VALUES({c})" for c in _FIELDS)
    return (
        f"INSERT INTO {TABLE} ({', '.join(cols)}) VALUES ({placeholders}) "
        f"ON DUPLICATE KEY UPDATE {updates}"
    )


def row_to_params(trade_date: str, row: dict) -> tuple:
    return tuple([trade_date] + [row[f] for f in _FIELDS])


def _conn():
    load_dotenv()
    return connect_mysql()


def ensure_table() -> None:
    conn = _conn()
    try:
        with conn.cursor() as cur:
            cur.execute(CREATE_SQL)
        conn.commit()
    finally:
        conn.close()


def read_series(start=None, end=None) -> pd.DataFrame:
    s = config.fmt_date(start) if start else "19900101"
    e = config.fmt_date(end) if end else "99991231"
    conn = _conn()
    try:
        df = pd.read_sql(
            f"SELECT * FROM {TABLE} WHERE trade_date BETWEEN %s AND %s ORDER BY trade_date",
            conn, params=(s, e),
        )
    finally:
        conn.close()
    if not df.empty:
        df["trade_date"] = pd.to_datetime(df["trade_date"].astype(str), format="%Y%m%d")
        df = df.set_index("trade_date")
    return df


def max_cached_date() -> str | None:
    conn = _conn()
    try:
        with conn.cursor() as cur:
            cur.execute(f"SELECT MAX(trade_date) FROM {TABLE}")
            val = cur.fetchone()[0]
    finally:
        conn.close()
    return val
```

- [ ] **Step 4: 实现 `quant/concentration/build_cache.py`**

```python
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
```

- [ ] **Step 5: 运行单测**

Run: `.venv/bin/pytest tests/test_concentration_cache.py -v`
Expected: PASS。

- [ ] **Step 6:（手动集成）建表并预计算**

Run: `.venv/bin/python -m quant.concentration.build_cache --rebuild`
Expected: 逐批打印进度并写入 `market_concentration`（需连库，耗时较长，可先用 `--start/--end` 小区间验证）。

- [ ] **Step 7: 提交**

```bash
git add quant/concentration/cache.py quant/concentration/build_cache.py tests/test_concentration_cache.py
git commit -m "feat(quant): 集中度缓存表与预计算脚本"
```

---

### Task 6: 回测引擎与绩效指标

**Files:**
- Create: `quant/backtest/engine.py`
- Create: `quant/backtest/metrics.py`
- Test: `tests/test_backtest_engine.py`, `tests/test_metrics.py`

**Interfaces:**
- Produces:
  - `engine.run(df, signal, cost=0.0003, slippage=0.0) -> BacktestResult`
    - `df`：含 `close` 列，datetime 索引升序
    - `signal`：目标仓位 Series（∈ {0,1}），与 df 对齐；**T 日信号 → T+1 生效（内部 shift(1)）**
    - `BacktestResult`：`dataclass`，字段 `equity: pd.Series`, `position: pd.Series`, `strat_ret: pd.Series`, `trades: list[dict]`, `benchmark: pd.Series`（买入持有净值）
  - `metrics.performance(result) -> dict`（`total_return, ann_return, ann_vol, sharpe, max_drawdown, win_rate, profit_factor, num_trades, bench_total_return`）

- [ ] **Step 1: 写失败测试 `tests/test_backtest_engine.py`**

```python
import numpy as np
import pandas as pd

from quant.backtest import engine


def _df(prices):
    idx = pd.date_range("2020-01-01", periods=len(prices), freq="D")
    return pd.DataFrame({"close": prices}, index=idx, dtype=float)


def test_no_lookahead_shift():
    # 价格 100->110->121（每日+10%）。信号在 t=0 给出买入，应在 t=1 才吃到收益。
    df = _df([100, 110, 121])
    sig = pd.Series([1, 1, 0], index=df.index, dtype=float)
    res = engine.run(df, sig, cost=0.0)
    # t=0 无持仓（position 由 shift 得来），t=1 持仓吃到 +10%
    assert res.position.iloc[0] == 0
    assert res.position.iloc[1] == 1
    assert abs(res.strat_ret.iloc[1] - 0.10) < 1e-9
    assert abs(res.equity.iloc[1] - 1.10) < 1e-9


def test_cost_applied_on_change():
    df = _df([100, 100, 100])
    sig = pd.Series([1, 1, 1], index=df.index, dtype=float)
    res = engine.run(df, sig, cost=0.001)
    # t=1 建仓（position 0->1）扣一次手续费
    assert res.strat_ret.iloc[1] < 0
    assert abs(res.strat_ret.iloc[1] + 0.001) < 1e-9


def test_benchmark_buyhold():
    df = _df([100, 110, 121])
    sig = pd.Series([0, 0, 0], index=df.index, dtype=float)
    res = engine.run(df, sig, cost=0.0)
    assert abs(res.benchmark.iloc[-1] - 1.21) < 1e-9
```

- [ ] **Step 2: 运行确认失败**

Run: `.venv/bin/pytest tests/test_backtest_engine.py -v`
Expected: FAIL。

- [ ] **Step 3: 实现 `quant/backtest/engine.py`**

```python
"""向量化回测引擎（close-to-close，T+1 生效，防未来函数）。"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass
class BacktestResult:
    equity: pd.Series
    position: pd.Series
    strat_ret: pd.Series
    benchmark: pd.Series
    trades: list


def _extract_trades(close: pd.Series, position: pd.Series) -> list:
    trades = []
    entry_idx = None
    entry_px = None
    prev = 0.0
    for ts, pos in position.items():
        if prev == 0 and pos == 1:
            entry_idx, entry_px = ts, close.loc[ts]
        elif prev == 1 and pos == 0 and entry_idx is not None:
            exit_px = close.loc[ts]
            trades.append(
                {
                    "entry": entry_idx, "exit": ts,
                    "entry_px": float(entry_px), "exit_px": float(exit_px),
                    "ret": float(exit_px / entry_px - 1),
                }
            )
            entry_idx = None
        prev = pos
    if entry_idx is not None:  # 期末仍持仓，按最后收盘平掉
        exit_px = close.iloc[-1]
        trades.append(
            {
                "entry": entry_idx, "exit": close.index[-1],
                "entry_px": float(entry_px), "exit_px": float(exit_px),
                "ret": float(exit_px / entry_px - 1),
            }
        )
    return trades


def run(df: pd.DataFrame, signal: pd.Series, cost=0.0003, slippage=0.0) -> BacktestResult:
    close = df["close"].astype(float)
    signal = signal.reindex(close.index).fillna(0.0).clip(0, 1)
    position = signal.shift(1).fillna(0.0)          # T+1 生效
    ret = close.pct_change().fillna(0.0)
    turnover = position.diff().abs().fillna(position.abs())
    trade_cost = turnover * (cost + slippage)
    strat_ret = position * ret - trade_cost
    equity = (1 + strat_ret).cumprod()
    benchmark = (1 + ret).cumprod()
    trades = _extract_trades(close, position)
    return BacktestResult(
        equity=equity, position=position, strat_ret=strat_ret,
        benchmark=benchmark, trades=trades,
    )
```

- [ ] **Step 4: 写失败测试 `tests/test_metrics.py`**

```python
import numpy as np
import pandas as pd

from quant.backtest import engine, metrics


def test_performance_basic():
    idx = pd.date_range("2020-01-01", periods=4, freq="D")
    df = pd.DataFrame({"close": [100, 110, 121, 133.1]}, index=idx, dtype=float)
    sig = pd.Series([1, 1, 1, 1], index=idx, dtype=float)
    res = engine.run(df, sig, cost=0.0)
    perf = metrics.performance(res)
    assert perf["total_return"] > 0
    assert perf["max_drawdown"] <= 0
    assert "sharpe" in perf and "num_trades" in perf


def test_max_drawdown():
    idx = pd.date_range("2020-01-01", periods=3, freq="D")
    # 净值 1 -> 1.2 -> 0.9，最大回撤 = 0.9/1.2 - 1 = -0.25
    res = engine.BacktestResult(
        equity=pd.Series([1.0, 1.2, 0.9], index=idx),
        position=pd.Series([1, 1, 1], index=idx),
        strat_ret=pd.Series([0.0, 0.2, -0.25], index=idx),
        benchmark=pd.Series([1.0, 1.0, 1.0], index=idx),
        trades=[],
    )
    perf = metrics.performance(res)
    assert abs(perf["max_drawdown"] + 0.25) < 1e-9
```

- [ ] **Step 5: 实现 `quant/backtest/metrics.py`**

```python
"""回测绩效指标。"""
from __future__ import annotations

import numpy as np

TRADING_DAYS = 252


def performance(result) -> dict:
    equity = result.equity
    strat_ret = result.strat_ret
    n = len(equity)
    total_return = float(equity.iloc[-1] - 1) if n else 0.0
    ann_return = float(equity.iloc[-1] ** (TRADING_DAYS / n) - 1) if n else 0.0
    vol = float(strat_ret.std())
    ann_vol = vol * np.sqrt(TRADING_DAYS)
    mean = float(strat_ret.mean())
    sharpe = (mean / vol * np.sqrt(TRADING_DAYS)) if vol > 0 else 0.0

    running_max = equity.cummax()
    drawdown = equity / running_max - 1
    max_drawdown = float(drawdown.min()) if n else 0.0

    trades = result.trades
    rets = [t["ret"] for t in trades]
    wins = [r for r in rets if r > 0]
    losses = [r for r in rets if r < 0]
    win_rate = (len(wins) / len(rets)) if rets else 0.0
    gross_win = sum(wins)
    gross_loss = abs(sum(losses))
    profit_factor = (gross_win / gross_loss) if gross_loss > 0 else float("inf") if gross_win > 0 else 0.0

    bench_total = float(result.benchmark.iloc[-1] - 1) if len(result.benchmark) else 0.0

    return {
        "total_return": total_return,
        "ann_return": ann_return,
        "ann_vol": ann_vol,
        "sharpe": sharpe,
        "max_drawdown": max_drawdown,
        "win_rate": win_rate,
        "profit_factor": profit_factor,
        "num_trades": len(trades),
        "bench_total_return": bench_total,
    }
```

- [ ] **Step 6: 运行测试**

Run: `.venv/bin/pytest tests/test_backtest_engine.py tests/test_metrics.py -v`
Expected: PASS。

- [ ] **Step 7: 提交**

```bash
git add quant/backtest/engine.py quant/backtest/metrics.py tests/test_backtest_engine.py tests/test_metrics.py
git commit -m "feat(quant): 回测引擎与绩效指标"
```

---

### Task 7: 五个策略

**Files:**
- Create: `quant/backtest/strategies/base.py`
- Create: `quant/backtest/strategies/ma_cross.py`, `macd.py`, `bollinger.py`, `rsi.py`, `donchian.py`
- Modify: `quant/backtest/strategies/__init__.py`（注册表）
- Test: `tests/test_strategies.py`

**Interfaces:**
- Consumes: `quant.indicators.ta`。
- Produces:
  - `base.Strategy`：协议——`name: str`, `default_params: dict`, `generate(df, **params) -> pd.Series`（返回目标仓位 {0,1}，index 与 df 对齐）
  - 每个策略模块暴露一个 `Strategy` 实例：`STRATEGY`
  - `strategies.REGISTRY: dict[str, Strategy]`（键为 name）
  - `strategies.get(name) -> Strategy`

- [ ] **Step 1: 写失败测试 `tests/test_strategies.py`**

```python
import numpy as np
import pandas as pd

from quant.backtest import strategies


def _df(prices):
    idx = pd.date_range("2020-01-01", periods=len(prices), freq="D")
    p = pd.Series(prices, index=idx, dtype=float)
    return pd.DataFrame(
        {"open": p, "high": p * 1.01, "low": p * 0.99, "close": p,
         "volume": 1000.0, "amount": p * 1000.0}
    )


def test_registry_has_five():
    assert set(["ma_cross", "macd", "bollinger", "rsi", "donchian"]).issubset(
        set(strategies.REGISTRY)
    )


def test_signals_are_binary_and_aligned():
    df = _df(np.concatenate([np.linspace(10, 20, 60), np.linspace(20, 10, 60)]))
    for name, strat in strategies.REGISTRY.items():
        sig = strat.generate(df, **strat.default_params)
        assert sig.index.equals(df.index), name
        assert set(np.unique(sig.dropna().values)).issubset({0.0, 1.0}), name


def test_ma_cross_goes_long_in_uptrend():
    df = _df(np.linspace(10, 30, 80))
    sig = strategies.get("ma_cross").generate(df, fast=5, slow=20)
    assert sig.iloc[-1] == 1.0
```

- [ ] **Step 2: 运行确认失败**

Run: `.venv/bin/pytest tests/test_strategies.py -v`
Expected: FAIL。

- [ ] **Step 3: 实现 `quant/backtest/strategies/base.py`**

```python
"""策略接口：输入标准行情 DataFrame，输出目标仓位序列 {0,1}。"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

import pandas as pd


@dataclass
class Strategy:
    name: str
    label: str
    default_params: dict
    _fn: Callable[..., pd.Series]

    def generate(self, df: pd.DataFrame, **params) -> pd.Series:
        merged = {**self.default_params, **params}
        sig = self._fn(df, **merged)
        return sig.reindex(df.index).fillna(0.0).clip(0, 1)
```

- [ ] **Step 4: 实现五个策略模块**

`quant/backtest/strategies/ma_cross.py`:

```python
"""双均线交叉：快线上穿慢线持有，下穿空仓。"""
import pandas as pd

from quant.indicators import ta
from quant.backtest.strategies.base import Strategy


def _gen(df, fast=5, slow=20):
    f = ta.ma(df["close"], fast)
    s = ta.ma(df["close"], slow)
    return (f > s).astype(float)


STRATEGY = Strategy("ma_cross", "双均线交叉", {"fast": 5, "slow": 20}, _gen)
```

`quant/backtest/strategies/macd.py`:

```python
"""MACD：DIF 上穿 DEA 持有，下穿空仓。"""
import pandas as pd

from quant.indicators import ta
from quant.backtest.strategies.base import Strategy


def _gen(df, fast=12, slow=26, signal=9):
    dif, dea, _ = ta.macd(df["close"], fast, slow, signal)
    return (dif > dea).astype(float)


STRATEGY = Strategy("macd", "MACD 金叉死叉", {"fast": 12, "slow": 26, "signal": 9}, _gen)
```

`quant/backtest/strategies/bollinger.py`:

```python
"""布林带均值回归：收盘跌破下轨买入，回到中轨以上离场。"""
import numpy as np
import pandas as pd

from quant.indicators import ta
from quant.backtest.strategies.base import Strategy


def _gen(df, n=20, k=2.0):
    upper, mid, lower = ta.boll(df["close"], n, k)
    close = df["close"]
    pos = np.where(close < lower, 1.0, np.where(close > mid, 0.0, np.nan))
    return pd.Series(pos, index=df.index).ffill().fillna(0.0)


STRATEGY = Strategy("bollinger", "布林带均值回归", {"n": 20, "k": 2.0}, _gen)
```

`quant/backtest/strategies/rsi.py`:

```python
"""RSI 超买超卖：RSI 低于超卖阈买入，高于超买阈离场。"""
import numpy as np
import pandas as pd

from quant.indicators import ta
from quant.backtest.strategies.base import Strategy


def _gen(df, n=14, oversold=30, overbought=70):
    r = ta.rsi(df["close"], n)
    pos = np.where(r < oversold, 1.0, np.where(r > overbought, 0.0, np.nan))
    return pd.Series(pos, index=df.index).ffill().fillna(0.0)


STRATEGY = Strategy("rsi", "RSI 超买超卖", {"n": 14, "oversold": 30, "overbought": 70}, _gen)
```

`quant/backtest/strategies/donchian.py`:

```python
"""唐奇安通道突破（海龟式）：突破 N 日最高买入，跌破 M 日最低离场。"""
import numpy as np
import pandas as pd

from quant.backtest.strategies.base import Strategy


def _gen(df, entry=20, exit=10):
    upper = df["high"].rolling(entry).max().shift(1)
    lower = df["low"].rolling(exit).min().shift(1)
    close = df["close"]
    pos = np.where(close > upper, 1.0, np.where(close < lower, 0.0, np.nan))
    return pd.Series(pos, index=df.index).ffill().fillna(0.0)


STRATEGY = Strategy("donchian", "唐奇安通道突破", {"entry": 20, "exit": 10}, _gen)
```

- [ ] **Step 5: 实现注册表 `quant/backtest/strategies/__init__.py`**

```python
"""策略注册表。"""
from quant.backtest.strategies.base import Strategy
from quant.backtest.strategies import ma_cross, macd, bollinger, rsi, donchian

REGISTRY = {
    s.name: s
    for s in [
        ma_cross.STRATEGY,
        macd.STRATEGY,
        bollinger.STRATEGY,
        rsi.STRATEGY,
        donchian.STRATEGY,
    ]
}


def get(name: str) -> Strategy:
    if name not in REGISTRY:
        raise KeyError(f"未知策略: {name}. 可选: {list(REGISTRY)}")
    return REGISTRY[name]
```

- [ ] **Step 6: 运行测试**

Run: `.venv/bin/pytest tests/test_strategies.py -v`
Expected: PASS。

- [ ] **Step 7: 提交**

```bash
git add quant/backtest/strategies tests/test_strategies.py
git commit -m "feat(quant): 五个回测策略与注册表"
```

---

### Task 8: Plotly 图表封装

**Files:**
- Create: `quant/charts/plots.py`
- Test: `tests/test_charts.py`

**Interfaces:**
- Consumes: `quant.indicators.ta`。
- Produces（均返回 `plotly.graph_objects.Figure`）：
  - `kline_chart(df, overlays=("ma5","ma20","boll"), sub=("macd","rsi"), drawable=True) -> Figure`
  - `backtest_chart(result) -> Figure`（净值 vs 基准 + 买卖点 + 回撤）
  - `concentration_chart(series_df, metric="hhi") -> Figure`
  - `board_area_chart(series_df) -> Figure`（板块成交额占比堆叠）
  - `concentration_detail_chart(cross_df, top=20) -> Figure`（某日成交额排行）

- [ ] **Step 1: 写失败测试 `tests/test_charts.py`**（Figure 类型与基本轨迹数烟测）

```python
import numpy as np
import pandas as pd
import plotly.graph_objects as go

from quant.charts import plots
from quant.backtest import engine


def _df(n=60):
    idx = pd.date_range("2020-01-01", periods=n, freq="D")
    p = pd.Series(np.linspace(10, 20, n), index=idx)
    return pd.DataFrame(
        {"open": p, "high": p * 1.02, "low": p * 0.98, "close": p,
         "volume": 1000.0, "amount": p * 1000.0}
    )


def test_kline_returns_figure():
    fig = plots.kline_chart(_df())
    assert isinstance(fig, go.Figure)
    assert len(fig.data) >= 1


def test_backtest_chart():
    df = _df()
    sig = pd.Series(1.0, index=df.index)
    res = engine.run(df, sig, cost=0.0)
    fig = plots.backtest_chart(res)
    assert isinstance(fig, go.Figure)


def test_concentration_chart():
    idx = pd.date_range("2020-01-01", periods=10, freq="D")
    sdf = pd.DataFrame({"hhi": np.linspace(0.1, 0.2, 10)}, index=idx)
    fig = plots.concentration_chart(sdf, metric="hhi")
    assert isinstance(fig, go.Figure)
```

- [ ] **Step 2: 运行确认失败**

Run: `.venv/bin/pytest tests/test_charts.py -v`
Expected: FAIL。

- [ ] **Step 3: 实现 `quant/charts/plots.py`**

```python
"""Plotly 图表封装：K线/回测/集中度。"""
from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from quant.indicators import ta

_BOARD_LABELS = {
    "amt_sh_main": "沪主板", "amt_sz_main": "深主板", "amt_sme": "中小板",
    "amt_gem": "创业板", "amt_star": "科创板", "amt_bse": "北交所",
}


def kline_chart(df, overlays=("ma5", "ma20", "boll"), sub=("macd", "rsi"), drawable=True):
    rows = 1 + 1 + len(sub)  # 主图 + 量 + 各副图
    heights = [0.5, 0.15] + [0.35 / max(len(sub), 1)] * len(sub)
    fig = make_subplots(
        rows=rows, cols=1, shared_xaxes=True, vertical_spacing=0.02,
        row_heights=heights,
    )
    fig.add_trace(
        go.Candlestick(
            x=df.index, open=df["open"], high=df["high"], low=df["low"],
            close=df["close"], name="K线",
        ),
        row=1, col=1,
    )
    for ov in overlays:
        if ov.startswith("ma"):
            n = int(ov[2:])
            fig.add_trace(go.Scatter(x=df.index, y=ta.ma(df["close"], n),
                                     name=f"MA{n}", line=dict(width=1)), row=1, col=1)
        elif ov == "boll":
            up, mid, low = ta.boll(df["close"])
            for y, nm in [(up, "BOLL上"), (mid, "BOLL中"), (low, "BOLL下")]:
                fig.add_trace(go.Scatter(x=df.index, y=y, name=nm,
                                         line=dict(width=1, dash="dot")), row=1, col=1)
    fig.add_trace(go.Bar(x=df.index, y=df["volume"], name="成交量"), row=2, col=1)

    r = 3
    for name in sub:
        if name == "macd":
            dif, dea, hist = ta.macd(df["close"])
            fig.add_trace(go.Scatter(x=df.index, y=dif, name="DIF"), row=r, col=1)
            fig.add_trace(go.Scatter(x=df.index, y=dea, name="DEA"), row=r, col=1)
            fig.add_trace(go.Bar(x=df.index, y=hist, name="MACD"), row=r, col=1)
        elif name == "rsi":
            fig.add_trace(go.Scatter(x=df.index, y=ta.rsi(df["close"]), name="RSI"),
                          row=r, col=1)
        r += 1

    fig.update_layout(
        height=800, xaxis_rangeslider_visible=False,
        dragmode="drawline" if drawable else "zoom",
        newshape=dict(line_color="orange"),
        modebar_add=["drawline", "drawopenpath", "eraseshape"] if drawable else [],
        legend=dict(orientation="h"),
        margin=dict(l=40, r=20, t=30, b=20),
    )
    fig.update_xaxes(rangeslider_visible=False)
    return fig


def backtest_chart(result):
    fig = make_subplots(
        rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.05,
        row_heights=[0.7, 0.3],
    )
    eq = result.equity
    fig.add_trace(go.Scatter(x=eq.index, y=eq, name="策略净值"), row=1, col=1)
    fig.add_trace(go.Scatter(x=result.benchmark.index, y=result.benchmark,
                             name="买入持有", line=dict(dash="dot")), row=1, col=1)
    for t in result.trades:
        fig.add_trace(go.Scatter(x=[t["entry"]], y=[eq.loc[t["entry"]]], mode="markers",
                                 marker=dict(symbol="triangle-up", color="red", size=10),
                                 showlegend=False), row=1, col=1)
        fig.add_trace(go.Scatter(x=[t["exit"]], y=[eq.loc[t["exit"]]], mode="markers",
                                 marker=dict(symbol="triangle-down", color="green", size=10),
                                 showlegend=False), row=1, col=1)
    dd = eq / eq.cummax() - 1
    fig.add_trace(go.Scatter(x=dd.index, y=dd, name="回撤", fill="tozeroy",
                             line=dict(color="rgba(200,0,0,0.5)")), row=2, col=1)
    fig.update_layout(height=600, legend=dict(orientation="h"),
                      margin=dict(l=40, r=20, t=30, b=20))
    return fig


def concentration_chart(series_df, metric="hhi"):
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=series_df.index, y=series_df[metric], name=metric))
    fig.update_layout(height=400, title=f"市场资金集中度：{metric}",
                      margin=dict(l=40, r=20, t=40, b=20))
    return fig


def board_area_chart(series_df):
    fig = go.Figure()
    cols = [c for c in _BOARD_LABELS if c in series_df.columns]
    total = series_df[cols].sum(axis=1).replace(0, pd.NA)
    for c in cols:
        share = series_df[c] / total
        fig.add_trace(go.Scatter(x=series_df.index, y=share, name=_BOARD_LABELS[c],
                                 stackgroup="one"))
    fig.update_layout(height=400, title="各板块成交额占比",
                      yaxis_tickformat=".0%", margin=dict(l=40, r=20, t=40, b=20))
    return fig


def concentration_detail_chart(cross_df, top=20):
    d = cross_df.sort_values("amount", ascending=False).head(top)
    label = d["name"].fillna(d["ts_code"]) if "name" in d else d["ts_code"]
    fig = go.Figure(go.Bar(x=d["amount"], y=label, orientation="h"))
    fig.update_layout(height=500, title=f"成交额前 {top} 名",
                      yaxis=dict(autorange="reversed"), margin=dict(l=120, r=20, t=40, b=20))
    return fig
```

- [ ] **Step 4: 运行测试**

Run: `.venv/bin/pytest tests/test_charts.py -v`
Expected: PASS。

- [ ] **Step 5: 提交**

```bash
git add quant/charts/plots.py tests/test_charts.py
git commit -m "feat(quant): Plotly 图表封装"
```

---

### Task 9: Streamlit 界面

**Files:**
- Create: `app/main.py`
- Test: `tests/test_app_import.py`（烟测：可 import，不启动服务）

**Interfaces:**
- Consumes: `quant.data.loader`、`quant.indicators.ta`、`quant.concentration.cache`、`quant.backtest.{engine,metrics,strategies}`、`quant.charts.plots`。
- Produces: 可运行的 Streamlit app（`.venv/bin/streamlit run app/main.py`）。

- [ ] **Step 1: 写失败测试 `tests/test_app_import.py`**

```python
import importlib
import sys
from pathlib import Path


def test_app_module_imports(monkeypatch):
    # 仅验证模块可被解析（不执行 streamlit 运行时）
    root = Path(__file__).resolve().parent.parent
    app_file = root / "app" / "main.py"
    assert app_file.exists()
    src = app_file.read_text(encoding="utf-8")
    # 关键组件存在
    assert "st.tabs" in src
    assert "kline_chart" in src
    assert "backtest_chart" in src
    assert "concentration_chart" in src
```

- [ ] **Step 2: 运行确认失败**

Run: `.venv/bin/pytest tests/test_app_import.py -v`
Expected: FAIL（`app/main.py` 不存在）。

- [ ] **Step 3: 实现 `app/main.py`**

```python
"""量化分析系统 Streamlit 界面。运行: .venv/bin/streamlit run app/main.py"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd
import streamlit as st

from quant.data import loader
from quant.concentration import cache
from quant.backtest import engine, metrics, strategies
from quant.charts import plots

st.set_page_config(page_title="量化分析系统", layout="wide")


@st.cache_data(ttl=600)
def _stocks():
    return loader.list_stocks()


@st.cache_data(ttl=600)
def _daily(ts_code, start, end):
    return loader.load_daily(ts_code, start, end)


st.title("量化交易分析系统")

with st.sidebar:
    st.header("参数")
    try:
        stocks = _stocks()
        options = (stocks["ts_code"] + "  " + stocks["name"].fillna("")).tolist()
    except Exception as exc:  # 连库失败友好提示
        st.error(f"无法连接 MySQL，请检查 database/mysql/mysql.env：{exc}")
        st.stop()
    picked = st.selectbox("股票", options)
    ts_code = picked.split("  ")[0]
    start = st.date_input("开始", pd.Timestamp("2022-01-01")).strftime("%Y%m%d")
    end = st.date_input("结束", pd.Timestamp.today()).strftime("%Y%m%d")

tab1, tab2, tab3 = st.tabs(["行情分析", "资金集中度", "策略回测"])

with tab1:
    df = _daily(ts_code, start, end)
    if df.empty:
        st.warning("该区间无数据。")
    else:
        overlays = st.multiselect("叠加", ["ma5", "ma10", "ma20", "ma60", "boll"],
                                  default=["ma5", "ma20", "boll"])
        sub = st.multiselect("副图", ["macd", "rsi"], default=["macd", "rsi"])
        st.plotly_chart(plots.kline_chart(df, tuple(overlays), tuple(sub)),
                        use_container_width=True)

with tab2:
    st.subheader("市场资金集中度（历史）")
    try:
        sdf = cache.read_series(start, end)
    except Exception as exc:
        st.error(f"读取集中度缓存失败：{exc}")
        sdf = pd.DataFrame()
    if sdf.empty:
        st.info("集中度缓存为空，请先运行：.venv/bin/python -m quant.concentration.build_cache --rebuild")
    else:
        metric = st.selectbox("指标", ["hhi", "gini", "cr5", "cr10", "cr20", "cr50", "cr100"])
        st.plotly_chart(plots.concentration_chart(sdf, metric), use_container_width=True)
        st.plotly_chart(plots.board_area_chart(sdf), use_container_width=True)
        detail_date = st.date_input("查看某日明细", pd.Timestamp(sdf.index[-1]))
        cross = loader.load_cross_section(detail_date.strftime("%Y%m%d"))
        if not cross.empty:
            st.plotly_chart(plots.concentration_detail_chart(cross), use_container_width=True)

with tab3:
    st.subheader("策略回测")
    strat_name = st.selectbox("策略", list(strategies.REGISTRY),
                              format_func=lambda k: strategies.get(k).label)
    strat = strategies.get(strat_name)
    params = {}
    cols = st.columns(max(len(strat.default_params), 1))
    for (k, v), c in zip(strat.default_params.items(), cols):
        params[k] = c.number_input(k, value=float(v))
    cost = st.number_input("单边手续费率", value=0.0003, format="%.4f")
    if st.button("运行回测"):
        df = _daily(ts_code, start, end)
        if df.empty:
            st.warning("该区间无数据。")
        else:
            sig = strat.generate(df, **params)
            res = engine.run(df, sig, cost=cost)
            perf = metrics.performance(res)
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("总收益", f"{perf['total_return']:.2%}")
            c2.metric("年化", f"{perf['ann_return']:.2%}")
            c3.metric("夏普", f"{perf['sharpe']:.2f}")
            c4.metric("最大回撤", f"{perf['max_drawdown']:.2%}")
            c5, c6, c7, c8 = st.columns(4)
            c5.metric("胜率", f"{perf['win_rate']:.2%}")
            c6.metric("盈亏比", f"{perf['profit_factor']:.2f}")
            c7.metric("交易次数", perf["num_trades"])
            c8.metric("基准收益", f"{perf['bench_total_return']:.2%}")
            st.plotly_chart(plots.backtest_chart(res), use_container_width=True)
```

- [ ] **Step 4: 运行测试**

Run: `.venv/bin/pytest tests/test_app_import.py -v`
Expected: PASS。

- [ ] **Step 5:（手动集成）启动界面**

Run: `.venv/bin/streamlit run app/main.py`
Expected: 浏览器打开 `localhost:8501`，三个 Tab 可用（需连库）。

- [ ] **Step 6: 全量测试 + 提交**

Run: `.venv/bin/pytest -q`
Expected: 全部 PASS。

```bash
git add app/main.py tests/test_app_import.py
git commit -m "feat(app): Streamlit 三 Tab 界面"
```

---

## Self-Review

**Spec coverage：**
- 数据访问层（MySQL）→ Task 2 ✅
- 技术指标库（趋势/动量/量能/波动/结构辅助）→ Task 3 ✅
- 资金集中度 A（CR_N/HHI/基尼/板块）→ Task 4；缓存表 + 预计算 → Task 5 ✅
- 回测引擎（防未来函数）+ 绩效 → Task 6 ✅
- 五个策略 → Task 7 ✅
- Plotly 图表（K线/趋势线/时间轴/净值/集中度）→ Task 8 ✅
- Streamlit 三 Tab → Task 9 ✅
- 测试 → 各 Task 内含 ✅

**范围细化（相对 spec）：** 执行模型明确为 close-to-close、T+1 生效；策略为多头（{0,1}）。已在 Global Constraints 记录。

**Placeholder scan：** 无 TBD/TODO；每个代码步骤含完整代码。

**Type consistency：** `BacktestResult` 字段（equity/position/strat_ret/benchmark/trades）在 engine 定义、metrics 与 charts 一致引用；`Strategy.generate` 返回 {0,1} Series 与 engine `signal` 约定一致；`concentration_row` 字段与 `cache._FIELDS`、`row_to_params`、`CREATE_SQL` 顺序一致。
