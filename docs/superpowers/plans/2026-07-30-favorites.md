# 股票收藏与侧栏导航 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 Streamlit 侧栏增加「首页 / 收藏」竖向切换，用 MySQL 全局表持久化收藏股票，收藏页可点击列表并留在该页查看分析。

**Architecture:** `quant/favorites/store.py` 负责建表与增删查（复用 `mysql_config`）；`app/main.py` 用 `st.radio` 切换导航，首页下拉旁 ★/☆，收藏页列表点选写入 `session_state.ts_code`；主区三个分析 tab 共用同一 `ts_code`/日期，不复制业务逻辑。

**Tech Stack:** Python 3.13、pandas、pymysql、streamlit、pytest（现有 `.venv`）。

## Global Constraints

- 全局单份收藏，无 `user_id` / 登录。
- 表名 `favorites`：`ts_code` VARCHAR(16) PK，`created_at` DATETIME DEFAULT CURRENT_TIMESTAMP。
- `add` 用 `INSERT IGNORE` 幂等；`remove` 删 0 行也成功。
- 点击收藏列表后**留在收藏页**，主区渲染分析。
- 日期区间首页与收藏共用 `session_state`（切换导航不丢）。
- 单测不依赖真实 MySQL：mock 连接；UI 用源码关键字烟测。
- `.venv/bin/python -m pytest`；每 Task 提交一次。
- Spec：`docs/superpowers/specs/2026-07-30-favorites-design.md`。

## File Structure

| 文件 | 职责 |
|---|---|
| `quant/favorites/__init__.py` | 包导出（可空或 re-export store API） |
| `quant/favorites/store.py` | `ensure_table` / `list_favorites` / `is_favorite` / `add` / `remove` |
| `app/main.py` | 侧栏导航、★、收藏列表、共用分析主区 |
| `tests/test_favorites_store.py` | store 单元测试（mock DB） |
| `tests/test_app_import.py` | 导航/收藏相关源码断言 |

---

### Task 1: Favorites store（MySQL 访问层）

**Files:**
- Create: `quant/favorites/__init__.py`
- Create: `quant/favorites/store.py`
- Create: `tests/test_favorites_store.py`

**Interfaces:**
- Consumes: `mysql_config.connect_mysql`, `mysql_config.load_dotenv`（经 `from quant import config` 注入 `sys.path`）
- Produces:
  - `ensure_table() -> None`
  - `list_favorites() -> pd.DataFrame` 列 `ts_code`, `name`, `created_at`，`created_at` DESC
  - `is_favorite(ts_code: str) -> bool`
  - `add(ts_code: str) -> None`
  - `remove(ts_code: str) -> None`

- [ ] **Step 1: 写失败测试（mock 连接）**

创建 `tests/test_favorites_store.py`：

```python
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from quant.favorites import store


class _FakeCursor:
    def __init__(self, fetchone=None, fetchall=None, description=None):
        self._fetchone = fetchone
        self._fetchall = fetchall or []
        self.description = description or []
        self.executed = []

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def execute(self, sql, params=None):
        self.executed.append((sql, params))

    def fetchone(self):
        return self._fetchone

    def fetchall(self):
        return list(self._fetchall)


class _FakeConn:
    def __init__(self, cursor: _FakeCursor):
        self._cursor = cursor
        self.committed = False
        self.closed = False

    def cursor(self):
        return self._cursor

    def commit(self):
        self.committed = True

    def close(self):
        self.closed = True


def test_ensure_table_runs_create():
    cur = _FakeCursor()
    conn = _FakeConn(cur)
    with patch.object(store, "_conn", return_value=conn):
        store.ensure_table()
    assert any("CREATE TABLE" in sql.upper() and "favorites" in sql.lower()
               for sql, _ in cur.executed)
    assert conn.committed and conn.closed


def test_add_insert_ignore_and_is_favorite():
    cur = _FakeCursor(fetchone=(1,))
    conn = _FakeConn(cur)
    with patch.object(store, "_conn", return_value=conn):
        store.add("600519.SH")
        assert store.is_favorite("600519.SH") is True
    assert any("INSERT IGNORE" in sql.upper() for sql, _ in cur.executed)
    assert any("600519.SH" in (params or ()) for _, params in cur.executed)


def test_remove_idempotent():
    cur = _FakeCursor()
    conn = _FakeConn(cur)
    with patch.object(store, "_conn", return_value=conn):
        store.remove("600519.SH")  # 即使 0 行也不抛
    assert any("DELETE" in sql.upper() for sql, _ in cur.executed)
    assert conn.committed


def test_list_favorites_ordered_with_name():
    cur = _FakeCursor(
        fetchall=[
            ("600519.SH", "贵州茅台", "2026-07-30 10:00:00"),
            ("000001.SZ", "平安银行", "2026-07-29 09:00:00"),
        ],
        description=[("ts_code",), ("name",), ("created_at",)],
    )
    conn = _FakeConn(cur)
    with patch.object(store, "_conn", return_value=conn):
        df = store.list_favorites()
    assert list(df.columns) == ["ts_code", "name", "created_at"]
    assert df.iloc[0]["ts_code"] == "600519.SH"
    assert "ORDER BY" in cur.executed[0][0].upper()
    assert "DESC" in cur.executed[0][0].upper()


def test_is_favorite_false_when_missing():
    cur = _FakeCursor(fetchone=None)
    conn = _FakeConn(cur)
    with patch.object(store, "_conn", return_value=conn):
        assert store.is_favorite("999999.SH") is False
```

