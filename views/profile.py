"""«Профиль»: баптаулар және апталық PDF есеп (барлық рөлдер)."""
from __future__ import annotations

from datetime import timedelta

import streamlit as st

from core import access
from core.fmt import fmt_date, today, week_start
from services import family, goals, reports
from ui import kit, session


def report_block(uid: int, student) -> None:
    kit.h("Апталық есеп (PDF)", "Файл сұраған сәтте жасалады. Ешкімге автоматты түрде жіберілмейді.")
    weeks = [week_start(today()) - timedelta(weeks=k) for k in range(0, 6)]
    wk = st.selectbox("Апта", weeks, format_func=lambda w: f"{fmt_date(w)} — {fmt_date(w + timedelta(days=6))}",
                      key=f"rep_wk_{uid}")
    fin = st.checkbox("Қаржы бөлімін қосу", value=False, key=f"rep_fin_{uid}",
                      help="Қаржы деректері тек сен таңдасаң ғана есепке кіреді.")
    if st.button("Есепті дайындау", key=f"rep_go_{uid}"):
        st.session_state[f"rep_pdf_{uid}"] = (reports.build_weekly(uid, student["id"], wk, fin), wk)
    if (got := st.session_state.get(f"rep_pdf_{uid}")) and got[1] == wk:
        st.download_button("PDF жүктеп алу", data=got[0], file_name=f"nazarda_{student['id']}_{wk.isoformat()}.pdf",
                           mime="application/pdf", type="primary", icon=":material/download:")


def render() -> None:
    uid = session.current_uid()
    u = session.current_user()
    kit.show_flash()
    st.title("Профиль")
    st.html(f'<div class="nz-row">{kit.avatar(u["name"], u["color"], 48)}<div><div class="nz-h">'
            f'{kit.esc(u["full_name"])}</div><div class="nz-muted">{session.ROLE_LABEL[u["role"]]} · '
            f'демо аккаунт</div></div></div>')
    cfg = family.settings(uid)
    c1, c2 = st.columns(2, gap="medium")
    with c1, st.container(border=True, key="card_settings"):
        kit.h("Баптаулар")
        with st.form("settings", border=False):
            vals = {}
            if u["role"] == "student":
                gl = goals.list_goals(uid, uid, ("active", "paused"))
                opts = [None] + [g["id"] for g in gl]
                vals["featured_goal_id"] = st.selectbox(
                    "Басты беттегі мақсат", opts, index=opts.index(cfg["featured_goal_id"])
                    if cfg["featured_goal_id"] in opts else 0,
                    format_func=lambda x: "Көрсетпеу" if x is None else next(g["title"] for g in gl if g["id"] == x))
                vals["hide_money_home"] = st.toggle("Басты бетте сомаларды жасыру", bool(cfg["hide_money_home"]))
                vals["alert_threshold"] = st.slider("Ерте ескерту шегі, пайыздық тармақ", 5, 30,
                                                    int(cfg["alert_threshold"]),
                                                    help="Соңғы 3 салыстырмалы жұмыс қатарынан төмендеп, жалпы "
                                                         "төмендеу осы шектен кем болмаса, ескерту шығады.")
            vals["reduce_motion"] = st.toggle("Анимацияны азайту", bool(cfg["reduce_motion"]))
            vals["celebrate"] = st.toggle("Мақсат орындалғанда құттықтау көрсету", bool(cfg["celebrate"]))
            if st.form_submit_button("Сақтау", type="primary"):
                if kit.run_action(family.save_settings, uid, **vals, ok="Баптаулар сақталды."):
                    if u["role"] == "student":
                        from services import alerts
                        alerts.recompute_all(uid)
                    st.rerun()
    with c2, st.container(border=True, key="card_report"):
        if u["role"] == "student":
            report_block(uid, u)
        elif u["role"] == "parent":
            child = session.selected_child(uid)
            if child:
                report_block(uid, child)
        else:
            kit.h("Есептер")
            st.caption("Мұғалімге арналған PDF есеп бұл нұсқада жоқ. Сынып нәтижелерін «Сыныптар» бөлімінен көруге болады.")
