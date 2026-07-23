# Astocks QFQ MySQL Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 新增 MySQL DDL、SQLite→MySQL 全量迁移脚本与 MySQL 日更脚本，不改动现有 SQLite 脚本，不迁移 `app_*`。

**Architecture:** 共用 `mysql_config.py` 读取环境变量/`mysql.env`；`schema_mysql.sql` 定义两表；`migrate_sqlite_to_mysql.py` 只读 SQLite 分批写入 MySQL 并校验；`update_daily_mysql.py` 复制现有日更逻辑但用 PyMySQL 写入。

**Tech Stack:** Python 3、sqlite3、pymysql、baostock、MySQL 8.x（InnoDB）

## Global Constraints

- 不修改：`update_daily.py`、`backfill_qfq_to_yesterday.py`、`bs_qfq_downloader.py`
- 不创建 MySQL 版 backfill；不迁移 `app_*`
- 连接：`MYSQL_HOST` / `MYSQL_PORT` / `MYSQL_USER` / `MYSQL_PASSWORD` / `MYSQL_DATABASE`；可选 `database/mysql.env`（勿提交密钥）
- 默认库名：`astocks_qfq`；默认 SQLite：`database/astocks_qfq.db`（脚本内相对 `database/` 目录）
- `daily_qfq` 主键 `(ts_code, trade_date)`，无自增 `id`；SQL 中 `` `open` `` 必须反引号
- 未经用户明确要求，不执行 `git commit`

---

## File Structure

| 路径 | 职责 |
| --- | --- |
| `database/schema_mysql.sql` | 建库建表 DDL |
| `database/mysql_config.py` | 加载 env、建立 PyMySQL 连接 |
| `database/migrate_sqlite_to_mysql.py` | 全量迁移 + 校验 |
| `database/update_daily_mysql.py` | baostock → MySQL 日更 |
| `database/requirements.txt` | 增加 pymysql |
| `database/.gitignore` | 忽略 `mysql.env`（若目录尚无 gitignore 则创建） |
| `database/README.md` | MySQL 用法小节 |
| `database/test_mysql_config.py` | 配置加载单元测试 |

---

### Task 1: Schema + 依赖 + 配置模块

**Files:**
- Create: `database/schema_mysql.sql`
- Create: `database/mysql_config.py`
- Create: `database/test_mysql_config.py`
- Create: `database/.gitignore`（仅含 `mysql.env`，若已有则追加）
- Modify: `database/requirements.txt`

**Interfaces:**
- Produces:
  - `load_dotenv(path: str | None = None) -> None`
  - `mysql_settings() -> dict` 键：`host, port, user, password, database`
  - `connect_mysql(**overrides) -> pymysql.Connection`（`charset=utf8mb4`, `autocommit=False`）

- [ ] **Step 1: 写失败测试（配置默认值与 env 覆盖）**

创建 `database/test_mysql_config.py`：

```python
import os
import importlib

import mysql_config


def test_mysql_settings_defaults(monkeypatch):
    for key in list(os.environ):
        if key.startswith("MYSQL_"):
            monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("MYSQL_USER", "u1")
    s = mysql_config.mysql_settings()
    assert s["host"] == "127.0.0.1"
    assert s["port"] == 3306
    assert s["user"] == "u1"
    assert s["password"] == ""
    assert s["database"] == "astocks_qfq"


def test_mysql_settings_requires_user(monkeypatch):
    for key in list(os.environ):
        if key.startswith("MYSQL_"):
            monkeypatch.delenv(key, raising=False)
    try:
        mysql_config.mysql_settings()
        assert False, "expected ValueError"
    except ValueError as e:
        assert "MYSQL_USER" in str(e)


def test_load_dotenv_file(tmp_path, monkeypatch):
    for key in list(os.environ):
        if key.startswith("MYSQL_"):
            monkeypatch.delenv(key, raising=False)
    env = tmp_path / "mysql.env"
    env.write_text("MYSQL_USER=fromfile\nMYSQL_HOST=db.local\nMYSQL_PORT=3307\n", encoding="utf-8")
    mysql_config.load_dotenv(str(env))
    s = mysql_config.mysql_settings()
    assert s["user"] == "fromfile"
    assert s["host"] == "db.local"
    assert s["port"] == 3307
```

