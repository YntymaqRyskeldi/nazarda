"""Мұғалім кабинеті. Мұғалім тек өзіне тағайындалған сынып пен пәннің деректерін көреді және өзгертеді."""
from __future__ import annotations

from datetime import datetime, time, timedelta

import pandas as pd
import streamlit as st

from core import access
from core.fmt import WEEKDAYS, fmt_date, fmt_dt, today
from services import alerts, calc, messaging, study
from ui import kit, messages, nav, session


def _pair_picker(uid: int, key: str):
    pairs = access.teacher_pairs(uid)
    if not pairs:
        kit.empty("Сізге сынып тағайындалмаған.")
        st.stop()
    labels = {k: f"{p['class_name']} · {p['subject_name']}" for k, p in enumerate(pairs)}
    k = st.selectbox("Сынып және пән", list(labels), format_func=labels.get, key=key)
    return pairs[k]


def desk() -> None:
    uid = session.current_uid()
    u = session.current_user()
    kit.show_flash()
    st.html(f'<p class="nz-greet">Қайырлы күн, {kit.esc(u["name"])}!</p>'
            f'<p class="nz-sub">{kit.esc(fmt_date(today(), True))} · байланыс уақыты: '
            f'{kit.esc(messaging.hours_text(uid))} {kit.demo_badge()}</p>')
    pend = study.pending_reviews(uid)
    dlg = [d for d in messaging.dialogs_for(uid) if d["status"] in ("new", "in_review")]
    unread = messaging.unread_count(uid)
    deferred = messaging.deferred_count(uid)
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Тексеруді күтетін жауаптар", len(pend))
    c2.metric("Ашық сұрақтар", len(dlg))
    c3.metric("Оқылмаған хабарлар", unread)
    c4.metric("Кейінге қалған хабарлар", deferred,
              help="Байланыс уақытынан тыс жазылған хабарлар. Олар сақталған, ескерту кейін шығады.")
    c1, c2 = st.columns(2, gap="medium")
    with c1, st.container(border=True, key="card_t_rev"):
        kit.h("Тексеру кезегі")
        for s in pend[:5]:
            st.write(f"• {s['student_name']} · {s['class_name']} · {s['title']} ({fmt_dt(s['submitted_at'])})")
        if not pend:
            st.caption("Кезек бос.")
        nav.link("t_review", "Тексеруге өту", icon=":material/fact_check:")
    with c2, st.container(border=True, key="card_t_q"):
        kit.h("Жаңа сұрақтар")
        for d in dlg[:5]:
            st.write(f"• {d['title']} — {messaging.STATUS_LABEL[d['status']]}")
        if not dlg:
            st.caption("Ашық сұрақ жоқ.")
        nav.link("t_questions", "Сұрақтарға өту", icon=":material/forum:")
    with st.container(border=True, key="card_t_alerts"):
        kit.h("Ерте ескертулер", "Сіздің пәндеріңіз бойынша")
        found = False
        for p in access.teacher_pairs(uid):
            for s in study.class_students(uid, p["class_id"]):
                for a in alerts.active_alerts(s["id"]):
                    if a["subject_id"] == p["subject_id"]:
                        found = True
                        kit.warn(f"{s['full_name']} · {a['subject_name']}: {a['details']['reason']}")
        if not found:
            st.caption("Белсенді ескерту жоқ.")


