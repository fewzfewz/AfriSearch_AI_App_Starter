# SAAS-P0-01 — Database Design: Multi-Tenant Schema & Invariants

**Document Version:** 1.1.0 (Post-Review Final Architecture Specification)  
**Scope:** Stage A — Relational DDL, Invariants, Invitation Cryptography, and Deletion Safeguards  
**Target Engine:** SQLite 3 (WAL mode) with Full PostgreSQL Forward Compatibility  

---

## 1. Relational Schema Architecture

```
                                    +-----------------------------------+
                                    |               users               |
                                    | - id TEXT PRIMARY KEY             |
                                    | - email TEXT NOT NULL             |
                                    | - name TEXT NOT NULL              |
                                    | - created_at TEXT NOT NULL        |
                                    +-----------------------------------+
                                             |                 |
                       +---------------------+                 +--------------------+
                       | 1:N (owner_id)                                             | 1:N (user_id)
                       v                                                            v
+---------------------------------------------+              +---------------------------------------------+
|                organizations                | 1 : N        |            organization_members             |
| - id TEXT PRIMARY KEY                       |------------->| - organization_id TEXT REFERENCES orgs (PK) |
| - name TEXT NOT NULL                        |              | - user_id TEXT REFERENCES users (PK)        |
| - owner_id TEXT NOT NULL (FK -> users)      |              | - role TEXT NOT NULL ('owner','admin','mbr')|
| - created_at TEXT NOT NULL                  |              | - joined_at TEXT NOT NULL                   |
| - updated_at TEXT NOT NULL                  |              +---------------------------------------------+
+---------------------------------------------+
         |                          |
         | 1 : N                    | 1 : N
         v                          v
+---------------------------------------------+              +---------------------------------------------+
|                 workspaces                  |              |          organization_invitations           |
| - id TEXT PRIMARY KEY                       |              | - id TEXT PRIMARY KEY                       |
| - organization_id TEXT NOT NULL (FK -> orgs)|              | - organization_id TEXT REFERENCES orgs      |
| - name TEXT NOT NULL                        |              | - email TEXT NOT NULL (normalized lower)    |
| - created_at TEXT NOT NULL                  |              | - role TEXT NOT NULL ('admin', 'member')    |
+---------------------------------------------+              | - token_hash TEXT NOT NULL UNIQUE (SHA-256) |
                                                             | - expires_at TEXT NOT NULL (ISO 8601)       |
                                                             | - invited_by TEXT REFERENCES users          |
                                                             | - created_at TEXT NOT NULL                  |
                                                             +---------------------------------------------+
```

---

## 2. Table Definitions & DDL Specifications

### 1. `organizations` Table
The top-level customer and tenant container.

```sql
CREATE TABLE IF NOT EXISTS organizations (
    id TEXT PRIMARY KEY,                       -- UUID v4 hex string (32 characters)
    name TEXT NOT NULL CHECK (length(trim(name)) >= 1 AND length(name) <= 100),
    owner_id TEXT NOT NULL REFERENCES users (id) ON DELETE RESTRICT,
    created_at TEXT NOT NULL,                  -- ISO 8601 UTC
    updated_at TEXT NOT NULL                   -- ISO 8601 UTC
);

CREATE INDEX IF NOT EXISTS organizations_owner ON organizations (owner_id);
```

- **Owner Constraint:** `owner_id` references `users(id)` with `ON DELETE RESTRICT`. A user who owns an organization cannot be deleted until ownership is transferred or the organization is explicitly deleted.
- **System Recovery Entity:** The system provisions a dedicated organization reserved strictly for orphaned workspaces:
  - `id = 'system-recovery-org-000000000000'`
  - `owner_id = 'system'`
  - `name = 'System Recovery Organization'`

---

### 2. `organization_members` Table
Represents user membership and permissions within an organization.

```sql
CREATE TABLE IF NOT EXISTS organization_members (
    organization_id TEXT NOT NULL REFERENCES organizations (id) ON DELETE CASCADE,
    user_id TEXT NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    role TEXT NOT NULL CHECK (role IN ('owner', 'admin', 'member')),
    joined_at TEXT NOT NULL,
    PRIMARY KEY (organization_id, user_id)
);

CREATE INDEX IF NOT EXISTS org_members_user ON organization_members (user_id);
```

