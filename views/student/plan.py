"""«Күн жоспарым»: күн, апта, қиылысулар, ауыстыру, «Жеңіл күн», күнді қорытындылау, апталық шолу."""
from __future__ import annotations

from datetime import datetime, time, timedelta

import streamlit as st

from core.fmt import WEEKDAYS, fmt_date, k_of_n, today, week_start
from services import family, planner
from ui import kit, nav, session, timeline


def day_review(uid: int, items: list[planner.Item]) -> None:
    """Күнді қорытындылау. Жеке жазба ата-анаға автоматты түрде берілмейді."""
    day = today().isoformat()
    done = [i for i in items if i.status == "done" and i.tracked]
    open_ = [i for i in items if i.kind == "event" and i.status == "planned" and i.movable]
    c1, c2 = st.columns(2)
    with c1:
        st.markdown("**Орындалды**")
        if done:
            for i in done:
                st.write(f"• {i.title}")
        else:
            st.caption("Әзірге белгіленген іс жоқ.")
    with c2:
        st.markdown("**Ертеңге ауыстыруға болады**")
        if open_:
            pick = st.multiselect("Ауыстыратын істер", [i.key for i in open_],
                                  format_func={i.key: f"{i.start} {i.title}" for i in open_}.get, key="rv_move",
                                  label_visibility="collapsed", placeholder="Таңдаңыз")
            if st.button("Таңдалғанды ертеңге ауыстыру", disabled=not pick, key="rv_go"):
                tm = (today() + timedelta(days=1)).isoformat()
                for i in open_:
                    if i.key in pick:
                        planner.move_once(uid, i.event_id, i.orig_date, tm, i.start)
                kit.flash(f"{len(pick)} іс ертеңге ауыстырылды.")
                st.rerun()
        else:
            st.caption("Ауыстыратын ашық іс жоқ.")
    with st.form("day_review", border=False):
        note = st.text_area("Бүгін не жақсы болды?", value=family.day_review(uid, day), max_chars=500,
                            placeholder="Бір-екі сөйлем жеткілікті.")
        st.caption("Бұл жазба тек өзіңе көрінеді. Ата-анаға автоматты түрде берілмейді.")
        if st.form_submit_button("Сақтау"):
            family.save_day_review(uid, day, note)
            kit.flash("Сақталды.")
            st.rerun()


@st.dialog("Істі ауыстыру")
def move_dialog(uid: int, item_key: str, suggest: str | None = None) -> None:
    day = st.session_state["plan_day"]
    item = next((i for i in planner.day_items(uid, uid, day) if i.key == item_key), None)
    if not item:
        st.error("Іс табылмады.")
        return
    st.write(f"**{item.title}** — {fmt_date(day)}, {item.start}")
    scope = "Тек осы күн"
    if item.recurring:
        scope = st.radio("Қай күндерге?", ["Тек осы күн", "Келесі күндерге де"], horizontal=True)
    default_t = datetime.strptime(suggest or item.start, "%H:%M").time()
    new_t = st.time_input("Жаңа уақыт", value=default_t, step=900)
    new_d = st.date_input("Жаңа күн", value=day, format="DD.MM.YYYY", disabled=scope != "Тек осы күн")
    if suggest:
        st.caption(f"Бос уақыт ұсынысы: {suggest}. Кесте автоматты түрде өзгертілмейді — шешім сенде.")
    if st.button("Ауыстыру", type="primary"):
        try:
            if scope == "Тек осы күн":
                planner.move_once(uid, item.event_id, item.orig_date, new_d.isoformat(), new_t.strftime("%H:%M"))
            else:
                planner.move_series(uid, item.event_id, day.isoformat(), new_t.strftime("%H:%M"))
            kit.flash("Іс ауыстырылды.")
            st.rerun()
        except ValueError as e:
            st.error(str(e))


