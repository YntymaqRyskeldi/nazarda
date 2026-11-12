"""Мақсаттар: сатып алу, үйрену, қол жеткізу. Қадамдар, жоспармен байланыс, ата-ана қолдауы."""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date

from core import access
from core.db import one, query, tx
from core.fmt import d, now_iso, today
from services import finance, planner

KIND_LABEL = {"buy": "Сатып алғым келеді", "learn": "Үйренгім келеді", "achieve": "Қол жеткізгім келеді"}
STATUS_LABEL = {"active": "Белсенді", "paused": "Үзілісте", "done": "Аяқталды"}


def list_goals(actor: int, student_id: int, statuses: tuple = ("active", "paused", "done")) -> list:
    access.require_family(actor, student_id)
    marks = ",".join("?" * len(statuses))
    sql = f"SELECT * FROM goals WHERE student_id = ? AND status IN ({marks})"
    if access.role(actor) == "parent":
        sql += " AND visible_to_parent = 1"   # ата-ана тек бөлісілген мақсаттарды көреді
    return query(sql + " ORDER BY status, COALESCE(target_date, '9999'), id", (student_id, *statuses))


def get_goal(actor: int, goal_id: int):
    g = one("SELECT * FROM goals WHERE id = ?", (goal_id,))
    if not g:
        raise ValueError("Мақсат табылмады.")
    access.require_family(actor, g["student_id"])
    if actor != g["student_id"] and not g["visible_to_parent"]:
        raise access.AccessDenied("Оқушы бұл мақсатпен бөліспеген.")
    return g


def steps(goal_id: int) -> list:
    return query("SELECT gs.*, (SELECT e.start_date FROM events e WHERE e.source='goal_step' AND e.source_ref=gs.id) "
                 "AS planned_date, (SELECT e.start_time FROM events e WHERE e.source='goal_step' AND "
                 "e.source_ref=gs.id) AS planned_time FROM goal_steps gs WHERE goal_id = ? ORDER BY position, id",
                 (goal_id,))


def create_goal(actor: int, kind: str, title: str, why: str, target_date: str | None, price_tiyn: int | None,
                visible: bool, step_titles: list[str], image: str = "", weekly_plan_tiyn: int | None = None) -> int:
    if access.role(actor) != "student":
        raise access.AccessDenied()
    if kind not in KIND_LABEL:
        raise ValueError("Мақсат түрін таңдаңыз.")
    if not title.strip():
        raise ValueError("Мақсат атауын жазыңыз.")
    if kind == "buy" and (not price_tiyn or price_tiyn <= 0):
        raise ValueError("Сатып алу мақсаты үшін бағаны енгізіңіз.")
    with tx() as c:
        gid = c.execute(
            "INSERT INTO goals (student_id, kind, title, image, why, target_date, price_tiyn, weekly_plan_tiyn, "
            "visible_to_parent, created_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (actor, kind, title.strip(), image, why.strip(), target_date, price_tiyn if kind == "buy" else None,
             weekly_plan_tiyn, int(visible), now_iso())).lastrowid
        for pos, s in enumerate([s.strip() for s in step_titles if s.strip()]):
            c.execute("INSERT INTO goal_steps (goal_id, title, position) VALUES (?,?,?)", (gid, s, pos))
    return gid


def update_goal(actor: int, goal_id: int, title: str, why: str, target_date: str | None, price_tiyn: int | None,
                visible: bool, weekly_plan_tiyn: int | None, image: str | None = None) -> None:
    g = get_goal(actor, goal_id)
    access.require_student_self(actor, g["student_id"])
    if not title.strip():
        raise ValueError("Мақсат атауын жазыңыз.")
    if g["kind"] == "buy" and (not price_tiyn or price_tiyn <= 0):
        raise ValueError("Бағаны енгізіңіз.")
    with tx() as c:
        c.execute("UPDATE goals SET title=?, why=?, target_date=?, price_tiyn=?, visible_to_parent=?, "
                  "weekly_plan_tiyn=?, image=COALESCE(?, image) WHERE id=?",
                  (title.strip(), why.strip(), target_date, price_tiyn if g["kind"] == "buy" else None,
                   int(visible), weekly_plan_tiyn, image, goal_id))


def set_status(actor: int, goal_id: int, status: str) -> None:
    g = get_goal(actor, goal_id)
    access.require_student_self(actor, g["student_id"])
    if status not in STATUS_LABEL:
        raise ValueError("Күй белгісіз.")
    with tx() as c:
        c.execute("UPDATE goals SET status=?, completed_at=? WHERE id=?",
                  (status, now_iso() if status == "done" else None, goal_id))


