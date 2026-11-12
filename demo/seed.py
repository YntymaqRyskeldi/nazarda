"""Демо деректер. Барлық адамдар мен ұйымдар — ойдан шығарылған.

Деректер бір рет жасалады (meta.seeded белгісі). Қайта іске қосу немесе rerun
көшірме жасамайды. Күндер жасалған күнге қатысты қойылады.
"""
from __future__ import annotations

from datetime import timedelta

from core.db import connect, init_db, one, tx
from core.fmt import now, now_iso, today
from services import alerts


def is_seeded() -> bool:
    init_db()
    return one("SELECT value FROM meta WHERE key='seeded'") is not None


def ensure_seeded() -> None:
    if not is_seeded():
        seed()


def reset() -> None:
    """Демо дерекқорды тазалап, қайта толтырады (тек демо режимде)."""
    conn = connect()
    try:
        tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table' "
                                             "AND name NOT LIKE 'sqlite_%'")]
        conn.execute("PRAGMA foreign_keys = OFF")
        for t in tables:
            conn.execute(f'DROP TABLE IF EXISTS "{t}"')
        conn.execute("PRAGMA foreign_keys = ON")
    finally:
        conn.close()
    init_db()
    seed()


def seed() -> None:
    T = today()
    D = lambda k: (T + timedelta(days=k)).isoformat()  # noqa: E731
    ts = lambda k, hm="10:00": f"{D(k)}T{hm}:00"         # noqa: E731
    wd = T.weekday()

    with tx() as c:
        if c.execute("SELECT 1 FROM meta WHERE key='seeded'").fetchone():
            return
        ins = lambda sql, p=(): c.execute(sql, p).lastrowid  # noqa: E731

        c8a = ins("INSERT INTO classes (name) VALUES ('8 «А»')")
        c6b = ins("INSERT INTO classes (name) VALUES ('6 «Б»')")
        subj = {n: ins("INSERT INTO subjects (name) VALUES (?)", (n,)) for n in
                ["Алгебра", "Математика", "Физика", "Ағылшын тілі", "Қазақ тілі", "Информатика"]}

        def user(name, full, role, cls=None, color="#4F46E5"):
            return ins("INSERT INTO users (name, full_name, role, class_id, color) VALUES (?,?,?,?,?)",
                       (name, full, role, cls, color))

        aidana = user("Айдана", "Айдана Серікқызы", "student", c8a, "#4F46E5")
        nurislam = user("Нұрислам", "Нұрислам Серікұлы", "student", c6b, "#0F766E")
        asel = user("Әсел", "Әсел Ахметова", "parent", None, "#B45309")
        serik = user("Серік", "Серік Нұрланов", "parent", None, "#475569")
        gulnar = user("Гүлнар Сейтқызы", "Гүлнар Сейтқызы", "teacher", None, "#7C3AED")
        erlan = user("Ерлан Мұратұлы", "Ерлан Мұратұлы", "teacher", None, "#0369A1")
        dinara = user("Динара Әбілқызы", "Динара Әбілқызы", "teacher", None, "#BE185D")
        saule = user("Сәуле Қайратқызы", "Сәуле Қайратқызы", "teacher", None, "#15803D")

        for p, s, rel in [(asel, aidana, "анасы"), (asel, nurislam, "анасы"),
                          (serik, aidana, "әкесі"), (serik, nurislam, "әкесі")]:
            ins("INSERT INTO parent_links (parent_id, student_id, relation) VALUES (?,?,?)", (p, s, rel))

        for t, cl, s in [(gulnar, c8a, "Алгебра"), (gulnar, c6b, "Математика"), (erlan, c8a, "Физика"),
                         (erlan, c8a, "Информатика"), (erlan, c6b, "Информатика"), (dinara, c8a, "Ағылшын тілі"),
                         (dinara, c6b, "Ағылшын тілі"), (saule, c8a, "Қазақ тілі"), (saule, c6b, "Қазақ тілі")]:
            ins("INSERT INTO teacher_assignments (teacher_id, class_id, subject_id) VALUES (?,?,?)", (t, cl, subj[s]))

        for t, days, s, e in [(gulnar, range(0, 5), "09:00", "18:00"), (erlan, range(0, 5), "10:00", "17:00"),
                              (erlan, [5], "10:00", "12:00"), (dinara, range(0, 4), "14:00", "19:00"),
                              (saule, range(0, 5), "09:00", "16:00")]:
            for w in days:
                ins("INSERT INTO office_hours (teacher_id, weekday, start_time, end_time) VALUES (?,?,?,?)", (t, w, s, e))

        # Сабақ кестесі (Дс–Жм)
        slots = [("08:00", "08:40"), ("08:50", "09:30"), ("09:40", "10:20"), ("10:35", "11:15"),
                 ("11:25", "12:05"), ("12:15", "12:55")]
        plan8 = [["Алгебра", "Қазақ тілі", "Физика", "Ағылшын тілі", "Информатика", "Алгебра"],
                 ["Физика", "Ағылшын тілі", "Алгебра", "Қазақ тілі", "Алгебра"],
                 ["Ағылшын тілі", "Алгебра", "Информатика", "Физика", "Қазақ тілі", "Ағылшын тілі"],
                 ["Қазақ тілі", "Физика", "Алгебра", "Ағылшын тілі", "Физика"],
                 ["Информатика", "Алгебра", "Қазақ тілі", "Ағылшын тілі", "Физика"]]
        plan6 = [["Математика", "Қазақ тілі", "Ағылшын тілі", "Информатика"],
                 ["Қазақ тілі", "Математика", "Ағылшын тілі", "Математика"],
                 ["Математика", "Информатика", "Қазақ тілі", "Ағылшын тілі"],
                 ["Ағылшын тілі", "Математика", "Қазақ тілі", "Математика"],
                 ["Математика", "Қазақ тілі", "Информатика", "Ағылшын тілі"]]
        for cl, plan in [(c8a, plan8), (c6b, plan6)]:
            for w, lessons in enumerate(plan):
                for n, s in enumerate(lessons):
                    ins("INSERT INTO timetable (class_id, weekday, lesson_no, subject_id, start_time, end_time) "
                        "VALUES (?,?,?,?,?,?)", (cl, w, n + 1, subj[s], *slots[n]))

        # ---------- Тапсырмалар ----------
        def assignment(cl, s, t, title, desc, topic, kind, due, mx, w=1, created=-7):
            return ins("INSERT INTO assignments (class_id, subject_id, teacher_id, title, description, topic, "
                       "assessment_type, due_date, max_score, weight, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                       (cl, subj[s], t, title, desc, topic, kind, due, mx, w, ts(created)))

        a_quad = assignment(c8a, "Алгебра", gulnar, "Квадрат теңдеулер: №1–10",
                            "Оқулықтағы №1–10 есептерді шығарып, шешу жолын жаз.", "Квадрат теңдеулер",
                            "Үй жұмысы", D(1), 10, 1, -2)
        a_arch = assignment(c8a, "Физика", erlan, "Архимед күші: зертханалық есеп",
                            "Тәжірибе нәтижелерін кестеге түсіріп, қорытынды жаз.", "Архимед күші",
                            "Үй жұмысы", D(3), 10, 1, -3)
        assignment(c8a, "Ағылшын тілі", dinara, "Essay: My favourite place",
                   "120–150 сөзден тұратын эссе жаз.", "Writing", "Үй жұмысы", D(5), 10, 1, -1)
        a_poly = assignment(c8a, "Алгебра", gulnar, "Көпмүшелерді көбейткіштерге жіктеу",
                            "№45–52 есептер.", "Көпмүшелер", "Үй жұмысы", D(-6), 10, 1, -12)
        a_flow = assignment(c6b, "Информатика", erlan, "Блок-схема құру",
                            "Таңғы әрекеттеріңнің блок-схемасын сал.", "Алгоритмдер", "Үй жұмысы", D(2), 10, 1, -3)
        assignment(c6b, "Математика", gulnar, "Бөлшектерді қосу: №12–20", "Есептерді дәптерге шығар.",
                   "Жай бөлшектер", "Үй жұмысы", D(1), 10, 1, -1)

        ins("INSERT INTO submissions (assignment_id, student_id, body, submitted_at, status, teacher_comment, reviewed_at) "
            "VALUES (?,?,?,?,?,?,?)", (a_poly, aidana, "Барлық есеп шығарылды, №50-де екі тәсілмен көрсеттім.",
                                       ts(-7, "18:20"), "reviewed", "Жақсы. №50-дегі екінші тәсіл өте ұқыпты.",
                                       ts(-5, "11:00")))
        ins("INSERT INTO submissions (assignment_id, student_id, body, submitted_at) VALUES (?,?,?,?)",
            (a_arch, aidana, "Өлшеу кестесі мен қорытынды: денеге әсер ететін ығыстырушы күш көлемге тәуелді.",
             ts(-1, "19:10")))
        ins("INSERT INTO submissions (assignment_id, student_id, body, submitted_at) VALUES (?,?,?,?)",
            (a_flow, nurislam, "Блок-схема: оянамын → жуынамын → таңғы ас → сөмкені тексеремін → мектепке барамын.",
             ts(-1, "17:40")))

        # ---------- Нәтижелер ----------
        def result(st, s, t, topic, kind, score, mx, w, day, comment="", aid=None):
            ins("INSERT INTO results (student_id, subject_id, teacher_id, assignment_id, topic, assessment_type, score, "
                "max_score, weight, date, comment) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (st, subj[s], t, aid, topic, kind, score, mx, w, D(day), comment))

        for topic, sc, day, cm in [("Сызықтық теңдеулер", 14, -48, ""), ("Теңсіздіктер", 16, -27, ""),
                                   ("Көпмүшелер", 17, -6, "Өсу байқалады. Есептің шешу жолы түсінікті жазылған.")]:
            result(aidana, "Алгебра", gulnar, topic, "БЖБ", sc, 20, 2, day, cm)
        result(aidana, "Алгебра", gulnar, "Көпмүшелерді көбейткіштерге жіктеу", "Үй жұмысы", 9, 10, 1, -5,
               "Жақсы. №50-дегі екінші тәсіл өте ұқыпты.", a_poly)
        result(aidana, "Алгебра", gulnar, "Функция ұғымы", "Сабақтағы жұмыс", 8, 10, 1, -15)
        for topic, sc, day, cm in [("Қысым", 22, -45, ""), ("Атмосфералық қысым", 19, -24, ""),
                                   ("Сұйықтағы қысым", 16, -4, "Формулаларды қайталауға кеңес беремін.")]:
            result(aidana, "Физика", erlan, topic, "БЖБ", sc, 25, 2, day, cm)
        result(aidana, "Физика", erlan, "Қысым бірліктері", "Үй жұмысы", 9, 10, 1, -20)
        for topic, sc, day in [("Present Simple", 18, -40), ("Past Simple", 19, -20), ("Future forms", 18, -3)]:
            result(aidana, "Ағылшын тілі", dinara, topic, "БЖБ", sc, 20, 2, day)
        for topic, sc, day in [("Сөз таптары", 15, -35), ("Есімдік", 13, -14), ("Етістік", 16, -2)]:
            result(aidana, "Қазақ тілі", saule, topic, "БЖБ", sc, 20, 2, day)
        result(aidana, "Информатика", erlan, "Python: айнымалылар", "Сабақтағы жұмыс", 10, 10, 1, -9)
        result(aidana, "Информатика", erlan, "Python: шарттар", "Сабақтағы жұмыс", 9, 10, 1, -2)
        for topic, sc, day in [("Натурал сандар", 16, -40), ("Бөлшектер", 14, -18), ("Ондық бөлшектер", 17, -2)]:
            result(nurislam, "Математика", gulnar, topic, "БЖБ", sc, 20, 2, day)
        result(nurislam, "Ағылшын тілі", dinara, "My family", "БЖБ", 15, 20, 2, -10)
        result(nurislam, "Информатика", erlan, "Алгоритм ұғымы", "Сабақтағы жұмыс", 9, 10, 1, -6)
        result(nurislam, "Қазақ тілі", saule, "Дыбыс пен әріп", "БЖБ", 17, 20, 2, -12)

        for s, v, day in [("Физика", 3, -10), ("Физика", 2, -3), ("Алгебра", 3, -20), ("Алгебра", 4, -4)]:
            ins("INSERT INTO self_assessments (student_id, subject_id, value, date, note) VALUES (?,?,?,?,?)",
                (aidana, subj[s], v, D(day), ""))
        ins("INSERT INTO mistakes (student_id, subject_id, topic, note, created_at) VALUES (?,?,?,?,?)",
            (aidana, subj["Алгебра"], "Дискриминант", "b² − 4ac есептегенде теріс b-ның квадратын қате алдым.", ts(-6)))
        ins("INSERT INTO mistakes (student_id, subject_id, topic, note, created_at) VALUES (?,?,?,?,?)",
            (aidana, subj["Физика"], "Қысым бірліктері", "кПа-ны Па-ға аударғанда 1000-ға көбейту керек.", ts(-4)))

        for s, q, opts, ok, ex in [
            ("Алгебра", "x² − 5x + 6 = 0 теңдеуінің түбірлері қандай?", "2 және 3|−2 және −3|1 және 6", 0,
             "Виет теоремасы: түбірлердің қосындысы 5, көбейтіндісі 6. Бұл — 2 мен 3."),
            ("Алгебра", "D < 0 болса, квадрат теңдеудің нақты түбірі неше?", "Екі|Біреу|Жоқ", 2,
             "Дискриминант теріс болса, нақты түбір болмайды."),
            ("Алгебра", "(a + b)² неге тең?", "a² + b²|a² + 2ab + b²|2a + 2b", 1,
             "Қосындының квадраты: a² + 2ab + b²."),
            ("Физика", "Қысымның ХБЖ-дағы бірлігі қандай?", "Ньютон|Паскаль|Джоуль", 1,
             "1 Па = 1 Н/м²."),
            ("Физика", "Сұйықтағы қысым тереңдік артқанда қалай өзгереді?", "Артады|Кемиді|Өзгермейді", 0,
             "p = ρgh: тереңдік h артса, қысым да артады."),
            ("Физика", "Архимед күші неге тәуелді?", "Дененің массасына|Ығыстырылған сұйық көлеміне|Дененің түсіне", 1,
             "F = ρ(сұйық)·g·V(ығыстырылған)."),
        ]:
            ins("INSERT INTO practice_questions (subject_id, question, options, correct, explanation) VALUES (?,?,?,?,?)",
                (subj[s], q, opts, ok, ex))

        # ---------- Жоспар ----------
        def event(st, title, cat, start, dur, start_date, weekdays="", tracked=1, optional=1, shared=0,
                  source="manual", ref=None):
            return ins("INSERT INTO events (student_id, title, category, start_time, duration_min, start_date, weekdays, "
                       "source, source_ref, tracked, optional, shared_with_parent, created_by, created_at) "
                       "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                       (st, title, cat, start, dur, start_date, weekdays, source, ref, tracked, optional, shared, st,
                        now_iso()))

        wk = ",".join(str(x) for x in sorted({0, 2, 4, wd}))
        start_hist = D(-21)
        e_hw = event(aidana, "Үй тапсырмасы", "Үй тапсырмасы", "15:00", 90, start_hist, "0,1,2,3,4", 1, 0, 1)
        e_bb = event(aidana, "Баскетбол", "Спорт", "17:00", 90, start_hist, wk, 1, 1, 1)
        e_read = event(aidana, "Кітап оқу", "Кітап оқу", "20:00", 30, start_hist, "0,1,2,3,4,5,6", 1, 1, 0)
        event(aidana, "Ыдыс жуу", "Үй шаруасы", "20:15", 20, D(0), "", 1, 1, 0)
        event(aidana, "Демалыс: велосипед тебу", "Демалыс", "12:00", 90, start_hist, "6", 0, 1, 1)

        for k in range(1, 8):  # өткен күндердің бір бөлігі орындалған
            day = T - timedelta(days=k)
            for e, wds in [(e_hw, {0, 1, 2, 3, 4}), (e_bb, {int(x) for x in wk.split(",")}), (e_read, set(range(7)))]:
                if day.weekday() in wds and not (e == e_read and k in (2, 5)):
                    ins("INSERT INTO occurrences (event_id, orig_date, status, done_at) VALUES (?,?,?,?)",
                        (e, day.isoformat(), "done", f"{day.isoformat()}T21:00:00"))
        if wd < 5:
            ins("INSERT INTO occurrences (event_id, orig_date, status, done_at) VALUES (?,?,?,?)",
                (e_hw, D(0), "done", ts(0, "16:20")))

        # Курстар (жоспардағы бір қайталанатын оқиғамен байланысты)
        def course(st, title, org, url, days, start, dur, total, done, stage, nxt):
            cid = ins("INSERT INTO courses (student_id, title, organizer, url, weekdays, start_time, duration_min, "
                      "total_lessons, completed_lessons, stage, next_task, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                      (st, title, org, url, days, start, dur, total, done, stage, nxt, ts(-30)))
            event(st, title, "Курс", start, dur, D(-30), days, 1, 1, 1, "course", cid)
            return cid

        eng_days = ",".join(str(x) for x in sorted({1, 3, wd}))
        course(aidana, "Ағылшын тілі: сөйлеу клубы", "«Тілдер үйі» орталығы (ойдан шығарылған)",
               "https://example.com/english-club", eng_days, "19:00", 60, 12, 5, "Present Perfect",
               "Өз хоббиім туралы 2 минуттық әңгіме дайындау")
        course(aidana, "Python негіздері", "«Код мектебі» онлайн курсы (ойдан шығарылған)",
               "https://example.com/python-basics", "2,5", "18:45", 60, 16, 6, "Циклдар",
               "for циклімен көбейту кестесін шығару")
        course(nurislam, "Робототехника", "Мектептегі үйірме", "https://example.com/robotics", "5", "10:00", 90,
               10, 3, "Датчиктер", "Жарық датчигімен тәжірибе")

        n_days = ",".join(str(x) for x in sorted({0, 2, wd}))
        event(nurislam, "Футбол", "Спорт", "16:00", 90, start_hist, n_days, 1, 1, 1)
        event(nurislam, "Шахмат үйірмесі", "Үйірме", "15:00", 60, start_hist, "1,3", 1, 1, 1)
        event(nurislam, "Кітап оқу", "Кітап оқу", "20:00", 20, start_hist, "0,1,2,3,4,5,6", 1, 1, 0)
        event(nurislam, "Үй тапсырмасы", "Үй тапсырмасы", "14:30", 60, start_hist, "0,1,2,3,4", 1, 0, 1)

        # ---------- Мақсаттар ----------
        def goal(st, kind, title, why, target, price, weekly, visible, status="active", completed=None):
            return ins("INSERT INTO goals (student_id, kind, title, why, target_date, price_tiyn, weekly_plan_tiyn, "
                       "visible_to_parent, status, created_at, completed_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                       (st, kind, title, why, target, price, weekly, visible, status, ts(-40), completed))

        def steps(g, items):
            ids = []
            for pos, (title, done) in enumerate(items):
                ids.append(ins("INSERT INTO goal_steps (goal_id, title, position, done, done_at) VALUES (?,?,?,?,?)",
                               (g, title, pos, int(done), ts(-3 - pos) if done else None)))
            return ids

        g_bike = goal(aidana, "buy", "Велосипед", "Жазда мектепке және жаттығуға велосипедпен бару үшін.",
                      D(105), 60_000_00, 3_000_00, 1)
        g_guitar = goal(aidana, "learn", "Гитарада 4 аккорд үйрену", "Достарыммен бірге ән айту үшін.",
                        D(40), None, None, 1)
        st_ids = steps(g_guitar, [("Гитараны күйге келтіруді үйрену", True), ("Am және C аккордтары", True),
                                  ("G және D аккордтары", False), ("Қарапайым әнді басынан аяғына дейін ойнау", False)])
        event(aidana, "G және D аккордтары (Гитарада 4 аккорд үйрену)", "Мақсат қадамы", "18:40", 30, D(1), "",
              1, 1, 1, "goal_step", st_ids[2])
        g_alg = goal(aidana, "achieve", "Алгебрадан БЖБ-ны 85%-дан жоғары жазу", "Өзіме сенімді болу үшін.",
                     D(30), None, None, 0)
        steps(g_alg, [("Квадрат теңдеулер тақырыбын қайталау", True), ("10 жаттығу есебін шығару", False),
                      ("Мұғалімнен түсінбеген сұрақты сұрау", False)])
        goal(aidana, "achieve", "Бір айда 3 кітап оқу", "Оқуды әдетке айналдыру.", D(-12), None, None, 1,
             "done", ts(-14))
        g_ball = goal(nurislam, "buy", "Футбол добы", "Аулада ойнау үшін өз добым болсын.", D(35), 12_000_00, None, 1)
        goal(nurislam, "learn", "Шахматта 3 дебют үйрену", "Үйірмеде жарысқа қатысу үшін.", D(60), None, None, 1)

        # ---------- Қаржы (тиынмен) ----------
        def money_tx(st, kind, amount, day, cat="", g=None, note="", author=None):
            ins("INSERT INTO transactions (student_id, kind, amount_tiyn, category, goal_id, note, date, author_id, "
                "created_at) VALUES (?,?,?,?,?,?,?,?,?)",
                (st, kind, amount * 100, cat, g, note, D(day), author or st, ts(day)))

        for k in (-27, -20, -13, -6):
            money_tx(aidana, "income", 5_000, k, "Қалта ақша", note="Апталық қалта ақша", author=asel)
        money_tx(aidana, "income", 10_000, -18, "Сыйлық", note="Әжемнің сыйлығы")
        money_tx(aidana, "income", 3_000, -9, "Өз табысым", note="Көршінің итін серуендеттім")
        money_tx(aidana, "allocate", 10_000, -17, g=g_bike, note="Велосипедке")
        money_tx(aidana, "allocate", 5_000, -6, g=g_bike, note="Велосипедке")
        for amount, day, cat, note in [(1_200, -15, "Жол", "Автобус картасы"), (2_500, -12, "Тамақ", "Асхана"),
                                       (1_800, -8, "Оқу", "Дәптерлер"), (3_000, -4, "Демалыс", "Кино"),
                                       (900, -1, "Тамақ", "Шырын мен тоқаш")]:
            money_tx(aidana, "expense", amount, day, cat, note=note)
        for k in (-20, -6):
            money_tx(nurislam, "income", 3_000, k, "Қалта ақша", note="Қалта ақша", author=serik)
        money_tx(nurislam, "allocate", 4_000, -5, g=g_ball, note="Допқа")
        money_tx(nurislam, "expense", 700, -2, "Тамақ", note="Балмұздақ")

        ins("INSERT INTO promises (goal_id, parent_id, amount_tiyn, condition_text, created_at) VALUES (?,?,?,?,?)",
            (g_bike, asel, 10_000_00, "Сен 30 000 ₸ жинағанда, мен 10 000 ₸ қосамын.", ts(-10)))
        ins("INSERT INTO goal_comments (goal_id, author_id, body, created_at, token) VALUES (?,?,?,?,?)",
            (g_bike, asel, "Жоспарың түсінікті. Сенбіде дүкенге барып, бағаларды бірге салыстырайық.", ts(-3),
             "seed-gc-1"))

        # ---------- Хабарламалар ----------
        def dialog(kind, title, members, st, s=None, aid=None, status="new", topic=None, created=-2):
            did = ins("INSERT INTO dialogs (kind, title, student_id, subject_id, assignment_id, help_topic, status, "
                      "created_by, created_at) VALUES (?,?,?,?,?,?,?,?,?)",
                      (kind, title, st, subj[s] if s else None, aid, topic, status, members[0], ts(created)))
            for u in members:
                ins("INSERT INTO dialog_participants (dialog_id, user_id) VALUES (?,?)", (did, u))
            return did

        msg_n = [0]

        def msg(did, author, body, at, deliver=None, read_by=()):
            msg_n[0] += 1
            mid = ins("INSERT INTO messages (dialog_id, author_id, body, created_at, deliver_at, token) "
                      "VALUES (?,?,?,?,?,?)", (did, author, body, at, deliver or at, f"seed-m-{msg_n[0]}"))
            for u in (author, *read_by):
                c.execute("UPDATE dialog_participants SET last_read_id=? WHERE dialog_id=? AND user_id=?", (mid, did, u))

        d1 = dialog("student_teacher", "Архимед күші: 3-бөлім", [aidana, erlan], aidana, "Физика", a_arch, "new")
        msg(d1, aidana, "Сәлеметсіз бе! Есептің 3-бөлімінде тығыздықты кг/м³ бірлігімен жазу керек пе?",
            ts(-1, "21:40"), ts(0, "10:00"))
        d2 = dialog("student_teacher", "Квадрат теңдеулер: Виет теоремасы", [aidana, gulnar], aidana, "Алгебра",
                    a_quad, "answered", created=-1)
        msg(d2, aidana, "Виет теоремасын қай кезде қолданған ыңғайлы?", ts(-1, "15:30"), read_by=(gulnar,))
        msg(d2, gulnar, "a = 1 болғанда және түбірлер бүтін сан болса, тексеруге ыңғайлы. Ертең сабақта мысал "
                        "көрсетемін.", ts(-1, "16:05"))
        d3 = dialog("parent_teacher", "Айдананың алгебрадағы ілгерілеуі", [asel, gulnar], aidana, "Алгебра",
                    None, "answered", created=-5)
        msg(d3, asel, "Сәлеметсіз бе! Айдана соңғы кезде алгебраға көбірек уақыт бөліп жүр. Үйде немен көмектесе "
                      "аламыз?", ts(-5, "12:10"), read_by=(gulnar,))
        msg(d3, gulnar, "Сәлеметсіз бе! Ілгерілеу бар. Аптасына екі рет 20 минут қайталау жеткілікті. "
                        "Түсінбеген сұрақтарын сабақтан кейін сұрауына болады.", ts(-5, "14:30"), read_by=(asel,))
        d4 = dialog("support", "Айдананы физикадан қолдау", [asel, aidana, erlan], aidana, "Физика", None,
                    "in_review", created=-3)
        msg(d4, asel, "Ерлан Мұратұлы, физикадан соңғы нәтижелер төмендеп келеді. Үшеуміз бірге жоспар құрайық.",
            ts(-3, "13:00"), read_by=(erlan, aidana))
        msg(d4, erlan, "Келісемін. Айдана, «Сұйықтағы қысым» тақырыбындағы жаттығуларды бейсенбіге дейін шығарып көр.",
            ts(-3, "15:20"), read_by=(asel,))
        d5 = dialog("help", "Сатып алуды талқылайық", [aidana, asel], aidana, None, None, "new",
                    "Сатып алуды талқылайық", -1)
        msg(d5, aidana, "Анашым, велосипедке жинап жүрмін, бірақ досымның туған күніне сыйлық алғым келеді. "
                        "Жинақтан алсам ба, әлде басқа жол бар ма?", ts(-1, "20:30"))
        d6 = dialog("student_teacher", "Блок-схемадағы шарт белгісі", [nurislam, erlan], nurislam, "Информатика",
                    a_flow, "new", created=0)
        msg(d6, nurislam, "Шарт ромбпен беріледі ме, әлде тіктөртбұрышпен бе?", ts(-1, "18:15"), ts(0, "10:00"))

        for t, cl, s, title, body, day in [
            (gulnar, c8a, "Алгебра", "БЖБ келесі аптада",
             "«Квадрат теңдеулер» бөлімі бойынша БЖБ келесі сәрсенбіде. Оқулықтың 3-тарауын қайталаңыздар.", -1),
            (dinara, c8a, "Ағылшын тілі", "Эссе талаптары", "Эссе 120–150 сөз болуы керек. Қолмен жазуға болады.", -2),
            (gulnar, c6b, "Математика", "Сызғыш әкеліңіздер", "Ертеңгі сабаққа сызғыш пен транспортир керек.", 0),
        ]:
            ins("INSERT INTO announcements (teacher_id, class_id, subject_id, title, body, created_at, token) "
                "VALUES (?,?,?,?,?,?,?)", (t, cl, subj[s], title, body, ts(day, "12:00"), f"seed-a-{title}"))

        ws = (T - timedelta(days=wd)).isoformat()
        ins("INSERT INTO agreements (student_id, week_start, body, author_id, updated_at) VALUES (?,?,?,?,?)",
            (aidana, ws, "Сенбіде бірге велосипед дүкеніне барып, бағаларды салыстырамыз. Физикадан бейсенбіге дейін "
                         "жаттығуларды шығарамын.", asel, now_iso()))
        ins("INSERT INTO user_settings (user_id, featured_goal_id) VALUES (?,?)", (aidana, g_bike))
        ins("INSERT INTO user_settings (user_id, featured_goal_id) VALUES (?,?)", (nurislam, g_ball))
        c.execute("INSERT INTO meta (key, value) VALUES ('seeded', ?)", (now_iso(),))
        ids = (aidana, nurislam)

    for sid in ids:
        alerts.recompute_all(sid)