def _add_form(uid: int, day) -> None:
    prefill = st.session_state.pop("plan_prefill", "")
    with st.form("plan_add", clear_on_submit=True):
        title = st.text_input("Атауы", value=prefill)
        c1, c2, c3 = st.columns(3)
        cat = c1.selectbox("Санаты", planner.CATEGORIES, index=planner.CATEGORIES.index("Басқа"))
        start = c2.time_input("Басталуы", value=time(18, 0), step=900)
        dur = c3.number_input("Ұзақтығы, мин", 5, 600, 45, 5)
        c1, c2 = st.columns(2)
        d0 = c1.date_input("Күні (немесе басталу күні)", value=day, format="DD.MM.YYYY")
        rep = c2.multiselect("Қайталау", list(range(7)), format_func=lambda w: WEEKDAYS[w],
                             placeholder="Бір реттік")
        c1, c2, c3 = st.columns(3)
        tracked = c1.checkbox("Орындалуда есептелсін", True)
        optional = c2.checkbox("«Жеңіл күнде» ауыстыруға болады", True)
        shared = c3.checkbox("Ата-анаға көрінсін", False)
        if st.form_submit_button("Қосу", type="primary"):
            try:
                planner.create_event(uid, uid, title, cat, start.strftime("%H:%M"), int(dur), d0.isoformat(), rep,
                                     tracked, optional, shared)
                kit.flash("Іс қосылды.")
                st.rerun()
            except ValueError as e:
                st.error(str(e))


def _day_tab(uid: int) -> None:
    if "plan_day" not in st.session_state:
        st.session_state.plan_day = today()
    def shift(k: int | None):
        st.session_state.plan_day = today() if k is None else st.session_state.plan_day + timedelta(days=k)

    c0, c1, c2, c3 = st.columns([1, 2, 1, 1], vertical_alignment="bottom")
    c0.button("Алдыңғы", icon=":material/chevron_left:", width="stretch", on_click=shift, args=(-1,))
    c1.date_input("Күн", key="plan_day", format="DD.MM.YYYY")
    c2.button("Келесі", icon=":material/chevron_right:", width="stretch", on_click=shift, args=(1,))
    c3.button("Бүгін", width="stretch", on_click=shift, args=(None,))
    day = st.session_state.plan_day
    items = planner.day_items(uid, uid, day)
    done, total = planner.progress(items)

    left, right = st.columns([1.6, 1], gap="medium")
    with left, st.container(border=True, key="card_plan_day"):
        kit.h(fmt_date(day, True), k_of_n(done, total, "істің", "орындалды"))
        for a, b in planner.overlaps(items):
            mover = b if b.kind == "event" and b.movable else a
            if mover.kind != "event":
                kit.warn(f"Уақыт қиылысады: «{a.title}» ({a.start}–{a.end}) және «{b.title}» ({b.start}–{b.end}).")
                continue
            slot = planner.free_slot(items, mover.duration, after=max(a.end, b.end), ignore_key=mover.key)
            kit.warn(f"Уақыт қиылысады: «{a.title}» ({a.start}–{a.end}) және «{b.title}» ({b.start}–{b.end})."
                     + (f" Ұсыныс: «{mover.title}» ісін {slot} уақытына ауыстыру." if slot else ""))
            if st.button(f"«{mover.title}» ісін ауыстыру", key=f"ov_{a.key}_{b.key}"):
                move_dialog(uid, mover.key, slot)
        if items:
            timeline.render(uid, uid, items, True, "plan", on_open_study=lambda aid: nav.go("study", study_focus=aid),
                            show_menu=True)
        else:
            kit.empty("Бұл күнге іс жоқ.", "Төмендегі форма арқылы қосуға болады.")
    with right:
        with st.container(border=True, key="card_plan_edit"):
            kit.h("Өзгерту")
            events = [i for i in items if i.kind == "event"]
            if events:
                key = st.selectbox("Іс", [i.key for i in events],
                                   format_func={i.key: f"{i.start} · {i.title}" for i in events}.get, key="plan_pick")
                it = next(i for i in events if i.key == key)
                b1, b2 = st.columns(2)
                if b1.button("Ауыстыру", key="plan_mv", width="stretch"):
                    move_dialog(uid, key)
                if it.source != "course" and b2.button("Өшіру", key="plan_del", width="stretch",
                                                         help="Қайталанатын болса, барлық күндері өшеді."):
                    st.session_state["confirm_del"] = it.event_id
                if st.session_state.get("confirm_del") == it.event_id:
                    st.warning("Бұл іс барлық күндерден өшеді. Растайсың ба?")
                    if st.button("Иә, өшіру", type="primary", key="plan_del_ok"):
                        kit.run_action(planner.delete_event, uid, it.event_id, ok="Өшірілді.")
                        st.session_state.pop("confirm_del", None)
                        st.rerun()
                if it.source == "course":
                    st.caption("Курс сабақтарының кестесі «Курстарым» бөлімінде өзгертіледі.")
            else:
                st.caption("Өзгертуге болатын іс жоқ.")
        with st.container(border=True, key="card_light"):
            kit.h("Жеңіл күн", "Басты істерді таңда — қалған міндетті емес істер ертеңге ауысады.")
            movable = [i for i in items if i.kind == "event" and i.movable and i.status == "planned"]
            if movable:
                keep = st.multiselect("Бүгін қалатын басты істер", [i.key for i in movable],
                                      format_func={i.key: f"{i.start} · {i.title}" for i in movable}.get,
                                      key="light_keep", placeholder="Таңдаңыз")
                st.caption("Мектеп сабақтары мен тапсырма мерзімдері өзгермейді.")
                if st.button("Жеңіл күнді қосу", key="light_go"):
                    n = planner.light_day(uid, uid, day.isoformat(), set(keep))
                    kit.flash(f"{n} іс ертеңге ауыстырылды.")
                    st.rerun()
            else:
                st.caption("Ауыстыруға болатын міндетті емес іс жоқ.")
    with st.expander("Жаңа іс қосу", expanded=bool(st.session_state.get("plan_prefill")), icon=":material/add:"):
        _add_form(uid, day)
    if day == today():
        with st.expander("Күнді қорытындылау", icon=":material/nights_stay:"):
            day_review(uid, items)


