# AfriSearch AI — Feature Roadmap & Implementation Plan

This roadmap provides an ordered, risk-mitigated development plan for AfriSearch AI. It translates the project audit into concrete, bite-sized tasks structured according to production release gates:

- **P0 — Critical:** Required before external pilot onboarding (stability, deployment, verified auth).
- **P1 — High:** Essential for pilot organizations (table accuracy, permissions, expanded African languages).
- **P2 — Medium:** Scaling, persistent queues, and pan-African payment monetization.
- **P3 — Low:** Advanced multimodal, voice, conversational bots, and desktop offline bundles.

---

## Feature Evaluation Matrix (Keep, Add, Remove, Defer)

| Feature | Action | User Value | Complexity | Dependencies | Acceptance Criteria |
|---|---|---|---|---|---|
| **Folders & Tags** | **Keep & Finalize** | High. Allows teams to partition documents (e.g. Legal, Finance) and scope queries. | Low (code already written & passing tests). | None. | Document tagging, bulk tagging, and tag-scoped retrieval work in UI and API. |
| **Streamed Cited Answers** | **Keep & Improve** | Critical. Grounded answers with instant token streaming and verifiable citations. | Medium. | LLM providers. | Streaming produces citation chips; invalid citations are scrubbed; stops on refusal. |
| **Legacy `frontend/` Dir** | **Remove** | Medium. Eliminates confusion with active `web/` app. | Very Low. | None. | Orphaned `frontend/` folder removed without affecting `web/` or tests. |
| **Table-Aware Chunking** | **Add (P1)** | High. Avoids corrupted context when answering questions from financial spreadsheets and tabular PDFs. | Medium. | `openpyxl`, `pypdf`. | Excel and PDF tables maintain header associations in retrieved chunks. |
| **Workspace RBAC** | **Add (P1)** | High. Prevents junior staff or external viewers from deleting documents or settings. | Medium. | `backend/db.py`, `auth.py`. | Roles (`owner`, `admin`, `member`, `viewer`) enforced across all API endpoints. |
| **Chat Cursor Pagination**| **Add (P1)** | Medium. Ensures users with extensive chat histories can access older threads. | Low. | `backend/db.py`. | Chat sidebar loads subsequent 50 chats on scroll. |
| **PostgreSQL + pgvector** | **Defer (P2)** | Medium (for pilot), High (at scale). Eliminates memory limits of NumPy vector files. | High. | PostgreSQL infrastructure. | Vector similarity search executed via pgvector indices without file locks. |
| **Pan-African Payments** | **Defer (P2)** | High for revenue. Telebirr, M-Pesa, card payments via Chapa and Paystack. | High. | Merchant accounts, webhooks. | Subscriptions and quotas activated automatically upon payment confirmation. |
| **Voice / Speech Query** | **Defer (P3)** | High for rural/field users. Enables spoken queries in Swahili/Amharic. | High. | Speech recognition model. | Audio queries transcribed accurately and answered via audio synthesis. |
| **WhatsApp / Telegram Bot**| **Defer (P3)** | High for non-technical users. Allows document querying via mobile messengers. | High. | Webhook server, messaging APIs. | Field workers can query workspace documents via WhatsApp messages. |

---

## Phase 0: Launch Preparation & Stabilization (P0)

### TASK-SAAS-P0-01: Multi-Tenant Organization Data Model & Hierarchy Foundation (COMPLETED)
- **Status:** Completed & Verified (198/198 Backend tests, 5/5 Vitest, clean Vite build)
- **Delivered Capabilities:**
  - Multi-tenant organization tables (`organizations`, `organization_members`, `organization_invitations`).
  - Strict workspace-to-organization foreign key containment (`workspaces.organization_id`).
  - Safe transactional migration with backfill to personal organizations (`{user.name}'s Organization`).
  - Isolated System Recovery Organization (`system-recovery-org-000000000000`) for orphaned workspaces, plus admin recovery CLI (`backend/recover_workspace.py`).
  - Atomic ownership transfer and multi-member deletion lock (ADR-02 HTTP 409 Conflict).
  - Cryptographically secure invitation tokens (SHA-256 hashed, 7-day expiration).
  - Server-side containment authorization (`current_organization`, `current_workspace`, `X-Organization-Id`).
  - REST API suite (`/api/organizations/*`) with full validation.
  - Client UI hierarchical switcher (`Organization -> Workspace`) and Organization settings management.
