"""Accounts, workspaces, chats, feedback and indexing jobs, in SQLite (DATA_DIR/afrisearch.db).

Each call opens its own short-lived connection, so the functions are safe to use
from request handlers and the indexing thread alike.
"""
from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from typing import Any, Iterator

from backend import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    email TEXT NOT NULL DEFAULT '',
    name TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS users_email ON users (lower(email));
CREATE TABLE IF NOT EXISTS workspaces (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS members (
    workspace_id TEXT NOT NULL REFERENCES workspaces (id) ON DELETE CASCADE,
    user_id TEXT NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    role TEXT NOT NULL CHECK (role IN ('owner', 'member')),
    added_at TEXT NOT NULL,
    PRIMARY KEY (workspace_id, user_id)
);
CREATE TABLE IF NOT EXISTS invitations (
    workspace_id TEXT NOT NULL REFERENCES workspaces (id) ON DELETE CASCADE,
    email TEXT NOT NULL,
    invited_by TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (workspace_id, email)
);
CREATE INDEX IF NOT EXISTS invitations_by_email ON invitations (email);
CREATE TABLE IF NOT EXISTS chats (
    id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL REFERENCES workspaces (id) ON DELETE CASCADE,
    user_id TEXT NOT NULL,
    title TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS chats_by_user ON chats (workspace_id, user_id, updated_at);
CREATE TABLE IF NOT EXISTS messages (
    id TEXT PRIMARY KEY,
    chat_id TEXT NOT NULL REFERENCES chats (id) ON DELETE CASCADE,
    role TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
    content TEXT NOT NULL,
    data TEXT NOT NULL DEFAULT '{}',
    rating TEXT,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS messages_by_chat ON messages (chat_id, created_at);
CREATE TABLE IF NOT EXISTS feedback (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    workspace_id TEXT NOT NULL REFERENCES workspaces (id) ON DELETE CASCADE,
    user_id TEXT NOT NULL,
    message_id TEXT,
    rating TEXT NOT NULL CHECK (rating IN ('up', 'down')),
    question TEXT NOT NULL,
    answer TEXT,
    provider TEXT,
    comment TEXT NOT NULL DEFAULT '',
    sources TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS jobs (
    id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL REFERENCES workspaces (id) ON DELETE CASCADE,
    user_id TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('queued', 'running', 'done', 'failed')),
    progress TEXT NOT NULL DEFAULT '{}',
    result TEXT,
    error TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS jobs_by_workspace ON jobs (workspace_id, created_at);
"""

_initialized: set[str] = set()
_init_lock = threading.Lock()


def migrate(conn: sqlite3.Connection) -> None:
    """Bring databases created by earlier versions up to the current schema."""
    chat_columns = {row[1] for row in conn.execute("PRAGMA table_info(chats)")}
    if "shared" not in chat_columns:  # added in 0.3: chats shared read-only with the workspace
        conn.execute("ALTER TABLE chats ADD COLUMN shared INTEGER NOT NULL DEFAULT 0")


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def new_id() -> str:
    return uuid.uuid4().hex


@contextmanager
def connect() -> Iterator[sqlite3.Connection]:
    path = config.DATA_DIR / "afrisearch.db"
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        with _init_lock:
            if str(path) not in _initialized:
                conn.execute("PRAGMA journal_mode = WAL")  # readers don't block the writer
                conn.executescript(SCHEMA)
                migrate(conn)
                _initialized.add(str(path))
        with conn:  # commits on success, rolls back on error
            yield conn
    finally:
        conn.close()


def _row(row: sqlite3.Row | None, *json_fields: str) -> dict[str, Any] | None:
    if row is None:
        return None
    item = dict(row)
    for field in json_fields:
        if item.get(field) is not None:
            item[field] = json.loads(item[field])
    return item


# --- users and workspaces ---------------------------------------------------------

def ensure_user(user_id: str, email: str, name: str) -> None:
    """Create the user on first sight; keep email and name up to date; accept invitations."""
    with connect() as conn:
        conn.execute(
            "INSERT INTO users (id, email, name, created_at) VALUES (?, ?, ?, ?) "
            "ON CONFLICT (id) DO UPDATE SET email = excluded.email, name = excluded.name",
            (user_id, email, name, now()),
        )
        if email:
            # Invitations to this email turn into memberships the first time they sign in.
            conn.execute(
                "INSERT OR IGNORE INTO members (workspace_id, user_id, role, added_at) "
                "SELECT workspace_id, ?, 'member', ? FROM invitations WHERE email = lower(?)",
                (user_id, now(), email),
            )
            conn.execute("DELETE FROM invitations WHERE email = lower(?)", (email,))


def invite(workspace_id: str, email: str, invited_by: str) -> None:
    with connect() as conn:
        conn.execute("INSERT OR IGNORE INTO invitations VALUES (?, lower(?), ?, ?)",
                     (workspace_id, email.strip(), invited_by, now()))


def list_invitations(workspace_id: str) -> list[dict[str, Any]]:
    with connect() as conn:
        rows = conn.execute("SELECT email, created_at FROM invitations WHERE workspace_id = ? ORDER BY created_at",
                            (workspace_id,)).fetchall()
    return [dict(row) for row in rows]


def cancel_invitation(workspace_id: str, email: str) -> None:
    with connect() as conn:
        conn.execute("DELETE FROM invitations WHERE workspace_id = ? AND email = lower(?)", (workspace_id, email))


def find_user_by_email(email: str) -> dict[str, Any] | None:
    with connect() as conn:
        return _row(conn.execute("SELECT * FROM users WHERE lower(email) = lower(?)", (email.strip(),)).fetchone())


def create_workspace(name: str, owner_id: str, workspace_id: str | None = None) -> dict[str, Any]:
    workspace = {"id": workspace_id or new_id(), "name": name, "created_at": now()}
    with connect() as conn:
        conn.execute("INSERT INTO workspaces (id, name, created_at) VALUES (:id, :name, :created_at)", workspace)
        conn.execute("INSERT INTO members (workspace_id, user_id, role, added_at) VALUES (?, ?, 'owner', ?)",
                     (workspace["id"], owner_id, now()))
    return {**workspace, "role": "owner"}


def list_workspaces(user_id: str) -> list[dict[str, Any]]:
    with connect() as conn:
        rows = conn.execute(
            "SELECT w.id, w.name, w.created_at, m.role, "
            "(SELECT count(*) FROM members WHERE workspace_id = w.id) AS member_count "
            "FROM workspaces w JOIN members m ON m.workspace_id = w.id WHERE m.user_id = ? ORDER BY w.created_at",
            (user_id,),
        ).fetchall()
    return [dict(row) for row in rows]


def get_workspace(workspace_id: str, user_id: str) -> dict[str, Any] | None:
    """The workspace with the user's role, or None if the user isn't a member."""
    with connect() as conn:
        return _row(conn.execute(
            "SELECT w.id, w.name, w.created_at, m.role FROM workspaces w "
            "JOIN members m ON m.workspace_id = w.id WHERE w.id = ? AND m.user_id = ?",
            (workspace_id, user_id),
        ).fetchone())


def rename_workspace(workspace_id: str, name: str) -> None:
    with connect() as conn:
        conn.execute("UPDATE workspaces SET name = ? WHERE id = ?", (name, workspace_id))


def delete_workspace(workspace_id: str) -> None:
    with connect() as conn:
        conn.execute("DELETE FROM workspaces WHERE id = ?", (workspace_id,))


def list_members(workspace_id: str) -> list[dict[str, Any]]:
    with connect() as conn:
        rows = conn.execute(
            "SELECT u.id, u.email, u.name, m.role, m.added_at FROM members m JOIN users u ON u.id = m.user_id "
            "WHERE m.workspace_id = ? ORDER BY m.role DESC, m.added_at",
            (workspace_id,),
        ).fetchall()
    return [dict(row) for row in rows]


def add_member(workspace_id: str, user_id: str) -> None:
    with connect() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO members (workspace_id, user_id, role, added_at) VALUES (?, ?, 'member', ?)",
            (workspace_id, user_id, now()),
        )


def remove_member(workspace_id: str, user_id: str) -> None:
    with connect() as conn:
        conn.execute("DELETE FROM members WHERE workspace_id = ? AND user_id = ? AND role != 'owner'",
                     (workspace_id, user_id))


def user_data(user_id: str) -> dict[str, Any]:
    """Everything stored about a user, for export: account, memberships, chats with messages, ratings."""
    with connect() as conn:
        user = _row(conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone())
        chats = [dict(row) for row in conn.execute(
            "SELECT c.id, c.title, c.created_at, c.updated_at, w.name AS workspace FROM chats c "
            "JOIN workspaces w ON w.id = c.workspace_id WHERE c.user_id = ? ORDER BY c.created_at", (user_id,))]
        feedback = [_row(row, "sources") for row in conn.execute(
            "SELECT f.rating, f.question, f.answer, f.provider, f.comment, f.sources, f.created_at, w.name AS workspace "
            "FROM feedback f JOIN workspaces w ON w.id = f.workspace_id WHERE f.user_id = ? ORDER BY f.id", (user_id,))]
    for chat in chats:
        chat["messages"] = [{k: m[k] for k in ("role", "content", "data", "rating", "created_at")}
                            for m in list_messages(chat["id"])]
    return {"user": user, "workspaces": list_workspaces(user_id), "chats": chats, "feedback": feedback}


def delete_user(user_id: str) -> None:
    """Remove the user's chats, ratings and memberships everywhere, then the user."""
    with connect() as conn:
        conn.execute("DELETE FROM chats WHERE user_id = ?", (user_id,))  # messages go with them
        conn.execute("DELETE FROM feedback WHERE user_id = ?", (user_id,))
        conn.execute("DELETE FROM members WHERE user_id = ?", (user_id,))
        conn.execute("DELETE FROM users WHERE id = ?", (user_id,))


# --- chats and messages -------------------------------------------------------------

def create_chat(workspace_id: str, user_id: str, title: str) -> dict[str, Any]:
    chat = {"id": new_id(), "workspace_id": workspace_id, "user_id": user_id, "title": title[:120] or "New chat",
            "created_at": now(), "updated_at": now(), "shared": 0}
    with connect() as conn:
        conn.execute("INSERT INTO chats (id, workspace_id, user_id, title, created_at, updated_at, shared) "
                     "VALUES (:id, :workspace_id, :user_id, :title, :created_at, :updated_at, :shared)", chat)
    return chat


def list_chats(workspace_id: str, user_id: str, limit: int = 100) -> list[dict[str, Any]]:
    with connect() as conn:
        rows = conn.execute(
            "SELECT c.id, c.title, c.created_at, c.updated_at, c.shared, "
            "(SELECT count(*) FROM messages WHERE chat_id = c.id AND role = 'user') AS questions "
            "FROM chats c WHERE c.workspace_id = ? AND c.user_id = ? ORDER BY c.updated_at DESC LIMIT ?",
            (workspace_id, user_id, limit),
        ).fetchall()
    return [dict(row) for row in rows]


def get_chat(chat_id: str, workspace_id: str, user_id: str) -> dict[str, Any] | None:
    with connect() as conn:
        return _row(conn.execute("SELECT * FROM chats WHERE id = ? AND workspace_id = ? AND user_id = ?",
                                 (chat_id, workspace_id, user_id)).fetchone())


def get_visible_chat(chat_id: str, workspace_id: str, user_id: str) -> dict[str, Any] | None:
    """A chat the user may read: their own, or one shared with the workspace (with its owner)."""
    with connect() as conn:
        return _row(conn.execute(
            "SELECT c.*, u.name AS owner_name, u.email AS owner_email FROM chats c "
            "LEFT JOIN users u ON u.id = c.user_id "
            "WHERE c.id = ? AND c.workspace_id = ? AND (c.user_id = ? OR c.shared = 1)",
            (chat_id, workspace_id, user_id),
        ).fetchone())


def list_shared_chats(workspace_id: str, user_id: str, limit: int = 50) -> list[dict[str, Any]]:
    """Chats other members have shared with the workspace."""
    with connect() as conn:
        rows = conn.execute(
            "SELECT c.id, c.title, c.created_at, c.updated_at, u.name AS owner_name, "
            "(SELECT count(*) FROM messages WHERE chat_id = c.id AND role = 'user') AS questions "
            "FROM chats c LEFT JOIN users u ON u.id = c.user_id "
            "WHERE c.workspace_id = ? AND c.shared = 1 AND c.user_id != ? ORDER BY c.updated_at DESC LIMIT ?",
            (workspace_id, user_id, limit),
        ).fetchall()
    return [dict(row) for row in rows]


def set_chat_shared(chat_id: str, shared: bool) -> None:
    with connect() as conn:
        conn.execute("UPDATE chats SET shared = ? WHERE id = ?", (int(shared), chat_id))


def rename_chat(chat_id: str, title: str) -> None:
    with connect() as conn:
        conn.execute("UPDATE chats SET title = ? WHERE id = ?", (title[:120], chat_id))


def delete_chat(chat_id: str) -> None:
    with connect() as conn:
        conn.execute("DELETE FROM chats WHERE id = ?", (chat_id,))


def add_message(chat_id: str, role: str, content: str, data: dict[str, Any] | None = None) -> dict[str, Any]:
    message = {"id": new_id(), "chat_id": chat_id, "role": role, "content": content,
               "data": json.dumps(data or {}, ensure_ascii=False), "rating": None, "created_at": now()}
    with connect() as conn:
        conn.execute("INSERT INTO messages VALUES (:id, :chat_id, :role, :content, :data, :rating, :created_at)",
                     message)
        conn.execute("UPDATE chats SET updated_at = ? WHERE id = ?", (message["created_at"], chat_id))
    return {**message, "data": data or {}}


def list_messages(chat_id: str) -> list[dict[str, Any]]:
    with connect() as conn:
        rows = conn.execute("SELECT * FROM messages WHERE chat_id = ? ORDER BY created_at, rowid",
                            (chat_id,)).fetchall()
    return [_row(row, "data") for row in rows]


def get_message(message_id: str, workspace_id: str, user_id: str) -> dict[str, Any] | None:
    """A message in one of the user's own chats in the workspace."""
    with connect() as conn:
        return _row(conn.execute(
            "SELECT m.* FROM messages m JOIN chats c ON c.id = m.chat_id "
            "WHERE m.id = ? AND c.workspace_id = ? AND c.user_id = ?",
            (message_id, workspace_id, user_id),
        ).fetchone(), "data")


# --- feedback -------------------------------------------------------------------------

def add_feedback(workspace_id: str, user_id: str, record: dict[str, Any]) -> None:
    with connect() as conn:
        conn.execute(
            "INSERT INTO feedback (workspace_id, user_id, message_id, rating, question, answer, provider, comment, "
            "sources, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (workspace_id, user_id, record.get("message_id"), record["rating"], record["question"],
             record.get("answer"), record.get("provider"), record.get("comment", ""),
             json.dumps(record.get("sources", []), ensure_ascii=False), now()),
        )
        if record.get("message_id"):
            conn.execute("UPDATE messages SET rating = ? WHERE id = ?", (record["rating"], record["message_id"]))


def feedback_summary(workspace_id: str, limit: int = 20) -> dict[str, Any]:
    with connect() as conn:
        totals = conn.execute(
            "SELECT count(*) AS total, coalesce(sum(rating = 'up'), 0) AS up, coalesce(sum(rating = 'down'), 0) AS down "
            "FROM feedback WHERE workspace_id = ?", (workspace_id,),
        ).fetchone()
        recent = conn.execute(
            "SELECT f.rating, f.question, f.answer, f.provider, f.comment, f.sources, f.created_at AS time, "
            "u.email FROM feedback f LEFT JOIN users u ON u.id = f.user_id "
            "WHERE f.workspace_id = ? ORDER BY f.id DESC LIMIT ?",
            (workspace_id, max(0, min(limit, 200))),
        ).fetchall()
    return {**dict(totals), "recent": [_row(row, "sources") for row in recent]}


# --- indexing jobs ----------------------------------------------------------------------

def create_job(workspace_id: str, user_id: str) -> dict[str, Any]:
    job = {"id": new_id(), "workspace_id": workspace_id, "user_id": user_id, "status": "queued",
           "progress": "{}", "created_at": now(), "updated_at": now()}
    with connect() as conn:
        conn.execute("INSERT INTO jobs (id, workspace_id, user_id, status, progress, created_at, updated_at) "
                     "VALUES (:id, :workspace_id, :user_id, :status, :progress, :created_at, :updated_at)", job)
    return get_job(job["id"])


def update_job(job_id: str, **fields: Any) -> None:
    for key in ("progress", "result"):
        if key in fields and fields[key] is not None:
            fields[key] = json.dumps(fields[key], ensure_ascii=False)
    fields["updated_at"] = now()
    with connect() as conn:
        conn.execute(f"UPDATE jobs SET {', '.join(f'{k} = ?' for k in fields)} WHERE id = ?",
                     (*fields.values(), job_id))


def get_job(job_id: str, workspace_id: str | None = None) -> dict[str, Any] | None:
    query, params = "SELECT * FROM jobs WHERE id = ?", [job_id]
    if workspace_id:
        query, params = query + " AND workspace_id = ?", [job_id, workspace_id]
    with connect() as conn:
        return _row(conn.execute(query, params).fetchone(), "progress", "result")


def list_jobs(workspace_id: str, active_only: bool = False, limit: int = 10) -> list[dict[str, Any]]:
    query = "SELECT * FROM jobs WHERE workspace_id = ?"
    if active_only:
        query += " AND status IN ('queued', 'running')"
    with connect() as conn:
        rows = conn.execute(query + " ORDER BY created_at DESC LIMIT ?", (workspace_id, limit)).fetchall()
    return [_row(row, "progress", "result") for row in rows]


def fail_interrupted_jobs() -> None:
    """Jobs left queued or running by a server that stopped can't finish any more."""
    with connect() as conn:
        conn.execute("UPDATE jobs SET status = 'failed', error = 'The server restarted. Run indexing again.', "
                     "updated_at = ? WHERE status IN ('queued', 'running')", (now(),))


# --- insights -----------------------------------------------------------------------------

def insights(workspace_id: str, days: int = 14) -> dict[str, Any]:
    since = (datetime.now(timezone.utc) - timedelta(days=days - 1)).date().isoformat()
    with connect() as conn:
        per_day = {row["day"]: row["questions"] for row in conn.execute(
            "SELECT substr(m.created_at, 1, 10) AS day, count(*) AS questions FROM messages m "
            "JOIN chats c ON c.id = m.chat_id WHERE c.workspace_id = ? AND m.role = 'user' AND m.created_at >= ? "
            "GROUP BY day", (workspace_id, since),
        )}
        answers = [json.loads(row["data"]) for row in conn.execute(
            "SELECT m.data FROM messages m JOIN chats c ON c.id = m.chat_id "
            "WHERE c.workspace_id = ? AND m.role = 'assistant'", (workspace_id,),
        )]
        totals = conn.execute(
            "SELECT (SELECT count(*) FROM chats WHERE workspace_id = :w) AS chats, "
            "(SELECT count(DISTINCT c.user_id) FROM chats c WHERE c.workspace_id = :w) AS people",
            {"w": workspace_id},
        ).fetchone()
    start = datetime.fromisoformat(since).date()
    cited: dict[str, int] = {}
    for data in answers:
        for name in {s["source_name"] for s in data.get("sources", [])}:
            cited[name] = cited.get(name, 0) + 1
    timed = [d["seconds"] for d in answers if d.get("seconds")]
    return {
        "questions": len(answers),
        "chats": totals["chats"],
        "people": totals["people"],
        "not_covered": sum(not d.get("covered", True) for d in answers),
        "average_seconds": round(sum(timed) / len(timed), 1) if timed else None,
        "per_day": [{"day": (start + timedelta(days=i)).isoformat(),
                     "questions": per_day.get((start + timedelta(days=i)).isoformat(), 0)} for i in range(days)],
        "top_documents": sorted(({"source_name": k, "answers": v} for k, v in cited.items()),
                                key=lambda item: -item["answers"])[:5],
    }
