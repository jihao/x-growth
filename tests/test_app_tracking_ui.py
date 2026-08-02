"""「跟踪复盘」页面 UI 测试：导航、侧栏参数隐藏、双视角渲染。"""
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pandas as pd
from streamlit.testing.v1 import AppTest

APP_FILE = Path(__file__).resolve().parent.parent / "app" / "main.py"

_STOCKS = pd.DataFrame(
    {"ts_code": ["000001.SZ", "000002.SZ"], "name": ["平安银行", "万科A"]}
)

_PICKS = pd.DataFrame({
    "trade_date": ["20260731"], "rank_no": [1], "ts_code": ["000001.SZ"],
    "name": ["平安银行"], "total_score": [0.91], "score_strategy": [1.0],
    "score_structure": [0.75], "score_volume": [0.9],
    "weights_json": ["{}"], "factors_json": ["{}"],
})

_REVIEW_DF = pd.DataFrame({
    "trade_date": ["20260731"], "ts_code": ["000001.SZ"], "name": ["平安银行"],
    "rank0": [1], "score0": [0.91], "action0": ["买入参考"],
    "entry_date": ["20260803"], "entry_price": [10.0], "entry_blocked": [False],
    "window_days": [22], "days_traded": [22], "complete": [False],
    "ret_5": [0.01], "ret_10": [0.02], "ret_20": [0.03], "ret_30": [np.nan],
    "ret_latest": [0.03], "max_gain": [0.08], "max_gain_day": ["20260810"],
    "max_dd": [-0.02], "max_dd_day": ["20260805"],
    "in_list_days": [5], "longest_streak": [3], "best_rank": [1],
    "last_rank": [4], "exit_day": [None], "action_last": ["买入参考"],
    "flips": [[]], "n_flips": [0], "events": [[]],
    "verdict": ["方向符合但涨幅有限（T+20 收益 +3.0%）"], "verdict_tone": ["ok"],
    "regime_level": ["弱势"], "regime_score": [-0.6],
})

_REVIEW_STATS = {
    "benchmark": {5: 0.0, 10: 0.0, 20: 0.0, 30: np.nan},
    "by_action": pd.DataFrame({
        "action0": ["买入参考"], "只数": [1], "胜率T+20": [1.0],
        "平均T+5": [0.01], "平均T+10": [0.02], "平均T+20": [0.03],
        "平均T+30": [np.nan], "平均至今": [0.03],
        "平均最大浮盈": [0.08], "平均最大浮亏": [-0.02], "超额T+20": [0.03],
    }),
    "by_bucket": pd.DataFrame({
        "_bucket": ["Top10"], "只数": [1], "胜率T+20": [1.0],
        "平均T+5": [0.01], "平均T+10": [0.02], "平均T+20": [0.03],
        "平均T+30": [np.nan], "平均至今": [0.03],
        "平均最大浮盈": [0.08], "平均最大浮亏": [-0.02], "超额T+20": [0.03],
    }),
    "score_corr": np.nan, "n_exits_day1": 0, "n_flips": 0,
}

_TRACK_DAILY = pd.DataFrame({
    "date": ["20260803", "20260804"], "day_n": [1, 2], "traded": [True, True],
    "close": [10.0, 10.2], "cum_ret": [0.0, 0.02],
    "in_list": [True, False], "rank_no": [1, None],
    "total_score": [0.91, np.nan], "action": ["买入参考", None],
})

_TRACK = {"daily": _TRACK_DAILY, "summary": _REVIEW_DF.iloc[0].to_dict()}


def _patches():
    return (
        patch("quant.data.loader.list_stocks", return_value=_STOCKS),
        patch("quant.data.loader.load_daily", return_value=pd.DataFrame()),
        patch("quant.concentration.cache.read_series", return_value=pd.DataFrame()),
        patch("quant.favorites.store.ensure_table"),
        patch("quant.favorites.store.is_favorite", return_value=False),
        patch("quant.screening.store.list_dates", return_value=["20260731"]),
        patch("quant.screening.store.load_results", return_value=_PICKS),
        patch("quant.screening.tracking.review_date",
              return_value=(_REVIEW_DF, _REVIEW_STATS)),
        patch("quant.screening.tracking.track_pick", return_value=_TRACK),
    )


def _run_tracking_page():
    ps = _patches()
    with ps[0], ps[1], ps[2], ps[3], ps[4], ps[5], ps[6], ps[7], ps[8]:
        app = AppTest.from_file(str(APP_FILE), default_timeout=20).run()
        btn = next(b for b in app.button if b.key == "nav_跟踪复盘")
        btn.click().run()
    return app


def _labels(app, kind):
    return {getattr(w, "label", None) for w in getattr(app, kind)}


def test_nav_has_tracking_page():
    ps = _patches()
    with ps[0], ps[1], ps[2], ps[3], ps[4], ps[5], ps[6], ps[7], ps[8]:
        app = AppTest.from_file(str(APP_FILE), default_timeout=20).run()
    assert not app.exception
    assert any(b.key == "nav_跟踪复盘" for b in app.button)


def test_tracking_page_hides_sidebar_params():
    app = _run_tracking_page()
    assert not app.exception
    assert "股票" not in _labels(app, "selectbox")
    assert "开始" not in _labels(app, "date_input")
    assert "选股日" in _labels(app, "selectbox")
    assert {t.label for t in app.tabs} == {"整体复盘", "个股跟踪"}


def test_tracking_review_renders_metrics_and_tables():
    app = _run_tracking_page()
    assert not app.exception
    metric_labels = _labels(app, "metric")
    assert "T+20 胜率" in metric_labels
    assert "次日落榜" in metric_labels
    # 整体复盘：建议类型/名次分层/逐只明细 三张表
    assert len(app.dataframe) >= 3


def test_tracking_stock_renders_verdict_and_chart():
    app = _run_tracking_page()
    assert not app.exception
    metric_labels = _labels(app, "metric")
    assert "最大浮盈" in metric_labels
    assert "再入选" in metric_labels
    assert "上榜股票" in _labels(app, "selectbox")
