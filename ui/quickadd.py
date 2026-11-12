"""«Жылдам қосу»: іс, шығыс немесе мақсат қадамы. Ең аз өріс, қалғаны «Қосымша» ішінде."""
from __future__ import annotations

from datetime import time

import streamlit as st

from core.fmt import WEEKDAYS, money, to_tiyn, today
from services import finance, goals, planner
from ui.kit import flash, renew_token, token


def render(uid: int) -> None:
    with st.popover("Жылдам қосу", icon=":material/add:", type="secondary"):
        kind = st.segmented_control("Не қосамыз?", ["Іс", "Шығыс", "Мақсат қадамы"], default="Іс",
                                    key="qa_kind", required=True)
        if kind == "Іс":
            _event(uid)
        elif kind == "Шығыс":
            _expense(uid)
        else:
            _step(uid)


def _event(uid: int) -> None:
    with st.form("qa_event", clear_on_submit=True, border=False):
        title = st.text_input("Атауы", placeholder="Мысалы: Физиканы қайталау")
        c1, c2 = st.columns(2)
        start = c1.time_input("Басталуы", value=time(18, 0), step=900)
        dur = c2.number_input("Ұзақтығы, мин", min_value=5, max_value=600, value=30, step=5)
        with st.expander("Қосымша"):
            cat = st.selectbox("Санаты", planner.CATEGORIES, index=planner.CATEGORIES.index("Басқа"))
            day = st.date_input("Күні", value=today(), format="DD.MM.YYYY")
            rep = st.multiselect("Қайталау (апта күндері)", list(range(7)), placeholder="Таңдаңыз", format_func=lambda w: WEEKDAYS[w])
            tracked = st.checkbox("Күннің орындалуында есептелсін", value=True)
            shared = st.checkbox("Ата-анаға ортақ күнтізбеде көрінсін", value=False)
        if st.form_submit_button("Жоспарға қосу", type="primary"):
            try:
                planner.create_event(uid, uid, title, cat, start.strftime("%H:%M"), int(dur), day.isoformat(),
                                     rep, tracked=tracked, shared=shared)
                flash("Іс жоспарға қосылды.")
                st.rerun()
            except ValueError as e:
                st.error(str(e))


def _expense(uid: int) -> None:
    b = finance.balance(uid, uid)
    st.caption(f"Шығынға қолжетімді: {money(b.available)}")
    with st.form("qa_exp", clear_on_submit=True, border=False):
        amount = st.text_input("Сома, ₸", placeholder="Мысалы: 1200")
        cat = st.selectbox("Санаты", finance.EXPENSE_CATEGORIES)
        with st.expander("Қосымша"):
            note = st.text_input("Түсініктеме")
            day = st.date_input("Күні", value=today(), format="DD.MM.YYYY")
        if st.form_submit_button("Шығысты жазу", type="primary"):
            try:
                finance.add(uid, uid, "expense", to_tiyn(amount), day.isoformat(), cat, note=note,
                            token=token("qa_exp"))
                renew_token("qa_exp")
                flash("Шығыс жазылды.")
                st.rerun()
            except ValueError as e:
                st.error(str(e))


def _step(uid: int) -> None:
    active = goals.list_goals(uid, uid, ("active",))
    if not active:
        st.info("Белсенді мақсат жоқ. Алдымен «Мақсаттарым» бөлімінде мақсат құр.")
        return
    with st.form("qa_step", clear_on_submit=True, border=False):
        gid = st.selectbox("Мақсат", [g["id"] for g in active],
                           format_func={g["id"]: g["title"] for g in active}.get)
        title = st.text_input("Қадам", placeholder="Мысалы: 20 минут жаттығу")
        with st.expander("Қосымша"):
            plan = st.checkbox("Жоспарға қою")
            day = st.date_input("Күні", value=today(), format="DD.MM.YYYY")
            start = st.time_input("Уақыты", value=time(18, 0), step=900)
        if st.form_submit_button("Қадам қосу", type="primary"):
            try:
                goals.add_step(uid, gid, title)
                if plan:
                    sid = max(s["id"] for s in goals.steps(gid))
                    goals.schedule_step(uid, sid, day.isoformat(), start.strftime("%H:%M"))
                flash("Қадам қосылды.")
                st.rerun()
            except ValueError as e:
                st.error(str(e))
