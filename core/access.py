"""Қол жеткізу құқықтары. Әр сервис деректерге жүгінбес бұрын осы тексерулерді шақырады.

Батырманы жасыру — қорғаныс емес. Сондықтан құқық осы жерде, сервис деңгейінде тексеріледі.
"""
from __future__ import annotations

from core.db import one, query


class AccessDenied(PermissionError):
    def __init__(self, msg: str = "Бұл деректерді көруге рұқсат жоқ."):
        super().__init__(msg)


def user(uid: int):
    row = one("SELECT * FROM users WHERE id = ?", (uid,))
    if not row:
        raise AccessDenied("Пайдаланушы табылмады.")
    return row


def role(uid: int) -> str:
    return user(uid)["role"]


def children_of(parent_id: int) -> list:
    return query(
        "SELECT u.* FROM users u JOIN parent_links p ON p.student_id = u.id "
        "WHERE p.parent_id = ? ORDER BY u.name", (parent_id,))


def parents_of(student_id: int) -> list:
    return query(
        "SELECT u.*, p.relation FROM users u JOIN parent_links p ON p.parent_id = u.id "
        "WHERE p.student_id = ? ORDER BY u.name", (student_id,))


def is_parent_of(parent_id: int, student_id: int) -> bool:
    return one("SELECT 1 FROM parent_links WHERE parent_id = ? AND student_id = ?",
               (parent_id, student_id)) is not None


def teacher_pairs(teacher_id: int) -> list:
    return query(
        "SELECT ta.class_id, ta.subject_id, c.name AS class_name, s.name AS subject_name "
        "FROM teacher_assignments ta JOIN classes c ON c.id = ta.class_id "
        "JOIN subjects s ON s.id = ta.subject_id WHERE ta.teacher_id = ? "
        "ORDER BY c.name, s.name", (teacher_id,))


def teaches(teacher_id: int, class_id: int, subject_id: int) -> bool:
    return one("SELECT 1 FROM teacher_assignments WHERE teacher_id=? AND class_id=? AND subject_id=?",
               (teacher_id, class_id, subject_id)) is not None


def teaches_student(teacher_id: int, student_id: int, subject_id: int | None = None) -> bool:
    st = one("SELECT class_id FROM users WHERE id = ? AND role = 'student'", (student_id,))
    if not st:
        return False
    if subject_id is None:
        return one("SELECT 1 FROM teacher_assignments WHERE teacher_id=? AND class_id=?",
                   (teacher_id, st["class_id"])) is not None
    return teaches(teacher_id, st["class_id"], subject_id)


def require_student_self(actor: int, student_id: int) -> None:
    """Тек оқушының өзі (мысалы, жеке жоспар, жеке жазба)."""
    if actor != student_id:
        raise AccessDenied()


def require_family(actor: int, student_id: int) -> None:
    """Оқушының өзі немесе байланысқан ата-анасы (қаржы, бөлісілген мақсаттар)."""
    if actor == student_id:
        return
    if role(actor) == "parent" and is_parent_of(actor, student_id):
        return
    raise AccessDenied()


def require_study_view(actor: int, student_id: int, subject_id: int | None = None) -> None:
    """Оқу нәтижелері: оқушы, ата-ана немесе осы сыныпқа тағайындалған мұғалім."""
    if actor == student_id:
        return
    r = role(actor)
    if r == "parent" and is_parent_of(actor, student_id):
        return
    if r == "teacher" and teaches_student(actor, student_id, subject_id):
        return
    raise AccessDenied()


def require_teacher_of(actor: int, class_id: int, subject_id: int) -> None:
    if role(actor) != "teacher" or not teaches(actor, class_id, subject_id):
        raise AccessDenied("Бұл сынып пен пән сізге тағайындалмаған.")


def require_dialog_member(actor: int, dialog_id: int) -> None:
    if one("SELECT 1 FROM dialog_participants WHERE dialog_id = ? AND user_id = ?",
           (dialog_id, actor)) is None:
        raise AccessDenied("Сіз бұл диалогтың қатысушысы емессіз.")


def allowed_contacts(actor: int) -> list:
    """Пайдаланушы хат жаза алатын адамдар (рөлдер арасындағы рұқсат етілген жұптар)."""
    r = role(actor)
    if r == "student":
        st = user(actor)
        teachers = query(
            "SELECT DISTINCT u.* FROM users u JOIN teacher_assignments ta ON ta.teacher_id = u.id "
            "WHERE ta.class_id = ? ORDER BY u.name", (st["class_id"],))
        return list(parents_of(actor)) + list(teachers)
    if r == "parent":
        out, seen = [], set()
        for ch in children_of(actor):
            for t in query(
                "SELECT DISTINCT u.* FROM users u JOIN teacher_assignments ta ON ta.teacher_id = u.id "
                "WHERE ta.class_id = ? ORDER BY u.name", (ch["class_id"],)):
                if t["id"] not in seen:
                    seen.add(t["id"])
                    out.append(t)
        return out
    return []
