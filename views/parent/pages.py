"""Ата-ана кабинеті: Шолу, Оқу барысы, Ортақ күнтізбе, Мақсаттар мен қаржы, Хабарламалар.

Ата-ана тек байланысқан баланың деректерін көреді; жоспардан тек бала бөліскен істер,
мақсаттардан тек бөлісілгендер көрінеді. Құқық сервис деңгейінде тексеріледі.
"""
from __future__ import annotations

from datetime import datetime, timedelta

import streamlit as st

from core import access
from core.fmt import fmt_date, fmt_dt, k_of_n, money, to_tiyn, today, week_start
from services import alerts, finance, goals, messaging, planner, study
from ui import kit, messages, nav, session
from views.student.money import history
from views.student.plan import family_review
from views.student.study import dynamics_chart, results_table, three_measures


def _child(uid: int):
    child = session.selected_child(uid)
    if not child:
        kit.empty("Сізге бала байланыстырылмаған.")
        st.stop()
    return child


def _positive_changes(uid: int, child) -> list[str]:
    """Тек деректерден алынған оң фактілер (соңғы жұмыс сол түрдегі алдыңғысынан жоғары)."""
    out = []
    for s in study.subjects_for_student(child["id"]):
        rows = study.results(uid, child["id"], s["id"])
        by_type: dict[str, list] = {}
        for r in rows:
            by_type.setdefault(r["assessment_type"], []).append(r)
        for t, rr in by_type.items():
            if len(rr) >= 2:
                a, b = rr[-2], rr[-1]
                pa, pb = a["score"] * 100 / a["max_score"], b["score"] * 100 / b["max_score"]
                if pb > pa and b["date"] >= (today() - timedelta(days=14)).isoformat():
                    out.append(f"{s['name']} ({t}): {pa:.0f}% → {pb:.0f}%")
    return out