def classes() -> None:
    uid = session.current_uid()
    kit.show_flash()
    st.title("Сыныптар")
    p = _pair_picker(uid, "t_cls_pair")
    studs = study.class_students(uid, p["class_id"])
    act = {s["id"]: any(a["subject_id"] == p["subject_id"] for a in alerts.active_alerts(s["id"])) for s in studs}
    rows = []
    for s in studs:
        res = study.results(uid, s["id"], p["subject_id"])
        val = calc.weighted_percent([calc.Work(r["score"], r["max_score"], r["weight"]) for r in res])
        k, n = study.completion_share(uid, s["id"], p["subject_id"])
        rows.append({"Оқушы": s["full_name"], "Есептелген пайыз": None if val is None else round(val),
                     "Жұмыс саны": len(res), "Тапсырмалар жіберілді": f"{k}/{n}" if n else "—",
                     "Ерте ескерту": "Иә" if act[s["id"]] else "—"})
    st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch",
                 column_config={"Есептелген пайыз": st.column_config.ProgressColumn(min_value=0, max_value=100,
                                                                                    format="%d%%")})
    if not studs:
        return
    sid = st.selectbox("Оқушы", [s["id"] for s in studs], format_func={s["id"]: s["full_name"] for s in studs}.get,
                       key="t_cls_student")
    res = study.results(uid, sid, p["subject_id"])
    c1, c2 = st.columns([1.4, 1], gap="medium")
    with c1, st.container(border=True, key="card_t_res"):
        kit.h("Нәтижелер")
        if res:
            from views.student.study import results_table
            results_table(res)
            with st.expander("Нәтижені түзету немесе өшіру"):
                rid = st.selectbox("Нәтиже", [r["id"] for r in res],
                                   format_func={r["id"]: f"{fmt_date(r['date'])} · {r['topic']}" for r in res}.get)
                r = next(x for x in res if x["id"] == rid)
                with st.form(f"tre_{rid}", border=False):
                    a, b, c = st.columns(3)
                    sc = a.number_input("Балл", 0, 1000, r["score"])
                    mx = b.number_input("Ең жоғары балл", 1, 1000, r["max_score"])
                    w = c.number_input("Салмағы", 1, 10, r["weight"])
                    cm = st.text_input("Пікір", value=r["comment"])
                    b1, b2 = st.columns(2)
                    if b1.form_submit_button("Сақтау", type="primary"):
                        if kit.run_action(study.update_result, uid, rid, int(sc), int(mx), int(w), cm,
                                          ok="Нәтиже түзетілді. Ескерту қайта есептелді."):
                            st.rerun()
                    if b2.form_submit_button("Өшіру"):
                        st.session_state["t_res_del"] = rid
                if st.session_state.get("t_res_del") == rid:
                    st.warning("Нәтиже өшіріледі. Растайсыз ба?")
                    if st.button("Иә, өшіру", type="primary", key=f"trd_{rid}"):
                        st.session_state.pop("t_res_del")
                        kit.run_action(study.delete_result, uid, rid, ok="Өшірілді.")
                        st.rerun()
        else:
            kit.empty("Нәтиже жоқ.")
    with c2, st.container(border=True, key="card_t_grade"):
        kit.h("Баға қою", "Тапсырмасыз жұмыс үшін (мысалы, сабақтағы жұмыс немесе БЖБ)")
        with st.form("t_grade", clear_on_submit=True, border=False):
            topic = st.text_input("Тақырып")
            kind = st.selectbox("Бағалау түрі", study.ASSESSMENT_TYPES)
            a, b, c = st.columns(3)
            sc = a.number_input("Балл", 0, 1000, 8)
            mx = b.number_input("Ең жоғары", 1, 1000, 10)
            w = c.number_input("Салмағы", 1, 10, 1)
            d = st.date_input("Күні", value=today(), format="DD.MM.YYYY")
            cm = st.text_input("Пікір (міндетті емес)")
            if st.form_submit_button("Бағаны сақтау", type="primary"):
                if not topic.strip():
                    st.error("Тақырыпты жазыңыз.")
                elif kit.run_action(study.add_result, uid, sid, p["subject_id"], topic, kind, int(sc), int(mx), int(w),
                                    d.isoformat(), cm, ok="Баға сақталды."):
                    st.rerun()


def assignments() -> None:
    uid = session.current_uid()
    kit.show_flash()
    st.title("Тапсырмалар")
    with st.expander("Жаңа тапсырма", icon=":material/add:"):
        p = _pair_picker(uid, "t_as_pair")
        with st.form("t_new_as", clear_on_submit=True, border=False):
            title = st.text_input("Атауы")
            desc = st.text_area("Сипаттама", height=90)
            a, b = st.columns(2)
            topic = a.text_input("Тақырып")
            kind = b.selectbox("Бағалау түрі", study.ASSESSMENT_TYPES, index=2)
            a, b, c = st.columns(3)
            due = a.date_input("Мерзімі", value=today() + timedelta(days=3), format="DD.MM.YYYY")
            mx = b.number_input("Ең жоғары балл", 1, 1000, 10)
            w = c.number_input("Салмағы", 1, 10, 1)
            if st.form_submit_button("Жариялау", type="primary"):
                if kit.run_action(study.create_assignment, uid, p["class_id"], p["subject_id"], title, desc, topic, kind,
                                  due.isoformat(), int(mx), int(w), ok="Тапсырма жарияланды."):
                    st.rerun()
    rows = study.teacher_assignments(uid)
    if not rows:
        kit.empty("Тапсырма жоқ.")
    for a in rows:
        with st.container(border=True, key=f"card_tas_{a['id']}"):
            st.html(f'<div class="nz-title">{kit.esc(a["title"])}</div><div class="nz-muted">{kit.esc(a["class_name"])} · '
                    f'{kit.esc(a["subject_name"])} · мерзімі {kit.esc(fmt_date(a["due_date"]))} · {kit.esc(a["assessment_type"])}'
                    f'</div>' + kit.progress_bar(a["n_sub"] / a["n_students"] if a["n_students"] else 0))
            st.caption(f"Жіберді: {a['n_sub']} / {a['n_students']} · тексерілді: {a['n_rev']}")


