"""Үлгілік есептеу. Ресми тоқсандық баға емес.

Формула: sum((score / max_score × 100) × weight) / sum(weight)

Жаңа жұмыстың сценарийі — жаңа жазбаны осы формулаға қосу арқылы есептеледі.
Салмақтар қосындысы жұмыс санымен АЛМАСТЫРЫЛМАЙДЫ.
"""
from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction


@dataclass(frozen=True)
class Work:
    score: int
    max_score: int
    weight: int = 1


def validate(w: Work) -> None:
    if w.max_score is None or w.max_score <= 0:
        raise ValueError("Ең жоғары балл нөлден үлкен болуы керек.")
    if w.score is None or w.score < 0:
        raise ValueError("Балл теріс болмайды.")
    if w.score > w.max_score:
        raise ValueError("Балл ең жоғары баллдан аспайды.")
    if w.weight is None or w.weight <= 0:
        raise ValueError("Салмақ нөлден үлкен болуы керек.")


def percent(w: Work) -> Fraction:
    validate(w)
    return Fraction(w.score * 100, w.max_score)


def weighted_percent(works: list[Work]) -> float | None:
    """Деректер жоқ болса None қайтарады. Нөл балл — дерек (0%), бос емес."""
    if not works:
        return None
    total_w = 0
    acc = Fraction(0)
    for w in works:
        acc += percent(w) * w.weight
        total_w += w.weight
    return float(acc / total_w)


@dataclass
class Forecast:
    current: float | None
    forecast: float
    change: float | None


def forecast(works: list[Work], new: Work) -> Forecast:
    validate(new)
    cur = weighted_percent(works)
    fut = weighted_percent(list(works) + [new])
    return Forecast(cur, fut, None if cur is None else fut - cur)