- [ ] **Step 2: 跑测试确认失败**

Run（在 `database/` 下，用项目 venv）：

```bash
cd /Users/hao/Downloads/tmp/database && ../.venv/bin/python -m pytest test_mysql_config.py -v
```

Expected: 失败（模块不存在或 pytest 未装）。若无 pytest：`../.venv/bin/pip install pytest` 后再跑；仍应因缺 `mysql_config` 失败。

- [ ] **Step 3: 实现 schema、requirements、gitignore、mysql_config**

`database/schema_mysql.sql` — 内容与 spec 中 DDL 完全一致（含 `CREATE DATABASE`、`USE`、两张表）。

`database/requirements.txt` 追加：

```text
pymysql>=1.1.0
```

`database/.gitignore`：

```text
mysql.env
```

`database/mysql_config.py`：

```python
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""MySQL 连接配置：环境变量 + 可选 mysql.env。"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import pymysql

_DEFAULT_ENV = Path(__file__).resolve().parent / "mysql.env"


def load_dotenv(path: str | None = None) -> None:
    """Load KEY=VALUE lines into os.environ if key not already set."""
    env_path = Path(path) if path else _DEFAULT_ENV
    if not env_path.is_file():
        return
    for raw in env_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip("'").strip('"')
        if key and key not in os.environ:
            os.environ[key] = value


def mysql_settings() -> dict[str, Any]:
    host = os.environ.get("MYSQL_HOST", "127.0.0.1")
    port = int(os.environ.get("MYSQL_PORT", "3306"))
    user = os.environ.get("MYSQL_USER")
    if not user:
        raise ValueError("MYSQL_USER is required (env or database/mysql.env)")
    password = os.environ.get("MYSQL_PASSWORD", "")
    database = os.environ.get("MYSQL_DATABASE", "astocks_qfq")
    return {
        "host": host,
        "port": port,
        "user": user,
        "password": password,
        "database": database,
    }


def connect_mysql(**overrides: Any) -> pymysql.connections.Connection:
    settings = mysql_settings()
    settings.update(overrides)
    return pymysql.connect(
        host=settings["host"],
        port=int(settings["port"]),
        user=settings["user"],
        password=settings["password"],
        database=settings.get("database"),
        charset="utf8mb4",
        autocommit=False,
        cursorclass=pymysql.cursors.Cursor,
    )
```

注意：`connect_mysql` 在尚未建库时可能连不上 `database`；迁移脚本需先无 database 建库再重连——在 Task 2 处理（`connect_mysql(database=None)` 或先连 server）。

调整 `connect_mysql`：允许 `database=None` 覆盖：

```python
def connect_mysql(**overrides: Any) -> pymysql.connections.Connection:
    settings = mysql_settings()
    settings.update(overrides)
    kwargs = dict(
        host=settings["host"],
        port=int(settings["port"]),
        user=settings["user"],
        password=settings["password"],
        charset="utf8mb4",
        autocommit=False,
        cursorclass=pymysql.cursors.Cursor,
    )
    db = settings.get("database")
    if db is not None:
        kwargs["database"] = db
    return pymysql.connect(**kwargs)
```

- [ ] **Step 4: 再跑测试**

```bash
cd /Users/hao/Downloads/tmp/database && ../.venv/bin/pip install -q pymysql pytest && ../.venv/bin/python -m pytest test_mysql_config.py -v
```

Expected: 全部 PASS。

---

### Task 2: `migrate_sqlite_to_mysql.py`

**Files:**
- Create: `database/migrate_sqlite_to_mysql.py`

