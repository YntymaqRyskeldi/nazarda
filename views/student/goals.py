"""«Мақсаттарым»: үш түрлі мақсат, қадамдар, сатып алу жоспары, ата-ана қолдауы, жетістіктер тарихы."""
from __future__ import annotations

from datetime import date, time, timedelta

import streamlit as st

from core.fmt import fmt_date, fmt_dt, k_of_n, money, to_tiyn, today
from services import finance, goals
from services.family import settings
from ui import kit, session


def _celebrate(uid: int) -> None:
    cfg = settings(uid)
    if cfg["celebrate"] and not cfg["reduce_motion"]:
        kit.confetti()


def _cover(g) -> str:
    return kit.image_tag(g["image"], 110) if g["image"].startswith("https://") else kit.cover_svg(g["title"], height=110)


def _buy_block(uid: int, g, b: finance.Balance) -> None:
    plan = goals.buy_plan(g, b.by_goal.get(g["id"], 0))
    st.html(f'<div class="nz-row" style="justify-content:space-between"><span class="nz-title">'
            f'{money(plan.saved)} / {money(plan.price)}</span><span class="nz-muted">{plan.percent:.0f}%</span></div>'
            + kit.progress_bar(plan.percent / 100))
    lines = [f"Қалды: {money(plan.remaining)}"]
    if plan.weekly_needed:
        lines.append(f"Мерзімге үлгеру үшін аптасына орта есеппен {money(plan.weekly_needed)} "
                     f"({plan.weeks_left} апта қалды)")
    st.write(" · ".join(lines))
    st.caption(plan.note)
    with st.popover("Мақсатқа бөлу", icon=":material/savings:"):
        st.caption(f"Шығынға қолжетімді: {money(b.available)}")
        with st.form(f"alloc_{g['id']}", clear_on_submit=True, border=False):
            amount = st.text_input("Сома, ₸")
            if st.form_submit_button("Бөлу", type="primary"):
                try:
                    finance.add(uid, uid, "allocate", to_tiyn(amount), today().isoformat(), goal_id=g["id"],
                                note=f"{g['title']} мақсатына", token=kit.token(f"alloc_{g['id']}"))
                    kit.renew_token(f"alloc_{g['id']}")
                    kit.flash("Мақсатқа бөлінді.")
                    st.rerun()
                except (ValueError, PermissionError) as e:
                    st.error(str(e))


def _steps_block(uid: int, g) -> None:
    rows = goals.steps(g["id"])
    k, n = goals.step_progress(g["id"])
    st.html(f'<div class="nz-title">{kit.esc(k_of_n(k, n, "қадамның", "аяқталды"))}</div>'
            + kit.progress_bar(k / n if n else 0))
    for s in rows:
        c1, c2, c3 = st.columns([6, 1, 1], vertical_alignment="center", gap="small")
        wk = f"stp_{s['id']}"
        st.session_state[wk] = bool(s["done"])
        label = s["title"] + (f" · жоспарда: {fmt_date(s['planned_date'])}" if s["planned_date"] and not s["done"] else "")
        c1.checkbox(label, key=wk, on_change=lambda sid=s["id"], k=wk: goals.toggle_step(uid, sid, st.session_state[k]))
        with c2.popover("", icon=":material/event:", help="Жоспарға қою"):
            with st.form(f"sch_{s['id']}", border=False):
                d = st.date_input("Күні", value=date.fromisoformat(s["planned_date"]) if s["planned_date"] else today(),
                                  format="DD.MM.YYYY")
                t = st.time_input("Уақыты", value=time(18, 0), step=900)
                if st.form_submit_button("Жоспарға қою"):
                    goals.schedule_step(uid, s["id"], d.isoformat(), t.strftime("%H:%M"))
                    kit.flash("Қадам жоспарға қойылды.")
                    st.rerun()
        c3.button("", icon=":material/delete:", key=f"sd_{s['id']}", type="tertiary", help="Қадамды өшіру",
                  on_click=goals.delete_step, args=(uid, s["id"]))
    with st.form(f"addstep_{g['id']}", clear_on_submit=True, border=False):
        c1, c2 = st.columns([4, 1], vertical_alignment="bottom")
        t = c1.text_input("Жаңа қадам", placeholder="Келесі нақты әрекет")
        if c2.form_submit_button("Қосу"):
            if kit.run_action(goals.add_step, uid, g["id"], t, ok="Қадам қосылды."):
                st.rerun()


