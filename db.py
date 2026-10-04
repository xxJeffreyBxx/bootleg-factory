"""SQLite task state. One file, one connection, one lock."""

import sqlite3
import threading
import time

DB_PATH = "tasks.db"

# The pipeline, in order. A task moves forward through these or falls to "failed".
STATUSES = ("queued", "imp_running", "qa_running", "pr_open", "done", "failed")

SCHEMA = """
CREATE TABLE IF NOT EXISTS tasks (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    text          TEXT    NOT NULL,
    status        TEXT    NOT NULL DEFAULT 'queued',
    slack_user    TEXT,
    slack_channel TEXT,
    slack_ts      TEXT,
    slack_thread  TEXT,
    created_at    REAL    NOT NULL,
    updated_at    REAL    NOT NULL,
    last_log      TEXT    DEFAULT '',
    worktree_path TEXT,
    branch        TEXT,
    pr_url        TEXT
);
-- One Slack message is one task, even if Slack redelivers the event.
CREATE UNIQUE INDEX IF NOT EXISTS tasks_slack_ts ON tasks(slack_ts);
"""

_lock = threading.Lock()
_conn = None


def connect():
    """Open the single shared connection. Safe to call more than once."""
    global _conn
    if _conn is None:
        _conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        _conn.row_factory = sqlite3.Row
        _conn.execute("PRAGMA journal_mode=WAL")
        _conn.executescript(SCHEMA)
        _conn.commit()
    return _conn


def _write(sql, args=()):
    """Run a write and return how many rows it touched."""
    with _lock:
        cur = connect().execute(sql, args)
        _conn.commit()
        return cur.rowcount


def _read(sql, args=()):
    with _lock:
        return connect().execute(sql, args).fetchall()


def add_task(text, user, channel, ts, thread):
    """Insert a queued task. Returns its id, or None if this ts is already a task."""
    now = time.time()
    with _lock:
        cur = connect().execute(
            "INSERT OR IGNORE INTO tasks"
            " (text, slack_user, slack_channel, slack_ts, slack_thread,"
            "  created_at, updated_at)"
            " VALUES (?,?,?,?,?,?,?)",
            (text, user, channel, ts, thread, now, now),
        )
        _conn.commit()
        return cur.lastrowid if cur.rowcount else None


def get_task(task_id):
    rows = _read("SELECT * FROM tasks WHERE id=?", (task_id,))
    return rows[0] if rows else None


def all_tasks():
    return _read("SELECT * FROM tasks ORDER BY id DESC")


def tasks_with_status(status):
    return _read("SELECT * FROM tasks WHERE status=? ORDER BY id", (status,))


def claim(task_id, want, new):
    """Move a task want -> new, but only if it is still in `want`.

    This is the whole idempotency story: the dispatcher only acts when claim()
    returns True, so a row already in imp_running/qa_running is never picked up
    twice, even if two threads look at the same instant.
    """
    return _write(
        "UPDATE tasks SET status=?, updated_at=? WHERE id=? AND status=?",
        (new, time.time(), task_id, want),
    ) == 1


def set_fields(task_id, **fields):
    """Update arbitrary columns on a task. Always bumps updated_at."""
    fields["updated_at"] = time.time()
    assigns = ", ".join(f"{k}=?" for k in fields)
    _write(
        f"UPDATE tasks SET {assigns} WHERE id=?",
        (*fields.values(), task_id),
    )

