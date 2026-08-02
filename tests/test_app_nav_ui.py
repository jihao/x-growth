"""按语义分页后的导航结构 UI 测试：各页面渲染正常，市场级页面不显示个股选择器。"""
from pathlib import Path
from unittest.mock import patch

import pandas as pd
from streamlit.testing.v1 import AppTest

APP_FILE = Path(__file__).resolve().parent.parent / "app" / "main.py"

_STOCKS = pd.DataFrame(
    {"ts_code": ["000001.SZ", "000002.SZ"], "name": ["平安银行", "万科A"]}
)


def _base_patches():
    return (
        patch("quant.data.loader.list_stocks", return_value=_STOCKS),
        patch("quant.data.loader.load_daily", return_value=pd.DataFrame()),
        patch("quant.concentration.cache.read_series", return_value=pd.DataFrame()),
        patch("quant.favorites.store.ensure_table"),
        patch("quant.favorites.store.is_favorite", return_value=False),
    )


def _labels(app, kind):
    return {getattr(w, "label", None) for w in getattr(app, kind)}


def _goto(app, page):
    btn = next(b for b in app.button if b.key == f"nav_{page}")
    btn.click().run()


def test_stock_page_has_picker_and_two_tabs():
    with _base_patches()[0], _base_patches()[1], _base_patches()[2], \
            _base_patches()[3], _base_patches()[4]:
        app = AppTest.from_file(str(APP_FILE), default_timeout=10).run()
    assert not app.exception
    assert "股票" in _labels(app, "selectbox")
    tab_labels = {t.label for t in app.tabs}
    assert tab_labels == {"行情分析", "策略回测"}


def test_concentration_page_has_dates_but_no_stock_picker():
    with _base_patches()[0], _base_patches()[1], _base_patches()[2], \
            _base_patches()[3], _base_patches()[4]:
        app = AppTest.from_file(str(APP_FILE), default_timeout=10).run()
        _goto(app, "资金集中度")
    assert not app.exception
    assert "股票" not in _labels(app, "selectbox")
    assert "开始" in _labels(app, "date_input")
    assert "结束" in _labels(app, "date_input")


def test_favorites_page_in_page_switcher():
    fav_df = pd.DataFrame(
        {
            "ts_code": ["000001.SZ", "000002.SZ"],
            "name": ["平安银行", "万科A"],
            "created_at": ["2026-08-01", "2026-08-02"],
        }
    )
    with _base_patches()[0], _base_patches()[1], _base_patches()[2], \
            _base_patches()[3], _base_patches()[4], \
            patch("quant.favorites.store.list_favorites", return_value=fav_df):
        app = AppTest.from_file(str(APP_FILE), default_timeout=10).run()
        _goto(app, "收藏")
        assert not app.exception
        # 进入收藏页自动选中第一只收藏
        assert app.session_state["ts_code"] == "000001.SZ"
        # 侧栏不再显示收藏列表/股票选择器，切换器在主区
        assert "股票" not in _labels(app, "selectbox")
        btn = next(b for b in app.button if b.key == "fav_pick_000002.SZ")
        btn.click().run()
        assert not app.exception
        assert app.session_state["ts_code"] == "000002.SZ"
        # 收藏页同样渲染行情分析/策略回测两个 Tab
        assert {t.label for t in app.tabs} == {"行情分析", "策略回测"}


def test_favorites_page_empty_hint():
    with _base_patches()[0], _base_patches()[1], _base_patches()[2], \
            _base_patches()[3], _base_patches()[4], \
            patch("quant.favorites.store.list_favorites",
                  return_value=pd.DataFrame(columns=["ts_code", "name", "created_at"])):
        app = AppTest.from_file(str(APP_FILE), default_timeout=10).run()
        _goto(app, "收藏")
    assert not app.exception
    assert any("暂无收藏" in i.value for i in app.info)


def test_screening_page_hides_sidebar_params():
    results = pd.DataFrame(
        {
            "trade_date": ["20260731"],
            "rank_no": [1],
            "ts_code": ["000001.SZ"],
            "name": ["平安银行"],
            "total_score": [0.91],
            "score_strategy": [1.0],
            "score_structure": [0.75],
            "score_volume": [0.9],
            "weights_json": ["{}"],
            "factors_json": ["{}"],
        }
    )
    with _base_patches()[0], _base_patches()[1], _base_patches()[2], \
            _base_patches()[3], _base_patches()[4], \
            patch("quant.screening.store.list_dates", return_value=["20260731"]), \
            patch("quant.screening.store.load_results", return_value=results), \
            patch("quant.screening.llm.is_configured", return_value=False):
        app = AppTest.from_file(str(APP_FILE), default_timeout=10).run()
        _goto(app, "选股榜")
    assert not app.exception
    assert "股票" not in _labels(app, "selectbox")
    assert "开始" not in _labels(app, "date_input")
    assert "交易日" in _labels(app, "selectbox")
