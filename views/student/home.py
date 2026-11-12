"""«Менің күнім» — оқушының басты экраны."""
from __future__ import annotations

import plotly.graph_objects as go
import streamlit as st

from core.fmt import fmt_date, k_of_n, money, now, today
from services import alerts, calc, courses, finance, goals, messaging, planner, study
from services.family import settings
from ui import kit, nav, quickadd, session, timeline


def header(uid: int, greeting: str, sub: str) -> None:
    u = session.current_user()
    left, right = st.columns([3, 1.3], vertical_alignment="center")
    with left:
        st.html(f'<p class="nz-greet">{kit.esc(greeting)}</p><p class="nz-sub">{kit.esc(sub)}</p>')
    with right:
        unread = messaging.unread_count(uid)
        st.html(f'<div class="nz-row" style="justify-content:flex-end">'
                f'<div class="nz-meta">{kit.esc(fmt_date(today(), True))}<br>{kit.demo_badge()}</div>'
                f'{kit.avatar(u["name"], u["color"])}</div>')
        nav.link("inbox", f"Хабарламалар ({unread} жаңа)" if unread else "Хабарламалар",
                 icon=":material/notifications:")


def subject_chart(uid: int, student_id: int, height: int = 260) -> None:
    rows = []
    for s in study.subjects_for_student(student_id):
        res = study.results(uid, student_id, s["id"])
        val = calc.weighted_percent([calc.Work(r["score"], r["max_score"], r["weight"]) for r in res])
        if val is not None:
            rows.append((s["name"], val, len(res)))
    if not rows:
        kit.empty("Әзірге нәтиже енгізілмеген.", "Мұғалім бағалаған соң диаграмма осында пайда болады.")
        return
    rows.sort(key=lambda r: r[1])
    fig = go.Figure(go.Bar(x=[r[1] for r in rows], y=[r[0] for r in rows], orientation="h",
                           marker_color=kit.INDIGO, text=[f"{r[1]:.0f}%" for r in rows], textposition="outside",
                           hovertemplate="%{y}: %{x:.0f}%<br>Жұмыс саны: %{customdata}<extra></extra>",
                           customdata=[r[2] for r in rows]))
    fig.update_xaxes(range=[0, 115], title_text="Есептелген пайыз, %", tickvals=[0, 25, 50, 75, 100])
    st.plotly_chart(kit.style_fig(fig, height), config=kit.PLOTLY_CFG, width="stretch")
    st.caption("Мұғалім енгізген жұмыстар бойынша салмақпен есептелген пайыз. "
               "Бұл — білім деңгейінің дәлелі емес, тек енгізілген деректердің қорытындысы.")