- **Relevant Files:**
  - `backend/db.py`, `backend/auth.py`, `backend/main.py`, `backend/mailer.py`, `backend/recover_workspace.py`
  - `web/src/lib/types.ts`, `web/src/lib/api.ts`, `web/src/lib/workspace.tsx`, `web/src/pages/AppLayout.tsx`, `web/src/pages/SettingsPage.tsx`
  - `tests/test_organizations_db.py`, `tests/test_organizations_auth.py`, `tests/test_organizations_api.py`

---

### TASK-SAAS-P0-02: Subscription Plans, Usage Metering & Quotas (COMPLETED)
- **Status:** Completed & Verified (207/207 Backend tests, 5/5 Vitest, clean Vite build)
- **Delivered Capabilities:**
  - Database schema: `subscriptions` and `organization_usage_cycles` tables with transactional migration and auto-backfill of active Free plan.
  - Commercial subscription tiers: Free, Pro, Business, Enterprise with seat, workspace, storage, document, and monthly query limits.
  - Server-side entitlement enforcement engine in `backend/entitlements.py`.
  - HTTP 402/403 pre-flight verification on workspace creation, member invites, file uploads, and AI queries with actionable `X-Upgrade-Required` headers.
  - REST APIs: `GET /api/plans`, `GET /api/organizations/{id}/subscription`, `GET /api/organizations/{id}/usage`.
  - Frontend integration: live visual usage progress meters and active plan badge in Organization Settings.
- **Relevant Files:**
  - `backend/db.py`, `backend/entitlements.py`, `backend/main.py`
  - `web/src/lib/types.ts`, `web/src/pages/SettingsPage.tsx`
  - `tests/test_subscriptions_db.py`, `tests/test_entitlements.py`

---

### TASK-SAAS-P1-02: Payment Gateways & Invoicing Integration (Stripe & Chapa) (COMPLETED)
- **Status:** Completed & Verified (217/217 Backend tests, 5/5 Vitest, clean Vite build)
- **Delivered Capabilities:**
  - Database schema: `invoices` table and `webhook_events` idempotency journal table with transactional SQLite migrations.
  - Pluggable provider architecture in `backend/billing/` for Stripe (Global Credit Cards) and Chapa (Ethiopian Rails: Telebirr, CBE Birr in ETB).
  - Secure webhook ingestion pipeline with cryptographic HMAC signature verification (Stripe and Chapa).
  - Webhook event idempotency handling to prevent duplicate subscription state updates or duplicate invoice records.
  - Lifecycle management: `checkout.session.completed`, `invoice.paid`, `customer.subscription.updated`, `customer.subscription.deleted`, `charge.success`.
  - REST API suite: `POST /api/organizations/{id}/checkout`, `POST /api/organizations/{id}/billing-portal`, `GET /api/organizations/{id}/invoices`, `POST /api/webhooks/stripe`, `POST /api/webhooks/chapa`.
  - Web UI: Plan upgrade selector with dual payment rails (Stripe / Chapa) and interactive checkout, customer billing portal launcher, and Invoices ledger in Organization Settings.
- **Relevant Files:**
  - `backend/db.py`, `backend/config.py`, `backend/entitlements.py`, `backend/main.py`
  - `backend/billing/base.py`, `backend/billing/stripe_provider.py`, `backend/billing/chapa_provider.py`, `backend/billing/service.py`, `backend/billing/__init__.py`
  - `web/src/lib/types.ts`, `web/src/pages/SettingsPage.tsx`
  - `tests/test_billing.py`

---

### TASK-P0-01: Commit & Stabilize Active "Folders and Tags" Feature
- **Priority:** P0 (Critical)
- **Problem Being Solved:** The working directory contains uncommitted changes across 10 files implementing document tagging, bulk tagging, and tag-scoped search. The feature works and passes all tests, but must be cleanly committed to avoid state drift.
- **Relevant Files:**
  - `backend/main.py`
  - `backend/store.py`
  - `tests/test_ask.py`
  - `tests/test_documents.py`
  - `web/src/components/composer.tsx`
  - `web/src/lib/types.ts`
  - `web/src/pages/ChatPage.tsx`
  - `web/src/pages/LibraryPage.tsx`
  - `CHANGELOG.md`
  - `TODO.md`
