"""«Оқуым»: пәндер, тапсырмалар, калькулятор, қателер, жаттығу."""
from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from core import access
from core.fmt import fmt_date, fmt_dt, relative_day
from services import alerts, calc, study
from ui import kit, nav, session

TYPE_COLORS = ["#4F46E5", "#0F766E", "#A5B4FC", "#5EEAD4", "#94A3B8"]


def results_table(rows) -> None:
    df = pd.DataFrame([{
        "Күні": fmt_date(r["date"]), "Тақырып": r["topic"], "Бағалау түрі": r["assessment_type"],
        "Балл": f"{r['score']} / {r['max_score']}", "Салмағы": r["weight"],
        "Пайыз": round(r["score"] * 100 / r["max_score"]), "Мұғалім пікірі": r["comment"] or "—"} for r in rows])
    st.dataframe(df, hide_index=True, width="stretch",
                 column_config={"Пайыз": st.column_config.ProgressColumn("Пайыз", min_value=0, max_value=100,
                                                                         format="%d%%")})


def dynamics_chart(rows, height: int = 280) -> None:
    """Тек салыстырмалы жұмыстар бір сызықта: әр бағалау түрі — бөлек сызық."""
    fig = go.Figure()
    types = sorted({r["assessment_type"] for r in rows})
    for k, t in enumerate(types):
        rr = [r for r in rows if r["assessment_type"] == t]
        fig.add_trace(go.Scatter(x=[r["date"] for r in rr], y=[r["score"] * 100 / r["max_score"] for r in rr],
                                 mode="lines+markers", name=t, line=dict(color=TYPE_COLORS[k % 5], width=3),
                                 marker=dict(size=9), text=[r["topic"] for r in rr],
                                 hovertemplate="%{text}<br>%{y:.0f}%<extra>" + t + "</extra>"))
    fig.update_yaxes(range=[0, 105], title_text="Пайыз, %")
    fig.update_xaxes(title_text="Күні", tickformat="%d.%m")
    st.plotly_chart(kit.style_fig(fig, height), config=kit.PLOTLY_CFG, width="stretch")
    st.caption("Әр сызық — бір бағалау түрі (мысалы, тек БЖБ-лар). Әртүрлі жұмыстар бір сызыққа араластырылмайды.")


def three_measures(uid: int, student_id: int, subject_id: int, rows, show_self: bool = True) -> None:
    """Үш көрсеткіш бөлек: бағалау нәтижесі, тапсырмаларды орындау үлесі, өзін-өзі бағалау."""
    val = calc.weighted_percent([calc.Work(r["score"], r["max_score"], r["weight"]) for r in rows])
    k, n = study.completion_share(uid, student_id, subject_id)
    c1, c2, c3 = st.columns(3)
    c1.metric("Бағалау нәтижесі", "—" if val is None else f"{val:.0f}%",
              help="Мұғалім енгізген жұмыстардың салмақпен есептелген пайызы.")
    c2.metric("Тапсырмалар жіберілді", f"{k} / {n}" if n else "—",
              help="Мерзімі келген тапсырмалардың қаншасына жауап жіберілді. Бағаға қатысы жоқ.")
    if show_self:
        sa = study.self_assessments(uid, student_id, subject_id)
        c3.metric("Өзін-өзі бағалау", f"{sa[-1]['value']} / 5" if sa else "—",
                  help="Оқушының өз сезімі. Ресми бағаға кірмейді.")


def _subjects_tab(uid: int) -> None:
    subs = study.subjects_for_student(uid)
    ids = [s["id"] for s in subs]
    if st.session_state.get("study_subject") not in ids:
        st.session_state["study_subject"] = ids[0]
    sid = st.pills("Пән", ids, format_func={s["id"]: s["name"] for s in subs}.get, key="study_subject",
                   required=True)
    me = access.user(uid)
    teacher = study.teacher_for(me["class_id"], sid)
    rows = study.results(uid, uid, sid)
    for a in alerts.active_alerts(uid):
        if a["subject_id"] == sid:
            kit.warn(f"Ерте ескерту: {a['details']['reason']} Бұл себебін анықтамайды — "
                     "мұғаліммен немесе ата-анаңмен ақылдасуға болады.")
    with st.container(border=True, key="card_subject_main"):
        kit.h(next(s["name"] for s in subs if s["id"] == sid),
              f"Мұғалім: {teacher['name']}" if teacher else None)
        three_measures(uid, uid, sid, rows)
        if rows:
            dynamics_chart(rows)
            results_table(rows)
        else:
            kit.empty("Бұл пән бойынша нәтиже әлі жоқ.")
    c1, c2 = st.columns(2, gap="medium")
    with c1, st.container(border=True, key="card_self"):
        kit.h("Өзін-өзі бағалау", "Тақырыпты қаншалықты түсінгеніңді өзің белгіле (1–5).")
        with st.form("self_form", border=False):
            v = st.slider("Түсінуім", 1, 5, 3)
            note = st.text_input("Қысқа ескертпе (міндетті емес)")
            if st.form_submit_button("Сақтау"):
                kit.run_action(study.add_self_assessment, uid, sid, v, note, ok="Сақталды.")
                st.rerun()
    with c2, st.container(border=True, key="card_ask"):
        kit.h("Көмек керек пе?", "Мұғалімге немесе ата-анаңа нақты сұрақ жібер.")
        st.button("Көмек сұрау", icon=":material/help:", on_click=nav.go, args=("inbox",),
                  kwargs={"inbox_compose": {"subject_id": sid, "topic": "Тақырыпты түсіндіріп берші"}})


