# SAAS-P0-01 — Implementation Plan: Multi-Tenant Organization Hierarchy

**Document Version:** 1.1.0 (Post-Review Final Architecture Specification)  
**Status:** Approved in Principle (Pre-Implementation Review)  
**Milestone:** SAAS-P0-01 (Organization Data Model & Hierarchy Foundation)  
**Target Codebase:** AfriSearch AI Backend & Web Client  

---

## 1. Architecture Decision Record (ADR) Summary

| Decision ID | Topic | Approved Choice | Rationale & Boundaries |
|---|---|---|---|
| **ADR-01** | Personal Organization Naming | **Option A:** `{user.name}'s Organization`, falling back to `Personal Organization` | Intuitive for solo users, customizable at any time, handles blank names gracefully. |
| **ADR-02** | Organization Deletion Safeguards | **Option A:** Strict multi-member deletion lock | An organization with multiple members **cannot be deleted** until ownership is transferred or all other members are explicitly removed. Prevents silent data loss. |
| **ADR-03** | Workspace Authorization Model | **Organization-level membership containment** (Stage A) | Stage A does not introduce workspace-level memberships. Active organization members have access to workspaces belonging to that organization. Designed for future extension to workspace-level roles without rewriting authorization. |
| **ADR-04** | Orphan Workspace Recovery | **Isolated System Recovery Organization** | Orphaned workspaces are assigned to a system-owned recovery organization (`owner_id = 'system'`), completely hidden from regular users. A migration report is generated, requiring explicit CLI recovery. |
| **ADR-05** | Invitation Security & Cryptography | **Hashed tokens, expiration, verified emails** | Invitations use cryptographically secure random tokens (`secrets.token_urlsafe(32)`), stored only as SHA-256 hashes, with expiration dates, normalized email comparison, and single-use enforcement. |
| **ADR-06** | Migration Operational Window | **Brief Maintenance Window (Planned Restart)** | SQLite schema alterations require exclusive table locks. Described accurately as a managed deployment migration rather than "zero-downtime". |

---

## 2. Stage Breakdown & Execution Roadmap

```
+---------------------------------------------------------------------------------------------------+
| STAGE A: Database Schema & Invariant Specifications                                               |
| - organizations, organization_members, and organization_invitations tables                        |
| - Foreign keys, composite PKs, case-insensitive email indexing, and owner invariants              |
+---------------------------------------------------------------------------------------------------+
                                                  |
                                                  v
+---------------------------------------------------------------------------------------------------+
| STAGE B: Managed Migration & Orphan Recovery Engine                                               |
| - SQLite migration script in backend/db.py:migrate                                                |
| - Idempotent backfill with atomic transaction isolation                                           |
| - Dedicated system recovery organization for orphaned workspaces + JSON audit report              |
+---------------------------------------------------------------------------------------------------+
                                                  |
                                                  v
+---------------------------------------------------------------------------------------------------+
| STAGE C: Server-Side Authorization Pipeline                                                        |
| - current_organization dependency in backend/auth.py                                              |
| - Organization-scoped workspace containment in backend/main.py:current_workspace                   |
| - Hard server-side defense against manipulated cross-tenant IDs                                   |
| - Full preservation of local development mode (AFRISEARCH_AUTH=none)                              |
+---------------------------------------------------------------------------------------------------+
                                                  |
                                                  v
+---------------------------------------------------------------------------------------------------+
| STAGE D: REST API Endpoints & Invitation Management                                               |
| - /api/organizations (CRUD, members, ownership transfer)                                          |
| - /api/organizations/{id}/invitations (create, revoke, accept via secure token)                   |
| - Strict deletion safeguards (blocks deletion if non-owner members exist)                         |
+---------------------------------------------------------------------------------------------------+
                                                  |
                                                  v
+---------------------------------------------------------------------------------------------------+
| STAGE E: Client UI Integration                                                                    |
| - Update types.ts with Organization, OrganizationMember, Invitation models                        |
| - Inject X-Organization-Id header in api.ts                                                       |
| - Organization switcher dropdown in AppLayout.tsx sidebar                                         |
+---------------------------------------------------------------------------------------------------+
                                                  |
                                                  v
+---------------------------------------------------------------------------------------------------+
| STAGE F: Test Verification & Rollback Rehearsal                                                   |
| - Dedicated tests/test_organizations.py (migration, isolation, invitations, transfer)             |
| - 100% regression verification of all 177 existing backend tests and frontend Vitest suite        |
+---------------------------------------------------------------------------------------------------+
```

