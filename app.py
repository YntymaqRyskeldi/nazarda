"""NAZARDA — «Әр қадам назарда.»

Іске қосу:  streamlit run app.py
Дерекқор:   NAZARDA_DB айнымалысы (әдепкі: data/nazarda.db)
"""
from __future__ import annotations

import streamlit as st

from core.db import BASE_DIR, init_db
from demo import seed
from ui import kit, nav, session
from views import about, profile
from views.parent import pages as parent
from views.student import courses, goals, home, inbox, money, plan, study
from views.teacher import pages as teacher

st.set_page_config(page_title="NAZARDA", page_icon=str(BASE_DIR / "static" / "img" / "logo_mark.svg"),
                   layout="wide", initial_sidebar_state="auto")


@st.cache_resource(show_spinner=False)
def _bootstrap() -> bool:
    init_db()
    seed.ensure_seeded()
    return True


_bootstrap()
if not seed.is_seeded():          # демо деректер қалпына келтірілгеннен кейін
    seed.ensure_seeded()
kit.inject_css()
st.logo(str(BASE_DIR / "static" / "img" / "logo.svg"), icon_image=str(BASE_DIR / "static" / "img" / "logo_mark.svg"),
        size="large")

user = session.current_user()
role = user["role"]
P = st.Page

if role == "student":
    main = {
        "home": P(home.render, title="Менің күнім", icon=":material/wb_sunny:", url_path="home", default=True),
        "study": P(study.render, title="Оқуым", icon=":material/menu_book:", url_path="study"),
        "plan": P(plan.render, title="Күн жоспарым", icon=":material/calendar_month:", url_path="plan"),
        "courses": P(courses.render, title="Курстарым", icon=":material/school:", url_path="courses"),
        "money": P(money.render, title="Қаржым", icon=":material/account_balance_wallet:", url_path="money"),
        "goals": P(goals.render, title="Мақсаттарым", icon=":material/flag:", url_path="goals"),
        "inbox": P(inbox.render, title="Хабарламалар", icon=":material/notifications:", url_path="inbox"),
    }
elif role == "parent":
    main = {
        "p_home": P(parent.overview, title="Шолу", icon=":material/dashboard:", url_path="overview", default=True),
        "p_progress": P(parent.progress, title="Оқу барысы", icon=":material/trending_up:", url_path="progress"),
        "p_calendar": P(parent.calendar, title="Ортақ күнтізбе", icon=":material/calendar_month:", url_path="calendar"),
        "p_goals": P(parent.goals_money, title="Мақсаттар мен қаржы", icon=":material/savings:", url_path="goals-money"),
        "p_inbox": P(parent.inbox, title="Хабарламалар", icon=":material/forum:", url_path="messages"),
    }
else:
    main = {
        "t_desk": P(teacher.desk, title="Жұмыс үстелі", icon=":material/space_dashboard:", url_path="desk", default=True),
        "t_classes": P(teacher.classes, title="Сыныптар", icon=":material/groups:", url_path="classes"),
        "t_assign": P(teacher.assignments, title="Тапсырмалар", icon=":material/assignment:", url_path="assignments"),
        "t_review": P(teacher.review, title="Тексеру", icon=":material/fact_check:", url_path="review"),
        "t_questions": P(teacher.questions, title="Сұрақтар", icon=":material/forum:", url_path="questions"),
        "t_ann": P(teacher.announcements, title="Хабарландырулар", icon=":material/campaign:", url_path="announcements"),
        "t_hours": P(teacher.hours, title="Байланыс уақыты", icon=":material/schedule:", url_path="hours"),
    }
bottom = {
    "profile": P(profile.render, title="Профиль", icon=":material/person:", url_path="profile"),
    "about": P(about.render, title="Жоба туралы", icon=":material/info:", url_path="about"),
}
nav.PAGES.clear()
nav.PAGES.update(main)
nav.PAGES.update(bottom)

pg = st.navigation({"": list(main.values()), "Басқа": list(bottom.values())})

with st.sidebar:
    st.html(f'<div style="margin-top:8px">{kit.demo_badge()}</div>')
    session.switch_user_widget()
    st.caption("Демо режимі: рөл таңдау — кіру жүйесі емес. Жеке аккаунттар бұл нұсқада қосылмаған "
               "(«Жоба туралы» бөлімін қараңыз).")

nav.handle_goto()
pg.run()
