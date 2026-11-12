"""Баптаулар, күнді қорытындылау және апталық отбасылық шолу."""
from __future__ import annotations

from datetime import date, timedelta

from core import access
from core.db import one, query, tx
from core.fmt import now_iso, today, week_start
from services import planner, study

DEFAULTS = {"featured_goal_id": None, "hide_money_home": 0, "reduce_motion": 0, "celebrate": 1,
            "alert_threshold": 10}


def settings(uid: int) -> dict:
    r = one("SELECT * FROM user_settings WHERE user_id=?", (uid,))
    return dict(r) if r else {"user_id": uid, **DEFAULTS}


def save_settings(uid: int, **vals) -> None:
    cur = settings(uid)
    cur.update({k: v for k, v in vals.items() if k in DEFAULTS})
    if not 1 <= int(cur["alert_threshold"]) <= 50:
        raise ValueError("Ескерту шегі 1–50 аралығында болуы керек.")
    with tx() as c:
        c.execute("INSERT INTO user_settings (user_id, featured_goal_id, hide_money_home, reduce_motion, celebrate, "
                  "alert_threshold) VALUES (?,?,?,?,?,?) ON CONFLICT(user_id) DO UPDATE SET "
                  "featured_goal_id=excluded.featured_goal_id, hide_money_home=excluded.hide_money_home, "
                  "reduce_motion=excluded.reduce_motion, celebrate=excluded.celebrate, "
                  "alert_threshold=excluded.alert_threshold",
                  (uid, cur["featured_goal_id"], int(cur["hide_money_home"]), int(cur["reduce_motion"]),
                   int(cur["celebrate"]), int(cur["alert_threshold"])))


# ---------- Күнді қорытындылау (жеке, ата-анаға берілмейді) ----------

def day_review(actor: int, day: str) -> str:
    r = one("SELECT good_note FROM day_reviews WHERE student_id=? AND date=?", (actor, day))
    return r["good_note"] if r else ""


def save_day_review(actor: int, day: str, note: str) -> None:
    if access.role(actor) != "student":
        raise access.AccessDenied()
    with tx() as c:
        c.execute("INSERT INTO day_reviews (student_id, date, good_note) VALUES (?,?,?) "
                  "ON CONFLICT(student_id, date) DO UPDATE SET good_note=excluded.good_note", (actor, day, note.strip()))


# ---------- Апталық отбасылық шолу ----------

def agreement(actor: int, student_id: int, wk: str):
    access.require_family(actor, student_id)
    return one("SELECT a.*, u.name AS author_name FROM agreements a JOIN users u ON u.id = a.author_id "
               "WHERE student_id=? AND week_start=?", (student_id, wk))


def save_agreement(actor: int, student_id: int, wk: str, body: str) -> None:
    access.require_family(actor, student_id)
    if not body.strip():
        raise ValueError("Келісімнің мәтінін жазыңыз.")
    with tx() as c:
        c.execute("INSERT INTO agreements (student_id, week_start, body, author_id, updated_at) VALUES (?,?,?,?,?) "
                  "ON CONFLICT(student_id, week_start) DO UPDATE SET body=excluded.body, author_id=excluded.author_id, "
                  "updated_at=excluded.updated_at", (student_id, wk, body.strip(), actor, now_iso()))


def weekly_overview(actor: int, student_id: int, start: date | None = None) -> dict:
    """Тек деректерден алынған фактілер. Психологиялық қорытынды жасалмайды."""
    access.require_family(actor, student_id)
    start = start or week_start(today())
    end = start + timedelta(days=6)
    s, e = start.isoformat(), end.isoformat()
    done_items = []
    for day, items in planner.week_items(actor, student_id, start).items():
        if day > today().isoformat():
            break
        done_items += [i for i in items if i.status == "done" and i.tracked and i.kind == "event"]
    submitted = [a for a in study.assignments_for_student(actor, student_id)
                 if a["submitted_at"] and s <= a["submitted_at"][:10] <= e]
    res = study.results(actor, student_id, date_from=s, date_to=e)
    steps = query("SELECT gs.title, g.title AS goal_title, gs.done_at FROM goal_steps gs JOIN goals g ON g.id = gs.goal_id "
                  "WHERE g.student_id=? AND g.visible_to_parent=1 AND gs.done=1 AND substr(gs.done_at,1,10) BETWEEN ? AND ?",
                  (student_id, s, e))
    deadlines = [a for a in study.assignments_for_student(actor, student_id)
                 if today().isoformat() <= a["due_date"] <= (today() + timedelta(days=7)).isoformat()
                 and not a["submission_id"]]
    parent_ids = [p["id"] for p in access.parents_of(student_id)]
    help_rows = []
    if parent_ids:
        marks = ",".join("?" * len(parent_ids))
        help_rows = query(f"SELECT DISTINCT dg.* FROM dialogs dg JOIN dialog_participants dp ON dp.dialog_id = dg.id "
                          f"WHERE dg.kind='help' AND dg.student_id=? AND dp.user_id IN ({marks}) "
                          f"AND dg.status <> 'closed' ORDER BY dg.id DESC", (student_id, *parent_ids))
    return {"start": s, "end": e, "done_items": done_items, "submitted": submitted, "results": res, "steps": steps,
            "deadlines": deadlines, "help": help_rows, "agreement": agreement(actor, student_id, s)}