- [ ] **Step 2: 运行确认失败**

Run: `.venv/bin/python -m pytest tests/test_favorites_store.py -v`  
Expected: FAIL（`quant.favorites` 不存在或缺函数）

- [ ] **Step 3: 实现 store**

创建 `quant/favorites/__init__.py`（可为空文件）。

Create `quant/favorites/store.py`：

```python
"""全局股票收藏（MySQL favorites 表）。"""
from __future__ import annotations

import pandas as pd

from quant import config  # noqa: F401  # 注入 database/mysql 到 sys.path
from mysql_config import connect_mysql, load_dotenv

_CREATE_SQL = """
CREATE TABLE IF NOT EXISTS favorites (
  ts_code VARCHAR(16) NOT NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (ts_code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
"""


def _conn():
    load_dotenv()
    return connect_mysql()


def ensure_table() -> None:
    conn = _conn()
    try:
        with conn.cursor() as cur:
            cur.execute(_CREATE_SQL)
        conn.commit()
    finally:
        conn.close()


def add(ts_code: str) -> None:
    ensure_table()
    conn = _conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT IGNORE INTO favorites (ts_code) VALUES (%s)",
                (ts_code,),
            )
        conn.commit()
    finally:
        conn.close()


def remove(ts_code: str) -> None:
    ensure_table()
    conn = _conn()
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM favorites WHERE ts_code=%s", (ts_code,))
        conn.commit()
    finally:
        conn.close()


def is_favorite(ts_code: str) -> bool:
    ensure_table()
    conn = _conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT 1 FROM favorites WHERE ts_code=%s LIMIT 1",
                (ts_code,),
            )
            return cur.fetchone() is not None
    finally:
        conn.close()


def list_favorites() -> pd.DataFrame:
    ensure_table()
    conn = _conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT f.ts_code, s.name, f.created_at "
                "FROM favorites f "
                "LEFT JOIN stocks s ON s.ts_code=f.ts_code "
                "ORDER BY f.created_at DESC"
            )
            rows = cur.fetchall()
            cols = [c[0] for c in cur.description] if cur.description else [
                "ts_code", "name", "created_at"
            ]
        return pd.DataFrame(list(rows), columns=cols)
    finally:
        conn.close()
```

注意：`add`/`remove`/`is_favorite`/`list_favorites` 每次都会 `_conn()`；测试里每次调用需保证 `patch` 覆盖多次，或改为可注入。若单测因多次 `_conn` 失败，把 `patch.object(store, "_conn", return_value=conn)` 改为 `side_effect=lambda: conn` 同一 fake，或每次返回新 `_FakeConn` 共享同一 `cur`。推荐实现时让测试用：

```python
with patch.object(store, "_conn", side_effect=lambda: _FakeConn(cur)):
```

并在各测试里按需重置 `cur.executed` / 使用同一 cursor 状态机。若 `ensure_table` + `add` 两次连接，用 `side_effect` 返回两个都带同一 `executed` 列表的 cursor 包装，或简化：`ensure_table` 仅在 `list`/`add`/`remove`/`is_favorite` 开头调用时，测试对 `_conn` 用 `side_effect` 返回足够多次的相同行为连接。

更稳妥的测法：在 Step 3 实现后，把测试里的 patch 统一改成：

```python
def _patch_conn(cur):
    return patch.object(store, "_conn", side_effect=lambda: _FakeConn(cur))
```

且 `_FakeCursor.executed` 跨多次连接累积（每个新 `_FakeConn` 复用同一 `cur` 实例）。

- [ ] **Step 4: 运行测试通过**

Run: `.venv/bin/python -m pytest tests/test_favorites_store.py -v`  
Expected: 全部 PASS

- [ ] **Step 5: Commit**

