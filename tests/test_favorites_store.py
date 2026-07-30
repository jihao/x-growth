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
    select_sql = next(sql for sql, _ in cur.executed if "SELECT" in sql.upper())
    assert "ORDER BY" in select_sql.upper()
    assert "DESC" in select_sql.upper()


def test_is_favorite_false_when_missing():
    cur = _FakeCursor(fetchone=None)
    conn = _FakeConn(cur)
    with patch.object(store, "_conn", return_value=conn):
        assert store.is_favorite("999999.SH") is False