**Interfaces:**
- Consumes: `mysql_config.load_dotenv`, `mysql_config.mysql_settings`, `mysql_config.connect_mysql`
- Produces: CLI 入口 `main()`；退出码 0=成功，非 0=校验失败或前置失败

- [ ] **Step 1: 实现迁移脚本（完整文件）**

```python
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


def apply_schema(settings: dict) -> None:
    sql = SCHEMA_PATH.read_text(encoding="utf-8")
    # 连到 server（不选库）执行 CREATE DATABASE / USE / CREATE TABLE
    conn = mysql_config.connect_mysql(database=None)
    try:
        with conn.cursor() as cur:
            for stmt in _split_sql(sql):
                cur.execute(stmt)
        conn.commit()
    finally:
        conn.close()


def _split_sql(sql: str) -> list[str]:
    stmts = []
    buf = []
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
    print(f"MySQL: {settings['user']}@{settings['host']}:{settings['port']}/{settings['database']}")

    apply_schema(settings)
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
        # stocks
        rows = src.execute("SELECT ts_code, COALESCE(name,'') FROM stocks").fetchall()
        with dst.cursor() as cur:
            for i in range(0, len(rows), batch_size):
                cur.executemany(STOCKS_INSERT, rows[i : i + batch_size])
        dst.commit()
        print(f"stocks 导入: {len(rows)}")

        # daily_qfq by year
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
            buf = []
            year_n = 0
            with dst.cursor() as cur:
                while True:
                    chunk = batch.fetchmany(batch_size)
                    if not chunk:
                        break
                    buf = [
                        (
                            r[0],
                            r[1],
                            r[2],
                            r[3],
                            r[4],
                            r[5],
                            r[6],
                            r[7],
                        )
                        for r in chunk
                    ]
                    cur.executemany(DAILY_INSERT, buf)
                    year_n += len(buf)
                    total += len(buf)
                dst.commit()
            print(f"  {year}: {year_n} 行")
        print(f"daily_qfq 导入合计: {total} 耗时 {time.time()-t0:.1f}s")

        left = sqlite_stats(sqlite_path)
        right = table_counts(dst)
        print("校验 SQLite vs MySQL:")
        ok = True
        for key in ("stocks", "rows", "codes", "min_date", "max_date"):
            match = left[key] == right[key]
            ok = ok and match
            print(f"  {key}: {left[key]} vs {right[key]} {'OK' if match else 'FAIL'}")
        # sum_close 允许浮点误差
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
```

- [ ] **Step 2: 语法检查（无 MySQL 时）**

```bash
cd /Users/hao/Downloads/tmp/database && ../.venv/bin/python -m py_compile migrate_sqlite_to_mysql.py mysql_config.py
```

Expected: 无输出、退出码 0。

- [ ] **Step 3: 有连接信息后的联调（连接未提供则跳过并在 README 注明）**

```bash
# 先准备 database/mysql.env，再：
cd /Users/hao/Downloads/tmp/database
../.venv/bin/python migrate_sqlite_to_mysql.py --force
```

Expected: 打印逐年导入；校验项全部 `OK`；退出码 0。

---

### Task 3: `update_daily_mysql.py`

**Files:**
- Create: `database/update_daily_mysql.py`
- Reference only (勿改): `database/update_daily.py`

**Interfaces:**
- Consumes: `mysql_config.load_dotenv`, `mysql_config.connect_mysql`
- 行为对齐 `update_daily.py`：同步股票列表 + 当天 K 线 upsert

- [ ] **Step 1: 实现日更脚本**

基于 `update_daily.py` 逻辑，关键替换：

1. 开头：`import pymysql` 不需要直接 import（用 `mysql_config`）；`load_dotenv()` 后 `connect_mysql()`。
2. 删除「检查 `.db` 是否存在」；改为检查能连上 MySQL。
3. SQL：

