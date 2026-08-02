"""CLI 参数与流程测试：mock 管线/落库，验证单日与区间模式的调度逻辑。"""
from __future__ import annotations

import pandas as pd
import pytest

from quant.screening import cli


def _fake_results(codes=("AAA.SZ", "BBB.SH")):
    return pd.DataFrame({
        "rank_no": [1, 2], "ts_code": list(codes),
        "total_score": [0.9, 0.8], "score_strategy": [0.6, 0.5],
        "score_structure": [0.7, 0.6], "score_volume": [0.5, 0.4],
        "weights_json": ["{}", "{}"], "factors_json": ["{}", "{}"],
    })


def _run_cli(monkeypatch, argv, dates=None, existing=()):
    saved = {}
    monkeypatch.setattr("sys.argv", argv)
    monkeypatch.setattr(cli.loader, "trading_dates",
                        lambda s, e: dates or [])
    monkeypatch.setattr(cli.pipeline, "_latest_trade_date", lambda: "20260731")
    monkeypatch.setattr(cli.store, "list_dates", lambda: list(existing))
    monkeypatch.setattr(cli.pipeline, "run", lambda **kw: _fake_results())
    monkeypatch.setattr(cli.store, "save_results",
                        lambda d, df: saved.setdefault(d, len(df)) or len(df))
    cli.main()
    return saved


def test_single_date_saves(monkeypatch):
    saved = _run_cli(monkeypatch, ["cli", "--date", "20260729"])
    assert saved == {"20260729": 2}


def test_dry_run_does_not_save(monkeypatch):
    saved = _run_cli(monkeypatch, ["cli", "--date", "20260729", "--dry-run"])
    assert saved == {}


def test_range_runs_each_day(monkeypatch):
    days = ["20260701", "20260702", "20260703"]
    saved = _run_cli(monkeypatch, ["cli", "--from", "20260701"], dates=days)
    assert sorted(saved) == days


def test_range_skip_existing(monkeypatch):
    days = ["20260701", "20260702"]
    saved = _run_cli(monkeypatch,
                     ["cli", "--from", "20260701", "--skip-existing"],
                     dates=days, existing=["20260701"])
    assert sorted(saved) == ["20260702"]


def test_range_empty_exits(monkeypatch):
    with pytest.raises(SystemExit):
        _run_cli(monkeypatch, ["cli", "--from", "20260101"], dates=[])


def test_date_and_from_conflict(monkeypatch):
    monkeypatch.setattr("sys.argv",
                        ["cli", "--date", "20260701", "--from", "20260701"])
    with pytest.raises(SystemExit):
        cli._parse_args()
