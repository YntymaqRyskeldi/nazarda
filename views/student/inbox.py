"""Оқушының «Хабарламалар» беті: диалогтар, мұғалімге сұрақ, «Көмек керек», хабарландырулар."""
from __future__ import annotations

import streamlit as st

from core import access
from services import messaging, study
from ui import kit, messages, session


def _new_question(uid: int, pre: dict) -> None:
    me = access.user(uid)
    subs = study.subjects_for_student(uid)
    ids = [s["id"] for s in subs]
    sid = st.selectbox("Пән", ids, format_func={s["id"]: s["name"] for s in subs}.get,
                       index=ids.index(pre["subject_id"]) if pre.get("subject_id") in ids else 0, key="nq_subject")
    teacher = study.teacher_for(me["class_id"], sid)
    if not teacher:
        st.info("Бұл пәнге мұғалім тағайындалмаған.")
        return
    st.caption(f"Мұғалім: {teacher['name']}. Байланыс уақыты: {messaging.hours_text(teacher['id'])}.")
    opts = [None] + [a["id"] for a in study.assignments_for_student(uid, uid) if a["subject_id"] == sid]
    names = {a["id"]: a["title"] for a in study.assignments_for_student(uid, uid)}
    with st.form("nq", clear_on_submit=True):
        aid = st.selectbox("Тапсырма (міндетті емес)", opts,
                           index=opts.index(pre["assignment_id"]) if pre.get("assignment_id") in opts else 0,
                           format_func=lambda x: "Тапсырмаға байланыссыз" if x is None else names[x])
        title = st.text_input("Тақырып", value=pre.get("title", ""))
        body = st.text_area("Сұрағың", height=110)
        if st.form_submit_button("Сұрақ жіберу", type="primary"):
            try:
                tok = kit.token("nq")
                did = messaging.start_dialog(uid, "student_teacher", title, [teacher["id"]], body, tok,
                                             subject_id=sid, assignment_id=aid)
                kit.renew_token("nq")
                st.session_state["dlg_open_st"] = did
                if not messaging.within_hours(teacher["id"]):
                    kit.flash(f"Сұрағыңыз қабылданды. Мұғалімнің байланыс уақыты: {messaging.hours_text(teacher['id'])}.",
                              "info")
                else:
                    kit.flash("Сұрақ жіберілді.")
                st.session_state["inbox_tab_next"] = "Диалогтар"
                st.rerun()
            except (ValueError, PermissionError) as e:
                st.error(str(e))


def _help(uid: int, pre: dict) -> None:
    st.caption("Кімнен көмек сұрағың келетінін өзің таңда. Сұрау тек сол адамға көрінеді.")
    contacts = access.allowed_contacts(uid)
    with st.form("help", clear_on_submit=True):
        topics = messaging.HELP_TOPICS
        topic = st.selectbox("Не керек?", topics, index=topics.index(pre["topic"]) if pre.get("topic") in topics else 0)
        to = st.selectbox("Кімнен?", [c["id"] for c in contacts],
                          format_func={c["id"]: f"{c['name']} ({'ата-ана' if c['role'] == 'parent' else 'мұғалім'})"
                                       for c in contacts}.get)
        body = st.text_area("Қысқаша жаз", height=100)
        if st.form_submit_button("Көмек сұрау", type="primary"):
            try:
                tok = kit.token("help")
                did = messaging.start_dialog(uid, "help", topic, [to], body, tok, subject_id=pre.get("subject_id"),
                                             help_topic=topic)
                kit.renew_token("help")
                st.session_state["dlg_open_st"] = did
                if access.role(to) == "teacher" and not messaging.within_hours(to):
                    kit.flash(f"Сұрағыңыз қабылданды. Мұғалімнің байланыс уақыты: {messaging.hours_text(to)}.", "info")
                else:
                    kit.flash("Көмек сұрауы жіберілді.")
                st.session_state["inbox_tab_next"] = "Диалогтар"
                st.rerun()
            except (ValueError, PermissionError) as e:
                st.error(str(e))


def render() -> None:
    uid = session.current_uid()
    kit.show_flash()
    st.title("Хабарламалар")
    pre = st.session_state.pop("inbox_compose", None)
    if pre is not None:
        st.session_state["inbox_pre"] = pre
        st.session_state["inbox_tab"] = "Көмек керек" if pre.get("topic") else "Мұғалімге сұрақ"
    pre = st.session_state.get("inbox_pre", {})
    if nxt := st.session_state.pop("inbox_tab_next", None):
        st.session_state["inbox_tab"] = nxt
    st.session_state.setdefault("inbox_tab", "Диалогтар")
    tab = st.segmented_control("Бөлім", ["Диалогтар", "Мұғалімге сұрақ", "Көмек керек", "Хабарландырулар"],
                               key="inbox_tab", required=True, label_visibility="collapsed")
    if tab == "Диалогтар":
        st.session_state.pop("inbox_pre", None)
        messages.inbox(uid, messaging.dialogs_for(uid), "st")
    elif tab == "Мұғалімге сұрақ":
        _new_question(uid, pre)
    elif tab == "Көмек керек":
        _help(uid, pre)
    else:
        messages.announcements(messaging.announcements_for(uid))
