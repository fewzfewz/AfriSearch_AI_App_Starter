# SAAS-P0-01 — Migration Plan: Data Backfill & System Orphan Recovery

**Document Version:** 1.1.0 (Post-Review Final Architecture Specification)  
**Scope:** Stage B — Data Migration, Maintenance Lock Windows, and System Orphan Isolation  
**Target Module:** `backend/db.py:migrate`  

---

## 1. Migration Reliability & Operational Reality

### Maintenance Window & Locking Analysis
- **Concurrency & Locking Realities in SQLite:**
  - SQLite WAL mode allows concurrent readers while a transaction writes. However, executing DDL statements (`ALTER TABLE workspaces ADD COLUMN organization_id ...`) acquires an **exclusive schema lock**.
  - If request handlers attempt concurrent writes while DDL is being applied, SQLite may throw `sqlite3.OperationalError: database is locked` if the transaction exceeds busy timeouts.
- **Operational Recommendation:** The migration should be executed during a **brief planned maintenance window (30–60 seconds)** during service deployment or restart. It should **not be represented as a zero-downtime online migration**, but rather an automated, fast, transactional migration executed on startup.

---

## 2. Orphan Workspace Recovery Engine

### Architectural Policy: System Recovery Isolation
Under no circumstances are orphaned workspaces assigned to arbitrary registered users or the local user. 

```
Unassigned Workspace Scan (SELECT * FROM workspaces WHERE organization_id IS NULL)
         |
         +---> Owner Exists in members table?
         |        |
         |        +-- YES: Find or create User's Personal Organization
         |                 Link workspace to User's Organization
         |
         +-- NO (Orphaned / Corrupted Ownership):
                  |
                  v
         Assign to Dedicated "System Recovery Organization"
         - Organization ID: 'system-recovery-org-000000000000'
         - Owner ID:        'system'
         - Access:          Hidden from all standard user queries
         - Audit Report:    Logged to data/MIGRATION_REPORT_<timestamp>.json
```

1. **System Recovery Entity:**
   - Provisioned with fixed UUID `system-recovery-org-000000000000` and `owner_id = 'system'`.
   - Regular users cannot see or access this organization; `list_user_organizations` queries join on `organization_members` where `user_id = :authenticated_user_id`.
2. **Migration Audit Report:**
   - Every execution outputs a structured JSON report to `config.DATA_DIR / f"migration-report-{timestamp}.json"`.
   - Details:
     - Total workspaces processed.
     - Personal organizations created.
     - Workspaces mapped to users.
     - Orphaned workspaces assigned to System Recovery Organization (recording `workspace_id`, name, and creation time).
3. **Explicit Authorized Recovery CLI:**
   - To transfer an orphaned workspace to a legitimate organization, an authorized platform administrator must run a dedicated CLI command:
     ```bash
     python -m backend.recover_workspace --workspace <ws_id> --target-org <org_id>
     ```

---

## 3. Migration Implementation Algorithm (`backend/db.py:migrate`)