```python
UPSERT_DAILY = (
    "INSERT INTO daily_qfq "
    "(ts_code, trade_date, `open`, high, low, close_qfq, volume, amount) "
    "VALUES (%s,%s,%s,%s,%s,%s,%s,%s) "
    "ON DUPLICATE KEY UPDATE "
    "`open`=VALUES(`open`), high=VALUES(high), low=VALUES(low), "
    "close_qfq=VALUES(close_qfq), volume=VALUES(volume), amount=VALUES(amount)"
)
INSERT_STOCK = "INSERT IGNORE INTO stocks (ts_code, name) VALUES (%s, %s)"
DELETE_STOCK = "DELETE FROM stocks WHERE ts_code=%s"
DELETE_DAILY = "DELETE FROM daily_qfq WHERE ts_code=%s"
LATEST_SQL = (
    "SELECT trade_date FROM daily_qfq WHERE ts_code=%s "
    "ORDER BY trade_date DESC LIMIT 1"
)
```

4. 占位符全部 `%s`；`cursor.execute(sql, params)`。
5. CLI：`argparse` 支持 `--dry-run`（dry-run 时不 commit 删除/写入，或跳过 execute）。
6. 打印标题改为「增量更新 MySQL astocks_qfq」。
7. baostock 筛选、重试节奏、`time.sleep(0.05)`、每 200 只进度与现脚本一致。

完整 `main` 结构（与现脚本同序）：login → query_stock_basic → sync stocks → loop update → commit → logout → summary。

`--dry-run`：仍查询 baostock 与最新日期，打印将要写入的数量，但不 `execute` 写操作、不 `commit` 变更。

- [ ] **Step 2: 语法检查**

```bash
cd /Users/hao/Downloads/tmp/database && ../.venv/bin/python -m py_compile update_daily_mysql.py
```

Expected: 退出码 0。

- [ ] **Step 3: 确认未改动旧脚本**

```bash
cd /Users/hao/Downloads/tmp && git status --short database/update_daily.py database/backfill_qfq_to_yesterday.py database/bs_qfq_downloader.py 2>/dev/null || true
# 或比对：不应出现对这些文件的修改
```

Expected: 三文件无变更。

---

### Task 4: README 文档

**Files:**
- Modify: `database/README.md`

- [ ] **Step 1: 在 README 末尾追加「MySQL」小节**

内容需包含：

1. 适用：研究用；仅 `stocks` / `daily_qfq`；`app_*` 不迁。
2. 依赖：`pip install -r requirements.txt`。
3. 配置示例 `mysql.env`：

```text
MYSQL_HOST=127.0.0.1
MYSQL_PORT=3306
MYSQL_USER=your_user
MYSQL_PASSWORD=your_password
MYSQL_DATABASE=astocks_qfq
```

4. 建表 + 全量迁移命令。
5. 日更命令：`python update_daily_mysql.py`。
6. 提醒：迁移前停 SQLite 写入；原 SQLite 脚本仍可用；backfill 仍走 SQLite。

- [ ] **Step 2: 更新 design spec 状态行**

将 `docs/superpowers/specs/2026-07-23-astocks-qfq-mysql-migration-design.md` 顶部状态改为：`已确认；实现见 plans/2026-07-23-astocks-qfq-mysql-migration.md`。

---

## Spec Coverage Check

| Spec 项 | Task |
| --- | --- |
| `schema_mysql.sql` | 1 |
| `migrate_sqlite_to_mysql.py` | 2 |
| `update_daily_mysql.py` | 3 |
| `requirements.txt` pymysql | 1 |
| README MySQL 小节 | 4 |
| 不改现有三脚本 | 3 Step 3 |
| 不迁 app_* / 无 MySQL backfill | 全局约束 + 无对应文件 |
| env 连接约定 | 1 `mysql_config` |
| 校验行数/日期/抽样合计 | 2 `migrate` |
| `--force` / batch | 2 CLI |

## 联调依赖

真正导入与日更需用户提供 MySQL 连接。实现阶段完成代码与本地单测/语法检查；拿到 `mysql.env` 后再跑 Task 2 Step 3 与一次真实日更验收。