def _support_block(uid: int, g) -> None:
    pr = goals.promises(uid, g["id"])
    cm = goals.comments(uid, g["id"])
    if not pr and not cm:
        return
    st.markdown("**Ата-ана қолдауы**")
    for p in pr:
        state = {"active": "күтілуде", "fulfilled": "орындалды, кіріс ретінде жазылды", "cancelled": "бас тартылды"}
        st.html(kit.badge("Уәде", "amber") + f'{kit.esc(p["parent_name"])}: {money(p["amount_tiyn"])} — '
                f'{kit.esc(p["condition_text"])} <span class="nz-muted">({state[p["status"]]})</span>')
    if any(p["status"] == "active" for p in pr):
        st.caption("Уәде балансқа қосылмайды. Ата-ана ақшаны бергенде ғана кіріс ретінде көрінеді.")
    for c in cm:
        st.html(f'<div class="nz-muted">{kit.esc(c["author_name"])}, {kit.esc(fmt_dt(c["created_at"]))}</div>'
                f'<div>{kit.esc(c["body"])}</div>')


def _edit(uid: int, g) -> None:
    with st.form(f"ge_{g['id']}", border=False):
        title = st.text_input("Атауы", value=g["title"])
        why = st.text_input("Неге маңызды?", value=g["why"])
        c1, c2 = st.columns(2)
        td = c1.date_input("Мерзімі", value=date.fromisoformat(g["target_date"]) if g["target_date"] else None,
                           format="DD.MM.YYYY")
        price = c2.text_input("Бағасы, ₸", value=str(g["price_tiyn"] // 100) if g["price_tiyn"] else "",
                              disabled=g["kind"] != "buy")
        weekly = c1.text_input("Апталық жинау жоспарым, ₸ (міндетті емес)",
                               value=str(g["weekly_plan_tiyn"] // 100) if g["weekly_plan_tiyn"] else "",
                               disabled=g["kind"] != "buy")
        image = c2.text_input("Сурет сілтемесі (https://..., міндетті емес)", value=g["image"])
        vis = st.checkbox("Ата-анаммен бөлісу", value=bool(g["visible_to_parent"]))
        if st.form_submit_button("Сақтау", type="primary"):
            try:
                goals.update_goal(uid, g["id"], title, why, td.isoformat() if td else None,
                                  to_tiyn(price) if price and g["kind"] == "buy" else None, vis,
                                  to_tiyn(weekly) if weekly and g["kind"] == "buy" else None, image.strip())
                kit.flash("Сақталды. Жоспар қайта есептелді.")
                st.rerun()
            except ValueError as e:
                st.error(str(e))
    c1, c2 = st.columns(2)
    if c1.button("Мақсатты өшіру", key=f"gdel_{g['id']}", type="tertiary"):
        st.session_state["goal_del"] = g["id"]
    if st.session_state.get("goal_del") == g["id"]:
        st.warning("Мақсат пен оның қадамдары өшеді. Растайсың ба?")
        if st.button("Иә, өшіру", key=f"gdelok_{g['id']}", type="primary"):
            st.session_state.pop("goal_del", None)
            if kit.run_action(goals.delete_goal, uid, g["id"], ok="Мақсат өшірілді."):
                st.rerun()


def _goal_card(uid: int, g, b: finance.Balance) -> None:
    with st.container(border=True, key=f"card_goal_{g['id']}"):
        st.html(_cover(g))
        badges = kit.badge(goals.KIND_LABEL[g["kind"]]) + kit.badge(goals.STATUS_LABEL[g["status"]],
                                                                   "teal" if g["status"] == "active" else "grey")
        badges += kit.badge("Ата-анаға көрінеді", "grey") if g["visible_to_parent"] else kit.badge("Тек өзіме", "grey")
        st.html(f'<p class="nz-h" style="margin-top:8px">{kit.esc(g["title"])}</p>{badges}'
                + (f'<p class="nz-muted" style="margin:6px 0 0">{kit.esc(g["why"])}</p>' if g["why"] else "")
                + (f'<p class="nz-muted" style="margin:2px 0 0">Мерзімі: {kit.esc(fmt_date(g["target_date"]))}</p>'
                   if g["target_date"] else ""))
        if g["kind"] == "buy":
            _buy_block(uid, g, b)
        else:
            _steps_block(uid, g)
        _support_block(uid, g)
        c1, c2 = st.columns(2)
        if g["status"] == "active":
            c1.button("Үзіліс жасау", key=f"gp_{g['id']}", on_click=goals.set_status, args=(uid, g["id"], "paused"),
                      width="stretch")
        else:
            c1.button("Жалғастыру", key=f"ga_{g['id']}", on_click=goals.set_status, args=(uid, g["id"], "active"),
                      width="stretch")
        if c2.button("Мақсатқа жеттім", key=f"gd_{g['id']}", type="primary", width="stretch"):
            goals.set_status(uid, g["id"], "done")
            st.session_state["celebrate"] = g["title"]
            st.rerun()
        with st.expander("Өзгерту"):
            _edit(uid, g)


def _new_goal(uid: int) -> None:
    kind = st.segmented_control("Мақсат түрі", list(goals.KIND_LABEL), format_func=goals.KIND_LABEL.get,
                                default="buy", key="ng_kind", required=True)
    with st.form("new_goal", clear_on_submit=True):
        title = st.text_input("Атауы", placeholder={"buy": "Мысалы: Велосипед", "learn": "Мысалы: Гитарада ойнау",
                                                    "achieve": "Мысалы: 5 км жүгіру"}[kind])
        why = st.text_input("Неге маңызды?")
        c1, c2 = st.columns(2)
        td = c1.date_input("Мерзімі (міндетті емес)", value=None, format="DD.MM.YYYY", min_value=today())
        price = c2.text_input("Бағасы, ₸", disabled=kind != "buy")
        steps = st.text_area("Бірінші қадамдар (әр жолға біреуі)", disabled=kind == "buy", height=90)
        image = st.text_input("Сурет сілтемесі (https://..., міндетті емес)")
        vis = st.checkbox("Ата-анаммен бөлісу", value=False,
                          help="Әдепкі бойынша мақсат тек өзіңе көрінеді.")
        if st.form_submit_button("Мақсат құру", type="primary"):
            try:
                goals.create_goal(uid, kind, title, why, td.isoformat() if td else None,
                                  to_tiyn(price) if kind == "buy" and price else None, vis,
                                  steps.splitlines() if kind != "buy" else [],
                                  image.strip() if image.strip().startswith("https://") else "")
                kit.flash("Мақсат құрылды.")
                st.rerun()
            except ValueError as e:
                st.error(str(e))


def render() -> None:
    uid = session.current_uid()
    kit.show_flash()
    if title := st.session_state.pop("celebrate", None):
        _celebrate(uid)
        st.success(f"Құттықтаймыз! «{title}» мақсатына жеттің.", icon=":material/celebration:")
    st.title("Мақсаттарым")
    t1, t2, t3 = st.tabs(["Белсенді", "Жетістіктер тарихы", "Жаңа мақсат"])
    b = finance.balance(uid, uid)
    with t1:
        rows = goals.list_goals(uid, uid, ("active", "paused"))
        if not rows:
            kit.empty("Белсенді мақсат жоқ.", "«Жаңа мақсат» қойындысында құруға болады.")
        cols = st.columns(2, gap="medium")
        for k, g in enumerate(rows):
            with cols[k % 2]:
                _goal_card(uid, g, b)
    with t2:
        done = goals.list_goals(uid, uid, ("done",))
        if not done:
            kit.empty("Әзірге аяқталған мақсат жоқ.")
        for g in done:
            with st.container(border=True, key=f"card_gdone_{g['id']}"):
                st.html(f'<div class="nz-title">{kit.esc(g["title"])}</div><div class="nz-muted">'
                        f'{kit.esc(goals.KIND_LABEL[g["kind"]])} · аяқталды: '
                        f'{kit.esc(fmt_date(g["completed_at"][:10]) if g["completed_at"] else "—")}</div>')
                st.button("Қайта белсенді ету", key=f"gr_{g['id']}", type="tertiary",
                          on_click=goals.set_status, args=(uid, g["id"], "active"))
    with t3:
        _new_goal(uid)