def overview() -> None:
    uid = session.current_uid()
    u = session.current_user()
    kit.show_flash()
    st.html(f'<p class="nz-greet">Сәлеметсіз бе, {kit.esc(u["name"])}!</p>'
            f'<p class="nz-sub">Бүгін — {kit.esc(fmt_date(today(), True))}. {kit.demo_badge()}</p>')
    child = _child(uid)
    cid = child["id"]
    c1, c2, c3 = st.columns(3, gap="medium")
    with c1, st.container(border=True, key="card_p_pos"):
        kit.h("Оң өзгерістер", "Соңғы 2 аптадағы деректер бойынша")
        pos = _positive_changes(uid, child)
        items = planner.day_items(uid, cid, today())
        done, total = planner.progress(items)
        for p in pos:
            st.write(f"• {p}")
        if total:
            st.write(f"• Бүгін ортақ күнтізбеде: {k_of_n(done, total, 'істің', 'орындалды')}")
        if not pos and not total:
            st.caption("Әзірге көрсетерлік жаңа дерек жоқ.")
    with c2, st.container(border=True, key="card_p_due"):
        kit.h("Жақын мерзімдер")
        due = [a for a in study.assignments_for_student(uid, cid)
               if not a["submission_id"] and today().isoformat() <= a["due_date"] <= (today() + timedelta(days=7)).isoformat()]
        for a in due:
            st.write(f"• {fmt_date(a['due_date'])} — {a['subject_name']}: {a['title']}")
        if not due:
            st.caption("Алдағы 7 күнде ашық тапсырма жоқ.")
    with c3, st.container(border=True, key="card_p_attn"):
        kit.h("Назар аударатын жайттар")
        al = alerts.active_alerts(cid)
        for a in al:
            kit.warn(f"{a['subject_name']}: {a['details']['reason']} Бұл себебін анықтамайды — баламен немесе "
                     "мұғаліммен сөйлесуге болады.")
        helps = messaging.dialogs_for(uid, "help", cid)
        for h in helps:
            if h["status"] != "closed":
                st.write(f"• {child['name']} көмек сұрады: «{h['title']}»")
        if not al and not helps:
            st.caption("Қазір ерекше назар аударатын жайт жоқ.")
        nav.link("p_inbox", "Хабарламаларға өту", icon=":material/forum:")
    c1, c2 = st.columns(2, gap="medium")
    with c1, st.container(border=True, key="card_p_goal"):
        kit.h("Бөлісілген мақсат")
        gl = goals.list_goals(uid, cid, ("active",))
        if not gl:
            st.caption("Бала мақсатымен бөліспеген. Бұл — оның жеке шешімі.")
        else:
            g = gl[0]
            st.html(f'<div class="nz-title">{kit.esc(g["title"])}</div>')
            if g["kind"] == "buy":
                plan = goals.buy_plan(g, finance.balance(uid, cid).by_goal.get(g["id"], 0))
                st.html(f'<div class="nz-muted">{money(plan.saved)} / {money(plan.price)}</div>'
                        + kit.progress_bar(plan.percent / 100))
            else:
                k, n = goals.step_progress(g["id"])
                st.html(f'<div class="nz-muted">{kit.esc(k_of_n(k, n, "қадамның", "аяқталды"))}</div>'
                        + kit.progress_bar(k / n if n else 0))
    with c2, st.container(border=True, key="card_p_money"):
        kit.h("Қалта ақша", "Енгізілген деректер бойынша")
        b = finance.balance(uid, cid)
        st.html(f'<div class="nz-num">{money(b.available)}</div><div class="nz-muted">шығынға қолжетімді · жалпы '
                f'{money(b.total)}, мақсаттарда {money(b.allocated)}</div>')
    with st.container(border=True, key="card_p_teach"):
        kit.h("Мұғалімдерден хабарлар")
        rows = [d for d in messaging.dialogs_for(uid, student_id=cid) if d["kind"] in ("parent_teacher", "support")]
        for d in rows[:3]:
            st.html(f'<div class="nz-title">{kit.esc(d["title"])}{" · " + str(d["unread"]) + " жаңа" if d["unread"] else ""}'
                    f'</div><div class="nz-muted">{kit.esc((d["last_body"] or "")[:140])}</div>')
        ann = messaging.announcements_for(uid, cid)[:2]
        for a in ann:
            st.html(f'<div class="nz-title">{kit.esc(a["title"])}</div><div class="nz-muted">{kit.esc(a["teacher_name"])}: '
                    f'{kit.esc(a["body"][:140])}</div>')
        if not rows and not ann:
            st.caption("Жаңа хабар жоқ.")
    st.subheader("Апталық отбасылық шолу")
    family_review(uid, cid)


def progress() -> None:
    uid = session.current_uid()
    st.title("Оқу барысы")
    child = _child(uid)
    subs = study.subjects_for_student(child["id"])
    sid = st.pills("Пән", [s["id"] for s in subs], format_func={s["id"]: s["name"] for s in subs}.get,
                   default=subs[0]["id"], key="p_subj", required=True)
    rows = study.results(uid, child["id"], sid)
    with st.container(border=True, key="card_p_subj"):
        three_measures(uid, child["id"], sid, rows)
        if rows:
            dynamics_chart(rows)
            results_table(rows)
        else:
            kit.empty("Бұл пән бойынша нәтиже жоқ.")
    with st.container(border=True, key="card_p_tasks"):
        kit.h("Тапсырмалар")
        for a in study.assignments_for_student(uid, child["id"]):
            if a["subject_id"] == sid:
                st.html(f'<div class="nz-title">{kit.esc(a["title"])}</div><div class="nz-muted">'
                        f'Мерзімі: {kit.esc(fmt_date(a["due_date"]))} · {kit.esc(study.assignment_state(a))}</div>')


