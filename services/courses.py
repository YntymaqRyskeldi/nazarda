"""Сыртқы курстар. Курс кестесі жоспардағы бір қайталанатын оқиғамен байланысады
(events.source='course', source_ref=course.id). Курсты өзгерткенде сол оқиға жаңарады —
жоспарда көшірме пайда болмайды."""
from __future__ import annotations

from datetime import date, timedelta

from core import access
from core.db import one, query, tx
from core.fmt import now, now_iso, today
from services import planner


def list_courses(actor: int, student_id: int) -> list:
    access.require_family(actor, student_id)
    return query("SELECT * FROM courses WHERE student_id = ? ORDER BY title", (student_id,))


def _validate(title: str, total: int, url: str, weekdays: list[int]) -> None:
    if not title.strip():
        raise ValueError("Курс атауын жазыңыз.")
    if total <= 0:
        raise ValueError("Сабақ саны нөлден үлкен болуы керек.")
    if url and not (url.startswith("https://") or url.startswith("http://")):
        raise ValueError("Сілтеме http:// немесе https:// деп басталуы керек.")
    if any(w not in range(7) for w in weekdays):
        raise ValueError("Апта күндері қате.")


def create_course(actor: int, title: str, organizer: str, url: str, weekdays: list[int], start_time: str,
                  duration: int, total: int, completed: int = 0, stage: str = "", next_task: str = "",
                  cover: str = "") -> int:
    if access.role(actor) != "student":
        raise access.AccessDenied()
    _validate(title, total, url, weekdays)
    start_time = planner.valid_time(start_time)
    with tx() as c:
        cid = c.execute(
            "INSERT INTO courses (student_id, title, cover, organizer, url, weekdays, start_time, duration_min, "
            "total_lessons, completed_lessons, stage, next_task, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (actor, title.strip(), cover, organizer.strip(), url.strip(), ",".join(map(str, sorted(set(weekdays)))),
             start_time, duration, total, min(max(completed, 0), total), stage.strip(), next_task.strip(),
             now_iso())).lastrowid
        if weekdays:
            planner.create_event(actor, actor, title, "Курс", start_time, duration, today().isoformat(),
                                 weekdays, tracked=True, optional=True, source="course", source_ref=cid, conn=c)
    return cid


def update_course(actor: int, course_id: int, **fields) -> None:
    c0 = one("SELECT * FROM courses WHERE id = ?", (course_id,))
    if not c0:
        raise ValueError("Курс табылмады.")
    access.require_student_self(actor, c0["student_id"])
    data = dict(c0)
    data.update({k: v for k, v in fields.items() if v is not None})
    weekdays = [int(x) for x in str(data["weekdays"]).split(",") if x != ""] if isinstance(data["weekdays"], str) \
        else list(data["weekdays"])
    _validate(data["title"], int(data["total_lessons"]), data["url"], weekdays)
    data["start_time"] = planner.valid_time(data["start_time"])
    completed = min(max(int(data["completed_lessons"]), 0), int(data["total_lessons"]))
    wd = ",".join(map(str, sorted(set(weekdays))))
    with tx() as c:
        c.execute("UPDATE courses SET title=?, organizer=?, url=?, weekdays=?, start_time=?, duration_min=?, "
                  "total_lessons=?, completed_lessons=?, stage=?, next_task=?, cover=? WHERE id=?",
                  (data["title"].strip(), data["organizer"], data["url"], wd, data["start_time"],
                   int(data["duration_min"]), int(data["total_lessons"]), completed, data["stage"],
                   data["next_task"], data["cover"], course_id))
        ev = c.execute("SELECT * FROM events WHERE source='course' AND source_ref=? "
                       "AND (end_date IS NULL OR end_date >= ?) ORDER BY start_date DESC", (course_id,
                                                                                            today().isoformat())).fetchall()
        if wd:
            e0 = ev[0] if ev else None
            changed = e0 is not None and (e0["start_time"], e0["duration_min"], e0["weekdays"]) != (
                data["start_time"], int(data["duration_min"]), wd)
            if e0 is not None and (not changed or e0["start_date"] >= today().isoformat()):
                c.execute("UPDATE events SET title=?, start_time=?, duration_min=?, weekdays=? WHERE id=?",
                          (data["title"].strip(), data["start_time"], int(data["duration_min"]), wd, e0["id"]))
            else:
                if e0 is not None:  # өткен сабақтар ескі уақытымен тарихта қалады
                    c.execute("UPDATE events SET end_date=? WHERE id=?",
                              ((today() - timedelta(days=1)).isoformat(), e0["id"]))
                planner.create_event(actor, actor, data["title"], "Курс", data["start_time"], int(data["duration_min"]),
                                     today().isoformat(), weekdays, source="course", source_ref=course_id, conn=c)
        else:
            for e in ev:  # кесте алынып тасталды: болашақ сабақтар жоспардан шығады, өткендер сақталады
                c.execute("UPDATE events SET end_date=? WHERE id=?",
                          ((today() - timedelta(days=1)).isoformat(), e["id"]))


def change_progress(actor: int, course_id: int, delta: int) -> None:
    c0 = one("SELECT * FROM courses WHERE id = ?", (course_id,))
    if not c0:
        raise ValueError("Курс табылмады.")
    access.require_student_self(actor, c0["student_id"])
    with tx() as c:
        c.execute("UPDATE courses SET completed_lessons = MAX(0, MIN(total_lessons, completed_lessons + ?)) "
                  "WHERE id = ?", (delta, course_id))


def delete_course(actor: int, course_id: int) -> None:
    c0 = one("SELECT * FROM courses WHERE id = ?", (course_id,))
    if not c0:
        return
    access.require_student_self(actor, c0["student_id"])
    with tx() as c:
        c.execute("DELETE FROM events WHERE source='course' AND source_ref=?", (course_id,))
        c.execute("DELETE FROM courses WHERE id=?", (course_id,))


def next_meeting(course) -> tuple[date, str] | None:
    days = [int(x) for x in course["weekdays"].split(",") if x != ""]
    if not days:
        return None
    n = now()
    for k in range(0, 8):
        day = n.date() + timedelta(days=k)
        if day.weekday() in days:
            if k == 0 and course["start_time"] <= n.strftime("%H:%M"):
                continue
            return day, course["start_time"]
    return None
