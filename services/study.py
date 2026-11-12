"""Оқу: пәндер, тапсырмалар, жауаптар, тексеру, нәтижелер, өзін-өзі бағалау, қателер, жаттығулар."""
from __future__ import annotations

from core import access
from core.db import one, query, tx
from core.fmt import now_iso, today
from services import alerts

ASSESSMENT_TYPES = ["БЖБ", "ТЖБ", "Үй жұмысы", "Сабақтағы жұмыс", "Жоба"]


def subjects_for_student(student_id: int) -> list:
    st = access.user(student_id)
    return query(
        "SELECT DISTINCT s.id, s.name FROM subjects s JOIN teacher_assignments ta ON ta.subject_id = s.id "
        "WHERE ta.class_id = ? ORDER BY s.name", (st["class_id"],))


def teacher_for(class_id: int, subject_id: int):
    return one(
        "SELECT u.* FROM users u JOIN teacher_assignments ta ON ta.teacher_id = u.id "
        "WHERE ta.class_id = ? AND ta.subject_id = ?", (class_id, subject_id))


# ---------- Нәтижелер ----------

def results(actor: int, student_id: int, subject_id: int | None = None,
            date_from: str | None = None, date_to: str | None = None) -> list:
    access.require_study_view(actor, student_id, subject_id)
    sql = ("SELECT r.*, s.name AS subject_name FROM results r JOIN subjects s ON s.id = r.subject_id "
           "WHERE r.student_id = ?")
    params: list = [student_id]
    if access.role(actor) == "teacher":
        # Мұғалім тек өз пәндерінің нәтижелерін көреді
        sql += " AND r.subject_id IN (SELECT subject_id FROM teacher_assignments WHERE teacher_id=? " \
               "AND class_id=(SELECT class_id FROM users WHERE id=?))"
        params += [actor, student_id]
    if subject_id:
        sql += " AND r.subject_id = ?"
        params.append(subject_id)
    if date_from:
        sql += " AND r.date >= ?"
        params.append(date_from)
    if date_to:
        sql += " AND r.date <= ?"
        params.append(date_to)
    return query(sql + " ORDER BY r.date, r.id", params)


def add_result(actor: int, student_id: int, subject_id: int, topic: str, assessment_type: str,
               score: int, max_score: int, weight: int, date: str, comment: str = "",
               assignment_id: int | None = None) -> int:
    """Бағаны тек осы сыныпқа және пәнге тағайындалған мұғалім қояды."""
    st = access.user(student_id)
    access.require_teacher_of(actor, st["class_id"], subject_id)
    _check_score(score, max_score, weight)
    with tx() as c:
        cur = c.execute(
            "INSERT INTO results (student_id, subject_id, teacher_id, assignment_id, topic, assessment_type, "
            "score, max_score, weight, date, comment) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (student_id, subject_id, actor, assignment_id, topic.strip(), assessment_type,
             score, max_score, weight, date, comment.strip()))
        rid = cur.lastrowid
    alerts.recompute(student_id, subject_id)
    return rid


def update_result(actor: int, result_id: int, score: int, max_score: int, weight: int, comment: str) -> None:
    r = one("SELECT r.*, u.class_id FROM results r JOIN users u ON u.id = r.student_id WHERE r.id = ?",
            (result_id,))
    if not r:
        raise ValueError("Нәтиже табылмады.")
    access.require_teacher_of(actor, r["class_id"], r["subject_id"])
    _check_score(score, max_score, weight)
    with tx() as c:
        c.execute("UPDATE results SET score=?, max_score=?, weight=?, comment=? WHERE id=?",
                  (score, max_score, weight, comment.strip(), result_id))
    alerts.recompute(r["student_id"], r["subject_id"])


def delete_result(actor: int, result_id: int) -> None:
    r = one("SELECT r.*, u.class_id FROM results r JOIN users u ON u.id = r.student_id WHERE r.id = ?",
            (result_id,))
    if not r:
        return
    access.require_teacher_of(actor, r["class_id"], r["subject_id"])
    with tx() as c:
        c.execute("DELETE FROM results WHERE id = ?", (result_id,))
        if r["assignment_id"]:
            c.execute("UPDATE submissions SET status='submitted', reviewed_at=NULL "
                      "WHERE assignment_id=? AND student_id=?", (r["assignment_id"], r["student_id"]))
    alerts.recompute(r["student_id"], r["subject_id"])


def _check_score(score, max_score, weight) -> None:
    if max_score is None or max_score <= 0:
        raise ValueError("Ең жоғары балл нөлден үлкен болуы керек.")
    if score is None or score < 0:
        raise ValueError("Балл теріс болмайды.")
    if score > max_score:
        raise ValueError("Балл ең жоғары баллдан аспайды.")
    if weight is None or weight <= 0:
        raise ValueError("Салмақ нөлден үлкен болуы керек.")


# ---------- Тапсырмалар ----------