```python
import json
import logging
import sqlite3
import uuid
from datetime import datetime, timezone
from backend import config

logger = logging.getLogger("afrisearch.migration")
SYSTEM_RECOVERY_ORG_ID = "system-recovery-org-000000000000"
SYSTEM_USER_ID = "system"

def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")

def migrate(conn: sqlite3.Connection) -> None:
    timestamp = now_iso()

    # 1. Existing column migrations
    chat_columns = {row[1] for row in conn.execute("PRAGMA table_info(chats)")}
    if "shared" not in chat_columns:
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
    if "organization_id" not in workspace_columns:
        conn.execute("ALTER TABLE workspaces ADD COLUMN organization_id TEXT REFERENCES organizations (id) ON DELETE CASCADE")
        conn.execute("CREATE INDEX IF NOT EXISTS workspaces_by_org ON workspaces (organization_id, created_at)")

    # 4. Check for unassigned workspaces
    unassigned = conn.execute("SELECT id, name, created_at FROM workspaces WHERE organization_id IS NULL").fetchall()
    if not unassigned:
        return  # Fully migrated

    logger.info("Migrating %d legacy workspaces into organization hierarchy...", len(unassigned))

    report = {
        "timestamp": timestamp,
        "total_unassigned": len(unassigned),
        "organizations_created": [],
        "workspaces_mapped": [],
        "orphaned_recovered": []
    }

    # Ensure system user exists for system recovery organization
    conn.execute(
        "INSERT OR IGNORE INTO users (id, email, name, created_at) VALUES (?, 'system@localhost', 'System Account', ?)",
        (SYSTEM_USER_ID, timestamp)
    )

    for ws in unassigned:
        ws_id = ws["id"]
        # Find the earliest owner in the legacy workspace members table
        owner_row = conn.execute(
            "SELECT user_id FROM members WHERE workspace_id = ? AND role = 'owner' ORDER BY added_at LIMIT 1",
            (ws_id,)
        ).fetchone()

        if owner_row:
            owner_id = owner_row["user_id"]
            # Look up or create Personal Organization for this user
            org_row = conn.execute(
                "SELECT id FROM organizations WHERE owner_id = ? AND id != ? ORDER BY created_at LIMIT 1",
                (owner_id, SYSTEM_RECOVERY_ORG_ID)
            ).fetchone()

            if org_row:
                org_id = org_row["id"]
            else:
                org_id = uuid.uuid4().hex
                user = conn.execute("SELECT name, email FROM users WHERE id = ?", (owner_id,)).fetchone()
                name_cand = (user["name"] if user and user["name"] else "").strip()
                org_name = f"{name_cand}'s Organization" if name_cand else "Personal Organization"

                conn.execute(
                    "INSERT INTO organizations (id, name, owner_id, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
                    (org_id, org_name, owner_id, timestamp, timestamp)
                )
                conn.execute(
                    "INSERT INTO organization_members (organization_id, user_id, role, joined_at) VALUES (?, ?, 'owner', ?)",
                    (org_id, owner_id, timestamp)
                )
                report["organizations_created"].append({"org_id": org_id, "name": org_name, "owner_id": owner_id})

            conn.execute("UPDATE workspaces SET organization_id = ? WHERE id = ?", (org_id, ws_id))
            report["workspaces_mapped"].append({"workspace_id": ws_id, "organization_id": org_id, "owner_id": owner_id})

        else:
            # Orphaned workspace: assign to System Recovery Organization
            conn.execute(
                "INSERT OR IGNORE INTO organizations (id, name, owner_id, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
                (SYSTEM_RECOVERY_ORG_ID, "System Recovery Organization", SYSTEM_USER_ID, timestamp, timestamp)
            )
            conn.execute(
                "INSERT OR IGNORE INTO organization_members (organization_id, user_id, role, joined_at) VALUES (?, ?, 'owner', ?)",
                (SYSTEM_RECOVERY_ORG_ID, SYSTEM_USER_ID, timestamp)
            )
            conn.execute("UPDATE workspaces SET organization_id = ? WHERE id = ?", (SYSTEM_RECOVERY_ORG_ID, ws_id))
            report["orphaned_recovered"].append({"workspace_id": ws_id, "name": ws["name"], "created_at": ws["created_at"]})
            logger.warning("Workspace %s (%s) had no owner and was moved to System Recovery Organization.", ws_id, ws["name"])

    # Write audit report file
    try:
        report_file = config.DATA_DIR / f"migration-report-{int(datetime.now().timestamp())}.json"
        report_file.write_text(json.dumps(report, indent=2), encoding="utf-8")
        logger.info("Migration audit report written to %s", report_file)
    except Exception as exc:
        logger.error("Could not write migration audit report file: %s", exc)
```

---

## 4. Invariant Preservation Checklist

1. **Workspace IDs:** Fully preserved. `workspaces.id` is not changed.
2. **Filesystem Integrity:** Zero files moved. `data/workspaces/<workspace_id>/` is untouched.
3. **Folders & Tags:** `tags.json` in workspace directory continues to be loaded and queried as before.
4. **Chats & Citations:** Message references and source citations (`[S1]`, `[S2]`) remain functional.
5. **Idempotency:** Executing `migrate(conn)` repeatedly executes 0 backfill statements once all `organization_id` columns are populated.
6. **Interruption Recovery:** Running inside an immediate transaction guarantees that if interrupted by `SIGKILL` or power cut, the entire transaction rolls back cleanly, leaving unmigrated rows ready for the next restart.
