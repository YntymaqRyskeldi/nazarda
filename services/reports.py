"""Апталық PDF есеп. Файл жадта жасалады (дискке ортақ файл жазылмайды),
сондықтан әр пайдаланушы өз есебін алады. Қазақ қарпі (Noto Sans) PDF ішіне енгізіледі.
Автоматты жіберу жоқ — есепті пайдаланушы өзі жүктеп алады."""
from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

from fpdf import FPDF

from core import access
from core.db import BASE_DIR
from core.fmt import fmt_date, fmt_date_long, money, now
from services import finance, goals, planner, study

FONT_DIR = BASE_DIR / "static" / "fonts"
INK, MUTED, INDIGO, TEAL, LINE = (24, 34, 56), (89, 101, 121), (79, 70, 229), (15, 118, 110), (227, 232, 240)


class _PDF(FPDF):
    def footer(self):
        self.set_y(-14)
        self.set_font("Noto", size=8)
        self.set_text_color(*MUTED)
        self.cell(0, 6, f"NAZARDA · {self.page_no()}-бет · Енгізілген деректер бойынша жасалды", align="C")


def build_weekly(actor: int, student_id: int, start: date, include_finance: bool = False) -> bytes:
    access.require_family(actor, student_id)
    end = start + timedelta(days=6)
    s, e = start.isoformat(), end.isoformat()
    st = access.user(student_id)

    pdf = _PDF(format="A4")
    pdf.add_font("Noto", "", str(FONT_DIR / "NotoSans-Regular.ttf"))
    pdf.add_font("Noto", "B", str(FONT_DIR / "NotoSans-Bold.ttf"))
    pdf.set_margins(18, 16, 18)
    pdf.set_auto_page_break(True, 18)
    pdf.add_page()

    pdf.set_font("Noto", "B", 20)
    pdf.set_text_color(*INDIGO)
    pdf.cell(0, 10, "NAZARDA", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Noto", "B", 15)
    pdf.set_text_color(*INK)
    pdf.cell(0, 9, f"Апталық есеп: {st['full_name']}", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Noto", "", 10)
    pdf.set_text_color(*MUTED)
    pdf.multi_cell(0, 5, f"Кезең: {fmt_date_long(s)} — {fmt_date_long(e)}. Жасалған уақыты: "
                         f"{fmt_date(now().date())}, {now():%H:%M}. Есепке тек осы кезеңнің жазбалары кірді.")
    pdf.ln(2)

    def h(title: str):
        pdf.ln(3)
        pdf.set_draw_color(*LINE)
        pdf.line(pdf.l_margin, pdf.get_y(), pdf.w - pdf.r_margin, pdf.get_y())
        pdf.ln(2)
        pdf.set_font("Noto", "B", 13)
        pdf.set_text_color(*TEAL)
        pdf.cell(0, 8, title, new_x="LMARGIN", new_y="NEXT")
        pdf.set_font("Noto", "", 10.5)
        pdf.set_text_color(*INK)

    def line(text: str):
        pdf.multi_cell(0, 5.6, text, new_x="LMARGIN", new_y="NEXT")

    def empty(text: str):
        pdf.set_text_color(*MUTED)
        line(text)
        pdf.set_text_color(*INK)

    h("Оқу нәтижелері")
    res = study.results(actor, student_id, date_from=s, date_to=e)
    if res:
        for r in res:
            pct = r["score"] * 100 / r["max_score"]
            line(f"• {fmt_date(r['date'])} — {r['subject_name']}, {r['topic']} ({r['assessment_type']}): "
                 f"{r['score']}/{r['max_score']} балл, {pct:.0f}%")
    else:
        empty("Бұл аптада жаңа нәтиже енгізілмеген.")

    h("Орындалған істер мен тапсырмалар")
    done = []
    for day, items in planner.week_items(actor, student_id, start).items():
        if day <= now().date().isoformat():
            done += [(day, i) for i in items if i.status == "done" and i.tracked and i.kind == "event"]
    subs = [a for a in study.assignments_for_student(actor, student_id)
            if a["submitted_at"] and s <= a["submitted_at"][:10] <= e]
    if done or subs:
        for a in subs:
            line(f"• {fmt_date(a['submitted_at'][:10])} — тапсырма жіберілді: {a['subject_name']}, {a['title']} "
                 f"({study.assignment_state(a).lower()})")
        for day, i in done:
            line(f"• {fmt_date(day)} — {i.title} ({i.category})")
    else:
        empty("Бұл аптада орындалған деп белгіленген іс жоқ.")

    h("Жақын мерзімдер")
    upcoming = [a for a in study.assignments_for_student(actor, student_id)
                if not a["submission_id"] and now().date().isoformat() <= a["due_date"]
                <= (now().date() + timedelta(days=7)).isoformat()]
    if upcoming:
        for a in upcoming:
            line(f"• {fmt_date(a['due_date'])} — {a['subject_name']}: {a['title']}")
    else:
        empty("Алдағы 7 күнде ашық тапсырма жоқ.")

    h("Бөлісілген мақсаттар")
    shared = [g for g in goals.list_goals(actor, student_id, ("active", "paused", "done")) if g["visible_to_parent"]]
    if shared:
        bal = finance.balance(actor, student_id) if include_finance else None
        for g in shared:
            k, n = goals.step_progress(g["id"])
            txt = f"• {g['title']} — {goals.KIND_LABEL[g['kind']]}, {goals.STATUS_LABEL[g['status']].lower()}"
            if n:
                txt += f"; қадамдар: {k}/{n}"
            if bal is not None and g["kind"] == "buy":
                txt += f"; жиналды: {money(bal.by_goal.get(g['id'], 0))} / {money(g['price_tiyn'])}"
            line(txt)
    else:
        empty("Ата-анамен бөлісілген мақсат жоқ.")

    h("Мұғалімнің расталған пікірлері")
    comments = [r for r in res if r["comment"] and r["comment_confirmed"]]
    if comments:
        for r in comments:
            line(f"• {r['subject_name']}, {r['topic']}: «{r['comment']}»")
    else:
        empty("Бұл аптада пікір қалдырылмаған.")

    if include_finance:
        h("Қаржы (енгізілген деректер бойынша)")
        b = finance.balance(actor, student_id)
        line(f"Жалпы қалдық: {money(b.total)}. Мақсаттарға бөлінген: {money(b.allocated)}. "
             f"Шығынға қолжетімді: {money(b.available)}.")
        rows = finance.list_tx(actor, student_id, s, e)
        if rows:
            for t in rows:
                extra = t["category"] or (t["goal_title"] or "")
                line(f"• {fmt_date(t['date'])} — {finance.KINDS[t['kind']]}: {money(t['amount_tiyn'])}"
                     f"{' (' + extra + ')' if extra else ''}; енгізген: {t['author_name']}")
        else:
            empty("Бұл аптада қаржы операциясы жоқ.")

    return bytes(pdf.output())