def calendar() -> None:
    uid = session.current_uid()
    st.title("Ортақ күнтізбе")
    child = _child(uid)
    st.caption("Мұнда мектеп сабақтары, тапсырма мерзімдері және бала бөліскен істер ғана көрінеді.")
    start = week_start(today())
    for day, items in planner.week_items(uid, child["id"], start).items():
        d0 = datetime.fromisoformat(day).date()
        with st.container(border=True, key=f"card_pc_{day}"):
            st.html(f'<div class="nz-title">{kit.esc(fmt_date(d0, True))}{" · бүгін" if d0 == today() else ""}</div>')
            if not items:
                st.caption("Бөлісілген іс жоқ.")
            for i in items:
                status = "орындалды" if i.status == "done" else ("бас тартылды" if i.status == "cancelled" else "")
                st.write(f"{i.start or '—'} · {i.title}" + (f" — {status}" if status else ""))


def goals_money() -> None:
    uid = session.current_uid()
    kit.show_flash()
    st.title("Мақсаттар мен қаржы")
    child = _child(uid)
    cid = child["id"]
    t1, t2 = st.tabs(["Мақсаттар", "Қаржы"])
    with t1:
        gl = goals.list_goals(uid, cid, ("active", "paused", "done"))
        if not gl:
            kit.empty("Бала мақсатымен бөліспеген.", "Мақсатпен бөлісу — баланың өз шешімі.")
        b = finance.balance(uid, cid)
        for g in gl:
            with st.container(border=True, key=f"card_pg_{g['id']}"):
                st.html(f'<p class="nz-h">{kit.esc(g["title"])}</p>' + kit.badge(goals.KIND_LABEL[g["kind"]])
                        + kit.badge(goals.STATUS_LABEL[g["status"]], "grey"))
                if g["kind"] == "buy":
                    plan = goals.buy_plan(g, b.by_goal.get(g["id"], 0))
                    st.html(f'<div class="nz-muted">{money(plan.saved)} / {money(plan.price)} · {plan.percent:.0f}%</div>'
                            + kit.progress_bar(plan.percent / 100))
                else:
                    k, n = goals.step_progress(g["id"])
                    if n:
                        st.write(k_of_n(k, n, "қадамның", "аяқталды"))
                proms = goals.promises(uid, g["id"])
                if proms:
                    st.markdown("**Уәделер** — балансқа қосылмайды, ақша берілгенде ғана кіріс болады.")
                for p in proms:
                    st.write(f"• {money(p['amount_tiyn'])} — {p['condition_text']} "
                             f"({ {'active': 'белсенді', 'fulfilled': 'орындалды', 'cancelled': 'бас тартылды'}[p['status']] })")
                    if p["parent_id"] == uid and p["status"] == "active":
                        c1, c2 = st.columns(2)
                        if c1.button("Ақшаны бердім", key=f"pf_{p['id']}", width="stretch"):
                            kit.run_action(goals.fulfill_promise, uid, p["id"], ok="Кіріс ретінде жазылды.")
                            st.rerun()
                        if c2.button("Уәдеден бас тарту", key=f"pc_{p['id']}", width="stretch"):
                            goals.cancel_promise(uid, p["id"])
                            st.rerun()
                if g["status"] != "done":
                    with st.expander("Уәде беру"):
                        st.caption("Уәде балаға көрінеді, бірақ балансқа қосылмайды.")
                        with st.form(f"prom_{g['id']}", clear_on_submit=True, border=False):
                            amt = st.text_input("Сома, ₸")
                            cond = st.text_input("Шарты", placeholder="Мысалы: 30 000 ₸ жинағанда")
                            if st.form_submit_button("Уәдені сақтау"):
                                try:
                                    goals.add_promise(uid, g["id"], to_tiyn(amt), cond)
                                    kit.flash("Уәде сақталды.")
                                    st.rerun()
                                except (ValueError, PermissionError) as e:
                                    st.error(str(e))
                for c in goals.comments(uid, g["id"]):
                    st.html(f'<div class="nz-muted">{kit.esc(c["author_name"])}, {kit.esc(fmt_dt(c["created_at"]))}</div>'
                            f'<div>{kit.esc(c["body"])}</div>')
                if g["status"] == "done":
                    continue
                with st.form(f"gc_{g['id']}", clear_on_submit=True, border=False):
                    body = st.text_input("Қолдау пікірі", placeholder="Мысалы: Жоспарың түсінікті, мақтанамын!")
                    if st.form_submit_button("Пікір қалдыру"):
                        if kit.run_action(goals.add_comment, uid, g["id"], body, kit.token(f"gc_{g['id']}"),
                                          ok="Пікір қосылды."):
                            kit.renew_token(f"gc_{g['id']}")
                            st.rerun()
    with t2:
        from views.student.money import balance_cards
        balance_cards(uid, cid)
        with st.container(border=True, key="card_p_income"):
            kit.h("Берілген ақшаны жазу", "Бала бұл жазбаны көреді, оны қайта енгізудің қажеті жоқ.")
            with st.form("p_income", clear_on_submit=True, border=False):
                c1, c2 = st.columns(2)
                amt = c1.text_input("Сома, ₸")
                d = c2.date_input("Күні", value=today(), format="DD.MM.YYYY")
                cat = st.selectbox("Түрі", finance.INCOME_CATEGORIES)
                note = st.text_input("Түсініктеме")
                if st.form_submit_button("Жазу", type="primary"):
                    try:
                        finance.add(uid, cid, "income", to_tiyn(amt), d.isoformat(), cat, note=note,
                                    token=kit.token("p_income"))
                        kit.renew_token("p_income")
                        kit.flash("Жазылды.")
                        st.rerun()
                    except (ValueError, PermissionError) as e:
                        st.error(str(e))
        with st.container(border=True, key="card_p_hist"):
            kit.h("Тарих", "Әр жазбаның авторы көрсетілген")
            history(uid, cid, editable=True)


