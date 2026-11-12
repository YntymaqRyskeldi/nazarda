"""«Қаржым»: кіріс, шығыс, мақсатқа бөлу, тарих және «Қазір сатып алсам ше?» сценарийі."""
from __future__ import annotations

from datetime import date, timedelta

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from core.fmt import fmt_date, money, to_tiyn, today
from services import finance, goals
from ui import kit, session


def balance_cards(uid: int, student_id: int) -> finance.Balance:
    b = finance.balance(uid, student_id)
    c1, c2, c3 = st.columns(3)
    c1.metric("Жалпы қалдық", money(b.total), help="Барлық кіріс минус барлық шығыс.")
    c2.metric("Мақсаттарға бөлінген", money(b.allocated), help="Мақсатқа бөлу — шығыс емес, ақша сенде қалады.")
    c3.metric("Шығынға қолжетімді", money(b.available), help="Жалпы қалдық минус мақсаттарға бөлінген сома.")
    st.caption("Енгізілген деректер бойынша. NAZARDA банк немесе төлем жүйесі емес.")
    return b


def history(uid: int, student_id: int, editable: bool) -> None:
    c1, c2 = st.columns(2)
    period = c1.segmented_control("Кезең", ["7 күн", "30 күн", "Барлығы"], default="30 күн", key=f"hist_p_{uid}",
                                  required=True)
    days = {"7 күн": 7, "30 күн": 30}.get(period)
    rows = finance.list_tx(uid, student_id, (today() - timedelta(days=days)).isoformat() if days else None)
    if not rows:
        kit.empty("Бұл кезеңде операция жоқ.")
        return
    df = pd.DataFrame([{"Күні": fmt_date(t["date"]), "Түрі": finance.KINDS[t["kind"]],
                        "Сома": money(t["amount_tiyn"]) if t["kind"] != "expense" else "−" + money(t["amount_tiyn"]),
                        "Санат / мақсат": t["category"] or t["goal_title"] or "—", "Түсініктеме": t["note"] or "—",
                        "Енгізген": t["author_name"] + (" (ата-ана)" if t["author_role"] == "parent" else "")}
                       for t in rows])
    st.dataframe(df, hide_index=True, width="stretch")
    own = [t for t in rows if t["author_id"] == uid]
    if editable and own:
        with st.expander("Өз жазбамды өзгерту немесе өшіру"):
            tid = st.selectbox("Операция", [t["id"] for t in own], key=f"edit_tx_{uid}",
                               format_func={t["id"]: f"{fmt_date(t['date'])} · {finance.KINDS[t['kind']]} · "
                                                     f"{money(t['amount_tiyn'])} · {t['note'] or t['category']}"
                                            for t in own}.get)
            t = next(x for x in own if x["id"] == tid)
            with st.form(f"txe_{tid}", border=False):
                c1, c2 = st.columns(2)
                amount = c1.text_input("Сома, ₸", value=str(t["amount_tiyn"] / 100).rstrip("0").rstrip("."))
                d = c2.date_input("Күні", value=date.fromisoformat(t["date"]), format="DD.MM.YYYY")
                cats = finance.EXPENSE_CATEGORIES if t["kind"] == "expense" else finance.INCOME_CATEGORIES
                cat = st.selectbox("Санаты", cats, index=cats.index(t["category"]) if t["category"] in cats else 0) \
                    if t["kind"] in ("expense", "income") else t["category"]
                note = st.text_input("Түсініктеме", value=t["note"])
                b1, b2 = st.columns(2)
                save = b1.form_submit_button("Сақтау", type="primary")
                delete = b2.form_submit_button("Өшіру")
            if save:
                try:
                    finance.update(uid, tid, to_tiyn(amount), d.isoformat(), cat, note)
                    kit.flash("Өзгертілді.")
                    st.rerun()
                except ValueError as e:
                    st.error(str(e))
            if delete:
                st.session_state["tx_del"] = tid
            if st.session_state.get("tx_del") == tid:
                st.warning("Операция өшіріледі және балансқа әсер етеді. Растайсың ба?")
                if st.button("Иә, өшіру", key=f"txdo_{tid}", type="primary"):
                    st.session_state.pop("tx_del", None)
                    if kit.run_action(finance.delete, uid, tid, ok="Өшірілді."):
                        st.rerun()


