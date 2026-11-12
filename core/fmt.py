"""Уақыт және қазақша пішімдеу (күн, ақша, сандық жалғаулар)."""
from __future__ import annotations

import os
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Asia/Almaty")

MONTHS = ["қаңтар", "ақпан", "наурыз", "сәуір", "мамыр", "маусым",
          "шілде", "тамыз", "қыркүйек", "қазан", "қараша", "желтоқсан"]
WEEKDAYS = ["дүйсенбі", "сейсенбі", "сәрсенбі", "бейсенбі", "жұма", "сенбі", "жексенбі"]
WEEKDAYS_SHORT = ["Дс", "Сс", "Ср", "Бс", "Жм", "Сб", "Жс"]


def now() -> datetime:
    """Ағымдағы уақыт (Алматы). Тест үшін NAZARDA_NOW='2026-10-01T10:00' қоюға болады."""
    fixed = os.environ.get("NAZARDA_NOW")
    if fixed:
        return datetime.fromisoformat(fixed).replace(tzinfo=TZ)
    return datetime.now(TZ)


def today() -> date:
    return now().date()


def now_iso() -> str:
    return now().strftime("%Y-%m-%dT%H:%M:%S")


def d(s: str | date) -> date:
    return s if isinstance(s, date) else date.fromisoformat(s)


def week_start(day: date) -> date:
    return day - timedelta(days=day.weekday())


def fmt_date(day: str | date, with_weekday: bool = False) -> str:
    day = d(day)
    s = f"{day.day} {MONTHS[day.month - 1]}"
    if with_weekday:
        s = f"{WEEKDAYS[day.weekday()].capitalize()}, {s}"
    return s


def fmt_date_long(day: str | date) -> str:
    day = d(day)
    return f"{day.year} жылғы {day.day} {MONTHS[day.month - 1]}"


def fmt_dt(s: str) -> str:
    dt = datetime.fromisoformat(s)
    return f"{dt.day} {MONTHS[dt.month - 1]}, {dt:%H:%M}"


def relative_day(day: str | date) -> str:
    diff = (d(day) - today()).days
    if diff == 0:
        return "бүгін"
    if diff == 1:
        return "ертең"
    if diff == -1:
        return "кеше"
    if diff > 1:
        return f"{diff} күннен кейін"
    return f"{-diff} күн бұрын"


# ---------- Ақша (тиынмен бүтін сан) ----------

def to_tiyn(value) -> int:
    """Пайдаланушы енгізген теңге сомасын тиынға айналдырады. float қолданылмайды."""
    try:
        dec = Decimal(str(value).replace(" ", "").replace(",", "."))
    except InvalidOperation as e:
        raise ValueError("Соманы сан түрінде енгізіңіз.") from e
    tiyn = dec * 100
    if tiyn != tiyn.to_integral_value():
        raise ValueError("Сома ең көбі екі ондық таңбамен енгізіледі.")
    return int(tiyn)


def money(tiyn: int | None) -> str:
    if tiyn is None:
        return "—"
    sign = "−" if tiyn < 0 else ""
    tiyn = abs(int(tiyn))
    tenge, rest = divmod(tiyn, 100)
    s = f"{tenge:,}".replace(",", " ")
    if rest:
        s += f",{rest:02d}"
    return f"{sign}{s} ₸"


# ---------- Сан жалғаулары ----------

_COLLECTIVE = {1: "і", 2: "еуі", 3: "еуі", 4: "еуі", 5: "еуі", 6: "уы", 7: "еуі", 8: "еуі", 9: "ы", 0: "ы"}


def k_of_n(k: int, n: int, noun_gen: str, verb: str) -> str:
    """'7 істің 4-еуі орындалды' сияқты сөйлем құрады.

    noun_gen — зат есімнің ілік септігі (істің, сабақтың, қадамның).
    """
    if n == 0:
        return "Әзірге ештеңе жоспарланбаған"
    if k == 0:
        neg = verb[:-2] + "ма" + verb[-2:]  # орындалды → орындалмады
        return f"{n} {noun_gen} әзірге ешқайсысы {neg}"
    if k >= n:
        return f"{n} {noun_gen} барлығы {verb}"
    return f"{n} {noun_gen} {k}-{_COLLECTIVE[k % 10]} {verb}"


def plural_days(n: int) -> str:
    return f"{n} күн"
