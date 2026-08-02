from unittest.mock import MagicMock

import app.ui_theme as ut
from app.ui_theme import ui_theme


def test_ui_theme_light(monkeypatch):
    class FakeTheme:
        type = "light"

    st = MagicMock()
    st.context.theme = FakeTheme()
    monkeypatch.setattr(ut, "st", st)
    monkeypatch.setattr(ut, "apply_layout_css", lambda: None)
    assert ui_theme() == "light"


def test_ui_theme_fallback(monkeypatch):
    class FakeTheme:
        type = "dark"

    st = MagicMock()
    st.context.theme = FakeTheme()
    monkeypatch.setattr(ut, "st", st)
    monkeypatch.setattr(ut, "apply_layout_css", lambda: None)
    assert ui_theme() == "dark"