def review() -> None:
    uid = session.current_uid()
    kit.show_flash()
    st.title("Тексеру")
    rows = study.pending_reviews(uid)
    if not rows:
        kit.empty("Тексеруді күтетін жауап жоқ.")
    for s in rows:
        with st.container(border=True, key=f"card_rev_{s['id']}"):
            st.html(f'<div class="nz-title">{kit.esc(s["student_full"])} · {kit.esc(s["title"])}</div>'
                    f'<div class="nz-muted">{kit.esc(s["class_name"])} · {kit.esc(s["subject_name"])} · жіберілді '
                    f'{kit.esc(fmt_dt(s["submitted_at"]))}</div>')
            st.write(s["body"])
            with st.form(f"rev_{s['id']}", border=False):
                a, b = st.columns([1, 3])
                sc = a.number_input(f"Балл (0–{s['max_score']})", 0, s["max_score"], s["max_score"])
                cm = b.text_input("Пікір")
                if st.form_submit_button("Тексерілді деп белгілеу", type="primary"):
                    if kit.run_action(study.review, uid, s["id"], int(sc), cm, ok="Жауап тексерілді, нәтиже жазылды."):
                        st.rerun()


def questions() -> None:
    uid = session.current_uid()
    kit.show_flash()
    st.title("Сұрақтар")
    deferred = messaging.deferred_count(uid)
    if deferred:
        st.info(f"Байланыс уақытынан тыс {deferred} хабар келді. Олар сақталған; ескерту байланыс уақыты "
                "басталғанда шығады.", icon=":material/schedule:")
    flt = st.segmented_control("Күйі", ["Ашық", "Барлығы"], default="Ашық", key="t_q_flt", required=True)
    rows = messaging.dialogs_for(uid)
    if flt == "Ашық":
        rows = [d for d in rows if d["status"] in ("new", "in_review")]
    messages.inbox(uid, rows, "t", teacher_controls=True)


def announcements() -> None:
    uid = session.current_uid()
    kit.show_flash()
    st.title("Хабарландырулар")
    st.caption("Хабарландыру сыныптың барлық оқушылары мен олардың ата-аналарына қолданба ішінде көрінеді.")
    with st.container(border=True, key="card_t_ann"):
        p = _pair_picker(uid, "t_ann_pair")
        with st.form("t_ann", clear_on_submit=True, border=False):
            title = st.text_input("Тақырып")
            body = st.text_area("Мәтін", height=100)
            if st.form_submit_button("Жариялау", type="primary"):
                if kit.run_action(messaging.post_announcement, uid, p["class_id"], p["subject_id"], title, body,
                                  kit.token("t_ann"), ok="Жарияланды."):
                    kit.renew_token("t_ann")
                    st.rerun()
    messages.announcements(messaging.announcements_for(uid))


def hours() -> None:
    uid = session.current_uid()
    kit.show_flash()
    st.title("Байланыс уақыты")
    st.caption("Осы уақыттан тыс жазылған хабарлар сақталады, бірақ сізге ескерту байланыс уақыты басталғанда шығады. "
               "Жазушыға байланыс уақыты көрсетіледі.")
    cur = messaging.office_hours(uid)
    with st.form("t_hours"):
        vals = {}
        for wd in range(7):
            a, b, c = st.columns([1.2, 1, 1], vertical_alignment="bottom")
            on = a.checkbox(WEEKDAYS[wd].capitalize(), value=wd in cur, key=f"oh_on_{wd}")
            s = b.time_input("Басталуы", value=datetime.strptime(cur[wd][0], "%H:%M").time() if wd in cur else time(9, 0),
                             step=900, key=f"oh_s_{wd}")
            e = c.time_input("Аяқталуы", value=datetime.strptime(cur[wd][1], "%H:%M").time() if wd in cur else time(17, 0),
                             step=900, key=f"oh_e_{wd}")
            vals[wd] = (s.strftime("%H:%M"), e.strftime("%H:%M")) if on else None
        if st.form_submit_button("Сақтау", type="primary"):
            if kit.run_action(messaging.set_office_hours, uid, vals, ok="Байланыс уақыты сақталды."):
                st.rerun()
    st.write(f"Қазіргі кесте: **{messaging.hours_text(uid)}**")