- **Composite Primary Key:** `(organization_id, user_id)` guarantees uniqueness.
- **Roles:**
  - `owner`: Can rename organization, invite admins/members, transfer ownership, and initiate deletion (when sole member).
  - `admin`: Can rename organization, invite members, and create child workspaces.
  - `member`: Can access workspaces belonging to the organization and view member lists.

---

### 3. `organization_invitations` Table
Represents cryptographically secured pending email invitations.

```sql
CREATE TABLE IF NOT EXISTS organization_invitations (
    id TEXT PRIMARY KEY,                       -- UUID v4 hex string
    organization_id TEXT NOT NULL REFERENCES organizations (id) ON DELETE CASCADE,
    email TEXT NOT NULL,                       -- Normalized lowercase email
    role TEXT NOT NULL CHECK (role IN ('admin', 'member')),
    token_hash TEXT NOT NULL UNIQUE,           -- SHA-256 hash of secrets.token_urlsafe(32)
    expires_at TEXT NOT NULL,                  -- ISO 8601 UTC timestamp (typically now + 7 days)
    invited_by TEXT NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    created_at TEXT NOT NULL,
    UNIQUE (organization_id, email)
);

CREATE INDEX IF NOT EXISTS org_invitations_lookup ON organization_invitations (token_hash);
CREATE INDEX IF NOT EXISTS org_invitations_email ON organization_invitations (email);
```

#### Cryptographic & Verification Protocol
1. **Token Generation:** The application generates a high-entropy secret token: `raw_token = secrets.token_urlsafe(32)`.
2. **Secure Storage:** The database stores strictly `hashlib.sha256(raw_token.encode()).hexdigest()`. Plaintext tokens are never persisted.
3. **Delivery:** The raw token is sent to the invitee via email link: `https://app.afrisearch.org/invite?token=<raw_token>`.
4. **Acceptance Verification:**
   - The user must sign in or register with an email matching the invitation.
   - The user's email must be verified (`claims.get('email_verified') == True`).
   - The hash of the submitted token is looked up in `organization_invitations`.
   - The application verifies `now() <= expires_at`.
   - Membership is inserted into `organization_members`, and the invitation is pruned (single-use).

---

### 4. Updating the `workspaces` Table
Establishes the containment relationship between Workspaces and Organizations.

```sql
ALTER TABLE workspaces ADD COLUMN organization_id TEXT REFERENCES organizations (id) ON DELETE CASCADE;

CREATE INDEX IF NOT EXISTS workspaces_by_org ON workspaces (organization_id, created_at);
```

---

## 3. Core Database Invariants

The data model maintains eight invariant guarantees enforced by SQL constraints, foreign keys, and atomic application transactions:

1. **Owner Existence Invariant:** An organization must always have a valid `owner_id` pointing to an existing `users(id)` record.
2. **Owner Membership Invariant:** The user designated in `organizations.owner_id` must always have an active row in `organization_members` with `role = 'owner'`.
3. **Atomic Ownership Transfer Invariant:** Transferring ownership from User A to User B must execute within a single immediate transaction:
   ```sql
   BEGIN IMMEDIATE;
     -- 1. Verify caller is current owner
     -- 2. Verify target user is an existing organization member
     -- 3. Update organizations table
     UPDATE organizations SET owner_id = :new_owner_id, updated_at = :now WHERE id = :org_id;
     -- 4. Demote old owner to 'admin'
     UPDATE organization_members SET role = 'admin' WHERE organization_id = :org_id AND user_id = :old_owner_id;
     -- 5. Promote new owner to 'owner'
     UPDATE organization_members SET role = 'owner' WHERE organization_id = :org_id AND user_id = :new_owner_id;
   COMMIT;
   ```
4. **Multi-Tenant Membership Invariant:** A user may belong to multiple organizations (`1:N`). Membership in Organization 1 confers zero visibility or privileges in Organization 2.
5. **Workspace Containment Invariant:** Every workspace belongs to exactly one organization (`workspaces.organization_id NOT NULL`).
6. **Multi-Member Deletion Lock Invariant:** If `SELECT count(*) FROM organization_members WHERE organization_id = :org_id` is greater than 1, the deletion request is rejected with `HTTP 409 Conflict`. All other members must be explicitly removed or ownership transferred before deletion.
7. **Cross-Tenant Cascade Invariant:** Deleting an organization cascades strictly to its child workspaces, chats, and messages. Foreign keys prevent any cascade from touching another organization's records.
8. **Foreign Key Enforcement:** Every SQLite connection executes `PRAGMA foreign_keys = ON;` prior to any query execution.