def delete_goal(actor: int, goal_id: int) -> None:
    g = get_goal(actor, goal_id)
    access.require_student_self(actor, g["student_id"])
    b = finance.balance(actor, g["student_id"])
    if b.by_goal.get(goal_id, 0) > 0:
        raise ValueError("Алдымен мақсаттағы жинақты қолжетімді қаражатқа қайтарыңыз.")
    with tx() as c:
        if c.execute("SELECT 1 FROM transactions WHERE goal_id=?", (goal_id,)).fetchone():
            raise ValueError("Бұл мақсатқа қаржы операциялары байланысқан. Өшірудің орнына «Аяқталды» "
                             "немесе «Үзілісте» күйін қойыңыз.")
        c.execute("DELETE FROM events WHERE source='goal_step' AND source_ref IN "
                  "(SELECT id FROM goal_steps WHERE goal_id=?)", (goal_id,))
        c.execute("DELETE FROM goals WHERE id=?", (goal_id,))


# ---------- Қадамдар ----------

def add_step(actor: int, goal_id: int, title: str) -> None:
    g = get_goal(actor, goal_id)
    access.require_student_self(actor, g["student_id"])
    if not title.strip():
        raise ValueError("Қадам атауын жазыңыз.")
    with tx() as c:
        pos = c.execute("SELECT COALESCE(MAX(position), -1) + 1 FROM goal_steps WHERE goal_id=?", (goal_id,)).fetchone()[0]
        c.execute("INSERT INTO goal_steps (goal_id, title, position) VALUES (?,?,?)", (goal_id, title.strip(), pos))


def toggle_step(actor: int, step_id: int, done: bool) -> None:
    """Қадамның күйі — бір ақиқат көзі (goal_steps). Жоспардағы байланысқан іс осыдан оқиды."""
    s = one("SELECT gs.*, g.student_id FROM goal_steps gs JOIN goals g ON g.id = gs.goal_id WHERE gs.id=?", (step_id,))
    if not s:
        raise ValueError("Қадам табылмады.")
    access.require_student_self(actor, s["student_id"])
    with tx() as c:
        c.execute("UPDATE goal_steps SET done=?, done_at=? WHERE id=?", (int(done), now_iso() if done else None, step_id))


def delete_step(actor: int, step_id: int) -> None:
    s = one("SELECT gs.*, g.student_id FROM goal_steps gs JOIN goals g ON g.id = gs.goal_id WHERE gs.id=?", (step_id,))
    if not s:
        return
    access.require_student_self(actor, s["student_id"])
    with tx() as c:
        c.execute("DELETE FROM events WHERE source='goal_step' AND source_ref=?", (step_id,))
        c.execute("DELETE FROM goal_steps WHERE id=?", (step_id,))


def schedule_step(actor: int, step_id: int, day: str, start_time: str, duration: int = 45) -> None:
    """Қадамды жоспарға қою. Бір қадамға бір ғана іс: қайта қойғанда күні жаңарады."""
    s = one("SELECT gs.*, g.student_id, g.title AS goal_title, g.visible_to_parent FROM goal_steps gs "
            "JOIN goals g ON g.id = gs.goal_id WHERE gs.id=?", (step_id,))
    if not s:
        raise ValueError("Қадам табылмады.")
    access.require_student_self(actor, s["student_id"])
    start_time = planner.valid_time(start_time)
    with tx() as c:
        ex = c.execute("SELECT id FROM events WHERE source='goal_step' AND source_ref=?", (step_id,)).fetchone()
        if ex:
            c.execute("UPDATE events SET start_date=?, start_time=?, duration_min=? WHERE id=?",
                      (day, start_time, duration, ex["id"]))
            c.execute("DELETE FROM occurrences WHERE event_id=?", (ex["id"],))
        else:
            planner.create_event(actor, s["student_id"], f"{s['title']} ({s['goal_title']})", "Мақсат қадамы",
                                 start_time, duration, day, None, tracked=True, optional=True,
                                 shared=bool(s["visible_to_parent"]), source="goal_step", source_ref=step_id, conn=c)


def refresh_status(step_id: int) -> None:
    """Жоспардан қадам орындалғанда шақырылады. Мақсат автоматты түрде жабылмайды —
    оқушы «Мақсатқа жеттім» батырмасын өзі басады."""
    return None


def step_progress(goal_id: int) -> tuple[int, int]:
    rows = steps(goal_id)
    return sum(1 for r in rows if r["done"]), len(rows)


