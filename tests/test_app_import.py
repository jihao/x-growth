from pathlib import Path


def test_app_module_imports():
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
    assert "find_trendlines" in src
    assert "即将支持" in src
    assert "起点 / 终点怎么定" in src
    assert "浪型速度" in src
    assert "analyze_wave_speed" in src
    assert "DIF 背离" in src
    assert "analyze_divergence" in src
    assert "优先关注" in src
    assert "缓=强" in src or "缓涨/缓跌" in src  # 参数说明含「缓=强」
    assert "结构分析" in src
    assert "tab1_collapse_right" in src
    assert "tab1_collapse_left" in src
    assert "个股分析" in src and "收藏" in src
    assert "资金集中度" in src and "选股榜" in src
    assert "fav_store" in src or "quant.favorites" in src
    assert "ui_theme" in src
    assert "tab1_indicator" in src
    assert "KDJ" in src and "BOLL" in src
    assert "toggle_fav_home" in src or "☆" in src or "★" in src
    assert "暂无收藏" in src
    assert 'key="nav"' in src or "session_state.nav" in src
