"""Қалта ақша есебі (енгізілген деректер бойынша, банк қызметі емес).

Операциялар:
  income   — кіріс (жалпы қалдықты көбейтеді)
  expense  — шығыс (жалпы қалдықты азайтады; goal_id болса — сол мақсаттың жинағынан сатып алу)
  allocate — мақсатқа бөлу (шығыс ЕМЕС: жалпы қалдық өзгермейді, қолжетімдісі азаяды)
  release  — мақсаттан қолжетімді қаражатқа қайтару

Ережелер:
  жалпы қалдық  = Σincome − Σexpense
  мақсаттағы    = Σallocate(goal) − Σrelease(goal) − Σexpense(goal)
  қолжетімді    = жалпы қалдық − Σ мақсаттағы

Инварианттар (әр өзгерістен кейін транзакция ішінде тексеріледі):
  қолжетімді ≥ 0 және әр мақсаттағы сома ≥ 0.
Бұзылса — транзакция кері қайтарылады. Сомалар тиынмен бүтін сан.
"""
from __future__ import annotations

from dataclasses import dataclass

from core import access
from core.db import one, query, tx
from core.fmt import money, now_iso

KINDS = {"income": "Кіріс", "expense": "Шығыс", "allocate": "Мақсатқа бөлу", "release": "Мақсаттан қайтару"}
EXPENSE_CATEGORIES = ["Жол", "Тамақ", "Оқу", "Демалыс", "Басқа"]
INCOME_CATEGORIES = ["Қалта ақша", "Сыйлық", "Өз табысым", "Басқа"]


@dataclass
class Balance:
    total: int
    allocated: int
    available: int
    by_goal: dict[int, int]


def compute(rows) -> Balance:
    total = 0
    by_goal: dict[int, int] = {}
    for r in rows:
        a, k, g = int(r["amount_tiyn"]), r["kind"], r["goal_id"]
        if k == "income":
            total += a
        elif k == "expense":
            total -= a
            if g:
                by_goal[g] = by_goal.get(g, 0) - a
        elif k == "allocate":
            by_goal[g] = by_goal.get(g, 0) + a
        elif k == "release":
            by_goal[g] = by_goal.get(g, 0) - a
    allocated = sum(by_goal.values())
    return Balance(total, allocated, total - allocated, by_goal)


def _check(b: Balance) -> None:
    if b.available < 0:
        raise ValueError(f"Қолжетімді қаражат жеткіліксіз (жетпейді: {money(-b.available)}). "
                         "Алдымен мақсаттан қаражат қайтарыңыз немесе соманы азайтыңыз.")
    for g, v in b.by_goal.items():
        if v < 0:
            raise ValueError("Мақсатта бұл соманы жабуға жинақ жеткіліксіз.")


def balance(actor: int, student_id: int) -> Balance:
    access.require_family(actor, student_id)
    return compute(query("SELECT kind, amount_tiyn, goal_id FROM transactions WHERE student_id = ?", (student_id,)))


def list_tx(actor: int, student_id: int, date_from: str | None = None, date_to: str | None = None) -> list:
    access.require_family(actor, student_id)
    sql = ("SELECT t.*, u.name AS author_name, u.role AS author_role, g.title AS goal_title FROM transactions t "
           "JOIN users u ON u.id = t.author_id LEFT JOIN goals g ON g.id = t.goal_id WHERE t.student_id = ?")
    p: list = [student_id]
    if date_from:
        sql += " AND t.date >= ?"
        p.append(date_from)
    if date_to:
        sql += " AND t.date <= ?"
        p.append(date_to)
    return query(sql + " ORDER BY t.date DESC, t.id DESC", p)


def _validate_args(actor: int, student_id: int, kind: str, amount: int, goal_id, category: str, c) -> None:
    if kind not in KINDS:
        raise ValueError("Операция түрі белгісіз.")
    if amount is None or amount <= 0:
        raise ValueError("Сома нөлден үлкен болуы керек.")
    r = access.role(actor)
    if r == "parent" and kind != "income":
        raise access.AccessDenied("Ата-ана тек берілген ақшаны (кірісті) жаза алады.")
    if kind in ("allocate", "release") and not goal_id:
        raise ValueError("Мақсатты таңдаңыз.")
    if goal_id:
        g = c.execute("SELECT student_id, kind FROM goals WHERE id = ?", (goal_id,)).fetchone()
        if not g or g["student_id"] != student_id:
            raise ValueError("Мақсат табылмады.")
    if kind == "expense" and category not in EXPENSE_CATEGORIES:
        raise ValueError("Шығыс санатын таңдаңыз.")