```bash
git add quant/favorites/__init__.py quant/favorites/store.py tests/test_favorites_store.py
git commit -m "$(cat <<'EOF'
feat(favorites): add MySQL favorites store

EOF
)"
```

---

### Task 2: Streamlit 侧栏导航 + ★ + 收藏列表

**Files:**
- Modify: `app/main.py`（侧栏约 40–56 行起；主区 tab 逻辑保持在解析出 `ts_code`/`start`/`end` 之后）

**Interfaces:**
- Consumes: `quant.favorites.store` 的 `ensure_table`, `list_favorites`, `is_favorite`, `add`, `remove`
- Produces: UI 行为（无新公开 Python API）
  - `st.session_state.nav` ∈ `{"首页", "收藏"}`
  - `st.session_state.ts_code`：当前分析用代码
  - 日期：`st.session_state.fav_start` / `fav_end` 或沿用带 `key=` 的 `st.date_input`，保证两页共用

- [ ] **Step 1: 在 `main.py` 顶部增加 import**

在现有 import 区追加：

```python
from quant.favorites import store as fav_store
```

- [ ] **Step 2: 重写侧栏：导航 + 首页/收藏分支**

将现有：

```python
with st.sidebar:
    st.header("参数")
    try:
        stocks = _stocks()
        options = (stocks["ts_code"] + "  " + stocks["name"].fillna("")).tolist()
    except Exception as exc:
        st.error(f"无法连接 MySQL，请检查 database/mysql/mysql.env：{exc}")
        st.stop()
    if stocks.empty or not options:
        st.error("股票列表为空，请检查数据库。")
        st.stop()
    picked = st.selectbox("股票", options)
    ts_code = picked.split("  ")[0]
    _default_start = pd.Timestamp.today() - pd.DateOffset(months=6)
    start = st.date_input("开始", _default_start).strftime("%Y%m%d")
    end = st.date_input("结束", pd.Timestamp.today()).strftime("%Y%m%d")
```

替换为（保持「股票列表拉取失败则 stop」；收藏表操作失败单独 `st.error`）：

```python
with st.sidebar:
    st.header("导航")
    if "nav" not in st.session_state:
        st.session_state.nav = "首页"
    nav = st.radio(
        "页面",
        ["首页", "收藏"],
        key="nav",
        label_visibility="collapsed",
    )

    st.header("参数")
    try:
        stocks = _stocks()
        options = (stocks["ts_code"] + "  " + stocks["name"].fillna("")).tolist()
        code_to_label = {
            c.split("  ")[0]: c for c in options
        }
    except Exception as exc:
        st.error(f"无法连接 MySQL，请检查 database/mysql/mysql.env：{exc}")
        st.stop()
    if stocks.empty or not options:
        st.error("股票列表为空，请检查数据库。")
        st.stop()

    if "ts_code" not in st.session_state:
        st.session_state.ts_code = options[0].split("  ")[0]

    _default_start = pd.Timestamp.today() - pd.DateOffset(months=6)
    start = st.date_input("开始", _default_start, key="date_start").strftime("%Y%m%d")
    end = st.date_input("结束", pd.Timestamp.today(), key="date_end").strftime("%Y%m%d")

    if nav == "首页":
        # 下拉默认对齐 session_state.ts_code
        cur = st.session_state.ts_code
        labels = options
        try:
            idx = next(i for i, lab in enumerate(labels) if lab.startswith(cur + "  ") or lab == cur)
        except StopIteration:
            idx = 0
        picked = st.selectbox("股票", labels, index=idx, key="home_stock")
        ts_code = picked.split("  ")[0]
        st.session_state.ts_code = ts_code

        # ★ / ☆
        try:
            fav_store.ensure_table()
            starred = fav_store.is_favorite(ts_code)
        except Exception as exc:
            st.error(f"读取收藏失败：{exc}")
            starred = False
        star_label = "★ 取消收藏" if starred else "☆ 收藏"
        if st.button(star_label, key="toggle_fav_home"):
            try:
                if starred:
                    fav_store.remove(ts_code)
                else:
                    fav_store.add(ts_code)
                st.rerun()
            except Exception as exc:
                st.error(f"更新收藏失败：{exc}")
    else:
        # 收藏页
        try:
            fav_store.ensure_table()
            fav_df = fav_store.list_favorites()
        except Exception as exc:
            st.error(f"读取收藏列表失败：{exc}")
            fav_df = pd.DataFrame(columns=["ts_code", "name", "created_at"])

        if fav_df.empty:
            st.info("暂无收藏")
            ts_code = st.session_state.ts_code
        else:
            for _, row in fav_df.iterrows():
                code = row["ts_code"]
                name = row["name"] if pd.notna(row["name"]) and row["name"] else ""
                label = f"{code}  {name}".rstrip()
                c1, c2 = st.columns([4, 1])
                with c1:
                    if st.button(label, key=f"fav_pick_{code}", use_container_width=True):
                        st.session_state.ts_code = code
                        st.rerun()
                with c2:
                    if st.button("✕", key=f"fav_del_{code}", help="取消收藏"):
                        try:
                            fav_store.remove(code)
                            st.rerun()
                        except Exception as exc:
                            st.error(f"取消收藏失败：{exc}")
            ts_code = st.session_state.ts_code
            st.caption(f"当前：{code_to_label.get(ts_code, ts_code)}")
```

