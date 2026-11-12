"""Күн жоспарының уақыт сызығы. Әр жолда: уақыт, санат, ұзақтық, күй және қолжетімді әрекет."""
from __future__ import annotations

import streamlit as st

from core.fmt import fmt_date
from services import planner
from services.family import settings
from ui.kit import check_icon, esc, flash


def _toggle(uid: int, item_key: str, event_id: int, orig_date: str, widget_key: str) -> None:
    done = st.session_state[widget_key]
    try:
        planner.set_status(uid, event_id, orig_date, "done" if done else "planned")
    except (ValueError, PermissionError) as e:
        st.session_state["_tl_error"] = str(e)
        return
    if done:
        st.session_state["just_done"] = item_key   # анимация тек бір рет ойнайды
        flash("Орындалды. Жарайсың!")


def _cancel(uid: int, event_id: int, orig_date: str) -> None:
    try:
        planner.set_status(uid, event_id, orig_date, "cancelled")
        flash("Бүгінге бас тартылды. Бұл сәтсіздік ретінде саналмайды.")
    except (ValueError, PermissionError) as e:
        st.session_state["_tl_error"] = str(e)


def _restore(uid: int, event_id: int, orig_date: str) -> None:
    planner.set_status(uid, event_id, orig_date, "planned")


def state_text(i: planner.Item) -> str:
    if i.kind == "assignment":
        return "Жіберілді" if i.status == "done" else f"Мерзімі: {fmt_date(i.extra['due_date'])}"
    if i.kind == "school":
        return f"{len(i.extra['lessons'])} сабақ"
    return planner.STATUS_LABEL[i.status]


def render(uid: int, student_id: int, items: list[planner.Item], editable: bool, prefix: str,
           on_open_study=None, show_menu: bool = False) -> None:
    if err := st.session_state.pop("_tl_error", None):
        st.error(err, icon=":material/error:")
    animate_key = st.session_state.pop("just_done", None)
    reduce = bool(settings(uid)["reduce_motion"]) if editable else True
    for i in items:
        done, cancelled = i.status == "done", i.status == "cancelled"
        anim = (i.key == animate_key) and not reduce
        title_cls = "nz-title done" if done else ("nz-title cancelled" if cancelled else "nz-title")
        meta = f"{i.category} · {i.duration} мин" if i.kind != "assignment" else f"{i.category}"
        if i.end:
            meta += f" · аяқталуы {i.end}"
        if i.recurring:
            meta += " · қайталанады"
        calm = ' class="nz-calm"' if anim else ""
        left, right = st.columns([5, 2], vertical_alignment="center")
        with left:
            st.html(f'<div class="nz-row"{calm}>{check_icon(done, anim, cancelled)}'
                    f'<span class="nz-time">{esc(i.start or "—")}</span>'
                    f'<div><div class="{title_cls}">{esc(i.title)}</div>'
                    f'<div class="nz-muted">{esc(meta)} · {esc(state_text(i))}</div></div></div>')
            if anim:
                st.caption("Белгіленді — прогресс жаңарды.")
        with right:
            if i.kind == "event" and editable and not cancelled:
                wk = f"{prefix}_chk_{i.key}"
                st.session_state[wk] = done
                st.checkbox("Орындалды", key=wk, on_change=_toggle, args=(uid, i.key, i.event_id, i.orig_date, wk))
                if show_menu and not done:
                    st.button("Бүгін бас тарту", key=f"{prefix}_cx_{i.key}", type="tertiary",
                              on_click=_cancel, args=(uid, i.event_id, i.orig_date))
            elif i.kind == "event" and editable and cancelled:
                st.button("Қайтару", key=f"{prefix}_rs_{i.key}", type="tertiary",
                          on_click=_restore, args=(uid, i.event_id, i.orig_date))
            elif i.kind == "assignment" and editable and not done and on_open_study:
                st.button("Ашу", key=f"{prefix}_as_{i.key}", on_click=on_open_study,
                          args=(i.source_ref,))
            elif i.kind == "school":
                with st.popover("Сабақтар"):
                    for les in i.extra["lessons"]:
                        st.write(f"{les['start_time']}–{les['end_time']} · {les['subject_name']}")
