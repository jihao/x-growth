from __future__ import annotations

import json
from unittest.mock import patch

import pandas as pd
import pytest

from quant.screening import store


@pytest.fixture(autouse=True)
def _reset_ensured():
    store._ensured = False
    yield
    store._ensured = False


class _FakeCursor:
    def __init__(self, fetchone=None, fetchall=None, description=None):
        self._fetchone = fetchone
        self._fetchall = fetchall or []
        self.description = description or []
        self.executed = []
        self.many = []

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def execute(self, sql, params=None):
        self.executed.append((sql, params))

    def executemany(self, sql, rows):
        self.many.append((sql, list(rows)))

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


def _results_df() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "ts_code": ["600519.SH", "000001.SZ"],
            "rank_no": [1, 2],
            "total_score": [0.91, 0.82],
            "score_strategy": [1.0, 0.8],
            "score_structure": [0.75, 0.6],
            "score_volume": [0.9, 0.95],
            "weights_json": [{"ma_cross": 1.0}, {"ma_cross": 1.0}],
            "factors_json": [{"strategy": {}}, {"strategy": {}}],
        }
    )


def test_ensure_table_runs_create():
    cur = _FakeCursor()
    conn = _FakeConn(cur)
    with patch.object(store, "_conn", return_value=conn):
        store.ensure_table()
        store.ensure_table()
    assert any(
        "CREATE TABLE" in sql.upper() and "screening_results" in sql.lower()
        for sql, _ in cur.executed
    )
    assert conn.committed and conn.closed


def test_save_results_delete_then_bulk_insert():
    cur = _FakeCursor()
    conn = _FakeConn(cur)
    with patch.object(store, "_conn", return_value=conn):
        n = store.save_results("2026-07-31", _results_df())
    assert n == 2
    delete_sql = next(
        sql for sql, _ in cur.executed if "DELETE" in sql.upper()
    )
    assert "trade_date" in delete_sql
    assert len(cur.many) == 1
    insert_sql, rows = cur.many[0]
    assert "INSERT INTO screening_results" in insert_sql
    assert rows[0][0] == "20260731"          # 日期被 fmt_date 归一化
    assert rows[0][1] == "600519.SH"
    # dict 被序列化为 JSON 字符串
    assert json.loads(rows[0][7]) == {"ma_cross": 1.0}


def test_load_results_ordered_with_name():
    cur = _FakeCursor(
        fetchall=[
            ("20260731", 1, "600519.SH", "贵州茅台",
             0.91, 1.0, 0.75, 0.9, "{}", "{}"),
        ],
        description=[
            ("trade_date",), ("rank_no",), ("ts_code",), ("name",),
            ("total_score",), ("score_strategy",), ("score_structure",),
            ("score_volume",), ("weights_json",), ("factors_json",),
        ],
    )
    conn = _FakeConn(cur)
    with patch.object(store, "_conn", return_value=conn):
        df = store.load_results("20260731")
    assert list(df["ts_code"]) == ["600519.SH"]
    assert df.iloc[0]["name"] == "贵州茅台"
    select_sql = next(sql for sql, _ in cur.executed if "SELECT" in sql.upper())
    assert "ORDER BY" in select_sql.upper()
    assert "rank_no" in select_sql


def test_list_dates_desc():
    cur = _FakeCursor(fetchall=[("20260731",), ("20260730",)])
    conn = _FakeConn(cur)
    with patch.object(store, "_conn", return_value=conn):
        dates = store.list_dates()
    assert dates == ["20260731", "20260730"]
    select_sql = next(sql for sql, _ in cur.executed if "SELECT" in sql.upper())
    assert "DESC" in select_sql.upper()


def test_dump_passthrough_and_json():
    assert store._dump('{"a": 1}') == '{"a": 1}'
    assert json.loads(store._dump({"a": 1})) == {"a": 1}
    assert json.loads(store._dump(None)) == {}
