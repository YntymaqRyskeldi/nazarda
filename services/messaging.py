"""Хабар алмасу: диалогтар, хабарламалар, сыныпқа хабарландыру, мұғалімнің байланыс уақыты.

Бұл — дерекқорды мерзімді түрде оқу (polling), лезде жеткізілетін realtime емес.
Байланыс уақытынан тыс жазылған хабар сақталады, бірақ мұғалімге ескерту ретінде
келесі байланыс уақыты басталғанда ғана саналады (deliver_at).
"""
from __future__ import annotations

from datetime import datetime, timedelta

from core import access
from core.db import one, query, tx
from core.fmt import TZ, WEEKDAYS_SHORT, now, now_iso

KIND_LABEL = {"student_teacher": "Оқушы — мұғалім", "parent_teacher": "Ата-ана — мұғалім",
              "support": "Баланы бірлесе қолдау", "help": "Көмек керек"}
STATUS_LABEL = {"new": "Жаңа", "in_review": "Қаралуда", "answered": "Жауап берілді", "closed": "Жабылды"}
HELP_TOPICS = ["Тақырыпты түсіндіріп берші", "Жоспар құруға көмектес", "Сатып алуды талқылайық", "Басқа"]


# ---------- Байланыс уақыты ----------

def office_hours(teacher_id: int) -> dict[int, tuple[str, str]]:
    return {r["weekday"]: (r["start_time"], r["end_time"])
            for r in query("SELECT * FROM office_hours WHERE teacher_id=? ORDER BY weekday", (teacher_id,))}


def set_office_hours(actor: int, hours: dict[int, tuple[str, str] | None]) -> None:
    if access.role(actor) != "teacher":
        raise access.AccessDenied()
    with tx() as c:
        for wd, val in hours.items():
            c.execute("DELETE FROM office_hours WHERE teacher_id=? AND weekday=?", (actor, wd))
            if val:
                s, e = val
                if s >= e:
                    raise ValueError("Байланыс уақытының басталуы аяқталуынан ерте болуы керек.")
                c.execute("INSERT INTO office_hours (teacher_id, weekday, start_time, end_time) VALUES (?,?,?,?)",
                          (actor, wd, s, e))


def hours_text(teacher_id: int) -> str:
    h = office_hours(teacher_id)
    if not h:
        return "байланыс уақыты көрсетілмеген"
    groups: list[list] = []
    for wd in sorted(h):
        if groups and groups[-1][1] == wd - 1 and groups[-1][2] == h[wd]:
            groups[-1][1] = wd
        else:
            groups.append([wd, wd, h[wd]])
    parts = []
    for a, b, (s, e) in groups:
        days = WEEKDAYS_SHORT[a] if a == b else f"{WEEKDAYS_SHORT[a]}–{WEEKDAYS_SHORT[b]}"
        parts.append(f"{days} {s}–{e}")
    return ", ".join(parts)


def within_hours(teacher_id: int, at: datetime | None = None) -> bool:
    at = at or now()
    h = office_hours(teacher_id).get(at.weekday())
    return bool(h) and h[0] <= at.strftime("%H:%M") < h[1]


def next_window(teacher_id: int, at: datetime | None = None) -> datetime | None:
    at = at or now()
    h = office_hours(teacher_id)
    if not h:
        return None
    for k in range(0, 8):
        day = (at + timedelta(days=k)).date()
        if day.weekday() in h:
            s = datetime.strptime(f"{day} {h[day.weekday()][0]}", "%Y-%m-%d %H:%M").replace(tzinfo=TZ)
            e = datetime.strptime(f"{day} {h[day.weekday()][1]}", "%Y-%m-%d %H:%M").replace(tzinfo=TZ)
            if k == 0 and at >= e:
                continue
            return max(s, at)
    return None


# ---------- Диалогтар ----------

def _can_start(actor: int, kind: str, others: list[int], student_id: int | None) -> None:
    r = access.role(actor)
    roles = {o: access.role(o) for o in others}
    if kind == "student_teacher":
        ok = r == "student" and len(others) == 1 and roles[others[0]] == "teacher" \
            and access.teaches_student(others[0], actor)
        ok = ok or (r == "teacher" and len(others) == 1 and roles[others[0]] == "student"
                    and access.teaches_student(actor, others[0]))
    elif kind == "parent_teacher":
        ok = student_id is not None and len(others) == 1
        if ok and r == "parent":
            ok = access.is_parent_of(actor, student_id) and roles[others[0]] == "teacher" \
                and access.teaches_student(others[0], student_id)
        elif ok and r == "teacher":
            ok = roles[others[0]] == "parent" and access.is_parent_of(others[0], student_id) \
                and access.teaches_student(actor, student_id)
        else:
            ok = False
    elif kind == "support":
        ok = r == "parent" and student_id is not None and access.is_parent_of(actor, student_id) \
            and student_id in others and all(
                o == student_id or (roles[o] == "teacher" and access.teaches_student(o, student_id)) for o in others)
    elif kind == "help":
        ok = r == "student" and len(others) == 1 and others[0] in [u["id"] for u in access.allowed_contacts(actor)]
    else:
        ok = False
    if not ok:
        raise access.AccessDenied("Бұл адамдармен мұндай диалог ашуға болмайды.")


