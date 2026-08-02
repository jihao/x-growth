"""Streamlit 主题检测：切换 light/dark 时同步 K 线配色。"""
from __future__ import annotations

from datetime import timedelta

import streamlit as st

# 收紧默认边距（不再插入空的 components.html 占位）
_LAYOUT_CSS = """
<style>
header[data-testid="stHeader"] {
  background: transparent !important;
}
div[data-testid="stDecoration"] {
  display: none !important;
}
div.block-container {
  padding-top: 2.4rem !important;
  padding-bottom: 1rem !important;
  padding-left: 1.25rem !important;
  padding-right: 1.25rem !important;
  max-width: 100% !important;
  overflow: visible !important;
}
h1 {
  margin-top: 0 !important;
  margin-bottom: 0.35rem !important;
  padding-top: 0.1rem !important;
  line-height: 1.35 !important;
  overflow: visible !important;
  font-size: 1.55rem !important;
}
section[data-testid="stSidebar"] > div:first-child {
  padding-top: 0 !important;
}
[data-testid="stSidebarHeader"] {
  height: 2.5rem !important;
  min-height: 2.5rem !important;
  padding: 0.35rem 0.75rem !important;
}
[data-testid="stSidebarUserContent"],
[data-testid="stSidebarContent"] {
  padding-top: 0.35rem !important;
}
section[data-testid="stSidebar"] h2,
section[data-testid="stSidebar"] .stMarkdown h2 {
  margin-top: 0.15rem !important;
  margin-bottom: 0.35rem !important;
}
</style>
"""


def apply_layout_css() -> None:
    st.markdown(_LAYOUT_CSS, unsafe_allow_html=True)


def ui_theme() -> str:
    """返回当前 UI 主题（light/dark）。"""
    apply_layout_css()
    try:
        t = st.context.theme.type
        if t in ("light", "dark"):
            return t
    except Exception:
        pass
    return "dark"


def install_theme_watcher() -> None:
    """定期探测主题；变化时整页 rerun（不插入空 iframe）。"""

    @st.fragment(run_every=timedelta(seconds=1))
    def _watch() -> None:
        try:
            t = st.context.theme.type
        except Exception:
            return
        if t not in ("light", "dark"):
            return
        prev = st.session_state.get("_ui_theme_seen")
        if prev is None:
            st.session_state["_ui_theme_seen"] = t
            return
        if t != prev:
            st.session_state["_ui_theme_seen"] = t
            st.rerun()

    _watch()
