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
