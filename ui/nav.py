"""Беттер тізілімі және беттер арасында ауысу (callback ішінде switch_page шақырылмайды)."""
from __future__ import annotations

import streamlit as st

PAGES: dict = {}


def go(name: str, **state) -> None:
    """Callback ішінен шақыруға болады: келесі rerun басында бетке ауысады."""
    st.session_state["goto"] = name
    for k, v in state.items():
        st.session_state[k] = v


def handle_goto() -> None:
    target = st.session_state.pop("goto", None)
    if target and target in PAGES:
        st.switch_page(PAGES[target])


def link(name: str, label: str, icon: str | None = None) -> None:
    if name in PAGES:
        st.page_link(PAGES[name], label=label, icon=icon)
