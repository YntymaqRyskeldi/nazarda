"""Интерфейс күйі (session_state). Тұрақты деректер мұнда сақталмайды.

Демо режимде пайдаланушы тізімнен таңдалады. Бұл — АВТОРИЗАЦИЯ ЕМЕС: тек
сценарийлерді көрсету үшін рөл ауыстыру. Нақты аккаунттар үшін README-ді қараңыз.
"""
from __future__ import annotations

import streamlit as st

from core import access
from core.db import query

ROLE_LABEL = {"student": "Оқушы", "parent": "Ата-ана", "teacher": "Мұғалім"}


def demo_users() -> list:
    return query("SELECT * FROM users ORDER BY CASE role WHEN 'student' THEN 0 WHEN 'parent' THEN 1 ELSE 2 END, id")


def current_uid() -> int:
    if "uid" not in st.session_state:
        st.session_state.uid = demo_users()[0]["id"]
    return st.session_state.uid


def current_user():
    return access.user(current_uid())


def switch_user_widget() -> None:
    users = demo_users()
    ids = [u["id"] for u in users]
    names = {u["id"]: f"{u['name']} · {ROLE_LABEL[u['role']].lower()}" for u in users}

    def _changed():
        st.session_state.uid = st.session_state._demo_pick
        for k in [k for k in st.session_state.keys() if k.startswith(("child_", "_child_", "dlg_open", "just_done"))]:
            del st.session_state[k]

    st.selectbox("Кім ретінде көру", ids, index=ids.index(current_uid()), format_func=names.get,
                 key="_demo_pick", on_change=_changed,
                 help="Демо режимде рөлді еркін ауыстыруға болады. Бұл қорғалған кіру емес.")


def selected_child(parent_id: int):
    """Ата-ана бірнеше балаға байланысқан болса, таңдалған бала.

    Таңдау виджет кілтінен бөлек айнымалыда сақталады: беттер ауысқанда Streamlit
    көрсетілмеген виджеттердің күйін тазалайды, ал таңдау сақталуы керек."""
    kids = access.children_of(parent_id)
    if not kids:
        return None
    ids = [k["id"] for k in kids]
    if st.session_state.get("child_sel") not in ids:
        st.session_state["child_sel"] = ids[0]
    if len(kids) > 1:
        def _pick():
            v = st.session_state.get("_child_widget")
            if v in ids:
                st.session_state["child_sel"] = v
        st.segmented_control("Бала", ids, default=st.session_state["child_sel"],
                             format_func={k["id"]: k["name"] for k in kids}.get, key="_child_widget",
                             on_change=_pick, required=True, label_visibility="collapsed")
    return next(k for k in kids if k["id"] == st.session_state["child_sel"])