- **Proposed Changes:** Review git diff, verify tests pass, and stage a formal commit: `Add folders and tags: document collections and scoped search`.
- **Dependencies:** None.
- **Acceptance Criteria:**
  - Working directory is clean.
  - Pytest (177 tests) and Vitest (5 tests) pass.
  - Tag creation, editing, deletion, and tag filtering in Ask and Library work seamlessly.
- **Tests Required:** `pytest tests/test_documents.py tests/test_ask.py`, `npm --prefix web run test`.
- **Risks & Rollback:** Low risk. Clean git commit allows standard `git revert` if necessary.

---

### TASK-P0-02: Clean Up Abandoned `frontend/` Directory
- **Priority:** P0 (Maintenance)
- **Problem Being Solved:** The `frontend/` directory contains only an obsolete `__pycache__` artifact from the superseded Streamlit prototype.
- **Relevant Files:**
  - `frontend/`
- **Proposed Changes:** Remove `frontend/` directory and ensure `.gitignore` excludes any future pycache artifacts.
- **Dependencies:** None.
- **Acceptance Criteria:**
  - `frontend/` directory no longer exists in repository.
  - Backend and frontend builds remain fully operational.
- **Tests Required:** Verify `git status` and run full pytest suite.
- **Risks & Rollback:** Zero risk. No code in `backend/` or `web/` references `frontend/`.

---

### TASK-P0-03: Live Supabase Auth E2E Validation
- **Priority:** P0 (Launch Blocker)
- **Problem Being Solved:** Authentication has been tested with synthetic JWTs in unit tests, but real-world Supabase OAuth, email confirmations, and password resets must be validated with a live instance.
- **Relevant Files:**
  - `backend/auth.py`
  - `web/src/lib/auth.tsx`
  - `web/src/pages/SignInPage.tsx`
  - `.env.example`
- **Proposed Changes:**
  - Configure staging Supabase project credentials in `.env`.
  - Validate email sign-up with email confirmation requirement.
  - Validate Google OAuth login flow and ensure redirect URL matches `/app`.
  - Validate password recovery token exchange.
- **Dependencies:** Live Supabase project.
- **Acceptance Criteria:**
  - User can register with email and receives confirmation link.
  - Unconfirmed users cannot access protected `/api` endpoints.
  - Authenticated session properly syncs user name and email into SQLite `users` table.
- **Tests Required:** Manual user registration test and Playwright E2E run with live auth credentials.
- **Risks & Rollback:** Configuration only; no schema changes required.

---

### TASK-P0-04: Default Cloud Model Provisioning & Benchmark Comparison
- **Priority:** P0 (Launch Blocker)
- **Problem Being Solved:** The small local model (`Qwen 2.5 0.5B`) achieves 0% accuracy on African-language questions. A hosted cloud provider must be activated as the default.
- **Relevant Files:**
  - `backend/llm.py`
  - `backend/config.py`
  - `evaluation/run_eval.py`
- **Proposed Changes:**
  - Provide an API key for at least one cloud provider (Anthropic, OpenAI, or Google Gemini).
  - Execute `python evaluation/run_eval.py --providers claude chatgpt gemini` (or the configured provider) to measure accuracy on the 45-question benchmark.
  - Set `AFRISEARCH_DEFAULT_PROVIDER` to the best performing model.
- **Dependencies:** Provider API key.
- **Acceptance Criteria:**
  - Hosted answer generation achieves >80% factual correctness across the African-language questions in `questions.json`.
  - Answers cite correct source tags (`[S1]`, `[S2]`).
- **Tests Required:** `tests/test_providers.py`, `evaluation/run_eval.py`.
- **Risks & Rollback:** Can revert to any other provider via environment variable.

---

### TASK-P0-05: Cloud VM Deployment with Automated HTTPS (Caddy)
- **Priority:** P0 (Launch Blocker)
- **Problem Being Solved:** The app must be accessible over HTTPS to secure JWT tokens and prevent credential interception.
- **Relevant Files:**
  - `deploy/Caddyfile`
  - `deploy/docker-compose.prod.yml`
  - `docs/deploy.md`
