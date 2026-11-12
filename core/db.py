"""SQLite қабаты: қосылым, транзакциялар және схема.

Барлық SQL сұраулары параметрленген (? белгілері). Сандық ақша сомалары
тиынмен бүтін сан ретінде сақталады (float қолданылмайды).
"""
from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


def db_path() -> Path:
    """Дерекқор жолы. NAZARDA_DB айнымалысымен тұрақты дискке бағыттауға болады."""
    p = os.environ.get("NAZARDA_DB")
    return Path(p) if p else BASE_DIR / "data" / "nazarda.db"


def connect() -> sqlite3.Connection:
    path = db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=10, isolation_level=None)  # autocommit; транзакция tx() арқылы
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


@contextmanager
def tx():
    """Бір транзакция: қате болса бәрі кері қайтарылады."""
    conn = connect()
    try:
        conn.execute("BEGIN IMMEDIATE")
        yield conn
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise
    finally:
        conn.close()


def query(sql: str, params: tuple | list = ()) -> list[sqlite3.Row]:
    conn = connect()
    try:
        return conn.execute(sql, params).fetchall()
    finally:
        conn.close()


def one(sql: str, params: tuple | list = ()):
    rows = query(sql, params)
    return rows[0] if rows else None


SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);

CREATE TABLE IF NOT EXISTS classes (id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE);
CREATE TABLE IF NOT EXISTS subjects (id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE);

CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    full_name TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('student','parent','teacher')),
    class_id INTEGER REFERENCES classes(id),
    color TEXT NOT NULL DEFAULT '#4F46E5'
);

CREATE TABLE IF NOT EXISTS parent_links (
    parent_id INTEGER NOT NULL REFERENCES users(id),
    student_id INTEGER NOT NULL REFERENCES users(id),
    relation TEXT NOT NULL DEFAULT 'ата-ана',
    PRIMARY KEY (parent_id, student_id)
);

CREATE TABLE IF NOT EXISTS teacher_assignments (
    teacher_id INTEGER NOT NULL REFERENCES users(id),
    class_id INTEGER NOT NULL REFERENCES classes(id),
    subject_id INTEGER NOT NULL REFERENCES subjects(id),
    PRIMARY KEY (teacher_id, class_id, subject_id)
);

CREATE TABLE IF NOT EXISTS office_hours (
    id INTEGER PRIMARY KEY,
    teacher_id INTEGER NOT NULL REFERENCES users(id),
    weekday INTEGER NOT NULL CHECK (weekday BETWEEN 0 AND 6),
    start_time TEXT NOT NULL,
    end_time TEXT NOT NULL,
    UNIQUE (teacher_id, weekday)
);

CREATE TABLE IF NOT EXISTS timetable (
    id INTEGER PRIMARY KEY,
    class_id INTEGER NOT NULL REFERENCES classes(id),
    weekday INTEGER NOT NULL,
    lesson_no INTEGER NOT NULL,
    subject_id INTEGER NOT NULL REFERENCES subjects(id),
    start_time TEXT NOT NULL,
    end_time TEXT NOT NULL,
    UNIQUE (class_id, weekday, lesson_no)
);

