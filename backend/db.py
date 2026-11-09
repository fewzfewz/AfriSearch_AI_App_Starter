"""Accounts, workspaces, chats, feedback, indexing jobs and model usage, in SQLite (DATA_DIR/afrisearch.db).

Each call opens its own short-lived connection, so the functions are safe to use
from request handlers and the indexing thread alike.
"""
from __future__ import annotations

import hashlib
import json
import logging
import secrets
import sqlite3
import threading
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from typing import Any, Iterator

from backend import config

logger = logging.getLogger("afrisearch.db")

SYSTEM_RECOVERY_ORG_ID = "system-recovery-org-000000000000"
SYSTEM_USER_ID = "system"
INVITATION_EXPIRY_DAYS = 7

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    email TEXT NOT NULL DEFAULT '',
    name TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS users_email ON users (lower(email));
CREATE TABLE IF NOT EXISTS organizations (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL CHECK (length(trim(name)) >= 1 AND length(name) <= 100),
    owner_id TEXT NOT NULL REFERENCES users (id) ON DELETE RESTRICT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS organizations_owner ON organizations (owner_id);
CREATE TABLE IF NOT EXISTS organization_members (
    organization_id TEXT NOT NULL REFERENCES organizations (id) ON DELETE CASCADE,
    user_id TEXT NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    role TEXT NOT NULL CHECK (role IN ('owner', 'admin', 'member')),
    joined_at TEXT NOT NULL,
    PRIMARY KEY (organization_id, user_id)
);
CREATE INDEX IF NOT EXISTS org_members_user ON organization_members (user_id);
CREATE TABLE IF NOT EXISTS organization_invitations (
    id TEXT PRIMARY KEY,
    organization_id TEXT NOT NULL REFERENCES organizations (id) ON DELETE CASCADE,
    email TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('admin', 'member')),
    token_hash TEXT NOT NULL UNIQUE,
    expires_at TEXT NOT NULL,
    invited_by TEXT NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    created_at TEXT NOT NULL,
    UNIQUE (organization_id, email)
);
CREATE INDEX IF NOT EXISTS org_invitations_lookup ON organization_invitations (token_hash);
CREATE INDEX IF NOT EXISTS org_invitations_email ON organization_invitations (email);
CREATE TABLE IF NOT EXISTS subscriptions (
    id TEXT PRIMARY KEY,
    organization_id TEXT NOT NULL UNIQUE REFERENCES organizations (id) ON DELETE CASCADE,
    plan_id TEXT NOT NULL CHECK (plan_id IN ('free', 'pro', 'business', 'enterprise')),
    status TEXT NOT NULL CHECK (status IN ('active', 'trialing', 'past_due', 'canceled', 'unpaid')),
    seats_purchased INTEGER NOT NULL DEFAULT 1,
    provider TEXT NOT NULL CHECK (provider IN ('none', 'stripe', 'chapa', 'paystack', 'manual')),
    provider_customer_id TEXT,
    provider_subscription_id TEXT,
    current_period_start TEXT NOT NULL,
    current_period_end TEXT NOT NULL,
    cancel_at_period_end INTEGER NOT NULL DEFAULT 0,
    canceled_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS subscriptions_provider_sub ON subscriptions (provider_subscription_id);
CREATE TABLE IF NOT EXISTS organization_usage_cycles (
    organization_id TEXT NOT NULL REFERENCES organizations (id) ON DELETE CASCADE,
    cycle_start TEXT NOT NULL,
    cycle_end TEXT NOT NULL,
    questions_count INTEGER NOT NULL DEFAULT 0,
    input_tokens INTEGER NOT NULL DEFAULT 0,
    output_tokens INTEGER NOT NULL DEFAULT 0,
    ai_cost_usd REAL NOT NULL DEFAULT 0.0,
    ocr_pages_count INTEGER NOT NULL DEFAULT 0,
    peak_storage_bytes INTEGER NOT NULL DEFAULT 0,
    peak_documents_count INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (organization_id, cycle_start)
);
CREATE TABLE IF NOT EXISTS workspaces (
    id TEXT PRIMARY KEY,
    organization_id TEXT REFERENCES organizations (id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS members (
    workspace_id TEXT NOT NULL REFERENCES workspaces (id) ON DELETE CASCADE,
    user_id TEXT NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    role TEXT NOT NULL CHECK (role IN ('owner', 'admin', 'member', 'viewer')),
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
    updated_at TEXT NOT NULL,
    shared INTEGER NOT NULL DEFAULT 0
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
CREATE TABLE IF NOT EXISTS usage (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    workspace_id TEXT NOT NULL REFERENCES workspaces (id) ON DELETE CASCADE,
    user_id TEXT NOT NULL,  -- '' once the user deleted their account
    provider TEXT NOT NULL,
    model TEXT NOT NULL,
    input_tokens INTEGER NOT NULL,
    output_tokens INTEGER NOT NULL,
    cost_usd REAL,  -- NULL when the model's price isn't configured
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS usage_by_workspace ON usage (workspace_id, created_at);
CREATE TABLE IF NOT EXISTS invoices (
    id TEXT PRIMARY KEY,
    organization_id TEXT NOT NULL REFERENCES organizations (id) ON DELETE CASCADE,
    subscription_id TEXT REFERENCES subscriptions (id) ON DELETE SET NULL,
    provider TEXT NOT NULL CHECK (provider IN ('stripe', 'chapa', 'paystack', 'manual')),
    provider_invoice_id TEXT,
    amount_cents INTEGER NOT NULL,
    currency TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('paid', 'open', 'void', 'uncollectible')),
    paid_at TEXT,
    hosted_invoice_url TEXT,
    pdf_url TEXT,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS invoices_by_org ON invoices (organization_id, created_at DESC);
CREATE INDEX IF NOT EXISTS invoices_by_provider ON invoices (provider_invoice_id);
CREATE TABLE IF NOT EXISTS webhook_events (
    id TEXT PRIMARY KEY,
    provider TEXT NOT NULL CHECK (provider IN ('stripe', 'chapa', 'paystack')),
    event_type TEXT NOT NULL,
    payload TEXT NOT NULL,
    processed_at TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('processed', 'ignored', 'failed')),
    error TEXT
);
CREATE INDEX IF NOT EXISTS webhook_events_lookup ON webhook_events (id, provider);
"""

_initialized: set[str] = set()
_init_lock = threading.Lock()


def migrate(conn: sqlite3.Connection) -> None:
    """Bring databases created by earlier versions up to the current schema."""
    # 1. Existing column migrations
    chat_columns = {row[1] for row in conn.execute("PRAGMA table_info(chats)")}
    if chat_columns and "shared" not in chat_columns:  # added in 0.3: chats shared read-only with the workspace
        conn.execute("ALTER TABLE chats ADD COLUMN shared INTEGER NOT NULL DEFAULT 0")

    # 2. Schema DDL: organizations, organization_members, organization_invitations
    conn.execute("""
    CREATE TABLE IF NOT EXISTS organizations (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL CHECK (length(trim(name)) >= 1 AND length(name) <= 100),
        owner_id TEXT NOT NULL REFERENCES users (id) ON DELETE RESTRICT,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    );
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS organizations_owner ON organizations (owner_id);")

    conn.execute("""
    CREATE TABLE IF NOT EXISTS organization_members (
        organization_id TEXT NOT NULL REFERENCES organizations (id) ON DELETE CASCADE,
        user_id TEXT NOT NULL REFERENCES users (id) ON DELETE CASCADE,
        role TEXT NOT NULL CHECK (role IN ('owner', 'admin', 'member')),
        joined_at TEXT NOT NULL,
        PRIMARY KEY (organization_id, user_id)
    );
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS org_members_user ON organization_members (user_id);")

    conn.execute("""
    CREATE TABLE IF NOT EXISTS organization_invitations (
        id TEXT PRIMARY KEY,
        organization_id TEXT NOT NULL REFERENCES organizations (id) ON DELETE CASCADE,
        email TEXT NOT NULL,
        role TEXT NOT NULL CHECK (role IN ('admin', 'member')),
        token_hash TEXT NOT NULL UNIQUE,
        expires_at TEXT NOT NULL,
        invited_by TEXT NOT NULL REFERENCES users (id) ON DELETE CASCADE,
        created_at TEXT NOT NULL,
        UNIQUE (organization_id, email)
    );
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS org_invitations_lookup ON organization_invitations (token_hash);")
    conn.execute("CREATE INDEX IF NOT EXISTS org_invitations_email ON organization_invitations (email);")

    # 3. Add organization_id column to workspaces if missing
    workspace_columns = {row[1] for row in conn.execute("PRAGMA table_info(workspaces)")}
    if workspace_columns and "organization_id" not in workspace_columns:
        conn.execute("ALTER TABLE workspaces ADD COLUMN organization_id TEXT REFERENCES organizations (id) ON DELETE CASCADE")
    if workspace_columns:
        conn.execute("CREATE INDEX IF NOT EXISTS workspaces_by_org ON workspaces (organization_id, created_at)")

    # 4. Schema DDL: subscriptions and organization_usage_cycles
    conn.execute("""
    CREATE TABLE IF NOT EXISTS subscriptions (
        id TEXT PRIMARY KEY,
        organization_id TEXT NOT NULL UNIQUE REFERENCES organizations (id) ON DELETE CASCADE,
        plan_id TEXT NOT NULL CHECK (plan_id IN ('free', 'pro', 'business', 'enterprise')),
        status TEXT NOT NULL CHECK (status IN ('active', 'trialing', 'past_due', 'canceled', 'unpaid')),
        seats_purchased INTEGER NOT NULL DEFAULT 1,
        provider TEXT NOT NULL CHECK (provider IN ('none', 'stripe', 'chapa', 'paystack', 'manual')),
        provider_customer_id TEXT,
        provider_subscription_id TEXT,
        current_period_start TEXT NOT NULL,
        current_period_end TEXT NOT NULL,
        cancel_at_period_end INTEGER NOT NULL DEFAULT 0,
        canceled_at TEXT,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    );
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS subscriptions_provider_sub ON subscriptions (provider_subscription_id);")

    conn.execute("""
    CREATE TABLE IF NOT EXISTS organization_usage_cycles (
        organization_id TEXT NOT NULL REFERENCES organizations (id) ON DELETE CASCADE,
        cycle_start TEXT NOT NULL,
        cycle_end TEXT NOT NULL,
        questions_count INTEGER NOT NULL DEFAULT 0,
        input_tokens INTEGER NOT NULL DEFAULT 0,
        output_tokens INTEGER NOT NULL DEFAULT 0,
        ai_cost_usd REAL NOT NULL DEFAULT 0.0,
        ocr_pages_count INTEGER NOT NULL DEFAULT 0,
        peak_storage_bytes INTEGER NOT NULL DEFAULT 0,
        peak_documents_count INTEGER NOT NULL DEFAULT 0,
        PRIMARY KEY (organization_id, cycle_start)
    );
    """)

    # Backfill subscriptions for existing organizations lacking one
    ts_now = now()
    orgs_without_sub = conn.execute(
        "SELECT id, created_at FROM organizations WHERE id NOT IN (SELECT organization_id FROM subscriptions)"
    ).fetchall()
    for org_row in orgs_without_sub:
        oid = org_row["id"]
        org_ts = org_row["created_at"] or ts_now
        conn.execute(
            "INSERT OR IGNORE INTO subscriptions (id, organization_id, plan_id, status, seats_purchased, provider, current_period_start, current_period_end, cancel_at_period_end, created_at, updated_at) "
            "VALUES (?, ?, 'free', 'active', 1, 'none', ?, '2099-12-31T23:59:59Z', 0, ?, ?)",
            (new_id(), oid, org_ts, org_ts, org_ts),
        )

    # 5. Expand members table role CHECK constraint if needed
    members_sql = conn.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='members'").fetchone()
    if members_sql and "viewer" not in members_sql[0]:
        conn.execute("PRAGMA foreign_keys = OFF")
        conn.execute("""
        CREATE TABLE IF NOT EXISTS members_new (
            workspace_id TEXT NOT NULL REFERENCES workspaces (id) ON DELETE CASCADE,
            user_id TEXT NOT NULL REFERENCES users (id) ON DELETE CASCADE,
            role TEXT NOT NULL CHECK (role IN ('owner', 'admin', 'member', 'viewer')),
            added_at TEXT NOT NULL,
            PRIMARY KEY (workspace_id, user_id)
        );
        """)
        conn.execute("INSERT OR IGNORE INTO members_new SELECT * FROM members")
        conn.execute("DROP TABLE members")
        conn.execute("ALTER TABLE members_new RENAME TO members")
        conn.execute("PRAGMA foreign_keys = ON")

    # 6. Schema DDL: invoices and webhook_events
    conn.execute("""
    CREATE TABLE IF NOT EXISTS invoices (
        id TEXT PRIMARY KEY,
        organization_id TEXT NOT NULL REFERENCES organizations (id) ON DELETE CASCADE,
        subscription_id TEXT REFERENCES subscriptions (id) ON DELETE SET NULL,
        provider TEXT NOT NULL CHECK (provider IN ('stripe', 'chapa', 'paystack', 'manual')),
        provider_invoice_id TEXT,
        amount_cents INTEGER NOT NULL,
        currency TEXT NOT NULL,
        status TEXT NOT NULL CHECK (status IN ('paid', 'open', 'void', 'uncollectible')),
        paid_at TEXT,
        hosted_invoice_url TEXT,
        pdf_url TEXT,
        created_at TEXT NOT NULL
    );
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS invoices_by_org ON invoices (organization_id, created_at DESC);")
    conn.execute("CREATE INDEX IF NOT EXISTS invoices_by_provider ON invoices (provider_invoice_id);")

    conn.execute("""
    CREATE TABLE IF NOT EXISTS webhook_events (
        id TEXT PRIMARY KEY,
        provider TEXT NOT NULL CHECK (provider IN ('stripe', 'chapa', 'paystack')),
        event_type TEXT NOT NULL,
        payload TEXT NOT NULL,
        processed_at TEXT NOT NULL,
        status TEXT NOT NULL CHECK (status IN ('processed', 'ignored', 'failed')),
        error TEXT
    );
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS webhook_events_lookup ON webhook_events (id, provider);")

    # 7. Check for unassigned workspaces
    unassigned = conn.execute("SELECT id, name, created_at FROM workspaces WHERE organization_id IS NULL").fetchall() if workspace_columns else []
    if not unassigned:
        return  # Fully migrated

    logger.info("Migrating %d legacy workspaces into organization hierarchy...", len(unassigned))
    ts = now()
    report: dict[str, Any] = {
        "timestamp": ts,
        "total_unassigned": len(unassigned),
        "organizations_created": [],
        "workspaces_mapped": [],
        "orphaned_recovered": [],
    }

    # Ensure system user exists for system recovery organization
    conn.execute(
        "INSERT OR IGNORE INTO users (id, email, name, created_at) VALUES (?, 'system@localhost', 'System Account', ?)",
        (SYSTEM_USER_ID, ts),
    )

    for ws in unassigned:
        ws_id = ws["id"]
        # Find the earliest owner in the legacy workspace members table
        owner_row = conn.execute(
            "SELECT user_id FROM members WHERE workspace_id = ? AND role = 'owner' ORDER BY added_at LIMIT 1",
            (ws_id,),
        ).fetchone()

        if owner_row:
            owner_id = owner_row["user_id"]
            # Look up or create Personal Organization for this user
            org_row = conn.execute(
                "SELECT id FROM organizations WHERE owner_id = ? AND id != ? ORDER BY created_at LIMIT 1",
                (owner_id, SYSTEM_RECOVERY_ORG_ID),
            ).fetchone()

            if org_row:
                org_id = org_row["id"]
            else:
                org_id = new_id()
                user = conn.execute("SELECT name, email FROM users WHERE id = ?", (owner_id,)).fetchone()
                name_cand = (user["name"] if user and user["name"] else "").strip()
                org_name = f"{name_cand}'s Organization" if name_cand else "Personal Organization"

                conn.execute(
                    "INSERT INTO organizations (id, name, owner_id, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
                    (org_id, org_name, owner_id, ts, ts),
                )
                conn.execute(
                    "INSERT INTO organization_members (organization_id, user_id, role, joined_at) VALUES (?, ?, 'owner', ?)",
                    (org_id, owner_id, ts),
                )
                report["organizations_created"].append({"org_id": org_id, "name": org_name, "owner_id": owner_id})

            conn.execute("UPDATE workspaces SET organization_id = ? WHERE id = ?", (org_id, ws_id))
            report["workspaces_mapped"].append({"workspace_id": ws_id, "organization_id": org_id, "owner_id": owner_id})
        else:
            # Orphaned workspace: assign to System Recovery Organization
            conn.execute(
                "INSERT OR IGNORE INTO organizations (id, name, owner_id, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
                (SYSTEM_RECOVERY_ORG_ID, "System Recovery Organization", SYSTEM_USER_ID, ts, ts),
            )
            conn.execute(
                "INSERT OR IGNORE INTO organization_members (organization_id, user_id, role, joined_at) VALUES (?, ?, 'owner', ?)",
                (SYSTEM_RECOVERY_ORG_ID, SYSTEM_USER_ID, ts),
            )
            conn.execute("UPDATE workspaces SET organization_id = ? WHERE id = ?", (SYSTEM_RECOVERY_ORG_ID, ws_id))
            report["orphaned_recovered"].append({"workspace_id": ws_id, "name": ws["name"], "created_at": ws["created_at"]})
            logger.warning("Workspace %s (%s) had no owner and was moved to System Recovery Organization.", ws_id, ws["name"])

    try:
        report_file = config.DATA_DIR / f"migration-report-{int(datetime.now().timestamp())}.json"
        report_file.write_text(json.dumps(report, indent=2), encoding="utf-8")
        logger.info("Migration audit report written to %s", report_file)
    except Exception as exc:
        logger.error("Could not write migration audit report file: %s", exc)


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


# --- users and organizations ------------------------------------------------------

def ensure_user(user_id: str, email: str, name: str) -> bool:
    """Create the user on first sight; keep email and name up to date; accept invitations.

    Returns True when the user is new.
    """
    ts = now()
    with connect() as conn:
        new = conn.execute("SELECT 1 FROM users WHERE id = ?", (user_id,)).fetchone() is None
        conn.execute(
            "INSERT INTO users (id, email, name, created_at) VALUES (?, ?, ?, ?) "
            "ON CONFLICT (id) DO UPDATE SET email = excluded.email, name = excluded.name",
            (user_id, email, name, ts),
        )
        if email:
            # Legacy workspace invitations to this email turn into memberships on first sign in.
            conn.execute(
                "INSERT OR IGNORE INTO members (workspace_id, user_id, role, added_at) "
                "SELECT workspace_id, ?, 'member', ? FROM invitations WHERE email = lower(?)",
                (user_id, ts, email),
            )
            conn.execute("DELETE FROM invitations WHERE email = lower(?)", (email,))

        # Ensure every real user has at least one personal organization
        if user_id != SYSTEM_USER_ID:
            has_org = conn.execute(
                "SELECT 1 FROM organizations WHERE owner_id = ? AND id != ?",
                (user_id, SYSTEM_RECOVERY_ORG_ID),
            ).fetchone()
            if not has_org:
                org_id = new_id()
                name_cand = name.strip()
                org_name = f"{name_cand}'s Organization" if name_cand else "Personal Organization"
                conn.execute(
                    "INSERT INTO organizations (id, name, owner_id, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
                    (org_id, org_name, user_id, ts, ts),
                )
                conn.execute(
                    "INSERT INTO organization_members (organization_id, user_id, role, joined_at) VALUES (?, ?, 'owner', ?)",
                    (org_id, user_id, ts),
                )
                conn.execute(
                    "INSERT INTO subscriptions (id, organization_id, plan_id, status, seats_purchased, provider, current_period_start, current_period_end, cancel_at_period_end, created_at, updated_at) "
                    "VALUES (?, ?, 'free', 'active', 1, 'none', ?, '2099-12-31T23:59:59Z', 0, ?, ?)",
                    (new_id(), org_id, ts, ts, ts),
                )
    return new


def get_user(user_id: str) -> dict[str, Any] | None:
    with connect() as conn:
        return _row(conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone())


def find_user_by_email(email: str) -> dict[str, Any] | None:
    with connect() as conn:
        return _row(conn.execute("SELECT * FROM users WHERE lower(email) = lower(?)", (email.strip(),)).fetchone())


# --- organizations and memberships --------------------------------------------------

def create_organization(name: str, owner_id: str, org_id: str | None = None) -> dict[str, Any]:
    name = name.strip()
    if not name or len(name) > 100:
        raise ValueError("Organization name must be between 1 and 100 characters")
    oid = org_id or new_id()
    ts = now()
    with connect() as conn:
        conn.execute(
            "INSERT INTO organizations (id, name, owner_id, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
            (oid, name, owner_id, ts, ts),
        )
        conn.execute(
            "INSERT INTO organization_members (organization_id, user_id, role, joined_at) VALUES (?, ?, 'owner', ?)",
            (oid, owner_id, ts),
        )
        conn.execute(
            "INSERT INTO subscriptions (id, organization_id, plan_id, status, seats_purchased, provider, current_period_start, current_period_end, cancel_at_period_end, created_at, updated_at) "
            "VALUES (?, ?, 'free', 'active', 1, 'none', ?, '2099-12-31T23:59:59Z', 0, ?, ?)",
            (new_id(), oid, ts, ts, ts),
        )
    return {"id": oid, "name": name, "owner_id": owner_id, "created_at": ts, "updated_at": ts, "role": "owner"}


def get_organization(org_id: str, user_id: str | None = None) -> dict[str, Any] | None:
    if user_id is not None and user_id != SYSTEM_USER_ID and org_id == SYSTEM_RECOVERY_ORG_ID:
        return None
    with connect() as conn:
        if user_id is not None:
            row = conn.execute(
                "SELECT o.*, m.role FROM organizations o "
                "JOIN organization_members m ON m.organization_id = o.id "
                "WHERE o.id = ? AND m.user_id = ?",
                (org_id, user_id),
            ).fetchone()
        else:
            row = conn.execute("SELECT * FROM organizations WHERE id = ?", (org_id,)).fetchone()
        return _row(row)


def list_user_organizations(user_id: str) -> list[dict[str, Any]]:
    with connect() as conn:
        rows = conn.execute(
            "SELECT o.id, o.name, o.owner_id, o.created_at, o.updated_at, m.role, "
            "(SELECT count(*) FROM organization_members WHERE organization_id = o.id) AS member_count, "
            "(SELECT count(*) FROM workspaces WHERE organization_id = o.id) AS workspace_count "
            "FROM organizations o JOIN organization_members m ON m.organization_id = o.id "
            "WHERE m.user_id = ? AND o.id != ? ORDER BY o.created_at",
            (user_id, SYSTEM_RECOVERY_ORG_ID),
        ).fetchall()
    return [dict(row) for row in rows]


def rename_organization(org_id: str, name: str) -> None:
    name = name.strip()
    if not name or len(name) > 100:
        raise ValueError("Organization name must be between 1 and 100 characters")
    with connect() as conn:
        conn.execute("UPDATE organizations SET name = ?, updated_at = ? WHERE id = ?", (name, now(), org_id))


def transfer_organization_ownership(org_id: str, current_owner_id: str, new_owner_id: str) -> None:
    if current_owner_id == new_owner_id:
        return
    with connect() as conn:
        row = conn.execute("SELECT owner_id FROM organizations WHERE id = ?", (org_id,)).fetchone()
        if not row or row["owner_id"] != current_owner_id:
            raise ValueError("Unauthorized: only the current owner can transfer ownership")
        target_member = conn.execute(
            "SELECT role FROM organization_members WHERE organization_id = ? AND user_id = ?",
            (org_id, new_owner_id),
        ).fetchone()
        if not target_member:
            raise ValueError("Target user must be a member of the organization")
        ts = now()
        conn.execute("UPDATE organizations SET owner_id = ?, updated_at = ? WHERE id = ?", (new_owner_id, ts, org_id))
        conn.execute(
            "UPDATE organization_members SET role = 'admin' WHERE organization_id = ? AND user_id = ?",
            (org_id, current_owner_id),
        )
        conn.execute(
            "UPDATE organization_members SET role = 'owner' WHERE organization_id = ? AND user_id = ?",
            (org_id, new_owner_id),
        )


def delete_organization(org_id: str, user_id: str) -> None:
    with connect() as conn:
        row = conn.execute("SELECT owner_id FROM organizations WHERE id = ?", (org_id,)).fetchone()
        if not row:
            raise ValueError("Organization not found")
        if row["owner_id"] != user_id:
            raise PermissionError("Only the organization owner can delete the organization")
        count = conn.execute(
            "SELECT count(*) as count FROM organization_members WHERE organization_id = ?",
            (org_id,),
        ).fetchone()["count"]
        if count > 1:
            raise ValueError("Cannot delete organization with multiple members. Transfer ownership or remove other members first.")
        conn.execute("DELETE FROM organizations WHERE id = ?", (org_id,))


def list_organization_members(org_id: str) -> list[dict[str, Any]]:
    with connect() as conn:
        rows = conn.execute(
            "SELECT u.id, u.email, u.name, m.role, m.joined_at FROM organization_members m "
            "JOIN users u ON u.id = m.user_id WHERE m.organization_id = ? "
            "ORDER BY CASE m.role WHEN 'owner' THEN 1 WHEN 'admin' THEN 2 ELSE 3 END, m.joined_at",
            (org_id,),
        ).fetchall()
    return [dict(row) for row in rows]


def add_organization_member(org_id: str, user_id: str, role: str = "member") -> None:
    if role not in ("owner", "admin", "member"):
        raise ValueError("Invalid role")
    with connect() as conn:
        conn.execute(
            "INSERT INTO organization_members (organization_id, user_id, role, joined_at) VALUES (?, ?, ?, ?) "
            "ON CONFLICT (organization_id, user_id) DO UPDATE SET role = excluded.role",
            (org_id, user_id, role, now()),
        )


def remove_organization_member(org_id: str, user_id: str) -> None:
    with connect() as conn:
        row = conn.execute("SELECT owner_id FROM organizations WHERE id = ?", (org_id,)).fetchone()
        if row and row["owner_id"] == user_id:
            raise ValueError("Cannot remove organization owner")
        conn.execute(
            "DELETE FROM organization_members WHERE organization_id = ? AND user_id = ? AND role != 'owner'",
            (org_id, user_id),
        )


# --- organization invitations -------------------------------------------------------

def create_organization_invitation(
    org_id: str,
    email: str,
    role: str,
    invited_by: str,
    expires_days: int = INVITATION_EXPIRY_DAYS,
) -> tuple[dict[str, Any], str]:
    clean_email = email.strip().lower()
    if not clean_email or "@" not in clean_email:
        raise ValueError("Invalid email address")
    if role not in ("admin", "member"):
        raise ValueError("Invitation role must be admin or member")
    with connect() as conn:
        is_member = conn.execute(
            "SELECT 1 FROM organization_members om JOIN users u ON u.id = om.user_id "
            "WHERE om.organization_id = ? AND lower(u.email) = ?",
            (org_id, clean_email),
        ).fetchone()
        if is_member:
            raise ValueError("User is already a member of this organization")
        raw_token = secrets.token_urlsafe(32)
        token_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
        inv_id = new_id()
        created = now()
        expires = (datetime.now(timezone.utc) + timedelta(days=expires_days)).isoformat(timespec="seconds")
        conn.execute(
            "INSERT INTO organization_invitations (id, organization_id, email, role, token_hash, expires_at, invited_by, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT (organization_id, email) DO UPDATE SET "
            "token_hash = excluded.token_hash, role = excluded.role, expires_at = excluded.expires_at, "
            "invited_by = excluded.invited_by, created_at = excluded.created_at",
            (inv_id, org_id, clean_email, role, token_hash, expires, invited_by, created),
        )
    return (
        {
            "id": inv_id,
            "organization_id": org_id,
            "email": clean_email,
            "role": role,
            "expires_at": expires,
            "invited_by": invited_by,
            "created_at": created,
        },
        raw_token,
    )


def list_organization_invitations(org_id: str) -> list[dict[str, Any]]:
    with connect() as conn:
        rows = conn.execute(
            "SELECT id, organization_id, email, role, expires_at, invited_by, created_at "
            "FROM organization_invitations WHERE organization_id = ? ORDER BY created_at DESC",
            (org_id,),
        ).fetchall()
    return [dict(row) for row in rows]


def cancel_organization_invitation(org_id: str, email: str) -> None:
    with connect() as conn:
        conn.execute(
            "DELETE FROM organization_invitations WHERE organization_id = ? AND email = lower(?)",
            (org_id, email.strip()),
        )


def get_invitation_by_token(raw_token: str) -> dict[str, Any] | None:
    token_hash = hashlib.sha256(raw_token.strip().encode("utf-8")).hexdigest()
    with connect() as conn:
        row = conn.execute(
            "SELECT i.id, i.organization_id, i.email, i.role, i.expires_at, i.invited_by, i.created_at, "
            "o.name AS organization_name "
            "FROM organization_invitations i JOIN organizations o ON o.id = i.organization_id "
            "WHERE i.token_hash = ?",
            (token_hash,),
        ).fetchone()
        return _row(row)


def accept_organization_invitation(raw_token: str, user_id: str, user_email: str) -> dict[str, Any]:
    token_hash = hashlib.sha256(raw_token.strip().encode("utf-8")).hexdigest()
    clean_user_email = user_email.strip().lower()
    with connect() as conn:
        row = conn.execute("SELECT * FROM organization_invitations WHERE token_hash = ?", (token_hash,)).fetchone()
        if not row:
            raise ValueError("Invalid invitation token")
        invite = dict(row)
        if now() > invite["expires_at"]:
            conn.execute("DELETE FROM organization_invitations WHERE id = ?", (invite["id"],))
            raise ValueError("Invitation has expired")
        if clean_user_email != invite["email"].lower():
            raise ValueError(f"Invitation was sent to {invite['email']}, but current user is {clean_user_email}")
        ts = now()
        conn.execute(
            "INSERT OR IGNORE INTO organization_members (organization_id, user_id, role, joined_at) VALUES (?, ?, ?, ?)",
            (invite["organization_id"], user_id, invite["role"], ts),
        )
        conn.execute("DELETE FROM organization_invitations WHERE id = ?", (invite["id"],))
        return {"organization_id": invite["organization_id"], "role": invite["role"]}


def recover_workspace(workspace_id: str, target_org_id: str) -> None:
    """Move an orphaned workspace from the system recovery organization to a target organization."""
    with connect() as conn:
        target = conn.execute("SELECT id FROM organizations WHERE id = ?", (target_org_id,)).fetchone()
        if not target:
            raise ValueError(f"Target organization {target_org_id} does not exist")
        ws = conn.execute("SELECT id, organization_id FROM workspaces WHERE id = ?", (workspace_id,)).fetchone()
        if not ws:
            raise ValueError(f"Workspace {workspace_id} does not exist")
        conn.execute("UPDATE workspaces SET organization_id = ? WHERE id = ?", (target_org_id, workspace_id))
        logger.info("Recovered workspace %s into organization %s", workspace_id, target_org_id)


# --- subscriptions and usage --------------------------------------------------------

def get_organization_subscription(org_id: str) -> dict[str, Any]:
    with connect() as conn:
        row = conn.execute("SELECT * FROM subscriptions WHERE organization_id = ?", (org_id,)).fetchone()
        if row:
            return dict(row)
        # Auto-create free subscription if missing
        sub_id = new_id()
        ts = now()
        conn.execute(
            "INSERT OR IGNORE INTO subscriptions (id, organization_id, plan_id, status, seats_purchased, provider, current_period_start, current_period_end, cancel_at_period_end, created_at, updated_at) "
            "VALUES (?, ?, 'free', 'active', 1, 'none', ?, '2099-12-31T23:59:59Z', 0, ?, ?)",
            (sub_id, org_id, ts, ts, ts),
        )
        row = conn.execute("SELECT * FROM subscriptions WHERE organization_id = ?", (org_id,)).fetchone()
        return dict(row) if row else {}


def update_organization_subscription(
    org_id: str,
    plan_id: str | None = None,
    status: str | None = None,
    seats_purchased: int | None = None,
    provider: str | None = None,
    provider_customer_id: str | None = None,
    provider_subscription_id: str | None = None,
    current_period_start: str | None = None,
    current_period_end: str | None = None,
    cancel_at_period_end: bool | None = None,
) -> dict[str, Any]:
    ts = now()
    with connect() as conn:
        sub = conn.execute("SELECT * FROM subscriptions WHERE organization_id = ?", (org_id,)).fetchone()
        if not sub:
            get_organization_subscription(org_id)
        updates: list[str] = ["updated_at = ?"]
        params: list[Any] = [ts]
        if plan_id is not None:
            updates.append("plan_id = ?")
            params.append(plan_id)
        if status is not None:
            updates.append("status = ?")
            params.append(status)
        if seats_purchased is not None:
            updates.append("seats_purchased = ?")
            params.append(seats_purchased)
        if provider is not None:
            updates.append("provider = ?")
            params.append(provider)
        if provider_customer_id is not None:
            updates.append("provider_customer_id = ?")
            params.append(provider_customer_id)
        if provider_subscription_id is not None:
            updates.append("provider_subscription_id = ?")
            params.append(provider_subscription_id)
        if current_period_start is not None:
            updates.append("current_period_start = ?")
            params.append(current_period_start)
        if current_period_end is not None:
            updates.append("current_period_end = ?")
            params.append(current_period_end)
        if cancel_at_period_end is not None:
            updates.append("cancel_at_period_end = ?")
            params.append(1 if cancel_at_period_end else 0)
        params.append(org_id)
        conn.execute(f"UPDATE subscriptions SET {', '.join(updates)} WHERE organization_id = ?", params)
        row = conn.execute("SELECT * FROM subscriptions WHERE organization_id = ?", (org_id,)).fetchone()
        return dict(row) if row else {}


def get_organization_usage_summary(org_id: str) -> dict[str, Any]:
    with connect() as conn:
        sub = conn.execute("SELECT * FROM subscriptions WHERE organization_id = ?", (org_id,)).fetchone()
        cycle_start = sub["current_period_start"] if sub else "1970-01-01T00:00:00Z"

        ws_rows = conn.execute("SELECT id FROM workspaces WHERE organization_id = ?", (org_id,)).fetchall()
        ws_ids = [row["id"] for row in ws_rows]
        workspace_count = len(ws_ids)

        member_count_row = conn.execute(
            "SELECT count(*) FROM organization_members WHERE organization_id = ?", (org_id,)
        ).fetchone()
        member_count = member_count_row[0] if member_count_row else 0

        invitation_count_row = conn.execute(
            "SELECT count(*) FROM organization_invitations WHERE organization_id = ?", (org_id,)
        ).fetchone()
        invitation_count = invitation_count_row[0] if invitation_count_row else 0

        usage_row = conn.execute(
            "SELECT count(*) AS questions_count, "
            "coalesce(sum(u.input_tokens), 0) AS input_tokens, "
            "coalesce(sum(u.output_tokens), 0) AS output_tokens, "
            "coalesce(sum(u.cost_usd), 0.0) AS cost_usd "
            "FROM usage u JOIN workspaces w ON w.id = u.workspace_id "
            "WHERE w.organization_id = ? AND u.created_at >= ?",
            (org_id, cycle_start),
        ).fetchone()

    total_bytes = 0
    total_docs = 0
    try:
        from backend import store
        for wid in ws_ids:
            st = store.get_store(wid)
            total_bytes += st.bytes_used()
            total_docs += len(st.uploaded_files())
    except Exception as e:
        logger.warning("Error computing workspace storage for org %s: %s", org_id, e)

    return {
        "organization_id": org_id,
        "workspace_count": workspace_count,
        "member_count": member_count,
        "invitation_count": invitation_count,
        "seats_used": member_count + invitation_count,
        "storage_bytes": total_bytes,
        "document_count": total_docs,
        "cycle_start": cycle_start,
        "questions_count": usage_row["questions_count"] if usage_row else 0,
        "input_tokens": usage_row["input_tokens"] if usage_row else 0,
        "output_tokens": usage_row["output_tokens"] if usage_row else 0,
        "cost_usd": round(float(usage_row["cost_usd"]), 6) if usage_row else 0.0,
    }


def get_subscription_by_provider_sub_id(provider_subscription_id: str) -> dict[str, Any] | None:
    with connect() as conn:
        row = conn.execute(
            "SELECT * FROM subscriptions WHERE provider_subscription_id = ?",
            (provider_subscription_id.strip(),),
        ).fetchone()
        return _row(row)


def get_subscription_by_customer_id(provider_customer_id: str) -> dict[str, Any] | None:
    with connect() as conn:
        row = conn.execute(
            "SELECT * FROM subscriptions WHERE provider_customer_id = ?",
            (provider_customer_id.strip(),),
        ).fetchone()
        return _row(row)


def record_invoice(
    organization_id: str,
    provider: str,
    amount_cents: int,
    currency: str,
    status: str,
    subscription_id: str | None = None,
    provider_invoice_id: str | None = None,
    paid_at: str | None = None,
    hosted_invoice_url: str | None = None,
    pdf_url: str | None = None,
    invoice_id: str | None = None,
) -> dict[str, Any]:
    inv_id = invoice_id or f"inv_{new_id()}"
    ts = now()
    with connect() as conn:
        conn.execute(
            "INSERT INTO invoices (id, organization_id, subscription_id, provider, provider_invoice_id, amount_cents, currency, status, paid_at, hosted_invoice_url, pdf_url, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (inv_id, organization_id, subscription_id, provider, provider_invoice_id, amount_cents, currency.upper(), status, paid_at, hosted_invoice_url, pdf_url, ts),
        )
        row = conn.execute("SELECT * FROM invoices WHERE id = ?", (inv_id,)).fetchone()
        return dict(row) if row else {}


def get_invoice(invoice_id: str) -> dict[str, Any] | None:
    with connect() as conn:
        return _row(conn.execute("SELECT * FROM invoices WHERE id = ?", (invoice_id,)).fetchone())


def list_organization_invoices(org_id: str, limit: int = 50) -> list[dict[str, Any]]:
    with connect() as conn:
        rows = conn.execute(
            "SELECT * FROM invoices WHERE organization_id = ? ORDER BY created_at DESC LIMIT ?",
            (org_id, limit),
        ).fetchall()
        return [dict(r) for r in rows]


def record_webhook_event(
    event_id: str,
    provider: str,
    event_type: str,
    payload: str | dict[str, Any],
    status: str,
    error: str | None = None,
) -> dict[str, Any]:
    if isinstance(payload, dict):
        payload_str = json.dumps(payload)
    else:
        payload_str = str(payload)
    ts = now()
    with connect() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO webhook_events (id, provider, event_type, payload, processed_at, status, error) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (event_id, provider, event_type, payload_str, ts, status, error),
        )
        row = conn.execute("SELECT * FROM webhook_events WHERE id = ? AND provider = ?", (event_id, provider)).fetchone()
        return dict(row) if row else {}


def is_webhook_event_processed(event_id: str, provider: str) -> bool:
    with connect() as conn:
        row = conn.execute(
            "SELECT 1 FROM webhook_events WHERE id = ? AND provider = ? AND status = 'processed'",
            (event_id, provider),
        ).fetchone()
        return row is not None


# --- workspaces and legacy invitations ----------------------------------------------

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


def create_workspace(
    name: str,
    owner_id: str,
    workspace_id: str | None = None,
    organization_id: str | None = None,
) -> dict[str, Any]:
    ws_id = workspace_id or new_id()
    created = now()
    with connect() as conn:
        if not organization_id:
            # Look up or provision personal organization for user
            row = conn.execute(
                "SELECT id FROM organizations WHERE owner_id = ? AND id != ? ORDER BY created_at LIMIT 1",
                (owner_id, SYSTEM_RECOVERY_ORG_ID),
            ).fetchone()
            if row:
                organization_id = row["id"]
            else:
                row = conn.execute(
                    "SELECT organization_id FROM organization_members WHERE user_id = ? AND organization_id != ? ORDER BY joined_at LIMIT 1",
                    (owner_id, SYSTEM_RECOVERY_ORG_ID),
                ).fetchone()
                if row:
                    organization_id = row["organization_id"]
                else:
                    u = conn.execute("SELECT name FROM users WHERE id = ?", (owner_id,)).fetchone()
                    name_cand = (u["name"] if u and u["name"] else "").strip()
                    org_name = f"{name_cand}'s Organization" if name_cand else "Personal Organization"
                    organization_id = new_id()
                    conn.execute(
                        "INSERT INTO organizations (id, name, owner_id, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
                        (organization_id, org_name, owner_id, created, created),
                    )
                    conn.execute(
                        "INSERT INTO organization_members (organization_id, user_id, role, joined_at) VALUES (?, ?, 'owner', ?)",
                        (organization_id, owner_id, created),
                    )
        workspace = {
            "id": ws_id,
            "organization_id": organization_id,
            "name": name,
            "created_at": created,
        }
        conn.execute(
            "INSERT INTO workspaces (id, organization_id, name, created_at) VALUES (:id, :organization_id, :name, :created_at)",
            workspace,
        )
        conn.execute(
            "INSERT INTO members (workspace_id, user_id, role, added_at) VALUES (?, ?, 'owner', ?)",
            (ws_id, owner_id, created),
        )
    return {**workspace, "role": "owner"}


def list_workspaces(user_id: str, organization_id: str | None = None) -> list[dict[str, Any]]:
    with connect() as conn:
        if organization_id:
            rows = conn.execute(
                "SELECT w.id, w.organization_id, w.name, w.created_at, coalesce(m.role, om.role) AS role, "
                "(SELECT count(*) FROM members WHERE workspace_id = w.id) AS member_count "
                "FROM workspaces w "
                "JOIN organization_members om ON om.organization_id = w.organization_id "
                "LEFT JOIN members m ON m.workspace_id = w.id AND m.user_id = om.user_id "
                "WHERE om.user_id = ? AND w.organization_id = ? "
                "AND (m.user_id IS NOT NULL OR om.role IN ('owner', 'admin')) "
                "ORDER BY w.created_at",
                (user_id, organization_id),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT w.id, w.organization_id, w.name, w.created_at, m.role, "
                "(SELECT count(*) FROM members WHERE workspace_id = w.id) AS member_count "
                "FROM workspaces w JOIN members m ON m.workspace_id = w.id "
                "WHERE m.user_id = ? ORDER BY w.created_at",
                (user_id,),
            ).fetchall()
    return [dict(row) for row in rows]


def get_workspace(workspace_id: str, user_id: str, organization_id: str | None = None) -> dict[str, Any] | None:
    """The workspace with the user's role, or None if the user isn't a member."""
    with connect() as conn:
        if organization_id:
            row = conn.execute(
                "SELECT w.id, w.organization_id, w.name, w.created_at, coalesce(m.role, om.role) AS role "
                "FROM workspaces w "
                "JOIN organization_members om ON om.organization_id = w.organization_id "
                "LEFT JOIN members m ON m.workspace_id = w.id AND m.user_id = om.user_id "
                "WHERE w.id = ? AND om.user_id = ? AND w.organization_id = ? "
                "AND (m.user_id IS NOT NULL OR om.role IN ('owner', 'admin'))",
                (workspace_id, user_id, organization_id),
            ).fetchone()
        else:
            row = conn.execute(
                "SELECT w.id, w.organization_id, w.name, w.created_at, m.role FROM workspaces w "
                "JOIN members m ON m.workspace_id = w.id WHERE w.id = ? AND m.user_id = ?",
                (workspace_id, user_id),
            ).fetchone()
        return _row(row)


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


def add_member(workspace_id: str, user_id: str, role: str = "member") -> None:
    if role not in ("owner", "admin", "member", "viewer"):
        raise ValueError("Invalid workspace role")
    with connect() as conn:
        conn.execute(
            "INSERT INTO members (workspace_id, user_id, role, added_at) VALUES (?, ?, ?, ?) "
            "ON CONFLICT (workspace_id, user_id) DO UPDATE SET role = excluded.role",
            (workspace_id, user_id, role, now()),
        )


def update_workspace_member_role(workspace_id: str, user_id: str, role: str) -> None:
    if role not in ("admin", "member", "viewer"):
        raise ValueError("Role must be admin, member, or viewer")
    with connect() as conn:
        current = conn.execute(
            "SELECT role FROM members WHERE workspace_id = ? AND user_id = ?",
            (workspace_id, user_id),
        ).fetchone()
        if not current:
            raise ValueError("Member not found in workspace")
        if current["role"] == "owner":
            raise ValueError("Cannot change role of workspace owner")
        conn.execute(
            "UPDATE members SET role = ? WHERE workspace_id = ? AND user_id = ?",
            (role, workspace_id, user_id),
        )


def remove_member(workspace_id: str, user_id: str) -> None:
    with connect() as conn:
        conn.execute("DELETE FROM members WHERE workspace_id = ? AND user_id = ? AND role != 'owner'",
                     (workspace_id, user_id))


def user_data(user_id: str) -> dict[str, Any]:
    """Everything stored about a user, for export: account, organizations, memberships, chats, ratings."""
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
    return {
        "user": user,
        "organizations": list_user_organizations(user_id),
        "workspaces": list_workspaces(user_id),
        "chats": chats,
        "feedback": feedback,
    }


def delete_user(user_id: str) -> None:
    """Remove the user's chats, ratings, memberships, personal organizations, then the user."""
    with connect() as conn:
        conn.execute("DELETE FROM chats WHERE user_id = ?", (user_id,))  # messages go with them
        conn.execute("DELETE FROM feedback WHERE user_id = ?", (user_id,))
        conn.execute("DELETE FROM members WHERE user_id = ?", (user_id,))
        conn.execute("UPDATE usage SET user_id = '' WHERE user_id = ?", (user_id,))  # kept for the workspace's bill
        # Handle organizations owned by this user
        owned_orgs = conn.execute("SELECT id FROM organizations WHERE owner_id = ?", (user_id,)).fetchall()
        for org in owned_orgs:
            count = conn.execute(
                "SELECT count(*) AS count FROM organization_members WHERE organization_id = ? AND user_id != ?",
                (org["id"], user_id),
            ).fetchone()["count"]
            if count > 0:
                raise ValueError(f"Cannot delete user who owns organization {org['id']} with other members. Transfer ownership first.")
            has_workspaces = conn.execute("SELECT 1 FROM workspaces WHERE organization_id = ?", (org["id"],)).fetchone()
            if has_workspaces:
                conn.execute(
                    "INSERT OR IGNORE INTO users (id, email, name, created_at) VALUES (?, 'system@localhost', 'System Account', ?)",
                    (SYSTEM_USER_ID, now()),
                )
                conn.execute(
                    "UPDATE organizations SET owner_id = ?, updated_at = ? WHERE id = ?",
                    (SYSTEM_USER_ID, now(), org["id"]),
                )
            else:
                conn.execute("DELETE FROM organizations WHERE id = ?", (org["id"],))
        conn.execute("DELETE FROM organization_members WHERE user_id = ?", (user_id,))
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


# --- model usage -------------------------------------------------------------------------

def record_usage(workspace_id: str, user_id: str, provider: str, model: str,
                 input_tokens: int, output_tokens: int, cost_usd: float | None) -> None:
    with connect() as conn:
        conn.execute(
            "INSERT INTO usage (workspace_id, user_id, provider, model, input_tokens, output_tokens, cost_usd, "
            "created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (workspace_id, user_id, provider, model, input_tokens, output_tokens, cost_usd, now()),
        )


def usage_summary(workspace_id: str, since: str) -> dict[str, Any]:
    """Tokens and estimated cost of hosted-model answers since an ISO date, by model."""
    with connect() as conn:
        rows = conn.execute(
            "SELECT provider, model, count(*) AS answers, sum(input_tokens) AS input_tokens, "
            "sum(output_tokens) AS output_tokens, sum(cost_usd) AS cost_usd, "
            "sum(cost_usd IS NULL) AS unpriced FROM usage WHERE workspace_id = ? AND created_at >= ? "
            "GROUP BY provider, model ORDER BY answers DESC",
            (workspace_id, since),
        ).fetchall()
    models = [dict(row) for row in rows]
    priced = [m["cost_usd"] for m in models if m["cost_usd"] is not None]
    return {
        "since": since,
        "answers": sum(m["answers"] for m in models),
        "input_tokens": sum(m["input_tokens"] for m in models),
        "output_tokens": sum(m["output_tokens"] for m in models),
        "cost_usd": round(sum(priced), 4) if priced else None,
        "unpriced_answers": sum(m["unpriced"] for m in models),
        "models": models,
    }


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