- **Proposed Changes:**
  - Deploy to target Linux server following `docs/deploy.md`.
  - Validate automatic Let's Encrypt certificate issuance via Caddy.
  - Set up a daily cron task for `python -m backend.backup create --out /var/backups/afrisearch --keep 14`.
- **Dependencies:** Domain name (DNS A record) and Linux VM with Docker Compose.
- **Acceptance Criteria:**
  - Navigating to `https://<domain>` renders the web app with an A+ TLS rating.
  - Background health check `/api/health` reports status `ok`.
  - Automated nightly backup archive is created in the backup volume.
- **Tests Required:** Curl health probe over HTTPS, verify backup creation via CLI.
- **Risks & Rollback:** Rollback via `docker compose down` and restore from backup if needed.

---

## Phase 1: Pilot Enhancements & Quality Improvements (P1)

### TASK-P1-01: Table-Aware Extraction & Structured Markdown Preservation (COMPLETED)
- **Status:** Completed & Verified (218/218 Backend tests, 5/5 Vitest, clean Vite build)
- **Priority:** P1 (High)
- **Problem Being Solved:** Financial spreadsheets (`.xlsx`), CSV files, and multi-column tables were flattened into unstructured text, causing split rows and lost column headers during chunking.
- **Relevant Files:**
  - `backend/extract.py`
  - `backend/text.py`
  - `tests/test_formats.py`
- **Delivered Capabilities:**
  - Implemented `format_markdown_table` in `backend/extract.py` converting spreadsheet sheets, CSV files, and Word tables into structured GitHub-flavored Markdown.
  - Table-boundary aware sentence splitting in `backend/text.py`: treats table rows as atomic sentence units, preventing mid-cell splits on decimal numbers (`12.50`), abbreviations (`Dr. Smith`), and punctuation.
  - Cross-chunk table header preservation in `chunk_document`: dynamically detects Markdown table headers and separators, and prepends them to subsequent chunks whenever a large table spans multiple chunks, ensuring all retrieved passages retain complete column context for retrieval and generative question answering.
- **Dependencies:** Existing `openpyxl` dependency.
- **Acceptance Criteria Met:**
  - Excel files and CSVs are extracted as valid Markdown tables with headers and separators.
  - Retrieval and chunking retain headers across multi-chunk segments with 100% test coverage.

---

### TASK-P1-02: Role-Based Access Control (RBAC) in Workspaces (COMPLETED)
- **Status:** Completed & Verified (212/212 Backend tests, 5/5 Vitest, clean Vite build)
- **Priority:** P1 (High)
- **Problem Being Solved:** Pre-RBAC, all workspace members had equal write permissions. Pilot organizations require distinct permission tiers (`owner`, `admin`, `member`, `viewer`).
- **Relevant Files:**
  - `backend/db.py`
  - `backend/main.py`
  - `web/src/lib/types.ts`
  - `web/src/pages/SettingsPage.tsx`
  - `web/src/pages/LibraryPage.tsx`
  - `tests/test_workspace_rbac.py`
- **Delivered Capabilities:**
  - Expanded roles hierarchy: `owner (4) > admin (3) > member (2) > viewer (1)`.
  - SQLite check constraint migration updating `members` role constraint.
  - Granular API route enforcement with `require_workspace_role()`:
    - `POST /documents/upload`, `POST /documents/index`, `POST /documents/{id}/replace`, `DELETE /documents/{id}` require `admin`.
    - `PATCH/PUT /documents/{id}/tags` require `member`.
    - Chat creation/saving restricted for viewers (HTTP 403 when saving).
    - Member invites and role management restricted to owners and admins (`PATCH /api/workspaces/{id}/members/{member_id}`).
  - Client UI controls:
    - Viewers and members see read-only controls in Library (no dropzone, no file replace/delete; viewers cannot edit tags).
    - Admins/owners see role selector when inviting members and inline dropdown to update roles (`admin`, `member`, `viewer`).

---