def start_dialog(actor: int, kind: str, title: str, others: list[int], body: str, token: str,
                 student_id: int | None = None, subject_id: int | None = None, assignment_id: int | None = None,
                 help_topic: str | None = None) -> int:
    if not title.strip() or not body.strip():
        raise ValueError("Тақырып пен хабарды жазыңыз.")
    existing = one("SELECT dialog_id FROM messages WHERE token = ?", (token,))
    if existing:
        return existing["dialog_id"]
    _can_start(actor, kind, others, student_id)
    if kind in ("student_teacher", "help") and access.role(actor) == "student":
        student_id = actor
    with tx() as c:
        did = c.execute("INSERT INTO dialogs (kind, title, student_id, subject_id, assignment_id, help_topic, "
                        "created_by, created_at) VALUES (?,?,?,?,?,?,?,?)",
                        (kind, title.strip(), student_id, subject_id, assignment_id, help_topic, actor,
                         now_iso())).lastrowid
        for u in {actor, *others}:
            c.execute("INSERT INTO dialog_participants (dialog_id, user_id) VALUES (?,?)", (did, u))
    send(actor, did, body, token)
    return did


def send(actor: int, dialog_id: int, body: str, token: str) -> dict:
    """Хабар жіберу. Қайталанған token жаңа жол жасамайды (rerun кезінде көшірме болмайды)."""
    access.require_dialog_member(actor, dialog_id)
    if not body.strip():
        raise ValueError("Хабар бос болмауы керек.")
    dlg = one("SELECT * FROM dialogs WHERE id=?", (dialog_id,))
    if dlg["status"] == "closed" and access.role(actor) != "teacher":
        raise ValueError("Диалог жабылған. Жаңа сұрақ ашыңыз.")
    at = now()
    deliver = at
    deferred_teacher = None
    for p in query("SELECT u.id, u.role FROM dialog_participants dp JOIN users u ON u.id = dp.user_id "
                   "WHERE dp.dialog_id=? AND u.id<>?", (dialog_id, actor)):
        if p["role"] == "teacher" and not within_hours(p["id"], at):
            nw = next_window(p["id"], at)
            if nw:
                deliver = max(deliver, nw)
            deferred_teacher = p["id"]
    with tx() as c:
        cur = c.execute("INSERT OR IGNORE INTO messages (dialog_id, author_id, body, created_at, deliver_at, token) "
                        "VALUES (?,?,?,?,?,?)", (dialog_id, actor, body.strip(), at.strftime("%Y-%m-%dT%H:%M:%S"),
                                                 deliver.strftime("%Y-%m-%dT%H:%M:%S"), token))
        if cur.rowcount:
            mid = cur.lastrowid
            c.execute("UPDATE dialog_participants SET last_read_id=? WHERE dialog_id=? AND user_id=?",
                      (mid, dialog_id, actor))
            if access.role(actor) == "teacher" and dlg["status"] in ("new", "in_review"):
                c.execute("UPDATE dialogs SET status='answered' WHERE id=?", (dialog_id,))
            elif access.role(actor) != "teacher" and dlg["status"] == "answered":
                c.execute("UPDATE dialogs SET status='new' WHERE id=?", (dialog_id,))
    return {"deferred": deferred_teacher is not None,
            "hours": hours_text(deferred_teacher) if deferred_teacher else None}


def set_status(actor: int, dialog_id: int, status: str) -> None:
    access.require_dialog_member(actor, dialog_id)
    if access.role(actor) != "teacher" and status != "closed":
        raise access.AccessDenied("Сұрақтың күйін мұғалім өзгертеді.")
    if status not in STATUS_LABEL:
        raise ValueError("Күй белгісіз.")
    with tx() as c:
        c.execute("UPDATE dialogs SET status=? WHERE id=?", (status, dialog_id))


