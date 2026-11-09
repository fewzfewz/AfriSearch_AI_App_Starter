# AfriSearch AI — Production Readiness Audit Report (PR-01)

**Audit Date:** November 9, 2026  
**Audited Target:** AfriSearch AI Commercial SaaS Platform  
**Audit Scope:** Full codebase (Backend, Frontend, Schema, Deployments, Integrations, and Evaluations)  
**Test Suite Baseline:** 219/219 backend pytest passing, 5/5 Vitest passing, clean TypeScript compilation and Vite build  
**Git Head Revision:** `f35700f` (Chat history cursor pagination)  

---

## 1. Executive Summary

AfriSearch AI is an AI-powered document search and grounded multilingual retrieval SaaS platform tailored for Pan-African languages and documents. Recent feature development has successfully delivered a multi-tenant hierarchy (`organizations`, `organization_members`, `workspaces`, `workspace_members`), workspace RBAC, dual payment gateways (Stripe & Chapa), token usage tracking, and table-aware document extraction.

However, an exhaustive, evidence-based code and architecture audit demonstrates that **the platform is NOT YET READY FOR HIGH-SCALE PRODUCTION COMMERCIAL TRAFFIC**. 

While the functional domain logic is well-architected and tested for single-user and synchronous flows, there are **critical vulnerabilities and reliability bottlenecks** that must be resolved prior to public release:
1. **Critical Payment Security Bypass:** Webhook signature verification in Stripe and Chapa providers defaults to `True` if secret keys are missing, permitting unauthenticated webhook forgery in unconfigured or misconfigured environments.
2. **Database Concurrency & Locking Bottleneck:** Every API call—including read-only GET requests—triggers an exclusive SQLite write transaction via `ensure_user()`. Under moderate concurrent multi-tenant load, this will trigger `sqlite3.OperationalError: database is locked`.
3. **Cross-Tenant Fallback Flaw:** Omitting the `X-Organization-Id` header causes workspace resolution to bypass organization scoping, leaking multi-tenant boundaries and generating false 404s for organization administrators.
4. **Single-Worker Indexing Queue:** A hardcoded `ThreadPoolExecutor(max_workers=1)` globally serializes document ingestion across all tenants, creating a denial-of-service vector where a single tenant's heavy upload stalls ingestion for the entire platform.
5. **AI Quality & Cost Gaps:** Local CPU inference on `Qwen2.5-0.5B` achieves only 35.9% accuracy on the test corpus with a 47.7-second average latency, while queries using local models bypass monthly AI quota counting entirely.

---

## 2. Completed Capabilities Audit