### TASK-P1-03: Chat History Cursor Pagination (COMPLETED)
- **Status:** Completed & Verified (219/219 Backend tests, 5/5 Vitest, clean Vite build)
- **Priority:** P1 (High)
- **Problem Being Solved:** Pre-pagination, `GET /api/chats` queried a hard-coded limit, restricting access to older conversations for active users.
- **Relevant Files:**
  - `backend/db.py`
  - `backend/main.py`
  - `web/src/pages/AppLayout.tsx`
  - `tests/test_chats.py`
- **Delivered Capabilities:**
  - Added `before` (timestamp ISO cursor) and `limit` query parameters to `GET /api/chats` and `db.list_chats()`.
  - Maintained backward compatibility returning `chats`, `shared`, `has_more`, and `next_cursor`.
  - Added "Load earlier chats" action in `AppLayout.tsx` which seamlessly appends subsequent pages to the sidebar chat list while preserving date grouping.
  - Added unit tests in `tests/test_chats.py` verifying cursor offset, page boundaries, and reverse-chronological ordering.

---

### TASK-P1-04: Expanded African Language Evaluation Set & Vocabulary Tuning
- **Priority:** P1 (High)
- **Problem Being Solved:** The evaluation benchmark contains only 1 question each for Somali, Hausa, and Afaan Oromo, and the Afaan Oromo question failed retrieval (`0/1 hits`).
- **Relevant Files:**
  - `evaluation/corpus/`
  - `evaluation/questions.json`
  - `evaluation/run_eval.py`
- **Proposed Changes:**
  - Add 5 new benchmark questions per language for Somali (`so`), Afaan Oromo (`om`), Hausa (`ha`), and Tigrinya (`ti`).
  - Add native-language test documents in agriculture and public health.
  - Tune vocabulary matching and test if query expansion improves cross-lingual retrieval for low-resource languages.
- **Dependencies:** Native speaker review for question phrasing and accepted fact variations.
- **Acceptance Criteria:**
  - Benchmark covers at least 60 questions across 7 languages.
  - Afaan Oromo retrieval hit rate improves from 0% to >80%.
- **Tests Required:** `evaluation/run_eval.py --retrieval-only`.
- **Risks & Rollback:** Isolated to evaluation suite; zero production impact.

---

### TASK-P1-05: Automatic Document Executive Summary & Topic Tagging
- **Priority:** P1 (High)
- **Problem Being Solved:** Users uploading large collections must read through each document or manually assign tags.
- **Relevant Files:**
  - `backend/jobs.py`
  - `backend/store.py`
  - `backend/main.py`
  - `web/src/pages/LibraryPage.tsx`
- **Proposed Changes:**
  - When background indexing completes, trigger a background summary task using the configured LLM.
  - Generate a 3-bullet executive summary and 2-3 suggested collection tags.
  - Store summary in document metadata and display it in the Library document drawer.
- **Dependencies:** TASK-P0-04 (working cloud LLM).
- **Acceptance Criteria:**
  - Completed uploads display an executive summary chip in the Library.
  - Suggested tags can be approved or edited with one click.
- **Tests Required:** `test_documents.py` verifying summary generation and storage.
- **Risks & Rollback:** Summary generation should be asynchronous and non-blocking; failure should not fail indexing.

---

## Phase 2: Scaling & Monetization (P2)

### TASK-P2-01: Persistent & Distributed Rate Limiting
- **Priority:** P2 (Medium)
- **Problem Being Solved:** The current in-memory rate limiter in `limits.py` is process-local and lost on server reboot.
- **Relevant Files:**
  - `backend/limits.py`
  - `backend/db.py`
- **Proposed Changes:**
  - Provide a pluggable rate limit storage engine: SQLite/PostgreSQL table for single-node deployments, or Redis for multi-worker setups.
  - Store token buckets or timestamp records in the persistent store.
- **Dependencies:** None for SQLite; Redis required only for multi-node deployments.
- **Acceptance Criteria:**
  - Rate limit counters persist across Uvicorn process restarts.
  - Multiple worker processes enforce a unified rate limit ceiling per user.
- **Tests Required:** `test_security.py:test_questions_are_rate_limited_per_user`.
- **Risks & Rollback:** Fallback to in-memory mode if external store is unavailable.

---

### TASK-P2-02: PostgreSQL & `pgvector` Migration Architecture
- **Priority:** P2 (Medium)
- **Problem Being Solved:** Per-workspace NumPy vector files and SQLite metadata limit horizontal scaling across multiple container nodes.
- **Relevant Files:**
  - `backend/db.py`
  - `backend/store.py`
  - `backend/config.py`