def create_assignment(actor: int, class_id: int, subject_id: int, title: str, description: str,
                      topic: str, assessment_type: str, due_date: str, max_score: int, weight: int) -> int:
    access.require_teacher_of(actor, class_id, subject_id)
    if not title.strip():
        raise ValueError("Тапсырма атауын жазыңыз.")
    _check_score(0, max_score, weight)
    with tx() as c:
        cur = c.execute(
            "INSERT INTO assignments (class_id, subject_id, teacher_id, title, description, topic, "
            "assessment_type, due_date, max_score, weight, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (class_id, subject_id, actor, title.strip(), description.strip(), topic.strip(),
             assessment_type, due_date, max_score, weight, now_iso()))
        return cur.lastrowid


def assignments_for_student(actor: int, student_id: int, only_open: bool = False) -> list:
    access.require_study_view(actor, student_id)
    st = access.user(student_id)
    sql = ("SELECT a.*, s.name AS subject_name, sb.id AS submission_id, sb.status AS sub_status, "
           "sb.body AS sub_body, sb.teacher_comment, sb.submitted_at, r.score, r.max_score AS r_max "
           "FROM assignments a JOIN subjects s ON s.id = a.subject_id "
           "LEFT JOIN submissions sb ON sb.assignment_id = a.id AND sb.student_id = ? "
           "LEFT JOIN results r ON r.assignment_id = a.id AND r.student_id = ? "
           "WHERE a.class_id = ?")
    params: list = [student_id, student_id, st["class_id"]]
    if access.role(actor) == "teacher":
        sql += " AND a.teacher_id = ?"
        params.append(actor)
    if only_open:
        sql += " AND sb.id IS NULL"
    return query(sql + " ORDER BY a.due_date, a.id", params)


def assignment_state(a) -> str:
    if a["sub_status"] == "reviewed":
        return "Тексерілді"
    if a["sub_status"] == "submitted":
        return "Жіберілді, тексеруде"
    if a["due_date"] < today().isoformat():
        return "Мерзімі өтті"
    return "Орындау керек"


def submit(actor: int, assignment_id: int, body: str) -> None:
    """Оқушы жауап жібереді. Тексерілген жауапты қайта жіберуге болмайды.
    Оқушы мәртебені 'тексерілді' деп өзі қоя алмайды."""
    a = one("SELECT * FROM assignments WHERE id = ?", (assignment_id,))
    st = access.user(actor)
    if not a or st["role"] != "student" or st["class_id"] != a["class_id"]:
        raise access.AccessDenied("Бұл тапсырма сізге берілмеген.")
    if not body.strip():
        raise ValueError("Жауап бос болмауы керек.")
    with tx() as c:
        ex = c.execute("SELECT status FROM submissions WHERE assignment_id=? AND student_id=?",
                       (assignment_id, actor)).fetchone()
        if ex and ex["status"] == "reviewed":
            raise ValueError("Жауап тексеріліп қойған. Сұрағыңыз болса, мұғалімге жазыңыз.")
        c.execute(
            "INSERT INTO submissions (assignment_id, student_id, body, submitted_at) VALUES (?,?,?,?) "
            "ON CONFLICT(assignment_id, student_id) DO UPDATE SET body=excluded.body, "
            "submitted_at=excluded.submitted_at", (assignment_id, actor, body.strip(), now_iso()))


def teacher_assignments(actor: int) -> list:
    if access.role(actor) != "teacher":
        raise access.AccessDenied()
    return query(
        "SELECT a.*, s.name AS subject_name, c.name AS class_name, "
        "(SELECT COUNT(*) FROM users u WHERE u.class_id = a.class_id AND u.role='student') AS n_students, "
        "(SELECT COUNT(*) FROM submissions sb WHERE sb.assignment_id = a.id) AS n_sub, "
        "(SELECT COUNT(*) FROM submissions sb WHERE sb.assignment_id = a.id AND sb.status='reviewed') AS n_rev "
        "FROM assignments a JOIN subjects s ON s.id = a.subject_id JOIN classes c ON c.id = a.class_id "
        "WHERE a.teacher_id = ? AND EXISTS (SELECT 1 FROM teacher_assignments ta WHERE ta.teacher_id = a.teacher_id "
        "AND ta.class_id = a.class_id AND ta.subject_id = a.subject_id) ORDER BY a.due_date DESC", (actor,))


def pending_reviews(actor: int) -> list:
    if access.role(actor) != "teacher":
        raise access.AccessDenied()
    return query(
        "SELECT sb.*, a.title, a.max_score, a.weight, a.subject_id, a.class_id, a.topic, a.assessment_type, "
        "a.due_date, u.name AS student_name, u.full_name AS student_full, s.name AS subject_name, c.name AS class_name "
        "FROM submissions sb JOIN assignments a ON a.id = sb.assignment_id JOIN users u ON u.id = sb.student_id "
        "JOIN subjects s ON s.id = a.subject_id JOIN classes c ON c.id = a.class_id "
        "JOIN teacher_assignments ta ON ta.teacher_id = ? AND ta.class_id = a.class_id AND ta.subject_id = a.subject_id "
        "WHERE sb.status = 'submitted' ORDER BY sb.submitted_at", (actor,))