# ---------- Сатып алу жоспары ----------

@dataclass
class BuyPlan:
    price: int
    saved: int
    remaining: int
    percent: float
    weeks_left: int | None
    weekly_needed: int | None
    note: str


def buy_plan(goal, saved_tiyn: int, on: date | None = None) -> BuyPlan:
    on = on or today()
    price = int(goal["price_tiyn"] or 0)
    saved = max(0, saved_tiyn)
    remaining = max(0, price - saved)
    pct = 100.0 if price and saved >= price else (saved * 100 / price if price else 0)
    weeks_left = weekly = None
    if remaining == 0:
        note = "Қажетті сома жиналды. Сатып алу шешімі — өзіңде."
    elif not goal["target_date"]:
        note = "Мерзім қойылмаған, сондықтан апталық жоспар есептелмейді."
    else:
        days = (d(goal["target_date"]) - on).days
        if days <= 0:
            note = "Қалаған күн өтіп кетті. Жаңа мерзім қойсаң, жоспар қайта есептеледі."
        else:
            weeks_left = max(1, math.ceil(days / 7))
            weekly = math.ceil(remaining / weeks_left / 100) * 100   # теңгеге дейін жоғары дөңгелектеу
            note = "Бұл — жоспар, кепілдік емес."
    return BuyPlan(price, saved, remaining, pct, weeks_left, weekly, note)


# ---------- Ата-ана: пікір және уәде ----------

def comments(actor: int, goal_id: int) -> list:
    get_goal(actor, goal_id)
    return query("SELECT gc.*, u.name AS author_name, u.role AS author_role FROM goal_comments gc "
                 "JOIN users u ON u.id = gc.author_id WHERE goal_id=? ORDER BY gc.id", (goal_id,))


def add_comment(actor: int, goal_id: int, body: str, token: str) -> None:
    get_goal(actor, goal_id)
    if not body.strip():
        raise ValueError("Пікір бос болмауы керек.")
    with tx() as c:
        c.execute("INSERT OR IGNORE INTO goal_comments (goal_id, author_id, body, created_at, token) VALUES (?,?,?,?,?)",
                  (goal_id, actor, body.strip(), now_iso(), token))


def promises(actor: int, goal_id: int) -> list:
    get_goal(actor, goal_id)
    return query("SELECT p.*, u.name AS parent_name FROM promises p JOIN users u ON u.id = p.parent_id "
                 "WHERE goal_id=? ORDER BY p.id", (goal_id,))


def add_promise(actor: int, goal_id: int, amount_tiyn: int, condition: str) -> int:
    """Уәде бөлек сақталады және балансқа ҚОСЫЛМАЙДЫ."""
    g = get_goal(actor, goal_id)
    if access.role(actor) != "parent":
        raise access.AccessDenied("Уәдені ата-ана береді.")
    if amount_tiyn <= 0:
        raise ValueError("Сома нөлден үлкен болуы керек.")
    if not condition.strip():
        raise ValueError("Шартын жазыңыз, мысалы: «30 000 ₸ жинағанда».")
    with tx() as c:
        return c.execute("INSERT INTO promises (goal_id, parent_id, amount_tiyn, condition_text, created_at) "
                         "VALUES (?,?,?,?,?)", (g["id"], actor, amount_tiyn, condition.strip(), now_iso())).lastrowid


def fulfill_promise(actor: int, promise_id: int) -> int:
    """Уәде орындалғанда ғана нақты кіріс жазылады (авторы — ата-ана)."""
    p = one("SELECT p.*, g.student_id, g.title FROM promises p JOIN goals g ON g.id = p.goal_id WHERE p.id=?",
            (promise_id,))
    if not p or p["parent_id"] != actor:
        raise access.AccessDenied()
    if p["status"] != "active":
        raise ValueError("Бұл уәде белсенді емес.")
    tid = finance.add(actor, p["student_id"], "income", p["amount_tiyn"], today().isoformat(), "Сыйлық",
                      note=f"Уәде бойынша: {p['title']}", token=f"promise-{promise_id}")
    with tx() as c:
        c.execute("UPDATE promises SET status='fulfilled', transaction_id=? WHERE id=?", (tid, promise_id))
    return tid


def cancel_promise(actor: int, promise_id: int) -> None:
    p = one("SELECT * FROM promises WHERE id=?", (promise_id,))
    if not p or p["parent_id"] != actor:
        raise access.AccessDenied()
    with tx() as c:
        c.execute("UPDATE promises SET status='cancelled' WHERE id=? AND status='active'", (promise_id,))
