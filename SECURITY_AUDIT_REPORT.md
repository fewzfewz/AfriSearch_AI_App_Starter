# AfriSearch AI — Security Audit Report (PR-01)

**Audit Target:** AfriSearch AI Commercial SaaS Platform  
**Scope:** Authentication, Multi-Tenant Isolation, RBAC, Payment Gateways & Webhooks, Data Protection, and API Boundaries  
**Status:** Comprehensive Security Audit  
**Date:** November 9, 2026  

---

## 1. Authentication & Authorization Findings

### 1.1. Insecure Default Authentication Fallback (`AFRISEARCH_AUTH=none`)
- **Classification:** **Verified Vulnerability**
- **File & Line Reference:** [`backend/auth.py:57-58`](file:///home/fewzan/Downloads/AfriSearch_AI_App_Starter/backend/auth.py#L57-L58), [`backend/config.py:32`](file:///home/fewzan/Downloads/AfriSearch_AI_App_Starter/backend/config.py#L32)
- **Vulnerability Mechanism:** 
  The configuration specifies `AUTH_MODE = os.getenv("AFRISEARCH_AUTH", "none").strip().lower()`. When `config.AUTH_MODE == "none"`, `current_user()` automatically returns `LOCAL_USER = User(id="local", email="", name="Local user")` without inspecting or requiring any `Authorization: Bearer <token>` header.
- **Impact:** 
  If deployed into a staging or production container without explicitly specifying `AFRISEARCH_AUTH=supabase`, the API runs completely unauthenticated. Any unauthenticated client on the internet can read, upload, delete, and query all documents and workspaces.
- **Recommended Remediation:** 
  Enforce a hard failure at startup in [`backend/main.py`](file:///home/fewzan/Downloads/AfriSearch_AI_App_Starter/backend/main.py) lifespan or [`backend/config.py`](file:///home/fewzan/Downloads/AfriSearch_AI_App_Starter/backend/config.py) if `AFRISEARCH_ENV == "production"` and `AFRISEARCH_AUTH != "supabase"`.

---

### 1.2. SQLite Write Contention in Authentication Dependency (`ensure_user`)
- **Classification:** **Verified Defect**
- **File & Line Reference:** [`backend/auth.py:78-80`](file:///home/fewzan/Downloads/AfriSearch_AI_App_Starter/backend/auth.py#L78-L80), [`backend/db.py:478-490`](file:///home/fewzan/Downloads/AfriSearch_AI_App_Starter/backend/db.py#L478-L490)
- **Vulnerability Mechanism:** 
  In [`backend/auth.py:78`](file:///home/fewzan/Downloads/AfriSearch_AI_App_Starter/backend/auth.py#L78), every authenticated request invokes `db.ensure_user(user.id, user.email, user.name)`. In [`backend/db.py:487-490`](file:///home/fewzan/Downloads/AfriSearch_AI_App_Starter/backend/db.py#L487-L490), this executes:
  ```sql
  INSERT INTO users (id, email, name, created_at) VALUES (?, ?, ?, ?)
  ON CONFLICT (id) DO UPDATE SET email = excluded.email, name = excluded.name
  ```
  Even read-only GET requests (e.g. `/api/workspaces`, `/api/documents`, `/api/chats`) acquire an exclusive database write lock in SQLite. Under concurrent traffic from multiple tenants, this results in immediate request latency spikes and `sqlite3.OperationalError: database is locked`.
- **Impact:** Denial of Service (DoS) under standard SaaS multi-user concurrency.
- **Recommended Remediation:** 
  Add a thread-safe in-memory cache (e.g. `functools.lru_cache` or a dictionary with timestamp invalidation) to `ensure_user`. Only perform the SQLite write if the user has not been verified within the past 10 minutes or if metadata has changed.

---

### 1.3. Absence of Realtime Token Revocation Checks
- **Classification:** **Missing Capability**
- **File & Line Reference:** [`backend/auth.py:45-53`](file:///home/fewzan/Downloads/AfriSearch_AI_App_Starter/backend/auth.py#L45-L53)
- **Vulnerability Mechanism:** 
  Token validation verifies JWT cryptographic signature and expiration (`exp`, `sub`) using PyJWKClient. However, if a user signs out via Supabase Auth, or if an administrator revokes a compromised session or suspends an account in Supabase, the backend cannot detect this revocation until the JWT expires.
- **Impact:** Stolen JWT access tokens remain functional for their entire lifetime (typically 1 hour) after administrative revocation.
- **Recommended Remediation:** 
  Subscribe to Supabase Auth webhooks to maintain an in-memory or Redis-backed token revocation blocklist, or provide a fast-path cache verification for active sessions.

---

## 2. Multi-Tenant Isolation & Authorization Findings

### 2.1. Tenant Isolation Breach on Omitted `X-Organization-Id`
- **Classification:** **Verified Vulnerability**
- **File & Line Reference:** [`backend/main.py:243-247`](file:///home/fewzan/Downloads/AfriSearch_AI_App_Starter/backend/main.py#L243-L247), [`backend/db.py:1115-1120`](file:///home/fewzan/Downloads/AfriSearch_AI_App_Starter/backend/db.py#L1115-L1120)
- **Vulnerability Mechanism:** 
  When a request provides `X-Workspace-Id` but omits `X-Organization-Id`, `current_workspace` falls back:
  ```python
  found = get_workspace_membership(x_workspace_id, user.id, org_id) if org_id else db.get_workspace(x_workspace_id, user.id)
  ```
  [`db.get_workspace(workspace_id, user_id)`](file:///home/fewzan/Downloads/AfriSearch_AI_App_Starter/backend/db.py#L1115-L1120) executes:
  ```sql
  SELECT w.id, w.organization_id, w.name, w.created_at, m.role FROM workspaces w
  JOIN members m ON m.workspace_id = w.id WHERE w.id = ? AND m.user_id = ?
  ```
  If User U is a member of Organization A and Organization B, and sends an API call intended for Organization A with a workspace ID belonging to Organization B, the backend executes the operation under Organization B's context without verifying organization scoping.
- **Impact:** Cross-tenant contamination, quota misappropriation, and false 404s for Organization Owners not explicitly listed in workspace `members`.
- **Recommended Remediation:** 
  Require `X-Organization-Id` on all workspace requests, or lookup `workspaces.organization_id` first and enforce that the user has an active membership in that organization before proceeding.

---

### 2.2. Shared Chat Access Authorization Boundary
- **Classification:** **Verified Defect**
- **File & Line Reference:** [`backend/main.py:1274-1282`](file:///home/fewzan/Downloads/AfriSearch_AI_App_Starter/backend/main.py#L1274-L1282), [`backend/main.py:1307-1309`](file:///home/fewzan/Downloads/AfriSearch_AI_App_Starter/backend/main.py#L1307-L1309)
- **Vulnerability Mechanism:** 
  Chats can be shared with a workspace via `PATCH /chats/{chat_id}` with `shared=true`. Other workspace members can view the chat via `GET /chats/{chat_id}`. However, when a viewer attempts to rate an answer via `POST /feedback`, line 1307 rejects the request:
  ```python
  if feedback.message_id and not db.get_message(feedback.message_id, workspace.id, workspace.user.id):
      raise HTTPException(status_code=404, detail="Message not found.")
  ```
  Because `get_message` filters by `workspace.user.id`, viewers cannot rate messages created by other members in shared workspace chats.
- **Impact:** Broken collaboration UX and false 404 security barriers for legitimate workspace members.
- **Recommended Remediation:** Allow feedback on messages belonging to any chat that is visible (shared) within the current workspace.

---

## 3. Payment Security & Webhook Findings

### 3.1. Webhook Signature Verification Bypass
- **Classification:** **Verified Vulnerability**
- **File & Line Reference:** [`backend/billing/stripe_provider.py:126-128`](file:///home/fewzan/Downloads/AfriSearch_AI_App_Starter/backend/billing/stripe_provider.py#L126-L128), [`backend/billing/chapa_provider.py:111-113`](file:///home/fewzan/Downloads/AfriSearch_AI_App_Starter/backend/billing/chapa_provider.py#L111-L113)
- **Vulnerability Mechanism:** 
  Both Stripe and Chapa payment providers contain the following fallback logic:
  ```python
  # stripe_provider.py
  if not self.webhook_secret:
      return True
  
  # chapa_provider.py
  if not self.webhook_secret:
      return True
  ```
  If an operator configures Stripe API keys but forgets `STRIPE_WEBHOOK_SECRET` (or if it is missing from environment), signature verification returns `True`. Any unauthenticated external client can POST forged JSON payloads to `/api/billing/stripe/webhook` with `client_reference_id` set to their organization ID and `plan_id: "enterprise"`.
- **Impact:** Complete compromise of commercial subscription billing; unauthorized activation of free enterprise subscriptions and falsification of invoices.
- **Recommended Remediation:** 
  If `self.webhook_secret` is unset or empty, `verify_webhook_signature` MUST return `False` and log a critical security warning. Never allow unverified webhook processing in any environment where authentication is enabled.

---

### 3.2. Out-of-Order Webhook Event Race Conditions
- **Classification:** **Potential Risk requiring further testing**
- **File & Line Reference:** [`backend/billing/stripe_provider.py:175-267`](file:///home/fewzan/Downloads/AfriSearch_AI_App_Starter/backend/billing/stripe_provider.py#L175-L267), [`backend/billing/chapa_provider.py:148-191`](file:///home/fewzan/Downloads/AfriSearch_AI_App_Starter/backend/billing/chapa_provider.py#L148-L191)
- **Vulnerability Mechanism:** 
  While idempotency is handled via `db.is_webhook_event_processed()`, events are not checked for monotonic ordering. Stripe delivery does not guarantee that events arrive in chronological order. If `customer.subscription.deleted` or `customer.subscription.updated` arrives before `checkout.session.completed`, the subscription can be permanently left in an incorrect state.
- **Impact:** Subscription state de-synchronization between payment provider and SaaS database.
- **Recommended Remediation:** Store the provider's `created` timestamp on the subscription record and reject incoming updates that carry older event timestamps than the latest recorded state.

---

### 3.3. Missing Secrets in Production Deployment Configurations
- **Classification:** **Verified Defect**
- **File & Line Reference:** [`deploy/docker-compose.prod.yml:8-17`](file:///home/fewzan/Downloads/AfriSearch_AI_App_Starter/deploy/docker-compose.prod.yml#L8-L17), [`.env.example`](file:///home/fewzan/Downloads/AfriSearch_AI_App_Starter/.env.example)
- **Vulnerability Mechanism:** 
  `deploy/docker-compose.prod.yml` defines the container environment for production, but omits:
  - `STRIPE_SECRET_KEY`
  - `STRIPE_WEBHOOK_SECRET`
  - `CHAPA_SECRET_KEY`
  - `CHAPA_WEBHOOK_SECRET`
  - `CHAPA_API_URL`
  - `BILLING_RETURN_URL_BASE`
- **Impact:** Operators deploying to production via `docker compose -f docker-compose.yml -f deploy/docker-compose.prod.yml up` will deploy a system where payment keys are absent, triggering the signature bypass vulnerability in Section 3.1.
- **Recommended Remediation:** Add explicit declarations for all billing keys to `.env.example` and `deploy/docker-compose.prod.yml`.

---

## 4. Data Protection & File Authorization Findings

### 4.1. Scoped Document Access & Path Traversal Verification
- **Classification:** **Informational Observation (Verified Secure)**
- **File & Line Reference:** [`backend/main.py:935-955`](file:///home/fewzan/Downloads/AfriSearch_AI_App_Starter/backend/main.py#L935-L955), [`backend/store.py:65-90`](file:///home/fewzan/Downloads/AfriSearch_AI_App_Starter/backend/store.py#L65-L90)
- **Observation:** 
  Document downloads (`GET /documents/{source_id}/file`) and citations are scoped by `workspace.store`. File paths are strictly resolved via internal integer/hash source IDs and UUID workspace storage paths (`data/workspaces/<workspace_id>/...`). User-supplied file names are sanitized, preventing path traversal attacks (`../`). Workspace membership checks successfully gate document access.

---

### 4.2. Unchecked In-Memory Object URL Leaks in Web Client
- **Classification:** **Verified Defect**
- **File & Line Reference:** [`web/src/lib/api.ts:123-137`](file:///home/fewzan/Downloads/AfriSearch_AI_App_Starter/web/src/lib/api.ts#L123-L137)
- **Vulnerability Mechanism:** 
  `openDocument()` calls `URL.createObjectURL(await response.blob())` to render PDFs in a new tab. Unlike `downloadFile()` which revokes the URL after 1000ms (`URL.revokeObjectURL(url)`), `openDocument()` never releases the blob.
- **Impact:** Client memory bloat and retention of sensitive document blobs in browser heap memory across long sessions.
- **Recommended Remediation:** Implement `URL.revokeObjectURL` cleanup after tab initialization.

---

## 5. Security Remediation Priority Matrix

| Risk ID | Title | Severity | Remediation Effort | Priority |
| :--- | :--- | :---: | :---: | :---: |
| **CRITICAL-01** | Stripe/Chapa Webhook Signature Bypass | **CRITICAL** | Low (1 hour) | **P0** |
| **CRITICAL-02** | `ensure_user` SQLite Write Lock Contention | **HIGH** | Medium (3 hours) | **P0** |
| **CRITICAL-03** | `X-Organization-Id` Fallback Cross-Tenant Leak | **HIGH** | Medium (2 hours) | **P0** |
| **HIGH-01** | Production Docker Compose Missing Secrets | **HIGH** | Low (30 min) | **P1** |
| **HIGH-02** | Out-of-Order Webhook Timestamp Checks | **MEDIUM** | Medium (4 hours) | **P1** |
| **MED-01** | Realtime Token Revocation Hook | **MEDIUM** | High (1-2 days) | **P2** |
| **MED-02** | Shared Chat Feedback 404 Bug | **LOW** | Low (1 hour) | **P2** |
| **LOW-01** | Client Object URL Revocation | **LOW** | Low (30 min) | **P2** |