def _assignments_tab(uid: int) -> None:
    focus = st.session_state.pop("study_focus", None)
    rows = study.assignments_for_student(uid, uid)
    open_rows = [a for a in rows if not a["submission_id"]]
    other = [a for a in rows if a["submission_id"]]
    st.caption(f"Ашық: {len(open_rows)} · Жіберілген: {len(other)}")
    if not rows:
        kit.empty("Тапсырма жоқ.")
    for a in open_rows + sorted(other, key=lambda r: r["submitted_at"] or "", reverse=True):
        state = study.assignment_state(a)
        tone = {"Тексерілді": "teal", "Жіберілді, тексеруде": "", "Мерзімі өтті": "amber"}.get(state, "grey")
        with st.expander(f"{a['subject_name']} · {a['title']} — {fmt_date(a['due_date'])} ({relative_day(a['due_date'])})",
                         expanded=(a["id"] == focus)):
            st.html(kit.badge(state, tone) + kit.badge(a["assessment_type"], "grey")
                    + f'<span class="nz-muted">Ең жоғары балл: {a["max_score"]}, салмағы: {a["weight"]}</span>')
            if a["description"]:
                st.write(a["description"])
            if a["sub_status"] == "reviewed":
                st.success(f"Нәтиже: {a['score']} / {a['r_max']}. Мұғалім пікірі: {a['teacher_comment'] or '—'}",
                           icon=":material/task_alt:")
                st.caption(f"Сенің жауабың: {a['sub_body']}")
            else:
                if a["sub_status"] == "submitted":
                    st.info(f"Жауап {fmt_dt(a['submitted_at'])} жіберілді. Мұғалім тексергенше өзгертуге болады.",
                            icon=":material/schedule_send:")
                with st.form(f"sub_{a['id']}", border=False):
                    body = st.text_area("Жауабың", value=a["sub_body"] or "", height=120)
                    if st.form_submit_button("Жауапты жіберу" if not a["sub_status"] else "Жауапты жаңарту",
                                             type="primary"):
                        if kit.run_action(study.submit, uid, a["id"], body, ok="Жауап мұғалімге жіберілді."):
                            st.rerun()
            st.button("Мұғалімге сұрақ қою", key=f"askq_{a['id']}", type="tertiary", on_click=nav.go,
                      args=("inbox",), kwargs={"inbox_compose": {"subject_id": a["subject_id"],
                                                                 "assignment_id": a["id"], "title": a["title"]}})


def _calc_tab(uid: int) -> None:
    kit.warn("Үлгілік есептеу. Ресми тоқсандық баға емес.")
    subs = study.subjects_for_student(uid)
    sid = st.selectbox("Пән", [s["id"] for s in subs], format_func={s["id"]: s["name"] for s in subs}.get,
                       key="calc_subject")
    rows = study.results(uid, uid, sid)
    works = [calc.Work(r["score"], r["max_score"], r["weight"]) for r in rows]
    st.caption("Формула: Σ(балл ÷ ең жоғары балл × 100 × салмақ) ÷ Σ салмақ. Нөл балл да есепке кіреді.")
    c1, c2, c3 = st.columns(3)
    score = c1.number_input("Жаңа жұмыстың баллы", min_value=0, value=8, step=1)
    mx = c2.number_input("Ең жоғары балл", min_value=0, value=10, step=1)
    w = c3.number_input("Салмағы", min_value=0, value=1, step=1)
    try:
        f = calc.forecast(works, calc.Work(int(score), int(mx), int(w)))
    except ValueError as e:
        st.error(str(e), icon=":material/error:")
        return
    m1, m2, m3 = st.columns(3)
    m1.metric("Қазіргі көрсеткіш", "Дерек жоқ" if f.current is None else f"{f.current:.1f}%")
    m2.metric("Болжам", f"{f.forecast:.1f}%")
    m3.metric("Өзгеріс", "—" if f.change is None else f"{f.change:+.1f}", delta=None if f.change is None
              else f"{f.change:+.1f} пайыздық тармақ", delta_color="normal")
    with st.expander("Есептеуге кірген жұмыстар"):
        if rows:
            results_table(rows)
        else:
            st.caption("Бұл пән бойынша енгізілген жұмыс жоқ — болжам тек жаңа жұмыстан тұрады.")
    st.caption("Ресми шектер мен ережелер енгізілмеген: олар мектепке байланысты. Нәтижені мұғаліммен тексер.")