---

## 3. Impacted Source Files & Functions

### Backend Modules

| File Path | Impacted / Target Functions | Exact Architectural Scope |
|---|---|---|
| `backend/db.py` | `SCHEMA`<br>`migrate(conn)`<br>`create_organization()`<br>`get_organization()`<br>`list_user_organizations()`<br>`rename_organization()`<br>`transfer_organization_ownership()`<br>`delete_organization()`<br>`add_organization_member()`<br>`list_organization_members()`<br>`remove_organization_member()`<br>`create_organization_invitation()`<br>`get_invitation_by_token()`<br>`accept_organization_invitation()`<br>`cancel_organization_invitation()` | Schema DDL, transactional migration, system recovery organization creation, and data access methods. |
| `backend/auth.py` | `current_organization()`<br>`current_user()` | FastAPI dependency pipeline verifying active user membership in requested organization via `X-Organization-Id` header (or defaulting to user's primary organization). |
| `backend/main.py` | `Organization`<br>`current_workspace()`<br>`api.get("/organizations")`<br>`api.post("/organizations")`<br>`api.get("/organizations/{id}")`<br>`api.patch("/organizations/{id}")`<br>`api.delete("/organizations/{id}")`<br>`api.post("/organizations/{id}/transfer-ownership")`<br>`api.get("/organizations/{id}/members")`<br>`api.delete("/organizations/{id}/members/{uid}")`<br>`api.post("/organizations/{id}/invitations")`<br>`api.post("/organizations/invitations/accept")` | Request routing, authorization guards, ownership transfer endpoints, and invitation token verification. |
| `backend/store.py` | *(Zero modifications required)* | Physical file storage remains strictly partitioned by `workspace_id`. |

### Frontend Modules

| File Path | Impacted Components / Functions | Exact Architectural Scope |
|---|---|---|
| `web/src/lib/types.ts` | `Organization`<br>`OrganizationMember`<br>`OrganizationInvitation`<br>`Workspace` (updated with `organization_id`) | TypeScript contract definitions. |
| `web/src/lib/api.ts` | `setOrganizationId()`<br>`authHeaders()` | Transmits `X-Organization-Id` header alongside `X-Workspace-Id`. |
| `web/src/lib/workspace.tsx` | `WorkspaceProvider`<br>`useWorkspace()` | Stores active organization, coordinates organization switching, and scopes child workspaces. |
| `web/src/pages/AppLayout.tsx` | `OrganizationSwitcher`<br>`WorkspaceSwitcher` | Two-tier hierarchical navigation in sidebar (Organization -> Workspace). |
| `web/src/pages/SettingsPage.tsx` | `OrganizationSection`<br>`MembersTable` | Manage organization name, invite members, transfer ownership, and safe deletion dialog. |

---

## 4. Work Invariants & Non-Goals

### Stage A Non-Goals (Strict Boundaries)
- **NO Billing Integration:** Stripe, Chapa, Paystack, and invoice generation are strictly excluded from SAAS-P0-01.
- **NO Workspace-Level Permissions:** Stage A models membership at the Organization tier. Fine-grained workspace-level roles (`workspace_members`) are slated for subsequent milestones.
- **NO Unnecessary File Moves:** Document uploads, chunk files, and embeddings remain in `data/workspaces/<id>/`.