def _forms(uid: int, b: finance.Balance) -> None:
    active = goals.list_goals(uid, uid, ("active", "paused"))
    goal_names = {g["id"]: g["title"] for g in active}
    kind = st.segmented_control("Операция", ["Шығыс", "Кіріс", "Мақсатқа бөлу", "Мақсаттан қайтару"],
                                default="Шығыс", key="money_kind", required=True)
    code = {"Шығыс": "expense", "Кіріс": "income", "Мақсатқа бөлу": "allocate", "Мақсаттан қайтару": "release"}[kind]
    with st.form(f"money_{code}", clear_on_submit=True):
        c1, c2 = st.columns(2)
        amount = c1.text_input("Сома, ₸", placeholder="Мысалы: 2000")
        d = c2.date_input("Күні", value=today(), format="DD.MM.YYYY")
        cat, gid = "", None
        if code == "expense":
            cat = st.selectbox("Санаты", finance.EXPENSE_CATEGORIES)
            buy_goals = [g for g in active if g["kind"] == "buy" and b.by_goal.get(g["id"], 0) > 0]
            if buy_goals:
                pick = st.selectbox("Мақсаттағы жинақтан төлеу (міндетті емес)", [None] + [g["id"] for g in buy_goals],
                                    format_func=lambda x: "Жоқ, қолжетімді қаражаттан" if x is None else goal_names[x])
                gid = pick
        elif code == "income":
            cat = st.selectbox("Көзі", finance.INCOME_CATEGORIES)
        else:
            if not active:
                st.info("Алдымен мақсат құр.")
            gid = st.selectbox("Мақсат", [g["id"] for g in active], format_func=goal_names.get) if active else None
            if code == "allocate":
                st.caption("Мақсатқа бөлу шығыс емес: ақша жалпы қалдықта қалады, тек «қолжетімдіден» азаяды.")
            else:
                st.caption(f"Мақсатта: {money(b.by_goal.get(gid, 0))}" if gid else "")
        note = st.text_input("Түсініктеме (міндетті емес)")
        confirm_dup = False
        if code == "income":
            confirm_dup = st.checkbox("Ата-ана енгізген кірісті қайталамайтынымды тексердім", value=False,
                                      help="Ата-ана берген ақшаны өзі жазса, оны қайта енгізудің қажеті жоқ.")
        ok = st.form_submit_button("Жазу", type="primary")
    if ok:
        try:
            amt = to_tiyn(amount)
            if code == "income":
                dup = finance.possible_duplicate(uid, amt, d.isoformat(), uid)
                if dup and not confirm_dup:
                    st.warning(f"{dup['author_name']} осы күні дәл осындай кірісті ({money(amt)}) енгізіп қойған. "
                               "Бұл басқа ақша болса, белгіні қойып, қайта жібер.")
                    return
            res = finance.add(uid, uid, code, amt, d.isoformat(), cat, gid, note, kit.token(f"money_{code}"))
            kit.renew_token(f"money_{code}")
            kit.flash("Жазылды." if res else "Бұл операция бұрын жазылған.")
            st.rerun()
        except (ValueError, PermissionError) as e:
            st.error(str(e))


def _scenario(uid: int, b: finance.Balance) -> None:
    kit.h("Қазір сатып алсам ше?", "Тек есептеу: ешқандай операция жасалмайды.")
    price = st.text_input("Заттың бағасы, ₸", placeholder="Мысалы: 12000", key="scn_price")
    if not price:
        return
    try:
        p = to_tiyn(price)
        featured = next((g for g in goals.list_goals(uid, uid, ("active",)) if g["kind"] == "buy"), None)
        weekly = featured["weekly_plan_tiyn"] if featured else None
        sc = finance.purchase_scenario(b, p, weekly)
    except ValueError as e:
        st.error(str(e))
        return
    if sc.from_goals == 0:
        st.success(f"Қолжетімді қаражат жетеді. Сатып алғаннан кейін қолжетімдіде {money(sc.available_after)} қалады. "
                   "Мақсаттардағы жинаққа тиіспейсің.")
    elif sc.affordable:
        txt = (f"Қолжетімді қаражат {money(sc.from_goals)} жетпейді. Сатып алу үшін мақсаттағы жинақтан "
               f"{money(sc.from_goals)} қайтаруға тура келеді.")
        if sc.weeks_delay and featured:
            txt += (f" Сонда «{featured['title']}» мақсаты апталық жоспарыңмен шамамен "
                    f"{sc.weeks_delay:.1f} аптаға кешігеді.")
        kit.warn(txt)
    else:
        kit.warn(f"Жалпы қалдық та жетпейді: тағы {money(p - b.total)} қажет.")
    st.caption("Шешім — өзіңде. Қаласаң, ата-анаңмен «Көмек керек → Сатып алуды талқылайық» арқылы ақылдас.")


def render() -> None:
    uid = session.current_uid()
    kit.show_flash()
    st.title("Қаржым")
    b = balance_cards(uid, uid)
    c1, c2 = st.columns([1.3, 1], gap="medium")
    with c1, st.container(border=True, key="card_money_form"):
        kit.h("Жаңа операция")
        _forms(uid, b)
    with c2:
        with st.container(border=True, key="card_money_scn"):
            _scenario(uid, b)
        with st.container(border=True, key="card_money_cat"):
            kit.h("Соңғы 30 күндегі шығыстар", "Санаттар бойынша")
            rows = [t for t in finance.list_tx(uid, uid, (today() - timedelta(days=30)).isoformat()) if t["kind"] == "expense"]
            if rows:
                agg: dict[str, int] = {}
                for t in rows:
                    agg[t["category"]] = agg.get(t["category"], 0) + t["amount_tiyn"]
                items = sorted(agg.items(), key=lambda x: x[1])
                fig = go.Figure(go.Bar(x=[v / 100 for _, v in items], y=[k for k, _ in items], orientation="h",
                                       marker_color=kit.TEAL, text=[money(v) for _, v in items],
                                       textposition="outside", hovertemplate="%{y}: %{text}<extra></extra>"))
                fig.update_xaxes(title_text="₸", range=[0, max(v for _, v in items) / 100 * 1.35])
                st.plotly_chart(kit.style_fig(fig, 220), config=kit.PLOTLY_CFG, width="stretch")
            else:
                st.caption("Соңғы 30 күнде шығыс жоқ.")
    with st.container(border=True, key="card_money_hist"):
        kit.h("Тарих")
        history(uid, uid, editable=True)
