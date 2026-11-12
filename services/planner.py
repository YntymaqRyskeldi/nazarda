"""Күн жоспары: оқиғалар, апта күндері бойынша қайталану, жеке күндердің күйі, қиылысулар.

Негізгі идея: қайталанатын оқиға бір жол (events) болып сақталады; әр нақты күннің
күйі (орындалды, бас тартылды, ауыстырылды) occurrences кестесінде (event_id, orig_date)
бойынша жазылады. Сондықтан бір күнді орындау келесі күндерге әсер етпейді.

Тапсырмалар мен мектеп сабақтары жоспарға КӨШІРІЛМЕЙДІ — олар өз кестелерінен
тұрақты кілтпен (assignment:ID, school:YYYY-MM-DD) оқылады.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

from core import access
from core.db import one, query, tx
from core.fmt import d, now, now_iso

CATEGORIES = ["Мектеп", "Үй тапсырмасы", "Курс", "Спорт", "Кітап оқу", "Тіл үйрену",
              "Үйірме", "Үй шаруасы", "Демалыс", "Мақсат қадамы", "Басқа"]
FIXED_CATEGORIES = {"Мектеп"}          # «Жеңіл күн» бұларды ауыстырмайды
STATUS_LABEL = {"planned": "Жоспарда", "done": "Орындалды", "cancelled": "Бас тартылды", "moved": "Ауыстырылды"}


@dataclass
class Item:
    key: str
    kind: str                 # event | assignment | school
    title: str
    category: str
    date: str
    start: str | None
    duration: int
    status: str = "planned"
    tracked: bool = True
    movable: bool = False
    recurring: bool = False
    event_id: int | None = None
    orig_date: str | None = None
    source: str = "manual"
    source_ref: int | None = None
    shared: bool = False
    done_at: str | None = None
    extra: dict = field(default_factory=dict)

    @property
    def end(self) -> str | None:
        if not self.start:
            return None
        t = datetime.strptime(self.start, "%H:%M") + timedelta(minutes=self.duration)
        return t.strftime("%H:%M")


def _minutes(hhmm: str) -> int:
    h, m = hhmm.split(":")
    return int(h) * 60 + int(m)


def _hhmm(mins: int) -> str:
    return f"{mins // 60:02d}:{mins % 60:02d}"


def valid_time(hhmm: str) -> str:
    try:
        t = datetime.strptime(hhmm.strip(), "%H:%M")
    except ValueError as e:
        raise ValueError("Уақытты СС:ММ түрінде жазыңыз, мысалы 17:30.") from e
    return t.strftime("%H:%M")


def _visible_events_sql(viewer_role: str) -> str:
    return " AND e.shared_with_parent = 1" if viewer_role == "parent" else ""


def day_items(actor: int, student_id: int, day: date | str, include_derived: bool = True) -> list[Item]:
    access.require_family(actor, student_id)
    day = d(day)
    ds = day.isoformat()
    wd = str(day.weekday())
    vis = _visible_events_sql(access.role(actor))
    items: list[Item] = []

    rows = query(
        "SELECT e.*, o.status AS o_status, o.new_date, o.new_time, o.done_at FROM events e "
        "LEFT JOIN occurrences o ON o.event_id = e.id AND o.orig_date = ? "
        "WHERE e.student_id = ? AND ((e.weekdays = '' AND e.start_date = ?) OR "
        "(e.weekdays <> '' AND e.start_date <= ? AND (e.end_date IS NULL OR e.end_date >= ?) "
        "AND (',' || e.weekdays || ',') LIKE ?))" + vis,
        (ds, student_id, ds, ds, ds, f"%,{wd},%"))
    for r in rows:
        if r["o_status"] == "moved" and r["new_date"] and r["new_date"] != ds:
            continue  # басқа күнге ауыстырылған
        start = r["new_time"] if r["o_status"] == "moved" and r["new_time"] else r["start_time"]
        if r["o_status"] == "moved":
            status = "done" if r["done_at"] else "planned"
        else:
            status = r["o_status"] if r["o_status"] in ("done", "cancelled") else "planned"
        items.append(_item_from_event(r, ds, ds, start, status, r["done_at"]))

    # Басқа күннен осы күнге ауыстырылған бір реттік көшірмелер
    moved = query(
        "SELECT e.*, o.orig_date, o.new_time, o.status AS o_status, o.done_at FROM occurrences o "
        "JOIN events e ON e.id = o.event_id WHERE e.student_id = ? AND o.new_date = ? AND o.status = 'moved' "
        "AND o.orig_date <> ?" + vis, (student_id, ds, ds))
    for r in moved:
        status = "done" if r["done_at"] else "planned"
        items.append(_item_from_event(r, ds, r["orig_date"], r["new_time"] or r["start_time"], status, r["done_at"]))

    # Мақсат қадамдарының күйі тек goal_steps кестесінен алынады (бір ақиқат көзі)
    step_ids = [i.source_ref for i in items if i.source == "goal_step"]
    if step_ids:
        marks = ",".join("?" * len(step_ids))
        done_steps = {r["id"]: r["done_at"] for r in query(
            f"SELECT id, done_at FROM goal_steps WHERE done = 1 AND id IN ({marks})", step_ids)}
        for i in items:
            if i.source == "goal_step":
                if i.source_ref in done_steps:
                    i.status, i.done_at = "done", done_steps[i.source_ref]
                elif i.status == "done":
                    i.status = "planned"

    if include_derived:
        st = access.user(student_id)
        lessons = query("SELECT t.*, s.name AS subject_name FROM timetable t JOIN subjects s ON s.id = t.subject_id "
                        "WHERE t.class_id = ? AND t.weekday = ? ORDER BY t.lesson_no", (st["class_id"], day.weekday()))
        if lessons:
            start, end = lessons[0]["start_time"], lessons[-1]["end_time"]
            items.append(Item(key=f"school:{ds}", kind="school", title="Мектеп", category="Мектеп", date=ds,
                              start=start, duration=_minutes(end) - _minutes(start), tracked=False,
                              extra={"lessons": [dict(x) for x in lessons]}))
        due_to = (day + timedelta(days=1)).isoformat()
        for a in query(
            "SELECT a.*, s.name AS subject_name, sb.id AS sub_id, sb.submitted_at FROM assignments a "
            "JOIN subjects s ON s.id = a.subject_id LEFT JOIN submissions sb ON sb.assignment_id = a.id "
            "AND sb.student_id = ? WHERE a.class_id = ? AND a.due_date BETWEEN ? AND ?",
                (student_id, st["class_id"], ds, due_to)):
            items.append(Item(key=f"assignment:{a['id']}", kind="assignment",
                              title=f"{a['subject_name']}: {a['title']}", category="Үй тапсырмасы", date=ds,
                              start=None, duration=45, status="done" if a["sub_id"] else "planned",
                              tracked=True, source="assignment", source_ref=a["id"], done_at=a["submitted_at"],
                              extra={"due_date": a["due_date"]}))
    items.sort(key=lambda i: (i.start is None, i.start or "", i.title))
    return items


def _item_from_event(r, ds: str, orig: str, start: str, status: str, done_at) -> Item:
    return Item(key=f"event:{r['id']}:{orig}", kind="event", title=r["title"], category=r["category"], date=ds,
                start=start, duration=r["duration_min"], status=status, tracked=bool(r["tracked"]),
                movable=bool(r["optional"]) and r["category"] not in FIXED_CATEGORIES,
                recurring=bool(r["weekdays"]), event_id=r["id"], orig_date=orig, source=r["source"],
                source_ref=r["source_ref"], shared=bool(r["shared_with_parent"]), done_at=done_at)


def progress(items: list[Item]) -> tuple[int, int]:
    """Тек бақыланатын істер есептеледі; бас тартылғандар есепке кірмейді (сәтсіздік емес)."""
    tracked = [i for i in items if i.tracked and i.status != "cancelled"]
    return sum(1 for i in tracked if i.status == "done"), len(tracked)


def next_action(items: list[Item], at: datetime | None = None) -> tuple[Item | None, str]:
    at = at or now()
    cur = at.hour * 60 + at.minute
    open_items = [i for i in items if i.status == "planned"]
    for i in open_items:
        if i.start and _minutes(i.start) <= cur < _minutes(i.start) + i.duration:
            return i, "Дәл қазір жүріп жатыр."
    timed = [i for i in open_items if i.start and _minutes(i.start) > cur]
    due = [i for i in open_items if i.kind == "assignment"]
    if due and (not timed or _minutes(timed[0].start) - cur > 60):
        a = due[0]
        when = "бүгін" if a.extra.get("due_date") == a.date else "ертең"
        return a, f"Тапсыру мерзімі — {when}. Келесі іске дейін уақыт бар."
    if timed:
        mins = _minutes(timed[0].start) - cur
        h, m = divmod(mins, 60)
        left = (f"{h} сағ {m} мин" if h else f"{m} мин")
        return timed[0], f"Келесі басталатын іс — {left} қалды."
    if due:
        return due[0], "Бүгінгі ашық тапсырма."
    return None, ""


def overlaps(items: list[Item]) -> list[tuple[Item, Item]]:
    timed = [i for i in items if i.start and i.status != "cancelled"]
    out = []
    for a_i, a in enumerate(timed):
        for b in timed[a_i + 1:]:
            if _minutes(a.start) < _minutes(b.start) + b.duration and _minutes(b.start) < _minutes(a.start) + a.duration:
                out.append((a, b))
    return out


def free_slot(items: list[Item], duration: int, after: str = "07:00", until: str = "22:00",
              ignore_key: str | None = None) -> str | None:
    busy = [(_minutes(i.start), _minutes(i.start) + i.duration) for i in items
            if i.start and i.status != "cancelled" and i.key != ignore_key]
    t = _minutes(after)
    t += (15 - t % 15) % 15
    while t + duration <= _minutes(until):
        if all(t + duration <= s or t >= e for s, e in busy):
            return _hhmm(t)
        t += 15
    return None


# ---------- Өзгерістер ----------

def _own_event(actor: int, event_id: int):
    e = one("SELECT * FROM events WHERE id = ?", (event_id,))
    if not e:
        raise ValueError("Іс табылмады.")
    access.require_student_self(actor, e["student_id"])
    return e


def create_event(actor: int, student_id: int, title: str, category: str, start_time: str, duration: int,
                 start_date: str, weekdays: list[int] | None = None, tracked: bool = True,
                 optional: bool = True, shared: bool = False, source: str = "manual",
                 source_ref: int | None = None, conn=None) -> int:
    access.require_student_self(actor, student_id)
    if not title.strip():
        raise ValueError("Іс атауын жазыңыз.")
    if duration <= 0:
        raise ValueError("Ұзақтығы нөлден үлкен болуы керек.")
    if category not in CATEGORIES:
        raise ValueError("Санатты тізімнен таңдаңыз.")
    args = (student_id, title.strip(), category, valid_time(start_time), int(duration), start_date,
            ",".join(str(w) for w in sorted(set(weekdays or []))), source, source_ref, int(tracked),
            int(optional), int(shared), actor, now_iso())
    sql = ("INSERT INTO events (student_id, title, category, start_time, duration_min, start_date, weekdays, "
           "source, source_ref, tracked, optional, shared_with_parent, created_by, created_at) "
           "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)")
    if conn is not None:
        return conn.execute(sql, args).lastrowid
    with tx() as c:
        return c.execute(sql, args).lastrowid


def set_status(actor: int, event_id: int, orig_date: str, status: str) -> None:
    """Бір нақты күннің күйін өзгертеді. Қайталанатын қатардың басқа күндері өзгермейді."""
    e = _own_event(actor, event_id)
    if status not in ("planned", "done", "cancelled"):
        raise ValueError("Белгісіз күй.")
    with tx() as c:
        ex = c.execute("SELECT * FROM occurrences WHERE event_id=? AND orig_date=?", (event_id, orig_date)).fetchone()
        done_at = now_iso() if status == "done" else None
        if ex and ex["status"] == "moved" and status != "cancelled":
            # ауыстырылған данада: орын сақталады, тек орындалғаны done_at арқылы белгіленеді
            c.execute("UPDATE occurrences SET done_at=? WHERE event_id=? AND orig_date=?",
                      (done_at, event_id, orig_date))
        else:
            c.execute("INSERT INTO occurrences (event_id, orig_date, status, done_at) VALUES (?,?,?,?) "
                      "ON CONFLICT(event_id, orig_date) DO UPDATE SET status=excluded.status, done_at=excluded.done_at",
                      (event_id, orig_date, status, done_at))
        if e["source"] == "goal_step":
            c.execute("UPDATE goal_steps SET done=?, done_at=? WHERE id=?",
                      (1 if status == "done" else 0, done_at, e["source_ref"]))
    if e["source"] == "goal_step":
        from services import goals
        goals.refresh_status(e["source_ref"])


def move_once(actor: int, event_id: int, orig_date: str, new_date: str, new_time: str) -> None:
    """«Тек осы күн»: бір дананы басқа күнге/уақытқа ауыстыру."""
    _own_event(actor, event_id)
    new_time = valid_time(new_time)
    with tx() as c:
        c.execute("INSERT INTO occurrences (event_id, orig_date, status, new_date, new_time) VALUES (?,?,?,?,?) "
                  "ON CONFLICT(event_id, orig_date) DO UPDATE SET status='moved', new_date=excluded.new_date, "
                  "new_time=excluded.new_time, done_at=NULL", (event_id, orig_date, "moved", new_date, new_time))


def move_series(actor: int, event_id: int, from_date: str, new_time: str) -> int:
    """«Келесі күндерге де»: from_date-тен бастап уақыт өзгереді, бұрынғы күндер сақталады."""
    e = _own_event(actor, event_id)
    new_time = valid_time(new_time)
    if not e["weekdays"] or e["start_date"] >= from_date:
        with tx() as c:
            c.execute("UPDATE events SET start_time=? WHERE id=?", (new_time, event_id))
        new_id = event_id
    else:
        with tx() as c:
            prev = (d(from_date) - timedelta(days=1)).isoformat()
            c.execute("UPDATE events SET end_date=? WHERE id=?", (prev, event_id))
            new_id = c.execute(
                "INSERT INTO events (student_id, title, category, start_time, duration_min, start_date, end_date, "
                "weekdays, source, source_ref, tracked, optional, shared_with_parent, created_by, created_at) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (e["student_id"], e["title"], e["category"], new_time, e["duration_min"], from_date, e["end_date"],
                 e["weekdays"], e["source"], e["source_ref"], e["tracked"], e["optional"],
                 e["shared_with_parent"], e["created_by"], now_iso())).lastrowid
            # from_date және кейінгі күндердің жеке күйлері жаңа қатарға көшеді
            c.execute("UPDATE occurrences SET event_id=? WHERE event_id=? AND orig_date >= ?",
                      (new_id, event_id, from_date))
    if e["source"] == "course":
        with tx() as c:
            c.execute("UPDATE courses SET start_time=? WHERE id=?", (new_time, e["source_ref"]))
    return new_id


def delete_event(actor: int, event_id: int) -> None:
    e = _own_event(actor, event_id)
    if e["source"] == "course":
        raise ValueError("Курс сабақтары «Курстарым» бөлімінде өзгертіледі.")
    with tx() as c:
        c.execute("DELETE FROM events WHERE id=?", (event_id,))


def light_day(actor: int, student_id: int, day: str, keep_keys: set[str]) -> int:
    """«Жеңіл күн»: таңдалмаған міндетті емес істер ертеңге ауыстырылады.
    Мектеп пен тапсырма мерзімдері өзгермейді."""
    access.require_student_self(actor, student_id)
    tomorrow = (d(day) + timedelta(days=1)).isoformat()
    moved = 0
    for i in day_items(actor, student_id, day):
        if i.kind == "event" and i.movable and i.status == "planned" and i.key not in keep_keys:
            move_once(actor, i.event_id, i.orig_date, tomorrow, i.start)
            moved += 1
    return moved


def week_items(actor: int, student_id: int, start: date) -> dict[str, list[Item]]:
    return {(start + timedelta(days=k)).isoformat(): day_items(actor, student_id, start + timedelta(days=k))
            for k in range(7)}
