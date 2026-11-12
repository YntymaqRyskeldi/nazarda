"""«Курстарым»: сыртқы курстар жоспармен байланысты."""
from __future__ import annotations

from datetime import datetime, time

import streamlit as st

from core.fmt import WEEKDAYS, WEEKDAYS_SHORT, fmt_date, k_of_n
from services import courses
from ui import kit, session


def _form(uid: int, c=None) -> None:
    key = f"course_form_{c['id'] if c else 'new'}"
    with st.form(key, clear_on_submit=c is None):
        title = st.text_input("Курс атауы", value=c["title"] if c else "")
        c1, c2 = st.columns(2)
        org = c1.text_input("Ұйымдастырушы", value=c["organizer"] if c else "")
        url = c2.text_input("Курс сілтемесі", value=c["url"] if c else "", placeholder="https://...")
        days = st.multiselect("Сабақ күндері", list(range(7)), placeholder="Таңдаңыз", format_func=lambda w: WEEKDAYS[w],
                              default=[int(x) for x in c["weekdays"].split(",") if x] if c else [])
        c1, c2, c3, c4 = st.columns(4)
        start = c1.time_input("Уақыты", value=datetime.strptime(c["start_time"], "%H:%M").time() if c else time(18, 0),
                              step=900)
        dur = c2.number_input("Ұзақтығы, мин", 15, 300, c["duration_min"] if c else 60, 15)
        total = c3.number_input("Барлық сабақ", 1, 500, c["total_lessons"] if c else 10)
        done = c4.number_input("Аяқталған сабақ", 0, 500, c["completed_lessons"] if c else 0)
        c1, c2 = st.columns(2)
        stage = c1.text_input("Қазіргі кезең", value=c["stage"] if c else "")
        nxt = c2.text_input("Келесі тапсырма", value=c["next_task"] if c else "")
        cover = st.text_input("Мұқаба суретінің сілтемесі (міндетті емес)", value=c["cover"] if c else "",
                              help="Бос қалдырсаң, атауға сай мұқаба автоматты түрде салынады.")
        st.caption("Курс кестесі «Күн жоспарым» бөлімінде бір қайталанатын іс ретінде көрінеді.")
        if st.form_submit_button("Сақтау" if c else "Курс қосу", type="primary"):
            try:
                if c:
                    courses.update_course(uid, c["id"], title=title, organizer=org, url=url, weekdays=days,
                                          start_time=start.strftime("%H:%M"), duration_min=int(dur),
                                          total_lessons=int(total), completed_lessons=int(done), stage=stage,
                                          next_task=nxt, cover=cover)
                    kit.flash("Курс жаңартылды. Жоспардағы сабақтар да жаңарды.")
                else:
                    courses.create_course(uid, title, org, url, days, start.strftime("%H:%M"), int(dur), int(total),
                                          int(done), stage, nxt, cover)
                    kit.flash("Курс қосылды және жоспарға енді.")
                st.session_state.pop("course_edit", None)
                st.rerun()
            except ValueError as e:
                st.error(str(e))


def render() -> None:
    uid = session.current_uid()
    kit.show_flash()
    st.title("Курстарым")
    st.caption("Сабақ саны оқушының белгілеуі бойынша есептеледі. NAZARDA курс платформасымен байланыспаған.")
    rows = courses.list_courses(uid, uid)
    if not rows:
        kit.empty("Әзірге курс жоқ.", "Төменде алғашқы курсыңды қос.")
    cols = st.columns(2, gap="medium")
    for k, c in enumerate(rows):
        with cols[k % 2], st.container(border=True, key=f"card_course_{c['id']}"):
            st.html(kit.image_tag(c["cover"]) if c["cover"].startswith("https://") else kit.cover_svg(c["title"]))
            days = ", ".join(WEEKDAYS_SHORT[int(x)] for x in c["weekdays"].split(",") if x) or "кесте жоқ"
            nm = courses.next_meeting(c)
            st.html(f'<p class="nz-h" style="margin-top:8px">{kit.esc(c["title"])}</p>'
                    f'<p class="nz-muted" style="margin:0">{kit.esc(c["organizer"] or "Ұйымдастырушы көрсетілмеген")}'
                    f' · {kit.esc(days)} {kit.esc(c["start_time"])}</p>')
            st.html(f'<p class="nz-title" style="margin:10px 0 4px">'
                    f'{kit.esc(k_of_n(c["completed_lessons"], c["total_lessons"], "сабақтың", "аяқталды"))}</p>'
                    + kit.progress_bar(c["completed_lessons"] / c["total_lessons"]))
            st.caption("Оқушының белгілеуі бойынша")
            info = []
            if nm:
                info.append(f"Келесі кездесу: {fmt_date(nm[0], True)}, {nm[1]}")
            if c["stage"]:
                info.append(f"Кезең: {c['stage']}")
            if c["next_task"]:
                info.append(f"Келесі тапсырма: {c['next_task']}")
            for line in info:
                st.write(line)
            b1, b2, b3, b4 = st.columns(4)
            if c["url"]:
                b1.link_button("Жалғастыру", c["url"], type="primary", width="stretch")
            b2.button("+1 сабақ", key=f"cp_{c['id']}", on_click=courses.change_progress, args=(uid, c["id"], 1),
                      width="stretch", disabled=c["completed_lessons"] >= c["total_lessons"])
            b3.button("−1", key=f"cm_{c['id']}", on_click=courses.change_progress, args=(uid, c["id"], -1),
                      width="stretch", disabled=c["completed_lessons"] == 0)
            if b4.button("Өзгерту", key=f"ce_{c['id']}", width="stretch"):
                st.session_state["course_edit"] = c["id"]
            if st.session_state.get("course_edit") == c["id"]:
                _form(uid, c)
                if st.button("Курсты өшіру", key=f"cd_{c['id']}", type="tertiary"):
                    st.session_state["course_del"] = c["id"]
                if st.session_state.get("course_del") == c["id"]:
                    st.warning("Курс пен оның жоспардағы сабақтары өшеді. Растайсың ба?")
                    if st.button("Иә, өшіру", key=f"cdo_{c['id']}", type="primary"):
                        courses.delete_course(uid, c["id"])
                        st.session_state.pop("course_edit", None)
                        kit.flash("Курс өшірілді.")
                        st.rerun()
    with st.expander("Жаңа курс қосу", icon=":material/add:", expanded=not rows):
        _form(uid)