def render() -> None:
    uid = session.current_uid()
    u = session.current_user()
    cfg = settings(uid)
    kit.show_flash()
    header(uid, f"Сәлем, {u['name']}!", "Бүгінгі күніңді өзің басқар.")
    quickadd.render(uid)

    items = planner.day_items(uid, uid, today())
    done, total = planner.progress(items)
    nxt, reason = planner.next_action(items)

    # ---------- Бірінші қатар ----------
    c1, c2 = st.columns([2.2, 1], gap="medium")
    with c1, st.container(border=True, key="card_hero"):
        txt, art = st.columns([3, 1], vertical_alignment="center")
        with txt:
            st.html('<p class="nz-kicker">Қазір не істеймін?</p>')
            if nxt:
                when = f"{nxt.start}–{nxt.end}" if nxt.start else f"Мерзімі: {fmt_date(nxt.extra['due_date'])}"
                st.html(f'<p class="nz-big">{kit.esc(nxt.title)}</p>'
                        f'<p class="nz-muted" style="margin:0">{kit.esc(nxt.category)} · {kit.esc(when)}</p>'
                        f'<p style="margin:8px 0 0">{kit.esc(reason)}</p>')
                if nxt.kind == "event":
                    def _done(eid=nxt.event_id, od=nxt.orig_date, key=nxt.key):
                        planner.set_status(uid, eid, od, "done")
                        st.session_state["just_done"] = key
                        kit.flash("Орындалды. Жарайсың!")
                    st.button("Орындадым", type="primary", on_click=_done, icon=":material/check:")
                elif nxt.kind == "assignment":
                    st.button("Тапсырманы ашу", type="primary", icon=":material/edit_note:",
                              on_click=nav.go, args=("study",), kwargs={"study_focus": nxt.source_ref})
                else:
                    st.button("Сабақ кестесін көру", type="primary", on_click=nav.go, args=("plan",))
            else:
                st.html('<p class="nz-big">Бүгінге жоспарланған іс қалмады</p>'
                        '<p class="nz-muted">Демалуға немесе ертеңгі күнді жоспарлауға болады.</p>')
                st.button("Ертеңді жоспарлау", type="primary", on_click=nav.go, args=("plan",))
        with art:
            st.html(f'<div style="max-width:180px;margin-left:auto">{kit.illustration()}</div>')
    with c2, st.container(border=True, key="card_progress"):
        st.html('<p class="nz-kicker">Күннің орындалуы</p>')
        st.html(f'<div style="display:flex;justify-content:center;padding:4px 0">'
                f'{kit.ring(done, total, label=k_of_n(done, total, "істің", "орындалды"))}</div>')
        st.html(f'<p class="nz-title" style="text-align:center;margin:0">'
                f'{kit.esc(k_of_n(done, total, "істің", "орындалды"))}</p>')
        st.caption("Тек бақыланатын істер саналады. Бас тартылған іс сәтсіздік емес.")

    # Ерте ескерту (бар болса ғана)
    for a in alerts.active_alerts(uid):
        with st.container(border=True, key=f"card_alert_{a['subject_id']}"):
            kit.warn(f"{a['subject_name']}: {a['details']['reason']}")
            b1, b2, b3 = st.columns(3)
            b1.button("Нәтижелерді көру", key=f"al_r_{a['id']}", on_click=nav.go, args=("study",),
                      kwargs={"study_subject": a["subject_id"], "study_jump_subject": True}, width="stretch")
            b2.button("Көмек сұрау", key=f"al_h_{a['id']}", on_click=nav.go, args=("inbox",),
                      kwargs={"inbox_compose": {"subject_id": a["subject_id"], "topic": "Тақырыпты түсіндіріп берші"}},
                      width="stretch")
            b3.button("Жоспарға қосу", key=f"al_p_{a['id']}", on_click=nav.go, args=("plan",),
                      kwargs={"plan_prefill": f"{a['subject_name']}: қайталау"}, width="stretch")

    # ---------- Екінші қатар ----------
    c1, c2 = st.columns([1.5, 1], gap="medium")
    with c1, st.container(border=True, key="card_timeline"):
        kit.h("Бүгінгі жоспар", fmt_date(today(), True))
        if items:
            timeline.render(uid, uid, items, True, "home", on_open_study=lambda aid: nav.go("study", study_focus=aid))
        else:
            kit.empty("Бүгінге ештеңе жоспарланбаған.", "«Жылдам қосу» арқылы іс қосуға болады.")
        nav.link("plan", "Толық жоспар", icon=":material/calendar_month:")
    with c2, st.container(border=True, key="card_subjects"):
        kit.h("Пәндердегі ілгерілеу")
        subject_chart(uid, uid)

    # ---------- Үшінші қатар ----------
    c1, c2, c3 = st.columns(3, gap="medium")
    with c1, st.container(border=True, key="card_courses"):
        kit.h("Курстарым")
        cs = courses.list_courses(uid, uid)
        upcoming = sorted([(courses.next_meeting(c), c) for c in cs], key=lambda x: (x[0] is None, x[0] or ()))[:2]
        if not upcoming:
            kit.empty("Курс қосылмаған.")
        for nm, c in upcoming:
            st.html(f'<div class="nz-title">{kit.esc(c["title"])}</div><div class="nz-muted">'
                    f'{kit.esc(k_of_n(c["completed_lessons"], c["total_lessons"], "сабақтың", "аяқталды"))}'
                    + (f' · келесі: {kit.esc(fmt_date(nm[0]))}, {kit.esc(nm[1])}' if nm else "") + "</div>"
                    + kit.progress_bar(c["completed_lessons"] / c["total_lessons"]))
        nav.link("courses", "Барлық курстар", icon=":material/school:")
    with c2, st.container(border=True, key="card_goal"):
        kit.h("Мақсатым")
        fid = cfg["featured_goal_id"]
        g = next((x for x in goals.list_goals(uid, uid, ("active", "paused")) if x["id"] == fid), None)
        if not g:
            kit.empty("Басты бетке мақсат таңдалмаған.", "«Профиль» бөлімінде таңдауға болады.")
        else:
            st.html(f'<div class="nz-title">{kit.esc(g["title"])}</div>')
            if g["kind"] == "buy":
                b = finance.balance(uid, uid)
                plan = goals.buy_plan(g, b.by_goal.get(g["id"], 0))
                if cfg["hide_money_home"]:
                    st.html(f'<div class="nz-muted">Жиналды: {plan.percent:.0f}%</div>' + kit.progress_bar(plan.percent / 100))
                else:
                    st.html(f'<div class="nz-muted">{money(plan.saved)} / {money(plan.price)} · '
                            f'{plan.percent:.0f}%</div>' + kit.progress_bar(plan.percent / 100))
                    if plan.weekly_needed:
                        st.caption(f"Аптасына орта есеппен {money(plan.weekly_needed)} жинау қажет. {plan.note}")
            else:
                k, n = goals.step_progress(g["id"])
                st.html(f'<div class="nz-muted">{kit.esc(k_of_n(k, n, "қадамның", "аяқталды"))}</div>'
                        + kit.progress_bar(k / n if n else 0))
        nav.link("goals", "Мақсаттарым", icon=":material/flag:")
    with c3, st.container(border=True, key="card_money"):
        kit.h("Қалта ақшам", "Енгізілген деректер бойынша")
        b = finance.balance(uid, uid)
        if cfg["hide_money_home"]:
            st.html('<div class="nz-num">•••••</div>')
            st.caption("Сома басты бетте жасырылған. Көрсету — «Профиль» бөлімінде.")
        else:
            st.html(f'<div class="nz-num">{money(b.available)}</div><div class="nz-muted">шығынға қолжетімді</div>')
            st.caption(f"Жалпы қалдық {money(b.total)}, оның {money(b.allocated)} мақсаттарға бөлінген.")
        nav.link("money", "Қаржым", icon=":material/account_balance_wallet:")

    # ---------- Күнді қорытындылау ----------
    from views.student.plan import day_review
    with st.expander("Күнді қорытындылау", expanded=now().hour >= 20, icon=":material/nights_stay:"):
        day_review(uid, items)