def dialogs_for(actor: int, kind: str | None = None, student_id: int | None = None) -> list:
    sql = ("SELECT dg.*, dp.last_read_id, s.name AS subject_name, st.name AS student_name, "
           "(SELECT body FROM messages m WHERE m.dialog_id = dg.id ORDER BY m.id DESC LIMIT 1) AS last_body, "
           "(SELECT created_at FROM messages m WHERE m.dialog_id = dg.id ORDER BY m.id DESC LIMIT 1) AS last_at, "
           "(SELECT COUNT(*) FROM messages m WHERE m.dialog_id = dg.id AND m.id > dp.last_read_id "
           " AND m.author_id <> ? AND (m.deliver_at <= ? OR ? = 0)) AS unread, "
           "(SELECT GROUP_CONCAT(u.name, ', ') FROM dialog_participants p2 JOIN users u ON u.id = p2.user_id "
           " WHERE p2.dialog_id = dg.id) AS members "
           "FROM dialogs dg JOIN dialog_participants dp ON dp.dialog_id = dg.id AND dp.user_id = ? "
           "LEFT JOIN subjects s ON s.id = dg.subject_id LEFT JOIN users st ON st.id = dg.student_id WHERE 1=1")
    is_teacher = 1 if access.role(actor) == "teacher" else 0
    p: list = [actor, now_iso(), is_teacher, actor]
    if kind:
        sql += " AND dg.kind = ?"
        p.append(kind)
    if student_id:
        sql += " AND dg.student_id = ?"
        p.append(student_id)
    return query(sql + " ORDER BY last_at DESC", p)


def messages(actor: int, dialog_id: int, mark_read: bool = True) -> list:
    access.require_dialog_member(actor, dialog_id)
    rows = query("SELECT m.*, u.name AS author_name, u.role AS author_role FROM messages m "
                 "JOIN users u ON u.id = m.author_id WHERE dialog_id=? ORDER BY m.id", (dialog_id,))
    if mark_read and rows:
        with tx() as c:
            c.execute("UPDATE dialog_participants SET last_read_id=MAX(last_read_id, ?) WHERE dialog_id=? AND user_id=?",
                      (rows[-1]["id"], dialog_id, actor))
            if access.role(actor) == "teacher":
                c.execute("UPDATE dialogs SET status='in_review' WHERE id=? AND status='new'", (dialog_id,))
    return rows


def participants(actor: int, dialog_id: int) -> list:
    access.require_dialog_member(actor, dialog_id)
    return query("SELECT u.* FROM dialog_participants dp JOIN users u ON u.id = dp.user_id WHERE dp.dialog_id=? "
                 "ORDER BY u.role, u.name", (dialog_id,))


def unread_count(actor: int) -> int:
    return sum(int(r["unread"]) for r in dialogs_for(actor))


def deferred_count(actor: int) -> int:
    """Мұғалім үшін: байланыс уақыты басталғанда көрсетілетін хабарлар саны."""
    r = one("SELECT COUNT(*) AS n FROM messages m JOIN dialog_participants dp ON dp.dialog_id = m.dialog_id "
            "AND dp.user_id = ? WHERE m.author_id <> ? AND m.deliver_at > ?", (actor, actor, now_iso()))
    return int(r["n"]) if r else 0


# ---------- Хабарландырулар ----------

def post_announcement(actor: int, class_id: int, subject_id: int, title: str, body: str, token: str) -> None:
    access.require_teacher_of(actor, class_id, subject_id)
    if not title.strip() or not body.strip():
        raise ValueError("Тақырып пен мәтінді жазыңыз.")
    with tx() as c:
        c.execute("INSERT OR IGNORE INTO announcements (teacher_id, class_id, subject_id, title, body, created_at, token) "
                  "VALUES (?,?,?,?,?,?,?)", (actor, class_id, subject_id, title.strip(), body.strip(), now_iso(), token))


def announcements_for(actor: int, student_id: int | None = None) -> list:
    r = access.role(actor)
    base = ("SELECT a.*, s.name AS subject_name, c.name AS class_name, u.name AS teacher_name FROM announcements a "
            "JOIN subjects s ON s.id = a.subject_id JOIN classes c ON c.id = a.class_id JOIN users u ON u.id = a.teacher_id ")
    if r == "teacher":
        return query(base + "WHERE a.teacher_id = ? ORDER BY a.id DESC", (actor,))
    sid = actor if r == "student" else student_id
    access.require_study_view(actor, sid)
    return query(base + "WHERE a.class_id = (SELECT class_id FROM users WHERE id = ?) ORDER BY a.id DESC", (sid,))