CREATE TABLE IF NOT EXISTS assignments (
    id INTEGER PRIMARY KEY,
    class_id INTEGER NOT NULL REFERENCES classes(id),
    subject_id INTEGER NOT NULL REFERENCES subjects(id),
    teacher_id INTEGER NOT NULL REFERENCES users(id),
    title TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    topic TEXT NOT NULL DEFAULT '',
    assessment_type TEXT NOT NULL,
    due_date TEXT NOT NULL,
    max_score INTEGER NOT NULL CHECK (max_score > 0),
    weight INTEGER NOT NULL DEFAULT 1 CHECK (weight > 0),
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS submissions (
    id INTEGER PRIMARY KEY,
    assignment_id INTEGER NOT NULL REFERENCES assignments(id) ON DELETE CASCADE,
    student_id INTEGER NOT NULL REFERENCES users(id),
    body TEXT NOT NULL,
    submitted_at TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'submitted' CHECK (status IN ('submitted','reviewed')),
    teacher_comment TEXT NOT NULL DEFAULT '',
    reviewed_at TEXT,
    UNIQUE (assignment_id, student_id)
);

CREATE TABLE IF NOT EXISTS results (
    id INTEGER PRIMARY KEY,
    student_id INTEGER NOT NULL REFERENCES users(id),
    subject_id INTEGER NOT NULL REFERENCES subjects(id),
    teacher_id INTEGER NOT NULL REFERENCES users(id),
    assignment_id INTEGER REFERENCES assignments(id) ON DELETE SET NULL,
    topic TEXT NOT NULL,
    assessment_type TEXT NOT NULL,
    score INTEGER NOT NULL CHECK (score >= 0),
    max_score INTEGER NOT NULL CHECK (max_score > 0),
    weight INTEGER NOT NULL DEFAULT 1 CHECK (weight > 0),
    date TEXT NOT NULL,
    comment TEXT NOT NULL DEFAULT '',
    comment_confirmed INTEGER NOT NULL DEFAULT 1,
    CHECK (score <= max_score),
    UNIQUE (student_id, assignment_id)
);

CREATE TABLE IF NOT EXISTS self_assessments (
    id INTEGER PRIMARY KEY,
    student_id INTEGER NOT NULL REFERENCES users(id),
    subject_id INTEGER NOT NULL REFERENCES subjects(id),
    value INTEGER NOT NULL CHECK (value BETWEEN 1 AND 5),
    date TEXT NOT NULL,
    note TEXT NOT NULL DEFAULT '',
    UNIQUE (student_id, subject_id, date)
);

CREATE TABLE IF NOT EXISTS mistakes (
    id INTEGER PRIMARY KEY,
    student_id INTEGER NOT NULL REFERENCES users(id),
    subject_id INTEGER NOT NULL REFERENCES subjects(id),
    topic TEXT NOT NULL,
    note TEXT NOT NULL,
    fixed INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS practice_questions (
    id INTEGER PRIMARY KEY,
    subject_id INTEGER NOT NULL REFERENCES subjects(id),
    question TEXT NOT NULL,
    options TEXT NOT NULL,      -- '|' арқылы бөлінген
    correct INTEGER NOT NULL,
    explanation TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS practice_attempts (
    id INTEGER PRIMARY KEY,
    student_id INTEGER NOT NULL REFERENCES users(id),
    subject_id INTEGER NOT NULL REFERENCES subjects(id),
    correct INTEGER NOT NULL,
    total INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    token TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY,
    student_id INTEGER NOT NULL REFERENCES users(id),
    title TEXT NOT NULL,
    category TEXT NOT NULL,
    start_time TEXT NOT NULL,
    duration_min INTEGER NOT NULL CHECK (duration_min > 0),
    start_date TEXT NOT NULL,
    end_date TEXT,              -- қайталанатын оқиғаның соңғы күні (қоса алғанда)
    weekdays TEXT NOT NULL DEFAULT '',  -- '0,2,4' — бос болса бір реттік
    source TEXT NOT NULL DEFAULT 'manual',
    source_ref INTEGER,
    tracked INTEGER NOT NULL DEFAULT 1,
    optional INTEGER NOT NULL DEFAULT 1,
    shared_with_parent INTEGER NOT NULL DEFAULT 0,
    created_by INTEGER NOT NULL REFERENCES users(id),
    created_at TEXT NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_event_source ON events(source, source_ref, start_date)
    WHERE source IN ('course','goal_step');

CREATE TABLE IF NOT EXISTS occurrences (
    event_id INTEGER NOT NULL REFERENCES events(id) ON DELETE CASCADE,
    orig_date TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'planned' CHECK (status IN ('planned','done','cancelled','moved')),
    new_date TEXT,
    new_time TEXT,
    done_at TEXT,
    PRIMARY KEY (event_id, orig_date)
);

CREATE TABLE IF NOT EXISTS courses (
    id INTEGER PRIMARY KEY,
    student_id INTEGER NOT NULL REFERENCES users(id),
    title TEXT NOT NULL,
    cover TEXT NOT NULL DEFAULT '',
    organizer TEXT NOT NULL DEFAULT '',
    url TEXT NOT NULL DEFAULT '',
    weekdays TEXT NOT NULL DEFAULT '',
    start_time TEXT NOT NULL DEFAULT '18:00',
    duration_min INTEGER NOT NULL DEFAULT 60,
    total_lessons INTEGER NOT NULL CHECK (total_lessons > 0),
    completed_lessons INTEGER NOT NULL DEFAULT 0,
    stage TEXT NOT NULL DEFAULT '',
    next_task TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    CHECK (completed_lessons BETWEEN 0 AND total_lessons)
);

CREATE TABLE IF NOT EXISTS goals (
    id INTEGER PRIMARY KEY,
    student_id INTEGER NOT NULL REFERENCES users(id),
    kind TEXT NOT NULL CHECK (kind IN ('buy','learn','achieve')),
    title TEXT NOT NULL,
    image TEXT NOT NULL DEFAULT '',
    why TEXT NOT NULL DEFAULT '',
    target_date TEXT,
    price_tiyn INTEGER CHECK (price_tiyn IS NULL OR price_tiyn > 0),
    weekly_plan_tiyn INTEGER,
    visible_to_parent INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','paused','done')),
    created_at TEXT NOT NULL,
    completed_at TEXT
);

CREATE TABLE IF NOT EXISTS goal_steps (
    id INTEGER PRIMARY KEY,
    goal_id INTEGER NOT NULL REFERENCES goals(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    position INTEGER NOT NULL DEFAULT 0,
    done INTEGER NOT NULL DEFAULT 0,
    done_at TEXT
);

CREATE TABLE IF NOT EXISTS goal_comments (
    id INTEGER PRIMARY KEY,
    goal_id INTEGER NOT NULL REFERENCES goals(id) ON DELETE CASCADE,
    author_id INTEGER NOT NULL REFERENCES users(id),
    body TEXT NOT NULL,
    created_at TEXT NOT NULL,
    token TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS promises (
    id INTEGER PRIMARY KEY,
    goal_id INTEGER NOT NULL REFERENCES goals(id) ON DELETE CASCADE,
    parent_id INTEGER NOT NULL REFERENCES users(id),
    amount_tiyn INTEGER NOT NULL CHECK (amount_tiyn > 0),
    condition_text TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','fulfilled','cancelled')),
    transaction_id INTEGER REFERENCES transactions(id),
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS transactions (
    id INTEGER PRIMARY KEY,
    student_id INTEGER NOT NULL REFERENCES users(id),
    kind TEXT NOT NULL CHECK (kind IN ('income','expense','allocate','release')),
    amount_tiyn INTEGER NOT NULL CHECK (amount_tiyn > 0),
    category TEXT NOT NULL DEFAULT '',
    goal_id INTEGER REFERENCES goals(id),
    note TEXT NOT NULL DEFAULT '',
    date TEXT NOT NULL,
    author_id INTEGER NOT NULL REFERENCES users(id),
    created_at TEXT NOT NULL,
    token TEXT UNIQUE
);

CREATE TABLE IF NOT EXISTS dialogs (
    id INTEGER PRIMARY KEY,
    kind TEXT NOT NULL CHECK (kind IN ('student_teacher','parent_teacher','support','help')),
    title TEXT NOT NULL,
    student_id INTEGER REFERENCES users(id),
    subject_id INTEGER REFERENCES subjects(id),
    assignment_id INTEGER REFERENCES assignments(id),
    help_topic TEXT,
    status TEXT NOT NULL DEFAULT 'new' CHECK (status IN ('new','in_review','answered','closed')),
    created_by INTEGER NOT NULL REFERENCES users(id),
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS dialog_participants (
    dialog_id INTEGER NOT NULL REFERENCES dialogs(id) ON DELETE CASCADE,
    user_id INTEGER NOT NULL REFERENCES users(id),
    last_read_id INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (dialog_id, user_id)
);

CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY,
    dialog_id INTEGER NOT NULL REFERENCES dialogs(id) ON DELETE CASCADE,
    author_id INTEGER NOT NULL REFERENCES users(id),
    body TEXT NOT NULL,
    created_at TEXT NOT NULL,
    deliver_at TEXT NOT NULL,   -- мұғалімге хабарлама көрсету уақыты (байланыс уақытына дейін кейінге қалуы мүмкін)
    token TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS announcements (
    id INTEGER PRIMARY KEY,
    teacher_id INTEGER NOT NULL REFERENCES users(id),
    class_id INTEGER NOT NULL REFERENCES classes(id),
    subject_id INTEGER NOT NULL REFERENCES subjects(id),
    title TEXT NOT NULL,
    body TEXT NOT NULL,
    created_at TEXT NOT NULL,
    token TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS alerts (
    id INTEGER PRIMARY KEY,
    student_id INTEGER NOT NULL REFERENCES users(id),
    subject_id INTEGER NOT NULL REFERENCES subjects(id),
    kind TEXT NOT NULL DEFAULT 'decline',
    active INTEGER NOT NULL DEFAULT 1,
    details TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE (student_id, subject_id, kind)
);

CREATE TABLE IF NOT EXISTS day_reviews (
    student_id INTEGER NOT NULL REFERENCES users(id),
    date TEXT NOT NULL,
    good_note TEXT NOT NULL DEFAULT '',
    PRIMARY KEY (student_id, date)
);

CREATE TABLE IF NOT EXISTS agreements (
    student_id INTEGER NOT NULL REFERENCES users(id),
    week_start TEXT NOT NULL,
    body TEXT NOT NULL,
    author_id INTEGER NOT NULL REFERENCES users(id),
    updated_at TEXT NOT NULL,
    PRIMARY KEY (student_id, week_start)
);

CREATE TABLE IF NOT EXISTS user_settings (
    user_id INTEGER PRIMARY KEY REFERENCES users(id),
    featured_goal_id INTEGER REFERENCES goals(id) ON DELETE SET NULL,
    hide_money_home INTEGER NOT NULL DEFAULT 0,
    reduce_motion INTEGER NOT NULL DEFAULT 0,
    celebrate INTEGER NOT NULL DEFAULT 1,
    alert_threshold INTEGER NOT NULL DEFAULT 10
);
"""


def init_db() -> None:
    conn = connect()
    try:
        conn.executescript(SCHEMA)
    finally:
        conn.close()