def _week_tab(uid: int) -> None:
    start = week_start(today())
    week = planner.week_items(uid, uid, start)
    for day, items in week.items():
        d0 = datetime.fromisoformat(day).date()
        done, total = planner.progress(items)
        with st.container(border=True, key=f"card_wk_{day}"):
            st.html(f'<div class="nz-row" style="justify-content:space-between"><span class="nz-title">'
                    f'{kit.esc(fmt_date(d0, True))}{" · бүгін" if d0 == today() else ""}</span>'
                    f'<span class="nz-muted">{done}/{total}</span></div>')
            line = " · ".join(f"{i.start or '—'} {i.title}" + (" (орындалды)" if i.status == "done" else "")
                              for i in items if i.status != "cancelled")
            st.caption(line or "Бос күн")


def family_review(uid: int, student_id: int) -> None:
    ov = family.weekly_overview(uid, student_id)
    st.caption(f"Кезең: {fmt_date(ov['start'])} — {fmt_date(ov['end'])}. Тек енгізілген деректер көрсетіледі.")
    c1, c2 = st.columns(2, gap="medium")
    with c1, st.container(border=True, key="card_fr_done"):
        kit.h("Жетістіктер")
        rows = [f"{fmt_date(r['date'])} — {r['subject_name']}: {r['score']}/{r['max_score']}" for r in ov["results"]]
        rows += [f"Тапсырма жіберілді: {a['subject_name']}, {a['title']}" for a in ov["submitted"]]
        rows += [f"Мақсат қадамы: {s['title']} ({s['goal_title']})" for s in ov["steps"]]
        rows.append(f"Ортақ күнтізбедегі орындалған істер: {len(ov['done_items'])}")
        for r in rows:
            st.write(f"• {r}")
    with c2, st.container(border=True, key="card_fr_due"):
        kit.h("Жақын мерзімдер")
        if ov["deadlines"]:
            for a in ov["deadlines"]:
                st.write(f"• {fmt_date(a['due_date'])} — {a['subject_name']}: {a['title']}")
        else:
            st.caption("Алдағы 7 күнде ашық тапсырма жоқ.")
        kit.h("Көмек сұраған жерлер")
        if ov["help"]:
            for h in ov["help"]:
                st.write(f"• {h['title']}")
        else:
            st.caption("Ата-анаға көмек сұрауы жоқ.")
    with st.container(border=True, key="card_fr_agree"):
        kit.h("Келесі аптаға келісім")
        ag = ov["agreement"]
        with st.form("agree_form", border=False):
            body = st.text_area("Келісім", value=ag["body"] if ag else "", label_visibility="collapsed",
                                placeholder="Мысалы: сенбіде бірге жоспар құрамыз.")
            if ag:
                st.caption(f"Соңғы өзгерткен: {ag['author_name']}")
            if st.form_submit_button("Келісімді сақтау"):
                if kit.run_action(family.save_agreement, uid, student_id, ov["start"], body, ok="Келісім сақталды."):
                    st.rerun()


def render() -> None:
    uid = session.current_uid()
    kit.show_flash()
    st.title("Күн жоспарым")
    st.caption("Мектеп, тапсырмалар, курстар, спорт және жеке істер — бір жоспарда. "
               "Бұл жоспарлау құралы, тәртіпті бағалау жүйесі емес.")
    t1, t2, t3 = st.tabs(["Күн", "Апта", "Апталық отбасылық шолу"])
    with t1:
        _day_tab(uid)
    with t2:
        _week_tab(uid)
    with t3:
        family_review(uid, uid)