def inbox() -> None:
    uid = session.current_uid()
    kit.show_flash()
    st.title("Хабарламалар")
    child = _child(uid)
    cid = child["id"]
    if nxt := st.session_state.pop("p_inbox_next", None):
        st.session_state["p_inbox_tab"] = nxt
    st.session_state.setdefault("p_inbox_tab", "Диалогтар")
    tab = st.segmented_control("Бөлім", ["Диалогтар", "Мұғалімге жазу", "Бірлесе қолдау", "Хабарландырулар"],
                               key="p_inbox_tab", required=True, label_visibility="collapsed")
    teachers = [t for t in access.allowed_contacts(uid) if access.teaches_student(t["id"], cid)]
    if tab == "Диалогтар":
        messages.inbox(uid, messaging.dialogs_for(uid, student_id=cid), f"p{cid}")
    elif tab in ("Мұғалімге жазу", "Бірлесе қолдау"):
        support = tab == "Бірлесе қолдау"
        if support:
            st.caption(f"Ортақ диалог: сіз, {child['name']} және таңдалған мұғалім. Бала да хабарларды көреді.")
        with st.form(f"p_new_{tab}", clear_on_submit=True):
            tid = st.selectbox("Мұғалім", [t["id"] for t in teachers], format_func={t["id"]: t["name"] for t in teachers}.get)
            if tid:
                st.caption(f"Байланыс уақыты: {messaging.hours_text(tid)}")
            title = st.text_input("Тақырып")
            body = st.text_area("Хабар", height=110)
            if st.form_submit_button("Жіберу", type="primary"):
                try:
                    tok = kit.token(f"p_new_{tab}")
                    did = messaging.start_dialog(uid, "support" if support else "parent_teacher", title,
                                                 [tid, cid] if support else [tid], body, tok, student_id=cid)
                    kit.renew_token(f"p_new_{tab}")
                    st.session_state[f"dlg_open_p{cid}"] = did
                    st.session_state["p_inbox_next"] = "Диалогтар"
                    kit.flash(f"Хабарыңыз қабылданды. Мұғалімнің байланыс уақыты: {messaging.hours_text(tid)}."
                              if not messaging.within_hours(tid) else "Хабар жіберілді.", "info")
                    st.rerun()
                except (ValueError, PermissionError) as e:
                    st.error(str(e))
    else:
        messages.announcements(messaging.announcements_for(uid, cid))