def review(actor: int, submission_id: int, score: int, comment: str) -> None:
    """Жауапты тексеру: нәтиже жазылады, жауап 'тексерілді' болады, ескерту қайта есептеледі."""
    sb = one("SELECT sb.*, a.class_id, a.subject_id, a.max_score, a.weight, a.title, a.topic, a.assessment_type "
             "FROM submissions sb JOIN assignments a ON a.id = sb.assignment_id WHERE sb.id = ?",
             (submission_id,))
    if not sb:
        raise ValueError("Жауап табылмады.")
    access.require_teacher_of(actor, sb["class_id"], sb["subject_id"])
    _check_score(score, sb["max_score"], sb["weight"])
    with tx() as c:
        c.execute("UPDATE submissions SET status='reviewed', teacher_comment=?, reviewed_at=? WHERE id=?",
                  (comment.strip(), now_iso(), submission_id))
        c.execute(
            "INSERT INTO results (student_id, subject_id, teacher_id, assignment_id, topic, assessment_type, "
            "score, max_score, weight, date, comment) VALUES (?,?,?,?,?,?,?,?,?,?,?) "
            "ON CONFLICT(student_id, assignment_id) DO UPDATE SET score=excluded.score, comment=excluded.comment",
            (sb["student_id"], sb["subject_id"], actor, sb["assignment_id"], sb["topic"] or sb["title"],
             sb["assessment_type"], score, sb["max_score"], sb["weight"], today().isoformat(), comment.strip()))
    alerts.recompute(sb["student_id"], sb["subject_id"])


def class_students(actor: int, class_id: int) -> list:
    if not query("SELECT 1 FROM teacher_assignments WHERE teacher_id=? AND class_id=?", (actor, class_id)):
        raise access.AccessDenied()
    return query("SELECT * FROM users WHERE class_id = ? AND role='student' ORDER BY name", (class_id,))


def completion_share(actor: int, student_id: int, subject_id: int | None = None) -> tuple[int, int]:
    """Мерзімі келген тапсырмалардың қаншасы жіберілді (бағамен араластырылмайды)."""
    rows = [a for a in assignments_for_student(actor, student_id)
            if a["due_date"] <= today().isoformat() and (subject_id is None or a["subject_id"] == subject_id)]
    return sum(1 for a in rows if a["submission_id"]), len(rows)


# ---------- Өзін-өзі бағалау, қателер, жаттығу ----------

def add_self_assessment(actor: int, subject_id: int, value: int, note: str) -> None:
    if access.role(actor) != "student":
        raise access.AccessDenied()
    with tx() as c:
        c.execute("INSERT INTO self_assessments (student_id, subject_id, value, date, note) VALUES (?,?,?,?,?) "
                  "ON CONFLICT(student_id, subject_id, date) DO UPDATE SET value=excluded.value, note=excluded.note",
                  (actor, subject_id, value, today().isoformat(), note.strip()))


def self_assessments(actor: int, student_id: int, subject_id: int) -> list:
    access.require_family(actor, student_id)
    return query("SELECT * FROM self_assessments WHERE student_id=? AND subject_id=? ORDER BY date",
                 (student_id, subject_id))


def mistakes(actor: int, student_id: int) -> list:
    access.require_student_self(actor, student_id)
    return query("SELECT m.*, s.name AS subject_name FROM mistakes m JOIN subjects s ON s.id = m.subject_id "
                 "WHERE m.student_id = ? ORDER BY m.fixed, m.created_at DESC", (student_id,))


def add_mistake(actor: int, subject_id: int, topic: str, note: str) -> None:
    if not topic.strip() or not note.strip():
        raise ValueError("Тақырып пен түсіндірмені толтырыңыз.")
    with tx() as c:
        c.execute("INSERT INTO mistakes (student_id, subject_id, topic, note, created_at) VALUES (?,?,?,?,?)",
                  (actor, subject_id, topic.strip(), note.strip(), now_iso()))


def toggle_mistake(actor: int, mistake_id: int) -> None:
    with tx() as c:
        c.execute("UPDATE mistakes SET fixed = 1 - fixed WHERE id = ? AND student_id = ?", (mistake_id, actor))


def practice_questions(subject_id: int) -> list:
    return query("SELECT * FROM practice_questions WHERE subject_id = ? ORDER BY id", (subject_id,))


def record_practice(actor: int, subject_id: int, correct: int, total: int, token: str) -> None:
    """Жаттығу нәтижесі ресми бағаға әсер етпейді. token қайта жазылуды болдырмайды."""
    with tx() as c:
        c.execute("INSERT OR IGNORE INTO practice_attempts (student_id, subject_id, correct, total, created_at, token) "
                  "VALUES (?,?,?,?,?,?)", (actor, subject_id, correct, total, now_iso(), token))