- **Proposed Changes:**
  - Design SQLAlchemy / asyncpg data access layer supporting both SQLite (dev) and PostgreSQL + `pgvector` (prod).
  - Store passage embeddings directly in a vector column with HNSW or IVFFlat indexing.
  - Store uploaded raw files in S3-compatible object storage (MinIO, AWS S3, Cloudflare R2).
- **Dependencies:** PostgreSQL server with `pgvector` extension.
- **Acceptance Criteria:**
  - Seamless retrieval across millions of chunks with sub-50ms vector query execution.
  - Multiple API containers share the same database and document index.
- **Tests Required:** Integration test suite against PostgreSQL container.
- **Risks & Rollback:** Keep SQLite adapter functional for simple local self-hosting.

---

### TASK-P2-03: Pan-African Payment Gateways & Tiered Billing
- **Priority:** P2 (Medium)
- **Problem Being Solved:** SaaS commercialization requires local payment methods (Telebirr/CBE in Ethiopia, M-Pesa in Kenya, card/bank in West Africa) alongside standard credit cards.
- **Relevant Files:**
  - `backend/db.py` (subscription schema)
  - `backend/main.py` (webhook endpoints)
  - `web/src/pages/SettingsPage.tsx` (plan selection)
- **Proposed Changes:**
  - Integrate Chapa (Ethiopia: Telebirr, CBE Birr) and Paystack / Flutterwave (Kenya M-Pesa, Nigeria, Ghana).
  - Add subscription plans (`free_pilot`, `pro_team`, `enterprise`) with quotas for storage (MB), members, and cloud questions.
  - Handle webhook notifications for automatic plan activation and renewal.
- **Dependencies:** Merchant API accounts with payment providers.
- **Acceptance Criteria:**
  - User can upgrade workspace via Telebirr or M-Pesa checkout.
  - Webhook verifies signature and upgrades workspace storage and model limits.
- **Tests Required:** Webhook signature verification tests with mock payloads.
- **Risks & Rollback:** Grace period for expired payments before restricting upload quotas.

---

## Phase 3: Strategic Innovations (P3)

### TASK-P3-01: Full UI Localization (Amharic & Swahili)
- **Priority:** P3 (Polish)
- **Problem Being Solved:** The user interface is currently English-only, even though the application serves African-language researchers and organizations.
- **Relevant Files:**
  - `web/src/` (introduce `react-i18next` or lightweight translation dictionaries)
- **Proposed Changes:**
  - Extract all UI strings into translation catalogs (`en`, `am`, `sw`).
  - Add language selector to the navigation bar.
  - Native speaker verification of all legal, settings, and navigation terminology.
- **Acceptance Criteria:** Switching to Amharic displays Ge'ez script UI throughout navigation, modals, and settings.

---

### TASK-P3-02: Voice Input & Speech Synthesis for Field Teams
- **Priority:** P3 (Innovation)
- **Problem Being Solved:** Rural field workers, agricultural extension officers, and community health personnel often prefer voice queries on mobile devices.
- **Relevant Files:**
  - `web/src/components/composer.tsx`
  - `backend/main.py`
- **Proposed Changes:**
  - Integrate browser Web Speech API with fallback to audio recording upload.
  - Add Whisper or SeamlessM4T speech-to-text endpoint for Amharic and Swahili.
  - Provide text-to-speech audio playback for generated answers.
- **Acceptance Criteria:** User can tap microphone, ask question in Swahili, and receive synthesized audio answer with source cards.

---

### TASK-P3-03: WhatsApp & Telegram Knowledge Query Bot
- **Priority:** P3 (Innovation)
- **Problem Being Solved:** Many African teams coordinate via WhatsApp and Telegram rather than browser apps.
- **Relevant Files:**
  - New service module: `backend/bots/`
- **Proposed Changes:**
  - Webhook listener for WhatsApp Business API and Telegram Bot API.
  - Route messages to the designated workspace, search documents, and return concise cited answers directly in chat.
- **Acceptance Criteria:** A user can send a PDF to a Telegram bot and immediately ask questions about it.
