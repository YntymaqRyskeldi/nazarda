"""Барлық рөлдерге ортақ хабар алмасу интерфейсі.

Жаңа хабарлар st.fragment(run_every=...) арқылы мерзімді тексеріледі.
Бұл polling — лезде жеткізілетін realtime емес; интерфейсте де солай жазылған.
"""
from __future__ import annotations

import streamlit as st

from core import access
from core.fmt import fmt_dt, now_iso
from services import messaging
from ui import kit

POLL = "10s"
STATUS_TONE = {"new": "amber", "in_review": "", "answered": "teal", "closed": "grey"}


def _label(d) -> str:
    unread = f" · {d['unread']} жаңа" if d["unread"] else ""
    return f"{d['title']} — {messaging.STATUS_LABEL[d['status']]}{unread}"


def inbox(uid: int, dialogs: list, key: str, teacher_controls: bool = False) -> None:
    if not dialogs:
        kit.empty("Әзірге диалог жоқ.", "Жаңа сұрақ ашуға болады.")
        return
    ids = [d["id"] for d in dialogs]
    if st.session_state.get(f"dlg_open_{key}") not in ids:
        st.session_state[f"dlg_open_{key}"] = ids[0]
    left, right = st.columns([1, 1.8], gap="medium")
    with left, st.container(border=True, key=f"card_dlist_{key}"):
        st.radio("Диалогтар", ids, format_func={d["id"]: _label(d) for d in dialogs}.get, key=f"dlg_open_{key}",
                 label_visibility="collapsed")
    with right, st.container(border=True, key=f"card_thread_{key}"):
        thread(uid, st.session_state[f"dlg_open_{key}"], teacher_controls)


@st.fragment(run_every=POLL)
def thread(uid: int, dialog_id: int, teacher_controls: bool = False) -> None:
    try:
        msgs = messaging.messages(uid, dialog_id)
        people = messaging.participants(uid, dialog_id)
    except PermissionError as e:
        st.error(str(e))
        return
    from core.db import one
    dlg = one("SELECT d.*, s.name AS subject_name FROM dialogs d LEFT JOIN subjects s ON s.id = d.subject_id "
              "WHERE d.id = ?", (dialog_id,))
    members = ", ".join(f"{p['name']}" for p in people)
    st.html(f'<p class="nz-h">{kit.esc(dlg["title"])}</p>'
            + kit.badge(messaging.STATUS_LABEL[dlg["status"]], STATUS_TONE[dlg["status"]])
            + kit.badge(messaging.KIND_LABEL[dlg["kind"]], "grey")
            + (kit.badge(dlg["subject_name"], "grey") if dlg["subject_name"] else "")
            + f'<p class="nz-muted" style="margin:6px 0 0">Қатысушылар: {kit.esc(members)}</p>')
    is_teacher = access.role(uid) == "teacher"
    for m in msgs:
        mine = m["author_id"] == uid
        later = is_teacher and not mine and m["deliver_at"] > now_iso()
        with st.chat_message("user" if mine else "assistant", avatar=":material/person:" if mine else
                             (":material/school:" if m["author_role"] == "teacher" else ":material/family_restroom:"
                              if m["author_role"] == "parent" else ":material/face:")):
            st.markdown(f"**{m['author_name']}** · {fmt_dt(m['created_at'])}")
            st.write(m["body"])
            if later:
                st.caption("Байланыс уақытынан тыс жіберілген. Ескерту байланыс уақыты басталғанда шығады.")
    st.caption(f"Жаңа хабарлар әр {POLL[:-1]} секунд сайын тексеріледі. Бұл лезде жеткізу (realtime) емес.")
    if teacher_controls:
        statuses = list(messaging.STATUS_LABEL)
        new = st.selectbox("Сұрақтың күйі", statuses, index=statuses.index(dlg["status"]),
                           format_func=messaging.STATUS_LABEL.get, key=f"dst_{dialog_id}")
        if new != dlg["status"]:
            messaging.set_status(uid, dialog_id, new)
            st.rerun(scope="fragment")
    if dlg["status"] == "closed" and not is_teacher:
        st.info("Диалог жабылған. Жаңа сұрақ ашуға болады.")
        return
    with st.form(f"reply_{dialog_id}", clear_on_submit=True, border=False):
        body = st.text_area("Хабар", placeholder="Хабарыңды жаз…", label_visibility="collapsed", height=90)
        sent = st.form_submit_button("Жіберу", type="primary", icon=":material/send:")
    if sent:
        try:
            res = messaging.send(uid, dialog_id, body, kit.token(f"reply_{dialog_id}"))
            kit.renew_token(f"reply_{dialog_id}")
            if res["deferred"]:
                st.session_state[f"deferred_{dialog_id}"] = res["hours"]
            st.rerun(scope="fragment")
        except (ValueError, PermissionError) as e:
            st.error(str(e))
    if hours := st.session_state.pop(f"deferred_{dialog_id}", None):
        st.info(f"Сұрағыңыз қабылданды. Мұғалімнің байланыс уақыты: {hours}.", icon=":material/schedule:")


def deferred_notice(res: dict) -> None:
    if res and res.get("deferred"):
        st.info(f"Сұрағыңыз қабылданды. Мұғалімнің байланыс уақыты: {res['hours']}.", icon=":material/schedule:")


def announcements(rows) -> None:
    if not rows:
        kit.empty("Хабарландыру жоқ.")
    for a in rows:
        with st.container(border=True, key=f"card_ann_{a['id']}"):
            st.html(f'<div class="nz-title">{kit.esc(a["title"])}</div>'
                    f'<div class="nz-muted">{kit.esc(a["teacher_name"])} · {kit.esc(a["subject_name"])} · '
                    f'{kit.esc(a["class_name"])} · {kit.esc(fmt_dt(a["created_at"]))}</div>')
            st.write(a["body"])
