# SAAS-P0-01 — Test & Authorization Verification Plan

**Document Version:** 1.1.0 (Post-Review Final Architecture Specification)  
**Scope:** Stage C & Stage D — Backend Authorization Pipeline, Security Invariants, and Test Matrix  
**Target Modules:** `backend/auth.py`, `backend/main.py`, `tests/test_organizations.py`  

---

## 1. Backend Authorization Architecture (Stage C)

### Authorization Decision & Initial Scope
- **Organization-Level Containment:** In Stage A, access to a workspace is granted if the user is an **active member of the organization that owns that workspace**.
- **No False Claims of Workspace Roles:** We do not claim to enforce fine-grained `workspace_members` in Stage A. Instead, the authorization code is structured cleanly with a placeholder `get_workspace_membership()` function so that workspace-specific roles (`viewer`, `editor`, `admin`) can be introduced in later milestones without rewriting the routing or dependency layer.

```
Inbound HTTP Request (e.g. GET /api/documents)
Headers:
  Authorization: Bearer <supabase_jwt>
  X-Organization-Id: <org_id> (Optional)
  X-Workspace-Id: <ws_id> (Optional)
         |
         v
[Step 1] current_user Dependency (backend/auth.py)
         - Verifies JWT signature against Supabase JWKS (ES256/RS256).
         - Returns User(id, email, name).
         |
         v
[Step 2] current_organization Dependency (backend/auth.py)
         - If X-Organization-Id provided:
             Query: SELECT role FROM organization_members
                    WHERE organization_id = :org_id AND user_id = :user_id
             If NOT FOUND -> raise HTTPException(404, "Organization not found.")
         - If X-Organization-Id omitted:
             Query user's first/default organization.
         - Enforces: Ordinary users cannot access SYSTEM_RECOVERY_ORG_ID.
         - Returns Organization(id, name, role, user).
         |
         v
[Step 3] current_workspace Dependency (backend/main.py)
         - If X-Workspace-Id provided:
             Query: SELECT w.id, w.name, w.organization_id, w.created_at
                    FROM workspaces w
                    WHERE w.id = :ws_id AND w.organization_id = :org_id
             If NOT FOUND -> raise HTTPException(404, "Workspace not found.")
         - If X-Workspace-Id omitted:
             Query user's first workspace within this organization.
         - Returns Workspace(id, name, role=org.role, organization_id, user).
         |
         v
[Step 4] Endpoint Execution
         - store.get_store(workspace.id) operates in strict isolation.
```

---

## 2. Invitation Security Protocol

1. **Token Generation:** The API generates high-entropy random tokens using `secrets.token_urlsafe(32)`.
2. **Hashed Persistence:** The token is hashed with SHA-256 (`hashlib.sha256(raw_token.encode()).hexdigest()`) before inserting into `organization_invitations`.
3. **Single-Use Enforcement:** Upon successful acceptance via `POST /api/organizations/invitations/accept`, the invitation row is permanently deleted inside the same database transaction that creates the `organization_members` record.
4. **Normalized Comparison:** Emails are compared strictly using `lower(trim(email))`.
5. **Expiration Validation:** The backend verifies `datetime.now(timezone.utc).isoformat() < expires_at`. Expired tokens return `HTTP 410 Gone`.

---

## 3. Automated Test Matrix (Stage D)

A new test module `tests/test_organizations.py` will be created.

| Test ID | Test Function Name | Architectural Objective & Invariant Checked |
|---|---|---|
| **ORG-01** | `test_legacy_migration_creates_personal_org` | Validates that an unassigned workspace is linked to `{user.name}'s Organization` (or `Personal Organization`) and that all existing chats/documents function. |
| **ORG-02** | `test_migration_is_idempotent` | Runs `db.migrate(conn)` twice; asserts zero duplicate organizations, identical counts, and unchanged entity IDs. |
| **ORG-03** | `test_multi_workspace_consolidation` | A user owning 3 legacy workspaces has all 3 assigned to a single Personal Organization. |
| **ORG-04** | `test_orphaned_workspace_recovery_isolation` | An unassigned workspace with no owner in `members` table is assigned to `System Recovery Organization`. Asserts that regular users cannot query or access it. |
| **ORG-05** | `test_migration_audit_report_generation` | Verifies that migration produces a valid JSON report file in `DATA_DIR` listing processed workspaces and recovery actions. |
| **ORG-06** | `test_organization_crud` | Verifies creation, retrieval, renaming, and member listing for organizations. |
| **ORG-07** | `test_organization_deletion_safeguards` | Asserts that deleting an organization with multiple members returns `HTTP 409 Conflict`. Asserts that deleting after member removal succeeds and cascades cleanly. |
| **ORG-08** | `test_atomic_ownership_transfer` | Owner transfers ownership to another member; asserts `organizations.owner_id` updates, old owner becomes `admin`, and new owner becomes `owner` in one atomic transaction. |
| **ORG-09** | `test_secure_invitation_lifecycle` | Validates token hashing, normalized email matching, 7-day expiration, and single-use acceptance. |
| **ORG-10** | `test_cross_tenant_workspace_isolation` | User in Org 1 provides `X-Workspace-Id` belonging to Org 2; asserts API returns `404 Not Found` and reveals no metadata. |
| **ORG-11** | `test_cross_tenant_document_download_blocked` | User in Org 1 attempts to download document file from Org 2 via `/api/documents/{id}/file`; asserts `404 Not Found`. |
| **ORG-12** | `test_folders_and_tags_under_organization` | Verifies that workspace tags (`tags.json`) and collection filters continue to operate without regression under the organization hierarchy. |
| **ORG-13** | `test_local_mode_preservation` | When `AFRISEARCH_AUTH=none`, verifies that `LOCAL_USER` receives a default local organization and can upload, search, and chat without errors. |
| **ORG-14** | `test_full_suite_regression` | Executes the complete existing 177 backend tests in pytest, verifying 100% backward compatibility. |

---

## 4. Pre-Migration Backup & Restoration Verification Procedure

Before running the migration in any production environment, the following CLI procedure is verified:

```bash
# 1. Take a verified live snapshot backup
python -m backend.backup create --out backups/pre-saas-migration/ --keep 14

# 2. Inspect the generated archive
ARCHIVE=$(ls -t backups/pre-saas-migration/afrisearch-backup-*.tar.gz | head -n 1)
tar -tzf "$ARCHIVE" | grep -E "(afrisearch.db|backup.json)"

# 3. Dry-run restoration in an isolated sandbox folder
TEST_DIR=$(mktemp -d -t afrisearch-test-restore-XXXXXX)
python -m backend.backup restore "$ARCHIVE" --data "$TEST_DIR" --force
python -c "
import sqlite3, pathlib
conn = sqlite3.connect('$TEST_DIR/afrisearch.db')
assert conn.execute('SELECT count(*) FROM workspaces').fetchone() is not None
print('Restoration verified successfully.')
"
rm -rf "$TEST_DIR"
```
