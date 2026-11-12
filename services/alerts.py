"""Ерте ескерту — қарапайым, түсіндірілетін ереже (нейрожелі емес).

1) Бір пәннің бір бағалау түріндегі (салыстырмалы) соңғы 3 жұмысы алынады.
2) Әрқайсысы пайызға келтіріледі: score / max_score × 100.
3) Пайыздар қатарынан төмендесе ЖӘНЕ бірінші мен соңғысының айырмасы
   баптауға болатын шектен (әдепкі 10 пайыздық тармақ) кем болмаса — ескерту белсенді.

Ескерту (student, subject, kind) бойынша бір жол ретінде сақталады: қайта есептеу
көшірме жасамайды, бағаны түзеткенде шарт орындалмаса — ескерту өшеді.
"""
from __future__ import annotations

import json

from core.db import one, query, tx
from core.fmt import now_iso

DEFAULT_THRESHOLD = 10


def threshold_for(student_id: int) -> int:
    row = one("SELECT alert_threshold FROM user_settings WHERE user_id = ?", (student_id,))
    return int(row["alert_threshold"]) if row else DEFAULT_THRESHOLD


def evaluate(series: list[dict], threshold: int) -> tuple[bool, str]:
    """series — уақыт бойынша реттелген соңғы 3 жұмыс (score, max_score)."""
    if len(series) < 3:
        return False, "Салыстыруға 3 жұмыс жеткіліксіз."
    pcts = [r["score"] * 100 / r["max_score"] for r in series]
    falling = pcts[0] > pcts[1] > pcts[2]
    drop = pcts[0] - pcts[2]
    if falling and drop >= threshold:
        return True, (f"Соңғы 3 жұмыс қатарынан төмендеді: "
                      f"{pcts[0]:.0f}% → {pcts[1]:.0f}% → {pcts[2]:.0f}% "
                      f"(барлығы {drop:.0f} пайыздық тармаққа, шек — {threshold}).")
    return False, "Қатарынан төмендеу байқалмады."


def recompute(student_id: int, subject_id: int) -> None:
    thr = threshold_for(student_id)
    types = query("SELECT DISTINCT assessment_type FROM results WHERE student_id=? AND subject_id=?",
                  (student_id, subject_id))
    found = None
    for t in types:
        rows = query(
            "SELECT id, topic, score, max_score, date, assessment_type FROM results "
            "WHERE student_id=? AND subject_id=? AND assessment_type=? "
            "ORDER BY date DESC, id DESC LIMIT 3", (student_id, subject_id, t["assessment_type"]))
        series = [dict(r) for r in reversed(rows)]
        ok, reason = evaluate(series, thr)
        if ok:
            found = {"reason": reason, "type": t["assessment_type"], "results": series, "threshold": thr}
            break
    with tx() as c:
        if found:
            c.execute(
                "INSERT INTO alerts (student_id, subject_id, kind, active, details, updated_at) "
                "VALUES (?,?,'decline',1,?,?) ON CONFLICT(student_id, subject_id, kind) "
                "DO UPDATE SET active=1, details=excluded.details, updated_at=excluded.updated_at",
                (student_id, subject_id, json.dumps(found, ensure_ascii=False), now_iso()))
        else:
            c.execute("UPDATE alerts SET active=0, updated_at=? WHERE student_id=? AND subject_id=?",
                      (now_iso(), student_id, subject_id))


def recompute_all(student_id: int) -> None:
    for r in query("SELECT DISTINCT subject_id FROM results WHERE student_id = ?", (student_id,)):
        recompute(student_id, r["subject_id"])


def active_alerts(student_id: int) -> list[dict]:
    rows = query(
        "SELECT a.*, s.name AS subject_name FROM alerts a JOIN subjects s ON s.id = a.subject_id "
        "WHERE a.student_id = ? AND a.active = 1 ORDER BY s.name", (student_id,))
    out = []
    for r in rows:
        item = dict(r)
        item["details"] = json.loads(r["details"])
        out.append(item)
    return out