def add(actor: int, student_id: int, kind: str, amount_tiyn: int, date: str, category: str = "",
        goal_id: int | None = None, note: str = "", token: str | None = None) -> int | None:
    """Операция қосу. token бір форманы екі рет жіберуден қорғайды."""
    access.require_family(actor, student_id)
    with tx() as c:
        if token and c.execute("SELECT 1 FROM transactions WHERE token = ?", (token,)).fetchone():
            return None
        _validate_args(actor, student_id, kind, amount_tiyn, goal_id, category, c)
        tid = c.execute(
            "INSERT INTO transactions (student_id, kind, amount_tiyn, category, goal_id, note, date, author_id, "
            "created_at, token) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (student_id, kind, amount_tiyn, category, goal_id, note.strip(), date, actor, now_iso(), token)).lastrowid
        _check(compute(c.execute("SELECT kind, amount_tiyn, goal_id FROM transactions WHERE student_id = ?",
                                 (student_id,)).fetchall()))
        return tid


def update(actor: int, tx_id: int, amount_tiyn: int, date: str, category: str, note: str) -> None:
    t = one("SELECT * FROM transactions WHERE id = ?", (tx_id,))
    if not t:
        raise ValueError("Операция табылмады.")
    access.require_family(actor, t["student_id"])
    if t["author_id"] != actor:
        raise access.AccessDenied("Операцияны тек оны енгізген адам өзгерте алады.")
    with tx() as c:
        _validate_args(actor, t["student_id"], t["kind"], amount_tiyn, t["goal_id"], category, c)
        c.execute("UPDATE transactions SET amount_tiyn=?, date=?, category=?, note=? WHERE id=?",
                  (amount_tiyn, date, category, note.strip(), tx_id))
        _check(compute(c.execute("SELECT kind, amount_tiyn, goal_id FROM transactions WHERE student_id = ?",
                                 (t["student_id"],)).fetchall()))


def delete(actor: int, tx_id: int) -> None:
    t = one("SELECT * FROM transactions WHERE id = ?", (tx_id,))
    if not t:
        return
    access.require_family(actor, t["student_id"])
    if t["author_id"] != actor:
        raise access.AccessDenied("Операцияны тек оны енгізген адам өшіре алады.")
    with tx() as c:
        if c.execute("SELECT 1 FROM promises WHERE transaction_id = ?", (tx_id,)).fetchone():
            c.execute("UPDATE promises SET status='active', transaction_id=NULL WHERE transaction_id=?", (tx_id,))
        c.execute("DELETE FROM transactions WHERE id=?", (tx_id,))
        _check(compute(c.execute("SELECT kind, amount_tiyn, goal_id FROM transactions WHERE student_id = ?",
                                 (t["student_id"],)).fetchall()))


def possible_duplicate(student_id: int, amount_tiyn: int, date: str, author_id: int):
    """Ата-ана жазған кірісті оқушы қайта енгізбеуі үшін ескерту."""
    return one("SELECT t.*, u.name AS author_name FROM transactions t JOIN users u ON u.id = t.author_id "
               "WHERE t.student_id=? AND t.kind='income' AND t.amount_tiyn=? AND t.date=? AND t.author_id<>?",
               (student_id, amount_tiyn, date, author_id))


@dataclass
class PurchaseScenario:
    price: int
    available_after: int
    from_goals: int            # жинақтан алу қажет сома (0 — қажет емес)
    affordable: bool
    weeks_delay: float | None  # көрсетілген жинау қарқынымен мақсат қанша аптаға кешігеді


def purchase_scenario(b: Balance, price_tiyn: int, weekly_tiyn: int | None = None) -> PurchaseScenario:
    """«Қазір сатып алсам ше?» — тек есептеу. Нақты операция ЖАСАЛМАЙДЫ."""
    if price_tiyn <= 0:
        raise ValueError("Бағаны енгізіңіз.")
    after = b.available - price_tiyn
    from_goals = max(0, -after)
    affordable = price_tiyn <= b.total
    delay = None
    if from_goals and weekly_tiyn and weekly_tiyn > 0:
        delay = from_goals / weekly_tiyn
    return PurchaseScenario(price_tiyn, after, from_goals, affordable, delay)