| Capability Area | Implemented Features | Status | Code Location |
| :--- | :--- | :--- | :--- |
| **Multi-Tenancy** | Organization hierarchy, membership management, invitation tokens, multi-tenant isolation | **Implemented** | [`backend/db.py`](file:///home/fewzan/Downloads/AfriSearch_AI_App_Starter/backend/db.py#L210-L280), [`backend/auth.py`](file:///home/fewzan/Downloads/AfriSearch_AI_App_Starter/backend/auth.py#L83-L101) |
| **Workspace RBAC** | 4-tier role enforcement (`owner`, `admin`, `member`, `viewer`), granular endpoint access gates | **Implemented** | [`backend/main.py`](file:///home/fewzan/Downloads/AfriSearch_AI_App_Starter/backend/main.py#L278-L315) |
| **Payments & Billing** | Stripe Checkout & Portal, Chapa Checkout, invoice ledger, webhook event deduplication | **Implemented** | [`backend/billing/`](file:///home/fewzan/Downloads/AfriSearch_AI_App_Starter/backend/billing/), [`backend/db.py`](file:///home/fewzan/Downloads/AfriSearch_AI_App_Starter/backend/db.py#L320-L420) |
| **Usage & Quotas** | Multi-tier plan definitions (`free`, `pro`, `business`, `enterprise`), storage & query entitlements | **Implemented** | [`backend/entitlements.py`](file:///home/fewzan/Downloads/AfriSearch_AI_App_Starter/backend/entitlements.py#L8-L78), [`backend/db.py`](file:///home/fewzan/Downloads/AfriSearch_AI_App_Starter/backend/db.py#L858-L886) |
| **Document Retrieval** | Multilingual semantic search (`multilingual-e5-small`), cross-encoder reranker, table extraction | **Implemented** | [`backend/search.py`](file:///home/fewzan/Downloads/AfriSearch_AI_App_Starter/backend/search.py), [`backend/extract.py`](file:///home/fewzan/Downloads/AfriSearch_AI_App_Starter/backend/extract.py#L130-L200) |
| **Chat & Pagination** | Grounded streaming answers, citations, chat cursor pagination (`before` + `limit`) | **Implemented** | [`backend/main.py`](file:///home/fewzan/Downloads/AfriSearch_AI_App_Starter/backend/main.py#L1250-L1266), [`backend/db.py`](file:///home/fewzan/Downloads/AfriSearch_AI_App_Starter/backend/db.py#L1260-L1285) |
| **Operations** | Online SQLite backup API, Caddy reverse proxy, Sentry exception capture | **Implemented** | [`backend/backup.py`](file:///home/fewzan/Downloads/AfriSearch_AI_App_Starter/backend/backup.py), [`deploy/Caddyfile`](file:///home/fewzan/Downloads/AfriSearch_AI_App_Starter/deploy/Caddyfile) |

---

## 3. Critical Findings (P0 Blockers)

### 3.1. [CRITICAL-01] Unauthenticated Payment Webhook Forgery via Missing Secret Gate
- **Classification:** **Verified Vulnerability**
- **Location:** [`backend/billing/stripe_provider.py:126-128`](file:///home/fewzan/Downloads/AfriSearch_AI_App_Starter/backend/billing/stripe_provider.py#L126-L128), [`backend/billing/chapa_provider.py:111-113`](file:///home/fewzan/Downloads/AfriSearch_AI_App_Starter/backend/billing/chapa_provider.py#L111-L113)
- **Description:** If `STRIPE_WEBHOOK_SECRET` or `CHAPA_WEBHOOK_SECRET` is unset or empty, `verify_webhook_signature` returns `True` unconditionally. Furthermore, [`deploy/docker-compose.prod.yml`](file:///home/fewzan/Downloads/AfriSearch_AI_App_Starter/deploy/docker-compose.prod.yml) and [`.env.example`](file:///home/fewzan/Downloads/AfriSearch_AI_App_Starter/.env.example) omit these environment variables entirely. Any malicious actor can POST forged checkout payloads to `/api/billing/stripe/webhook` or `/api/billing/chapa/webhook` and grant themselves free active Enterprise subscriptions and forged invoice records.
- **Evidence:**
```python
# backend/billing/stripe_provider.py:126-128
if not self.webhook_secret:
    # When unconfigured in dev/test, permit requests
    return True
```
- **Remediation:** Enforce strict rejection (`return False` or raise 500 configuration error) if webhook secrets are missing in production environments (`config.ENVIRONMENT == "production"` or `config.AUTH_MODE == "supabase"`).

---

### 3.2. [CRITICAL-02] SQLite Write Contention Bottleneck on Every HTTP Request
- **Classification:** **Verified Defect**
- **Location:** [`backend/auth.py:78-80`](file:///home/fewzan/Downloads/AfriSearch_AI_App_Starter/backend/auth.py#L78-L80), [`backend/db.py:478-490`](file:///home/fewzan/Downloads/AfriSearch_AI_App_Starter/backend/db.py#L478-L490)
- **Description:** The `current_user` FastAPI dependency runs on virtually every incoming HTTP endpoint. It calls `db.ensure_user(user.id, user.email, user.name)`. Inside `db.ensure_user`, an `INSERT INTO users ... ON CONFLICT (id) DO UPDATE` is executed within an exclusive write transaction. In SQLite WAL mode, concurrent readers do not block readers, but **any write takes an exclusive database write lock**. Concurrent requests from 20-50 simultaneous users will cause severe lock contention and `sqlite3.OperationalError: database is locked`.
- **Evidence:**
```python
# backend/auth.py:78
if db.ensure_user(user.id, user.email, user.name) and config.AUTH_MODE == "supabase":
    mailer.send(mailer.welcome(user.email, user.name))
```
- **Remediation:** Cache authenticated users in memory (LRU cache or Redis), or check if user exists in a read-only transaction first; only execute `INSERT ... ON CONFLICT` if user metadata has changed or the user is not found in cache.

---

### 3.3. [CRITICAL-03] Cross-Tenant Workspace Resolution Fallback
- **Classification:** **Verified Vulnerability**
- **Location:** [`backend/main.py:243-247`](file:///home/fewzan/Downloads/AfriSearch_AI_App_Starter/backend/main.py#L243-L247), [`backend/db.py:1115-1120`](file:///home/fewzan/Downloads/AfriSearch_AI_App_Starter/backend/db.py#L1115-L1120)
- **Description:** If a client provides `X-Workspace-Id` but omits `X-Organization-Id`, the backend falls back to `db.get_workspace(x_workspace_id, user.id)` without validating against the active organization. In multi-org user scenarios, operations execute across tenant boundaries. Additionally, an organization owner or admin who does not have an explicit entry in the `members` table is rejected with a 404 "Workspace not found" because line 1118 queries `JOIN members m` directly rather than checking `organization_members`.
- **Evidence:**
```python
# backend/main.py:244
found = get_workspace_membership(x_workspace_id, user.id, org_id) if org_id else db.get_workspace(x_workspace_id, user.id)
```
- **Remediation:** Make `X-Organization-Id` mandatory when `AFRISEARCH_AUTH=supabase`, or resolve the workspace's owning organization from `workspaces.organization_id` and verify membership against that specific organization.

---

### 3.4. [CRITICAL-04] Global Indexing Head-of-Line Blocking (Single Worker)
- **Classification:** **Verified Defect**
- **Location:** [`backend/jobs.py:14`](file:///home/fewzan/Downloads/AfriSearch_AI_App_Starter/backend/jobs.py#L14)
- **Description:** Background document indexing is executed via a global single-worker thread pool: `ThreadPoolExecutor(max_workers=1, thread_name_prefix="indexer")`. All organizations and workspaces share this single indexing worker. If Organization A uploads a 100-page scanned PDF requiring extensive Tesseract OCR, Organization B's uploads are queued behind it and completely blocked.
- **Evidence:**
```python
# backend/jobs.py:14
_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="indexer")
```
- **Remediation:** Introduce workspace or tenant-level concurrency with a distributed task queue (e.g. Celery / RQ / Arq) or a configurable worker pool with fair tenant scheduling.

---

## 4. Categorized Production Risks

### 4.1. High Risks (P1)

1. **Non-Atomic Quota Enforcement & Race Conditions**
   - *Classification:* **Verified Defect**
   - *Location:* [`backend/entitlements.py:91-155`](file:///home/fewzan/Downloads/AfriSearch_AI_App_Starter/backend/entitlements.py#L91-L155)
   - *Evidence:* Quota checks (`check_can_create_workspace`, `check_can_add_member`, `check_can_upload`, `check_can_ask`) read current totals from SQLite, but the subsequent insertions occur in decoupled transactions. Concurrent requests easily burst past storage, seat, and workspace quotas.
2. **Quota Bypass for Local & Zero-Token Models**
   - *Classification:* **Verified Defect**
   - *Location:* [`backend/main.py:1110-1111`](file:///home/fewzan/Downloads/AfriSearch_AI_App_Starter/backend/main.py#L1110-L1111)
   - *Evidence:* `record_usage()` aborts early if `not provider or not (usage.input_tokens or usage.output_tokens)`. In `db.get_organization_usage_summary`, `questions_count` is calculated via `count(*) FROM usage`. Consequently, local model queries (`local/qwen2.5-0.5b`) and canned responses never insert a row in `usage`, allowing free-tier tenants to consume infinite AI requests.
3. **Chapa Webhook Metadata Loss Risk**
   - *Classification:* **Potential Risk requiring further testing**
   - *Location:* [`backend/billing/chapa_provider.py:154-169`](file:///home/fewzan/Downloads/AfriSearch_AI_App_Starter/backend/billing/chapa_provider.py#L154-L169)
   - *Evidence:* `tx_ref` contains only the first 8 characters of `organization_id` (`org_id[:8]`). If Chapa's webhook fails to preserve the `meta` object, the backend attempts to look up the organization by truncated ID or prior subscription ID, which fails for initial checkouts. The webhook returns 200 OK ("processed"), but the organization is never upgraded.
4. **Out-of-Order Stripe Webhook Inconsistencies**
   - *Classification:* **Potential Risk requiring further testing**
   - *Location:* [`backend/billing/stripe_provider.py:239-267`](file:///home/fewzan/Downloads/AfriSearch_AI_App_Starter/backend/billing/stripe_provider.py#L239-L267)
   - *Evidence:* Webhook events are processed without monotonic event sequence timestamp validation. If an out-of-order `customer.subscription.deleted` or `customer.subscription.updated` event arrives before `checkout.session.completed`, subscription state can revert or remain active indefinitely.
5. **PDF Table Extraction Degradation**
   - *Classification:* **Missing Capability**
   - *Location:* [`backend/extract.py:209-224`](file:///home/fewzan/Downloads/AfriSearch_AI_App_Starter/backend/extract.py#L209-L224)
   - *Evidence:* Unlike `.docx`, `.xlsx`, and `.csv` which format tabular data into GitHub-Flavored Markdown tables, PDF processing uses `pypdf.PdfReader.extract_text()`, stripping table column structures and scrambling complex layout data prior to chunking and vector indexing.

---

### 4.2. Medium Risks (P2)

1. **Process-Local In-Memory Rate Limiting**
   - *Classification:* **Verified Defect**
   - *Location:* [`backend/limits.py:30-55`](file:///home/fewzan/Downloads/AfriSearch_AI_App_Starter/backend/limits.py#L30-L55)
   - *Evidence:* Rate limits (`_events: dict[str, deque[float]]`) are stored in process memory. Running multiple uvicorn workers or multi-node container clusters multiplies allowed request rates by the number of processes. Unused user keys are never evicted, causing unbounded memory growth.
2. **Missing Token Revocation & Blocklisting**
   - *Classification:* **Missing Capability**
   - *Location:* [`backend/auth.py:45-53`](file:///home/fewzan/Downloads/AfriSearch_AI_App_Starter/backend/auth.py#L45-L53)
   - *Evidence:* Supabase JWT verification validates expiration (`exp`) and signature locally. It does not check realtime Supabase session revocation or support a local revoked-token blocklist.
3. **Unbounded Client Memory in Document Viewer**
   - *Classification:* **Verified Defect**
   - *Location:* [`web/src/lib/api.ts:123-137`](file:///home/fewzan/Downloads/AfriSearch_AI_App_Starter/web/src/lib/api.ts#L123-L137)
   - *Evidence:* `openDocument()` creates blob object URLs via `URL.createObjectURL(blob)` but never revokes them. Browsing tens of large PDF documents in a single session causes client browser memory leaks.
4. **Chat Cursor Pagination Tie-Breaker Omission**
   - *Classification:* **Potential Risk requiring further testing**
   - *Location:* [`backend/db.py:1260-1285`](file:///home/fewzan/Downloads/AfriSearch_AI_App_Starter/backend/db.py#L1260-L1285)
   - *Evidence:* `list_chats` queries `WHERE c.updated_at < ? ORDER BY c.updated_at DESC`. In automated batch imports or rapid creation where two chats have identical microsecond timestamps, pagination boundaries will skip or duplicate items.
5. **Feedback Blocked on Shared Chats**
   - *Classification:* **Verified Defect**
   - *Location:* [`backend/main.py:1307-1309`](file:///home/fewzan/Downloads/AfriSearch_AI_App_Starter/backend/main.py#L1307-L1309)
   - *Evidence:* `add_feedback` checks `db.get_message(feedback.message_id, workspace.id, workspace.user.id)`. When User B interacts with a shared workspace chat created by User A, User B receives a 404 "Message not found" when submitting ratings.

---

### 4.3. Low Risks & Informational Observations

1. **Docker Compose Production Secret Pass-Through Gaps**
   - *Classification:* **Informational Observation**
   - *Location:* [`deploy/docker-compose.prod.yml:8-17`](file:///home/fewzan/Downloads/AfriSearch_AI_App_Starter/deploy/docker-compose.prod.yml#L8-L17)
   - Billing variables (`STRIPE_SECRET_KEY`, `CHAPA_SECRET_KEY`, etc.) are absent from `deploy/docker-compose.prod.yml`.
2. **Evaluation Corpus Language Imbalance**
   - *Classification:* **Informational Observation**
   - *Location:* [`evaluation/questions.json`](file:///home/fewzan/Downloads/AfriSearch_AI_App_Starter/evaluation/questions.json)
   - Over 55% of benchmark questions are English. African languages have 1 to 6 questions each, and major languages like Yoruba, Igbo, and Zulu have zero benchmark coverage.
3. **Database Migration Tracking Without Version Table**
   - *Classification:* **Informational Observation**
   - *Location:* [`backend/db.py:204-240`](file:///home/fewzan/Downloads/AfriSearch_AI_App_Starter/backend/db.py#L204-L240)
   - Migrations rely on `PRAGMA table_info` and `CREATE TABLE IF NOT EXISTS` scripts rather than an explicit versioned migration ledger (e.g. Alembic).

---

## 5. Production Readiness Verdict

| Category | Readiness Score | Gate Status |
| :--- | :---: | :--- |
| **Authentication & RBAC** | 7.5 / 10 | **CONDITIONAL** (Fix `ensure_user` lock and `X-Organization-Id` fallback) |
| **Payments & Invoicing** | 5.0 / 10 | **BLOCKED** (Fix webhook signature verification bypass & Chapa meta loss) |
| **Usage & Quotas** | 6.5 / 10 | **CONDITIONAL** (Fix atomic enforcement & local model quota counting) |
| **Retrieval & Ingestion** | 6.0 / 10 | **BLOCKED** (Resolve single-worker queue head-of-line blocking) |
| **Chat & Collaboration** | 8.5 / 10 | **READY** (Minor shared chat feedback fix required) |
| **Reliability & DevOps** | 6.0 / 10 | **CONDITIONAL** (Automate backup daemon & Redis rate limiting) |
| **Frontend Experience** | 8.0 / 10 | **READY** (Fix object URL revocation) |
| **OVERALL** | **6.8 / 10** | **NOT READY FOR PRODUCTION DEPLOYMENT** |