def _mistakes_tab(uid: int) -> None:
    st.caption("Қателерді жазып отыру — оларды қайталамаудың қарапайым жолы. Бұл тізім тек өзіңе көрінеді.")
    subs = study.subjects_for_student(uid)
    with st.form("mist_add", clear_on_submit=True):
        c1, c2 = st.columns([1, 2])
        sid = c1.selectbox("Пән", [s["id"] for s in subs], format_func={s["id"]: s["name"] for s in subs}.get)
        topic = c2.text_input("Тақырып")
        note = st.text_area("Не қате болды және қалай дұрыс?", height=80)
        if st.form_submit_button("Қосу"):
            if kit.run_action(study.add_mistake, uid, sid, topic, note, ok="Қосылды."):
                st.rerun()
    rows = study.mistakes(uid, uid)
    if not rows:
        kit.empty("Әзірге жазба жоқ.")
    for m in rows:
        c1, c2 = st.columns([5, 1], vertical_alignment="center")
        cls = "nz-title done" if m["fixed"] else "nz-title"
        c1.html(f'<div class="{cls}">{kit.esc(m["subject_name"])}: {kit.esc(m["topic"])}</div>'
                f'<div class="nz-muted">{kit.esc(m["note"])}</div>')
        c2.button("Қайта ашу" if m["fixed"] else "Түзеттім", key=f"mx_{m['id']}",
                  on_click=study.toggle_mistake, args=(uid, m["id"]))


def _practice_tab(uid: int) -> None:
    st.caption("Дайын сұрақтар түсіндірмемен. Нәтиже ресми бағаға әсер етпейді.")
    subs = [s for s in study.subjects_for_student(uid) if study.practice_questions(s["id"])]
    if not subs:
        kit.empty("Жаттығу сұрақтары әзірге жоқ.")
        return
    sid = st.selectbox("Пән", [s["id"] for s in subs], format_func={s["id"]: s["name"] for s in subs}.get,
                       key="pr_subject")
    qs = study.practice_questions(sid)
    with st.form(f"pr_{sid}"):
        answers = {}
        for q in qs:
            opts = q["options"].split("|")
            answers[q["id"]] = st.radio(q["question"], range(len(opts)), format_func=lambda k, o=opts: o[k],
                                        index=None, key=f"pq_{q['id']}")
        sent = st.form_submit_button("Тексеру", type="primary")
    if sent:
        if any(v is None for v in answers.values()):
            st.warning("Барлық сұраққа жауап бер.")
            return
        correct = sum(1 for q in qs if answers[q["id"]] == q["correct"])
        study.record_practice(uid, sid, correct, len(qs), kit.token(f"pr_{sid}"))
        kit.renew_token(f"pr_{sid}")
        st.success(f"{len(qs)} сұрақтың {correct}-не дұрыс жауап бердің.")
        for q in qs:
            ok = answers[q["id"]] == q["correct"]
            st.markdown(f"**{'Дұрыс' if ok else 'Қате'}:** {q['question']}")
            st.caption(q["explanation"])


def render() -> None:
    uid = session.current_uid()
    kit.show_flash()
    st.title("Оқуым")
    tabs = ["Пәндер", "Тапсырмалар", "Калькулятор", "Қателерім", "Жаттығу"]
    if st.session_state.get("study_focus"):
        st.session_state["study_tab"] = "Тапсырмалар"
    elif st.session_state.pop("study_jump_subject", False):
        st.session_state["study_tab"] = "Пәндер"
    st.session_state.setdefault("study_tab", "Пәндер")
    t = st.segmented_control("Бөлім", tabs, key="study_tab", required=True, label_visibility="collapsed")
    {"Пәндер": _subjects_tab, "Тапсырмалар": _assignments_tab, "Калькулятор": _calc_tab,
     "Қателерім": _mistakes_tab, "Жаттығу": _practice_tab}[t](uid)