侧栏结束后，主区现有 `tab1, tab2, tab3 = st.tabs(...)` **原样保留**，继续使用上面得到的 `ts_code` / `start` / `end`（不要再在主区重新 selectbox）。

注意：
- `st.radio(..., key="nav")` 会自动写入 `session_state.nav`；若同时手动初始化，避免与 `index=` 冲突——用 `key="nav"` 即可，可去掉手动 `if "nav" not in`。
- `selectbox` 的 `key="home_stock"` 与手动改 `index` 可能冲突：若 Streamlit 警告 widget 状态，改为在点收藏时 `st.session_state.home_stock = code_to_label[code]`，首页用 `key="home_stock"` 且不传 `index`。

推荐稳妥写法（首页选股）：

```python
    if nav == "首页":
        if "home_stock" not in st.session_state:
            st.session_state.home_stock = code_to_label.get(
                st.session_state.ts_code, options[0]
            )
        # 若 ts_code 被收藏页改过，同步 label
        want = code_to_label.get(st.session_state.ts_code)
        if want and st.session_state.home_stock != want:
            st.session_state.home_stock = want
        picked = st.selectbox("股票", options, key="home_stock")
        ts_code = picked.split("  ")[0]
        st.session_state.ts_code = ts_code
        # ... ★ 按钮同上
```

收藏页点选时：

```python
                        st.session_state.ts_code = code
                        if code in code_to_label:
                            st.session_state.home_stock = code_to_label[code]
                        st.rerun()
```

- [ ] **Step 3: 本地手动冒烟（有 MySQL 时）**

Run: `.venv/bin/streamlit run app/main.py`  
检查：
1. 侧栏顶部可竖向切「首页 / 收藏」
2. 首页 ☆ 收藏后变 ★；刷新后仍在
3. 收藏页出现该股；点击后主区 K 线变为该股，仍停在收藏导航
4. ✕ 可取消；空列表显示「暂无收藏」
5. 切换导航后日期区间保持

- [ ] **Step 4: Commit**

```bash
git add app/main.py
git commit -m "$(cat <<'EOF'
feat(app): add favorites nav and star toggle in sidebar

EOF
)"
```

---

### Task 3: App 源码烟测断言

**Files:**
- Modify: `tests/test_app_import.py`

**Interfaces:**
- Consumes: Task 2 写入的 `app/main.py` 关键字
- Produces: 无运行时 API

- [ ] **Step 1: 扩展失败断言**

在 `tests/test_app_import.py` 的 `test_app_module_imports` 末尾追加：

```python
    assert "首页" in src and "收藏" in src
    assert "fav_store" in src or "quant.favorites" in src
    assert "toggle_fav_home" in src or "☆" in src or "★" in src
    assert "暂无收藏" in src
    assert 'key="nav"' in src or "session_state.nav" in src
```

- [ ] **Step 2: 运行测试**

Run: `.venv/bin/python -m pytest tests/test_app_import.py tests/test_favorites_store.py -v`  
Expected: 全部 PASS

- [ ] **Step 3: Commit**

```bash
git add tests/test_app_import.py
git commit -m "$(cat <<'EOF'
test(app): assert favorites navigation markers in main

EOF
)"
```

---

## Spec coverage（self-review）

| Spec 要求 | Task |
|-----------|------|
| MySQL `favorites` 表 + ensure_table | Task 1 |
| list / is_favorite / add / remove 幂等 | Task 1 |
| 侧栏竖向首页/收藏 | Task 2 |
| 首页 ★/☆ | Task 2 |
| 收藏列表可点、留在收藏页看图 | Task 2 |
| 列表取消收藏 | Task 2 |
| 日期共用 | Task 2（`key=date_start/end`） |
| 主区逻辑不复制 | Task 2（共用 `ts_code`） |
| store 单测 + app 关键字测 | Task 1、3 |
| 非目标（多用户等） | 未实现 ✓ |
